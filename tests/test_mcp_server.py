"""End-to-end MCP server tests (v2 schema)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


def _decode_tool_result_payload(result: Any) -> Any:
    assert not result.isError
    if result.structuredContent is not None:
        structured = result.structuredContent
        if isinstance(structured, dict) and set(structured.keys()) == {"result"}:
            return structured["result"]
        return structured
    assert result.content
    text_blocks = [block.text for block in result.content if hasattr(block, "text")]
    assert text_blocks
    if len(text_blocks) == 1:
        try:
            return json.loads(text_blocks[0])
        except json.JSONDecodeError:
            return text_blocks[0]
    return text_blocks


def _run_mcp_session(tmp_path: Path, callback: Any) -> Any:
    async def _runner() -> Any:
        env = os.environ.copy()
        env["PROCESSOR_PLAYGROUND_STORAGE_DIR"] = str(tmp_path / "modules")
        env["PROCESSOR_PLAYGROUND_DATA_TYPES_DIR"] = str(tmp_path / "data-types")
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "processor_playground.mcp_server"],
            env=env,
            cwd=str(Path(__file__).resolve().parent.parent),
        )
        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                return await callback(session)

    return anyio.run(_runner)


def _echo_payload(module_id: str = "m1") -> dict:
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


def test_exposes_all_expected_tool_names(tmp_path: Path) -> None:
    async def _assert(session: ClientSession) -> None:
        result = await session.list_tools()
        names = {tool.name for tool in result.tools}
        assert names == {
            "list_modules", "get_module", "create_module", "upsert_module",
            "delete_module", "run_module",
            "list_data_types", "get_data_type", "upsert_data_type", "delete_data_type",
            "list_primitive_data_types", "list_node_kinds",
            "get_default_module_template", "run_script_test", "health",
        }

    _run_mcp_session(tmp_path, _assert)


def test_module_crud_and_run_via_mcp(tmp_path: Path) -> None:
    async def _assert(session: ClientSession) -> None:
        created = _decode_tool_result_payload(
            await session.call_tool("create_module", {"module_id": "m1", "name": "Module One"})
        )
        assert created["module_id"] == "m1"
        assert created["nodes"] == []

        saved = _decode_tool_result_payload(
            await session.call_tool(
                "upsert_module", {"module_id": "m1", "payload": _echo_payload("m1")}
            )
        )
        assert saved["module_id"] == "m1"
        assert saved["nodes"][0]["type"] == "module_input"

        run_result = _decode_tool_result_payload(
            await session.call_tool(
                "run_module",
                {"module_id": "m1", "input_signal": "in", "input_value": 99},
            )
        )
        assert run_result["outputs"] == {"out": [99]}
        assert run_result["status"] == "complete"

        modules = _decode_tool_result_payload(await session.call_tool("list_modules"))
        assert [item["module_id"] for item in modules] == ["m1"]

        deleted = _decode_tool_result_payload(
            await session.call_tool("delete_module", {"module_id": "m1"})
        )
        assert deleted == {"deleted": True}

    _run_mcp_session(tmp_path, _assert)


def test_data_types_catalogs_templates_and_script_test_via_mcp(tmp_path: Path) -> None:
    async def _assert(session: ClientSession) -> None:
        primitives = _decode_tool_result_payload(
            await session.call_tool("list_primitive_data_types")
        )
        assert primitives == ["int", "decimal", "string", "bool", "timestamp", "any"]

        node_kinds = _decode_tool_result_payload(await session.call_tool("list_node_kinds"))
        assert [item["type"] for item in node_kinds] == [
            "module_input", "module_output", "python", "submodule",
        ]

        saved_data_type = _decode_tool_result_payload(
            await session.call_tool(
                "upsert_data_type",
                {
                    "type_id": "Bag",
                    "payload": {
                        "type_id": "Bag",
                        "name": "Bag",
                        "kind": "array",
                        "fields": [{"name": "ignored", "type_ref": "int"}],
                    },
                },
            )
        )
        assert saved_data_type["fields"] == []
        assert saved_data_type["element_type"] == "any"

        template = _decode_tool_result_payload(
            await session.call_tool("get_default_module_template")
        )
        assert template["module_id"] == "example-module"

        _decode_tool_result_payload(
            await session.call_tool("create_module", {"module_id": "t1", "name": "T1"})
        )
        _decode_tool_result_payload(
            await session.call_tool(
                "upsert_module",
                {"module_id": "t1", "payload": _echo_payload("t1")},
            )
        )
        script_result = _decode_tool_result_payload(
            await session.call_tool(
                "run_script_test",
                {
                    "script": (
                        "result = run_module('t1', 'in', 7)\n"
                        "assert_equal(result['outputs']['out'][0], 7)\n"
                    )
                },
            )
        )
        assert script_result == {"assertions": 1, "status": "passed", "errors": []}

    _run_mcp_session(tmp_path, _assert)
