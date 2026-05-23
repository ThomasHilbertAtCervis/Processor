from pathlib import Path

from fastapi.testclient import TestClient

from processor_playground.api import app, data_type_repo, repo
from processor_playground.models import DataType, Module, Signal


def test_signal_supports_legacy_strings() -> None:
    signal = Signal.from_dict("shipment")

    assert signal.name == "shipment"
    assert signal.type_ref == "any"


def test_module_to_dict_keeps_legacy_interfaces() -> None:
    module = Module(
        module_id="mod",
        name="Module",
        inputs=[Signal(name="inbound", type_ref="ShipmentEvent")],
        outputs=[Signal(name="done")],
    )

    payload = module.to_dict()

    assert payload["inputs"][0]["type_ref"] == "ShipmentEvent"
    assert payload["interfaces"] == {"inputs": ["inbound"], "outputs": ["done"]}


def test_data_type_repository_round_trip(tmp_path: Path) -> None:
    from processor_playground.data_type_repository import DataTypeRepository

    repository = DataTypeRepository(tmp_path)
    repository.save(
        DataType(
            type_id="ShipmentEvent",
            name="Shipment Event",
            fields=[],
        )
    )

    assert repository.get("ShipmentEvent") is not None
    assert repository.delete("ShipmentEvent") is True
    assert repository.list() == []


def test_api_crud_and_static_endpoints(tmp_path: Path) -> None:
    original_module_path = repo.base_path
    original_data_type_path = data_type_repo.base_path
    repo.base_path = tmp_path / "modules"
    data_type_repo.base_path = tmp_path / "data-types"
    repo.base_path.mkdir(parents=True, exist_ok=True)
    data_type_repo.base_path.mkdir(parents=True, exist_ok=True)

    try:
        client = TestClient(app)

        save_module = client.put(
            "/api/modules/sample",
            json={
                "module_id": "sample",
                "name": "Sample",
                "inputs": [{"name": "incoming", "type_ref": "ShipmentEvent"}],
                "outputs": [{"name": "done", "type_ref": "any"}],
                "nodes": [],
                "edges": [],
                "flow": [],
                "submodules": [],
            },
        )
        assert save_module.status_code == 200

        save_type = client.put(
            "/api/data-types/ShipmentEvent",
            json={
                "type_id": "ShipmentEvent",
                "name": "Shipment Event",
                "kind": "struct",
                "fields": [{"name": "location", "type_ref": "string"}],
                "element_type": None,
            },
        )
        assert save_type.status_code == 200
        legacy_response = client.put(
            "/api/modules/legacy",
            json={
                "module_id": "legacy",
                "name": "Legacy",
                "interfaces": {"inputs": ["old-in"], "outputs": ["old-out"]},
                "flow": [],
                "submodules": [],
            },
        )
        assert legacy_response.status_code == 200
        assert legacy_response.json()["inputs"][0]["name"] == "old-in"
        assert client.get("/api/data-types").json()[0]["type_id"] == "ShipmentEvent"
        assert client.delete("/api/data-types/ShipmentEvent").status_code == 204
        assert client.delete("/api/modules/sample").status_code == 204
        assert client.get("/").status_code == 200
        assert client.get("/static/app.js").status_code == 200
    finally:
        repo.base_path = original_module_path
        data_type_repo.base_path = original_data_type_path
