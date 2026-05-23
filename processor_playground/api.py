from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .models import Module
from .repository import ModuleRepository
from .simulator import Simulator
from .testing import ScriptTestRunner

BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / "storage" / "modules"
STATIC_DIR = Path(__file__).resolve().parent / "static"

repo = ModuleRepository(STORAGE_DIR)
simulator = Simulator()
script_runner = ScriptTestRunner(repo, simulator)

app = FastAPI(title="Process Playground")


class ModulePayload(BaseModel):
    module_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    interfaces: dict[str, list[str]] = Field(default_factory=lambda: {"inputs": [], "outputs": []})
    flow: list[dict[str, Any]] = Field(default_factory=list)
    submodules: list[dict[str, Any]] = Field(default_factory=list)


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
    return [m.to_dict() for m in repo.list()]


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


@app.post("/api/modules/{module_id}/run")
def run_module(module_id: str, payload: RunPayload) -> dict[str, Any]:
    module = repo.get(module_id)
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")
    return simulator.run(module, input_data=payload.input_data, mocks=payload.mocks)


@app.post("/api/tests/run")
def run_script_test(payload: ScriptPayload) -> dict[str, Any]:
    return script_runner.run(payload.script)


@app.get("/api/templates/default-module")
def default_module_template() -> dict[str, Any]:
    template = {
        "module_id": "example-module",
        "name": "Example Module",
        "interfaces": {"inputs": ["input"], "outputs": ["result"]},
        "flow": [
            {"type": "set_var", "name": "counter", "value": 1},
            {"type": "datastore_write", "key": "counter", "value": 1},
            {"type": "api_call", "url": "https://api.example.com", "mock_response": {"ok": True}},
            {"type": "emit", "event": "finished", "payload": {"ok": True}},
        ],
        "submodules": [],
    }
    return template


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "storage": str(STORAGE_DIR)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("processor_playground.api:app", host="127.0.0.1", port=8000, reload=False)
