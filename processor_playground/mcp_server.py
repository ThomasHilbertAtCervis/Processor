"""MCP server exposing the full Processor Playground backend feature set.

This module intentionally mirrors the HTTP API capabilities so agentic clients
can create, maintain, and test process models without the browser UI.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .data_type_repository import DataTypeRepository
from .models import DataType, Module
from .node_kinds import list_node_kinds
from .primitives import list_primitive_type_ids
from .repository import ModuleRepository
from .simulator import Simulator
from .templates import default_module, new_module
from .testing import ScriptTestRunner

BASE_DIR = Path(__file__).resolve().parent.parent


def _modules_storage_dir() -> Path:
    value = os.environ.get("PROCESSOR_PLAYGROUND_STORAGE_DIR")
    return Path(value) if value else BASE_DIR / "storage" / "modules"


def _data_types_storage_dir() -> Path:
    value = os.environ.get("PROCESSOR_PLAYGROUND_DATA_TYPES_DIR")
    return Path(value) if value else BASE_DIR / "storage" / "data-types"


def create_mcp_server(
    *,
    modules: ModuleRepository | None = None,
    data_types: DataTypeRepository | None = None,
    sim: Simulator | None = None,
    runner: ScriptTestRunner | None = None,
) -> FastMCP:
    """Build the MCP server with a concrete service graph."""
    modules = modules or ModuleRepository(_modules_storage_dir())
    data_types = data_types or DataTypeRepository(_data_types_storage_dir())
    sim = sim or Simulator()
    runner = runner or ScriptTestRunner(modules, sim)

    server = FastMCP(
        name="processor-playground",
        instructions=(
            "Use these tools to manage modules, global data types, run module simulations, "
            "and execute script tests in Processor Playground."
        ),
    )

    @server.tool(name="list_modules")
    def list_modules() -> list[dict[str, Any]]:
        return [module.to_dict() for module in modules.list()]

    @server.tool(name="get_module")
    def get_module(module_id: str) -> dict[str, Any]:
        module = modules.get(module_id)
        if not module:
            raise ValueError(f"Module not found: {module_id}")
        return module.to_dict()

    @server.tool(name="create_module")
    def create_module_tool(module_id: str, name: str) -> dict[str, Any]:
        if modules.get(module_id):
            raise ValueError(f"Module already exists: {module_id}")
        module = new_module(module_id, name)
        modules.save(module)
        return module.to_dict()

    @server.tool(name="upsert_module")
    def upsert_module(module_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("module_id") != module_id:
            raise ValueError("Path id and payload module_id must match")
        module = Module.from_dict(payload)
        modules.save(module)
        return module.to_dict()

    @server.tool(name="delete_module")
    def delete_module(module_id: str) -> dict[str, bool]:
        deleted = modules.delete(module_id)
        if not deleted:
            raise ValueError(f"Module not found: {module_id}")
        return {"deleted": True}

    @server.tool(name="run_module")
    def run_module(
        module_id: str,
        input_data: dict[str, Any] | None = None,
        mocks: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        module = modules.get(module_id)
        if not module:
            raise ValueError(f"Module not found: {module_id}")
        return sim.run(
            module,
            input_data=input_data or {},
            mocks=mocks or {},
        )

    @server.tool(name="list_data_types")
    def list_data_types() -> list[dict[str, Any]]:
        return [data_type.to_dict() for data_type in data_types.list()]

    @server.tool(name="get_data_type")
    def get_data_type(type_id: str) -> dict[str, Any]:
        data_type = data_types.get(type_id)
        if not data_type:
            raise ValueError(f"Data type not found: {type_id}")
        return data_type.to_dict()

    @server.tool(name="upsert_data_type")
    def upsert_data_type(type_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("type_id") != type_id:
            raise ValueError("Path id and payload type_id must match")
        data_type = DataType.from_dict(payload)
        data_types.save(data_type)
        return data_type.to_dict()

    @server.tool(name="delete_data_type")
    def delete_data_type(type_id: str) -> dict[str, bool]:
        deleted = data_types.delete(type_id)
        if not deleted:
            raise ValueError(f"Data type not found: {type_id}")
        return {"deleted": True}

    @server.tool(name="list_primitive_data_types")
    def list_primitive_data_types() -> list[str]:
        return list_primitive_type_ids()

    @server.tool(name="list_node_kinds")
    def list_node_kinds_tool() -> list[dict[str, Any]]:
        return [kind.to_dict() for kind in list_node_kinds()]

    @server.tool(name="get_default_module_template")
    def get_default_module_template() -> dict[str, Any]:
        return default_module().to_dict()

    @server.tool(name="run_script_test")
    def run_script_test(script: str) -> dict[str, Any]:
        return runner.run(script)

    @server.tool(name="health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "storage": str(modules.base_path),
            "data_types": str(data_types.base_path),
        }

    return server


server = create_mcp_server()


def main() -> None:
    """Run the MCP server over stdio transport."""
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
