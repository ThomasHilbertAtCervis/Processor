"""End-to-end HTTP tests for every API endpoint (v2 schema)."""
from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from processor_playground.api import (
    app,
    get_data_type_repository,
    get_module_repository,
    get_script_runner,
    get_simulator,
)
from processor_playground.data_type_repository import DataTypeRepository
from processor_playground.repository import ModuleRepository
from processor_playground.simulator import Simulator
from processor_playground.testing import ScriptTestRunner


@pytest.fixture()
def client(tmp_path: Path) -> Iterator[TestClient]:
    modules = ModuleRepository(tmp_path / "modules")
    data_types = DataTypeRepository(tmp_path / "data-types")
    simulator = Simulator()
    runner = ScriptTestRunner(modules, simulator)

    app.dependency_overrides[get_module_repository] = lambda: modules
    app.dependency_overrides[get_data_type_repository] = lambda: data_types
    app.dependency_overrides[get_simulator] = lambda: simulator
    app.dependency_overrides[get_script_runner] = lambda: runner

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def _echo_module_payload(module_id: str = "m") -> dict:
    return {
        "module_id": module_id,
        "name": module_id.title(),
        "inputs": [{"name": "in", "type_ref": "any"}],
        "outputs": [{"name": "out", "type_ref": "any"}],
        "nodes": [
            {
                "id": "i", "type": "module_input",
                "inputs": [], "outputs": [{"name": "v", "type_ref": "any"}],
                "data": {"signal_name": "in"},
            },
            {
                "id": "o", "type": "module_output",
                "inputs": [{"name": "v", "type_ref": "any"}], "outputs": [],
                "data": {"signal_name": "out"},
            },
        ],
        "edges": [
            {"id": "e", "source": "i", "source_handle": "v",
             "target": "o", "target_handle": "v"},
        ],
        "submodules": [],
    }


# ---------------------------------------------------------------- modules

class TestModuleEndpoints:
    def test_list_is_empty_initially(self, client: TestClient) -> None:
        assert client.get("/api/modules").json() == []

    def test_put_creates(self, client: TestClient) -> None:
        response = client.put("/api/modules/sample", json=_echo_module_payload("sample"))
        assert response.status_code == 200
        body = response.json()
        assert body["module_id"] == "sample"
        assert body["inputs"][0]["type_ref"] == "any"

    def test_put_with_mismatched_path_id_is_400(self, client: TestClient) -> None:
        response = client.put(
            "/api/modules/sample",
            json={"module_id": "different", "name": "S"},
        )
        assert response.status_code == 400

    def test_get_missing_is_404(self, client: TestClient) -> None:
        assert client.get("/api/modules/missing").status_code == 404

    def test_put_then_get(self, client: TestClient) -> None:
        client.put("/api/modules/m", json=_echo_module_payload("m"))
        body = client.get("/api/modules/m").json()
        assert body["name"] == "M"

    def test_delete(self, client: TestClient) -> None:
        client.put("/api/modules/m", json=_echo_module_payload("m"))
        assert client.delete("/api/modules/m").status_code == 204
        assert client.delete("/api/modules/m").status_code == 404

    def test_legacy_flow_payload_is_rejected(self, client: TestClient) -> None:
        # ``flow`` was removed in v2. The DTO drops it, so the request
        # succeeds at the HTTP layer — what reaches the model is the v2
        # shape (empty nodes/edges). The point of the test is to pin that
        # behaviour, not to claim backward-compat.
        response = client.put(
            "/api/modules/empty",
            json={
                "module_id": "empty", "name": "Empty",
                "flow": [{"type": "emit", "payload": 1}],  # silently ignored
            },
        )
        assert response.status_code == 200
        assert "flow" not in response.json()
        assert response.json()["nodes"] == []

    def test_list_returns_saved_modules(self, client: TestClient) -> None:
        client.put("/api/modules/a", json=_echo_module_payload("a"))
        client.put("/api/modules/b", json=_echo_module_payload("b"))
        ids = [m["module_id"] for m in client.get("/api/modules").json()]
        assert ids == ["a", "b"]

    def test_post_creates_empty_module_from_server_template(self, client: TestClient) -> None:
        response = client.post(
            "/api/modules",
            json={"module_id": "fresh", "name": "Fresh"},
        )
        assert response.status_code == 201
        body = response.json()
        assert body == {
            "module_id": "fresh",
            "name": "Fresh",
            "inputs": [],
            "outputs": [],
            "nodes": [],
            "edges": [],
            "submodules": [],
        }
        assert client.get("/api/modules/fresh").status_code == 200

    def test_post_duplicate_module_is_409(self, client: TestClient) -> None:
        client.post("/api/modules", json={"module_id": "dup", "name": "Dup"})
        response = client.post("/api/modules", json={"module_id": "dup", "name": "Dup"})
        assert response.status_code == 409


