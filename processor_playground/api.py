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
from .database_repository import DatabaseRepository
from .models import Database, DataType, Module
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
DATABASES_DIR = BASE_DIR / "storage" / "databases"
STATIC_DIR = Path(__file__).resolve().parent / "static"


# ---------------------------------------------------------- composition root

# Default service graph used when the app runs as a real server. Tests build
# their own and inject via app.dependency_overrides.
repo = ModuleRepository(STORAGE_DIR)
data_type_repo = DataTypeRepository(DATA_TYPES_DIR)
database_repo = DatabaseRepository(DATABASES_DIR)
simulator = Simulator()
script_runner = ScriptTestRunner(repo, simulator)


def get_module_repository() -> ModuleRepository:
    return repo


def get_data_type_repository() -> DataTypeRepository:
    return data_type_repo


def get_database_repository() -> DatabaseRepository:
    return database_repo


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

    ``persist`` controls whether mutations performed by ``db_create``
    nodes are written back to disk. Defaults to ``False`` so that runs
    are safely repeatable.
    """

    input_signal: str = Field(min_length=1)
    input_value: Any = None
    persist: bool = False


class DatabasePayload(BaseModel):
    name: str = Field(min_length=1)
    tables: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)


class RowPayload(BaseModel):
    row: dict[str, Any]


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
    databases: DatabaseRepository = Depends(get_database_repository),
    sim: Simulator = Depends(get_simulator),
) -> dict[str, Any]:
    module = modules.get(module_id)
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")
    # ``submodule`` nodes reference other top-level modules by id. The
    # simulator expects those to be embedded in ``module.submodules`` — so
    # we resolve every referenced module from the repository and inject it
    # here, recursively, before kicking off the run. This keeps the
    # simulator free of repository concerns and lets the UI store
    # submodules by reference instead of duplicating their graphs.
    try:
        _embed_referenced_submodules(module, modules)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # Snapshot every saved database into a mutable in-memory dict that the
    # simulator's db_* activators read from and write to. We persist back
    # to disk only if the caller opts in.
    snapshot: dict[str, dict[str, list[dict[str, Any]]]] = {
        db.name: {table: [dict(row) for row in rows] for table, rows in db.tables.items()}
        for db in databases.list()
    }
    result = sim.run(
        module,
        input_signal=payload.input_signal,
        input_value=payload.input_value,
        databases=snapshot,
    )
    if payload.persist:
        for name, tables in snapshot.items():
            databases.save(Database(name=name, tables=tables))
    return result


def _embed_referenced_submodules(
    module: Any, repo: ModuleRepository, seen: set[str] | None = None
) -> None:
    seen = seen or set()
    if module.module_id in seen:
        return
    seen.add(module.module_id)
    existing_ids = {sub.module_id for sub in module.submodules}
    for node in module.nodes:
        if node.type != "submodule":
            continue
        sub_id = node.data.get("module_id") or node.data.get("moduleId")
        if not sub_id or sub_id in existing_ids:
            continue
        sub = repo.get(sub_id)
        if sub is None:
            raise KeyError(
                f"Submodule '{sub_id}' referenced by node '{node.id}' "
                f"does not exist in the repository."
            )
        module.submodules.append(sub)
        existing_ids.add(sub_id)
        _embed_referenced_submodules(sub, repo, seen)


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


# ---------------------------------------------------------------- Databases

def _validate_db_tables(
    tables: dict[str, list[dict[str, Any]]],
    data_types: DataTypeRepository,
) -> None:
    """Every key in ``tables`` must reference an existing data type."""
    for type_id in tables:
        if not data_types.get(type_id):
            raise HTTPException(
                status_code=400,
                detail=f"Table '{type_id}' does not reference an existing data type",
            )


@app.get("/api/databases")
def list_databases(
    databases: DatabaseRepository = Depends(get_database_repository),
) -> list[dict[str, Any]]:
    return [db.to_dict() for db in databases.list()]


@app.get("/api/databases/{name}")
def get_database(
    name: str,
    databases: DatabaseRepository = Depends(get_database_repository),
) -> dict[str, Any]:
    db = databases.get(name)
    if not db:
        raise HTTPException(status_code=404, detail="Database not found")
    return db.to_dict()


@app.post("/api/databases", status_code=201)
def create_database(
    payload: DatabasePayload,
    databases: DatabaseRepository = Depends(get_database_repository),
    data_types: DataTypeRepository = Depends(get_data_type_repository),
) -> dict[str, Any]:
    if databases.get(payload.name):
        raise HTTPException(status_code=409, detail="Database already exists")
    _validate_db_tables(payload.tables, data_types)
    db = Database(name=payload.name, tables=payload.tables)
    databases.save(db)
    return db.to_dict()


@app.put("/api/databases/{name}")
def upsert_database(
    name: str,
    payload: DatabasePayload,
    databases: DatabaseRepository = Depends(get_database_repository),
    data_types: DataTypeRepository = Depends(get_data_type_repository),
) -> dict[str, Any]:
    if name != payload.name:
        raise HTTPException(status_code=400, detail="Path name and payload name must match")
    _validate_db_tables(payload.tables, data_types)
    db = Database(name=payload.name, tables=payload.tables)
    databases.save(db)
    return db.to_dict()


@app.delete("/api/databases/{name}", status_code=204)
def delete_database(
    name: str,
    databases: DatabaseRepository = Depends(get_database_repository),
) -> Response:
    if not databases.delete(name):
        raise HTTPException(status_code=404, detail="Database not found")
    return Response(status_code=204)


@app.get("/api/databases/{name}/tables/{type_id}/rows")
def list_rows(
    name: str,
    type_id: str,
    databases: DatabaseRepository = Depends(get_database_repository),
) -> list[dict[str, Any]]:
    db = databases.get(name)
    if not db:
        raise HTTPException(status_code=404, detail="Database not found")
    return list(db.tables.get(type_id, []))


@app.post("/api/databases/{name}/tables/{type_id}/rows", status_code=201)
def append_row(
    name: str,
    type_id: str,
    payload: RowPayload,
    databases: DatabaseRepository = Depends(get_database_repository),
    data_types: DataTypeRepository = Depends(get_data_type_repository),
) -> dict[str, Any]:
    db = databases.get(name)
    if not db:
        raise HTTPException(status_code=404, detail="Database not found")
    if not data_types.get(type_id):
        raise HTTPException(
            status_code=400,
            detail=f"Table '{type_id}' does not reference an existing data type",
        )
    rows = db.tables.setdefault(type_id, [])
    rows.append(dict(payload.row))
    databases.save(db)
    return dict(payload.row)


@app.delete("/api/databases/{name}/tables/{type_id}/rows/{index}", status_code=204)
def delete_row(
    name: str,
    type_id: str,
    index: int,
    databases: DatabaseRepository = Depends(get_database_repository),
) -> Response:
    db = databases.get(name)
    if not db:
        raise HTTPException(status_code=404, detail="Database not found")
    rows = db.tables.get(type_id, [])
    if index < 0 or index >= len(rows):
        raise HTTPException(status_code=404, detail="Row not found")
    rows.pop(index)
    databases.save(db)
    return Response(status_code=204)


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
        "databases": str(DATABASES_DIR),
    }


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("processor_playground.api:app", host="127.0.0.1", port=8000, reload=False)
