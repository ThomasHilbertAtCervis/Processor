"""HTTP layer.

This module is a *thin adapter* over the service layer. It owns:

* the FastAPI app object and its routes,
* Pydantic DTOs that mirror HTTP payloads,
* a composition root that wires the default service graph.

It does **not** own business logic, default templates, or persistence rules
— those live in ``simulator.py``, ``templates.py`` and the repository layer.
See ARCHITECTURE.md for the rules this module is required to obey.

Tests construct their own services and override the dependencies via
``app.dependency_overrides`` (see ``tests/test_api.py``). They never mutate
the module-level objects defined here.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .data_type_repository import DataTypeRepository
from .models import DataType, Module
from .repository import ModuleRepository
from .simulator import Simulator
from .templates import default_module
from .testing import ScriptTestRunner

# --------------------------------------------------------------------- paths

BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / "storage" / "modules"
DATA_TYPES_DIR = BASE_DIR / "storage" / "data-types"
STATIC_DIR = Path(__file__).resolve().parent / "static"


# ---------------------------------------------------------- composition root

# Default service graph used when the app runs as a real server. Tests build
# their own and inject via app.dependency_overrides.
repo = ModuleRepository(STORAGE_DIR)
data_type_repo = DataTypeRepository(DATA_TYPES_DIR)
simulator = Simulator()
script_runner = ScriptTestRunner(repo, simulator)


def get_module_repository() -> ModuleRepository:
    return repo


def get_data_type_repository() -> DataTypeRepository:
    return data_type_repo


def get_simulator() -> Simulator:
    return simulator


def get_script_runner() -> ScriptTestRunner:
    return script_runner


# ------------------------------------------------------------------ DTOs

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


# ------------------------------------------------------------------- app

app = FastAPI(title="Process Playground")


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


@app.get("/api/modules")
def list_modules(
    modules: ModuleRepository = Depends(get_module_repository),
) -> list[dict[str, Any]]:
    return [module.to_dict() for module in modules.list()]


@app.get("/api/modules/{module_id}")
def get_module(
    module_id: str,
    modules: ModuleRepository = Depends(get_module_repository),
) -> dict[str, Any]:
    module = modules.get(module_id)
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")
    return module.to_dict()


@app.put("/api/modules/{module_id}")
def upsert_module(
    module_id: str,
    payload: ModulePayload,
    modules: ModuleRepository = Depends(get_module_repository),
) -> dict[str, Any]:
    if module_id != payload.module_id:
        raise HTTPException(status_code=400, detail="Path id and payload module_id must match")
    module = Module.from_dict(payload.model_dump())
    modules.save(module)
    return module.to_dict()


@app.delete("/api/modules/{module_id}", status_code=204)
def delete_module(
    module_id: str,
    modules: ModuleRepository = Depends(get_module_repository),
) -> Response:
    if not modules.delete(module_id):
        raise HTTPException(status_code=404, detail="Module not found")
    return Response(status_code=204)


@app.post("/api/modules/{module_id}/run")
def run_module(
    module_id: str,
    payload: RunPayload,
    modules: ModuleRepository = Depends(get_module_repository),
    sim: Simulator = Depends(get_simulator),
) -> dict[str, Any]:
    module = modules.get(module_id)
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")
    return sim.run(module, input_data=payload.input_data, mocks=payload.mocks)


@app.get("/api/data-types")
def list_data_types(
    data_types: DataTypeRepository = Depends(get_data_type_repository),
) -> list[dict[str, Any]]:
    return [data_type.to_dict() for data_type in data_types.list()]


@app.get("/api/data-types/{type_id}")
def get_data_type(
    type_id: str,
    data_types: DataTypeRepository = Depends(get_data_type_repository),
) -> dict[str, Any]:
    data_type = data_types.get(type_id)
    if not data_type:
        raise HTTPException(status_code=404, detail="Data type not found")
    return data_type.to_dict()


@app.put("/api/data-types/{type_id}")
def upsert_data_type(
    type_id: str,
    payload: DataTypePayload,
    data_types: DataTypeRepository = Depends(get_data_type_repository),
) -> dict[str, Any]:
    if type_id != payload.type_id:
        raise HTTPException(status_code=400, detail="Path id and payload type_id must match")
    data_type = DataType.from_dict(payload.model_dump())
    data_types.save(data_type)
    return data_type.to_dict()


@app.delete("/api/data-types/{type_id}", status_code=204)
def delete_data_type(
    type_id: str,
    data_types: DataTypeRepository = Depends(get_data_type_repository),
) -> Response:
    if not data_types.delete(type_id):
        raise HTTPException(status_code=404, detail="Data type not found")
    return Response(status_code=204)


@app.post("/api/tests/run")
def run_script_test(
    payload: ScriptPayload,
    runner: ScriptTestRunner = Depends(get_script_runner),
) -> dict[str, Any]:
    return runner.run(payload.script)


@app.get("/api/templates/default-module")
def default_module_template() -> dict[str, Any]:
    return default_module().to_dict()


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "storage": str(STORAGE_DIR),
        "data_types": str(DATA_TYPES_DIR),
    }


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("processor_playground.api:app", host="127.0.0.1", port=8000, reload=False)