# -------------------------------------------------------------- data-types

class TestDataTypeEndpoints:
    def test_crud(self, client: TestClient) -> None:
        response = client.put(
            "/api/data-types/Shipment",
            json={
                "type_id": "Shipment",
                "name": "Shipment",
                "kind": "struct",
                "fields": [{"name": "location", "type_ref": "string"}],
                "element_type": None,
            },
        )
        assert response.status_code == 200
        assert client.get("/api/data-types/Shipment").json()["name"] == "Shipment"
        assert [d["type_id"] for d in client.get("/api/data-types").json()] == ["Shipment"]
        assert client.delete("/api/data-types/Shipment").status_code == 204
        assert client.get("/api/data-types/Shipment").status_code == 404

    def test_primitives_endpoint(self, client: TestClient) -> None:
        body = client.get("/api/data-types/primitives").json()
        assert body == ["int", "decimal", "string", "bool", "timestamp", "any"]


# ----------------------------------------------------------------- run

class TestRunEndpoint:
    def test_run_existing_module(self, client: TestClient) -> None:
        client.put("/api/modules/m", json=_echo_module_payload("m"))
        response = client.post(
            "/api/modules/m/run",
            json={"input_data": {"in": 42}, "mocks": {}},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["outputs"] == {"out": [42]}
        assert body["status"] == "complete"

    def test_run_missing_is_404(self, client: TestClient) -> None:
        assert client.post(
            "/api/modules/missing/run", json={"input_data": {}, "mocks": {}}
        ).status_code == 404


# --------------------------------------------------------------- scripts

class TestScriptEndpoint:
    def test_passing_script(self, client: TestClient) -> None:
        client.put("/api/modules/m", json=_echo_module_payload("m"))
        report = client.post(
            "/api/tests/run",
            json={
                "script": (
                    "result = run_module('m', {'in': 9})\n"
                    "assert_equal(result['outputs']['out'][0], 9)\n"
                )
            },
        ).json()
        assert report == {"assertions": 1, "status": "passed", "errors": []}

    def test_empty_script_rejected(self, client: TestClient) -> None:
        assert client.post("/api/tests/run", json={"script": ""}).status_code == 422


# --------------------------------------------------------------- misc

class TestMiscEndpoints:
    def test_health(self, client: TestClient) -> None:
        body = client.get("/health").json()
        assert body["status"] == "ok"

    def test_default_module_template(self, client: TestClient) -> None:
        body = client.get("/api/templates/default-module").json()
        assert body["module_id"] == "example-module"
        assert body["nodes"]
        assert body["edges"]

    def test_node_kinds_catalog(self, client: TestClient) -> None:
        body = client.get("/api/node-kinds").json()
        types = [entry["type"] for entry in body]
        assert types == ["module_input", "module_output", "python", "submodule"]
        for entry in body:
            assert entry["palette_label"]
            assert entry["default_label"]

    def test_index_html_served(self, client: TestClient) -> None:
        response = client.get("/")
        assert response.status_code == 200
        assert "<html" in response.text.lower()

    def test_static_files_served(self, client: TestClient) -> None:
        for path in (
            "/static/app.js",
            "/static/components.js",
            "/static/nodes.js",
            "/static/lib/api.js",
            "/static/lib/html.js",
            "/static/style.css",
        ):
            assert client.get(path).status_code == 200, path
