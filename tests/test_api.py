"""End-to-end HTTP tests for every API endpoint.

These tests use ``app.dependency_overrides`` to inject fresh repositories
backed by ``tmp_path``. They never touch ``processor_playground.api``
module-level singletons — see ARCHITECTURE.md ("Hard rules").
"""
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


# ---------------------------------------------------------------- modules

class TestModuleEndpoints:
    def test_list_is_empty_initially(self, client: TestClient) -> None:
        response = client.get("/api/modules")
        assert response.status_code == 200
        assert response.json() == []

    def test_put_creates(self, client: TestClient) -> None:
        response = client.put(
            "/api/modules/sample",
            json={
                "module_id": "sample",
                "name": "Sample",
                "inputs": [{"name": "in", "type_ref": "Event"}],
                "outputs": [{"name": "out", "type_ref": "any"}],
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["module_id"] == "sample"
        assert body["inputs"][0]["type_ref"] == "Event"

    def test_put_with_mismatched_path_id_is_400(self, client: TestClient) -> None:
        response = client.put(
            "/api/modules/sample",
            json={"module_id": "different", "name": "S"},
        )
        assert response.status_code == 400

    def test_get_missing_is_404(self, client: TestClient) -> None:
        assert client.get("/api/modules/missing").status_code == 404

    def test_put_then_get(self, client: TestClient) -> None:
        client.put("/api/modules/m", json={"module_id": "m", "name": "M"})
        body = client.get("/api/modules/m").json()
        assert body["name"] == "M"

    def test_delete(self, client: TestClient) -> None:
        client.put("/api/modules/m", json={"module_id": "m", "name": "M"})
        assert client.delete("/api/modules/m").status_code == 204
        assert client.delete("/api/modules/m").status_code == 404

    def test_legacy_interfaces_payload_is_accepted(self, client: TestClient) -> None:
        response = client.put(
            "/api/modules/legacy",
            json={
                "module_id": "legacy",
                "name": "Legacy",
                "interfaces": {"inputs": ["old-in"], "outputs": ["old-out"]},
            },
        )
        assert response.status_code == 200
        assert response.json()["inputs"][0]["name"] == "old-in"

    def test_list_returns_saved_modules(self, client: TestClient) -> None:
        client.put("/api/modules/a", json={"module_id": "a", "name": "A"})
        client.put("/api/modules/b", json={"module_id": "b", "name": "B"})
        ids = [m["module_id"] for m in client.get("/api/modules").json()]
        assert ids == ["a", "b"]


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
        listing = client.get("/api/data-types").json()
        assert listing[0]["type_id"] == "Shipment"
        assert client.delete("/api/data-types/Shipment").status_code == 204
        assert client.get("/api/data-types/Shipment").status_code == 404
        assert client.delete("/api/data-types/Shipment").status_code == 404

    def test_put_mismatched_id_is_400(self, client: TestClient) -> None:
        assert client.put(
            "/api/data-types/A",
            json={"type_id": "B", "name": "B"},
        ).status_code == 400


# ----------------------------------------------------------------- run

class TestRunEndpoint:
    def test_run_existing_module(self, client: TestClient) -> None:
        client.put(
            "/api/modules/m",
            json={
                "module_id": "m",
                "name": "M",
                "flow": [{"type": "emit", "payload": {"ok": True}}],
            },
        )
        response = client.post("/api/modules/m/run", json={"input_data": {}, "mocks": {}})
        assert response.status_code == 200
        body = response.json()
        assert body["outputs"] == [{"ok": True}]

    def test_run_uses_mocks(self, client: TestClient) -> None:
        client.put(
            "/api/modules/p",
            json={
                "module_id": "p",
                "name": "P",
                "flow": [{"type": "run_submodule", "module_id": "c", "interface": "db"}],
                "submodules": [
                    {"module_id": "c", "name": "C", "flow": [{"type": "emit", "payload": "real"}]}
                ],
            },
        )
        body = client.post(
            "/api/modules/p/run",
            json={"input_data": {}, "mocks": {"db": {"rows": 3}}},
        ).json()
        assert body["events"][0]["mocked_interface"] == "db"

    def test_run_missing_is_404(self, client: TestClient) -> None:
        assert client.post(
            "/api/modules/missing/run", json={"input_data": {}, "mocks": {}}
        ).status_code == 404


# --------------------------------------------------------------- scripts

class TestScriptEndpoint:
    def test_passing_script(self, client: TestClient) -> None:
        client.put(
            "/api/modules/m",
            json={"module_id": "m", "name": "M", "flow": [{"type": "emit", "payload": 1}]},
        )
        report = client.post(
            "/api/tests/run",
            json={"script": "result = run_module('m')\nassert_equal(result['outputs'][0], 1)\n"},
        ).json()
        assert report == {"assertions": 1, "status": "passed", "errors": []}

    def test_empty_script_rejected(self, client: TestClient) -> None:
        assert client.post("/api/tests/run", json={"script": ""}).status_code == 422


# --------------------------------------------------------------- misc

class TestMiscEndpoints:
    def test_health(self, client: TestClient) -> None:
        body = client.get("/health").json()
        assert body["status"] == "ok"
        assert "storage" in body and "data_types" in body

    def test_default_module_template(self, client: TestClient) -> None:
        body = client.get("/api/templates/default-module").json()
        assert body["module_id"] == "example-module"
        assert body["nodes"]

    def test_index_html_served(self, client: TestClient) -> None:
        response = client.get("/")
        assert response.status_code == 200
        assert "<html" in response.text.lower()

    def test_static_files_served(self, client: TestClient) -> None:
        # Each split frontend module must be reachable.
        for path in (
            "/static/app.js",
            "/static/components.js",
            "/static/nodes.js",
            "/static/lib/api.js",
            "/static/lib/html.js",
            "/static/style.css",
        ):
            assert client.get(path).status_code == 200, path
