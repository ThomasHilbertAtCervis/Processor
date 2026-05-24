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
from .node_kinds import list_node_kinds
from .primitives import list_primitive_type_ids
from .repository import ModuleRepository
from .simulator import Simulator
from .templates import default_module, new_module
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
    inputs: list[dict[str, Any] | str] = Field(default_factory=list)
    outputs: list[dict[str, Any] | str] = Field(default_factory=list)
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)
    submodules: list[dict[str, Any]] = Field(default_factory=list)


class DataTypePayload(BaseModel):
    type_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    kind: Literal["struct", "array", "dict"] = "struct"
    fields: list[dict[str, Any]] = Field(default_factory=list)
    element_type: str | None = None


class RunPayload(BaseModel):
    """Trigger payload for ``POST /api/modules/{id}/run``.

    Execution is always initiated through a *single* input signal — the
    client picks which input to wake and supplies one value of the
    matching data type.
    """

    input_signal: str = Field(min_length=1)
    input_value: Any = None


class ScriptPayload(BaseModel):
    script: str = Field(min_length=1)


class NewModulePayload(BaseModel):
    """Body for ``POST /api/modules`` — only the bits a client must supply.

    The rest of a fresh module (empty inputs/outputs/nodes/edges/flow/
    submodules) is filled in server-side by ``templates.new_module`` so every
    client gets the same starting shape.
    """

    module_id: str = Field(min_length=1)
    name: str = Field(min_length=1)


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


@app.post("/api/modules", status_code=201)
def create_module(
    payload: NewModulePayload,
    modules: ModuleRepository = Depends(get_module_repository),
) -> dict[str, Any]:
    if modules.get(payload.module_id):
        raise HTTPException(status_code=409, detail="Module already exists")
    module = new_module(payload.module_id, payload.name)
    modules.save(module)
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
    return sim.run(
        module,
        input_signal=payload.input_signal,
        input_value=payload.input_value,
    )


@app.get("/api/data-types")
def list_data_types(
    data_types: DataTypeRepository = Depends(get_data_type_repository),
) -> list[dict[str, Any]]:
    return [data_type.to_dict() for data_type in data_types.list()]


@app.get("/api/data-types/primitives")
def list_primitives() -> list[str]:
    """Identifiers of the built-in primitive types (``int``, ``string``, …).

    Declared *before* ``/api/data-types/{type_id}`` so the static segment
    wins the route match.
    """
    return list_primitive_type_ids()


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


@app.get("/api/node-kinds")
def list_node_kinds_endpoint() -> list[dict[str, Any]]:
    """Catalog of node kinds (type, palette label, default label).

    The frontend uses this to render the palette and seed labels for freshly
    placed nodes; an MCP agent uses it to know what nodes it is allowed to
    add to a module. Single source of truth lives in ``node_kinds.py``.
    """
    return [kind.to_dict() for kind in list_node_kinds()]


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
