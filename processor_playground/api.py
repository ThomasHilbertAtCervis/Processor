from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .data_type_repository import DataTypeRepository
from .models import DataType, Module
from .repository import ModuleRepository
from .simulator import Simulator
from .testing import ScriptTestRunner

BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / "storage" / "modules"
STATIC_DIR = Path(__file__).resolve().parent / "static"

repo = ModuleRepository(STORAGE_DIR)
data_type_repo = DataTypeRepository(BASE_DIR / "storage" / "data-types")
simulator = Simulator()
script_runner = ScriptTestRunner(repo, simulator)

app = FastAPI(title="Process Playground")


class ModulePayload(BaseModel):
    module_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    interfaces: dict[str, list[str]] | None = None
    inputs: list[dict[str, Any] | str] | None = None
    outputs: list[dict[str, Any] | str] | None = None
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)
    flow: list[dict[str, Any]] = Field(default_factory=list)
    submodules: list[dict[str, Any]] = Field(default_factory=list)


class DataTypePayload(BaseModel):
    type_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    kind: Literal["struct", "array", "dict"] = "struct"
    fields: list[dict[str, Any]] = Field(default_factory=list)
    element_type: str | None = None


class RunPayload(BaseModel):
    input_data: dict[str, Any] = Field(default_factory=dict)
    mocks: dict[str, Any] = Field(default_factory=dict)


class ScriptPayload(BaseModel):
    script: str = Field(min_length=1)


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


@app.get("/api/modules")
def list_modules() -> list[dict[str, Any]]:
    return [module.to_dict() for module in repo.list()]


@app.get("/api/modules/{module_id}")
def get_module(module_id: str) -> dict[str, Any]:
    module = repo.get(module_id)
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")
    return module.to_dict()


@app.put("/api/modules/{module_id}")
def upsert_module(module_id: str, payload: ModulePayload) -> dict[str, Any]:
    if module_id != payload.module_id:
        raise HTTPException(status_code=400, detail="Path id and payload module_id must match")
    module = Module.from_dict(payload.model_dump())
    repo.save(module)
    return module.to_dict()


@app.delete("/api/modules/{module_id}", status_code=204)
def delete_module(module_id: str) -> Response:
    if not repo.delete(module_id):
        raise HTTPException(status_code=404, detail="Module not found")
    return Response(status_code=204)


@app.post("/api/modules/{module_id}/run")
def run_module(module_id: str, payload: RunPayload) -> dict[str, Any]:
    module = repo.get(module_id)
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")
    return simulator.run(module, input_data=payload.input_data, mocks=payload.mocks)


@app.get("/api/data-types")
def list_data_types() -> list[dict[str, Any]]:
    return [data_type.to_dict() for data_type in data_type_repo.list()]


@app.get("/api/data-types/{type_id}")
def get_data_type(type_id: str) -> dict[str, Any]:
    data_type = data_type_repo.get(type_id)
    if not data_type:
        raise HTTPException(status_code=404, detail="Data type not found")
    return data_type.to_dict()


@app.put("/api/data-types/{type_id}")
def upsert_data_type(type_id: str, payload: DataTypePayload) -> dict[str, Any]:
    if type_id != payload.type_id:
        raise HTTPException(status_code=400, detail="Path id and payload type_id must match")
    data_type = DataType.from_dict(payload.model_dump())
    data_type_repo.save(data_type)
    return data_type.to_dict()


@app.delete("/api/data-types/{type_id}", status_code=204)
def delete_data_type(type_id: str) -> Response:
    if not data_type_repo.delete(type_id):
        raise HTTPException(status_code=404, detail="Data type not found")
    return Response(status_code=204)


@app.post("/api/tests/run")
def run_script_test(payload: ScriptPayload) -> dict[str, Any]:
    return script_runner.run(payload.script)


@app.get("/api/templates/default-module")
def default_module_template() -> dict[str, Any]:
    template = Module.from_dict(
        {
            "module_id": "example-module",
            "name": "Example Module",
            "inputs": [{"name": "input", "type_ref": "any"}],
            "outputs": [{"name": "result", "type_ref": "any"}],
            "nodes": [
                {
                    "id": "start-1",
                    "type": "start",
                    "position": {"x": 80, "y": 180},
                    "data": {"label": "Start"},
                },
                {
                    "id": "event-1",
                    "type": "event",
                    "position": {"x": 170, "y": 160},
                    "data": {
                        "label": "Shipment picked up",
                        "signalType": "ShipmentHandoverEvent",
                    },
                },
                {
                    "id": "condition-1",
                    "type": "condition",
                    "position": {"x": 430, "y": 160},
                    "data": {
                        "label": "Check location",
                        "filter": "event.location == 'Berlin'",
                    },
                },
                {
                    "id": "emit-1",
                    "type": "emit",
                    "position": {"x": 700, "y": 160},
                    "data": {"label": "Emit finished", "signalType": "ShipmentProcessed"},
                },
                {
                    "id": "end-1",
                    "type": "end",
                    "position": {"x": 930, "y": 180},
                    "data": {"label": "End"},
                },
            ],
            "edges": [
                {"id": "e1", "source": "start-1", "target": "event-1"},
                {
                    "id": "e2",
                    "source": "event-1",
                    "target": "condition-1",
                    "label": "ShipmentHandoverEvent",
                },
                {"id": "e3", "source": "condition-1", "target": "emit-1"},
                {"id": "e4", "source": "emit-1", "target": "end-1"},
            ],
            "flow": [
                {"type": "set_var", "name": "counter", "value": 1},
                {"type": "datastore_write", "key": "counter", "value": 1},
                {"type": "api_call", "url": "https://api.example.com", "mock_response": {"ok": True}},
                {"type": "emit", "event": "finished", "payload": {"ok": True}},
            ],
            "submodules": [],
        }
    )
    return template.to_dict()


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "storage": str(STORAGE_DIR),
        "data_types": str(BASE_DIR / "storage" / "data-types"),
    }


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("processor_playground.api:app", host="127.0.0.1", port=8000, reload=False)
