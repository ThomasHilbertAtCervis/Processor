"""Drive the Processor Playground MCP server to build & run the half-or-double process.

Behaviour:
- If ``value < 10``  → output = value * 2
- If ``value >= 10`` → output = value / 2

The v2 model is a wire graph: ``module_input -> python -> module_output``.
The python node uses generator semantics — assigning to ``outputs[...]``
fires that output port, which is delivered along its outgoing wires.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

MODULE_ID = "half_or_double"

LOGIC_CODE = (
    "x = inputs['value']\n"
    "if x < 10:\n"
    "    outputs['result'] = x * 2\n"
    "else:\n"
    "    outputs['result'] = x / 2\n"
)

MODULE_PAYLOAD: dict[str, Any] = {
    "module_id": MODULE_ID,
    "name": "Half or Double",
    "inputs": [{"name": "value", "type_ref": "decimal"}],
    "outputs": [{"name": "result", "type_ref": "decimal"}],
    "nodes": [
        {
            "id": "in-value",
            "type": "module_input",
            "inputs": [],
            "outputs": [{"name": "v", "type_ref": "decimal"}],
            "data": {"signal_name": "value"},
        },
        {
            "id": "logic",
            "type": "python",
            "inputs": [{"name": "value", "type_ref": "decimal"}],
            "outputs": [{"name": "result", "type_ref": "decimal"}],
            "data": {"code": LOGIC_CODE},
        },
        {
            "id": "out-result",
            "type": "module_output",
            "inputs": [{"name": "v", "type_ref": "decimal"}],
            "outputs": [],
            "data": {"signal_name": "result"},
        },
    ],
    "edges": [
        {"id": "e1", "source": "in-value", "source_handle": "v",
         "target": "logic", "target_handle": "value"},
        {"id": "e2", "source": "logic", "source_handle": "result",
         "target": "out-result", "target_handle": "v"},
    ],
    "submodules": [],
}


def _decode(result: Any) -> Any:
    assert not result.isError, result
    if result.structuredContent is not None:
        sc = result.structuredContent
        if isinstance(sc, dict) and set(sc.keys()) == {"result"}:
            return sc["result"]
        return sc
    text_blocks = [b.text for b in result.content if hasattr(b, "text")]
    if len(text_blocks) == 1:
        try:
            return json.loads(text_blocks[0])
        except json.JSONDecodeError:
            return text_blocks[0]
    return text_blocks


async def _drive(session: ClientSession) -> None:
    try:
        await session.call_tool("delete_module", {"module_id": MODULE_ID})
    except Exception:
        pass

    created = _decode(
        await session.call_tool(
            "create_module", {"module_id": MODULE_ID, "name": "Half or Double"}
        )
    )
    print("CREATED:", created["module_id"])

    saved = _decode(
        await session.call_tool(
            "upsert_module", {"module_id": MODULE_ID, "payload": MODULE_PAYLOAD}
        )
    )
    print("SAVED nodes:", [n["id"] for n in saved["nodes"]])
    print("SAVED edges:", [(e["source"], e["target"]) for e in saved["edges"]])

    for v in [0, 4, 9, 10, 20, 100, 9.999, 10.0]:
        run = _decode(
            await session.call_tool(
                "run_module", {"module_id": MODULE_ID, "input_data": {"value": v}}
            )
        )
        print(f"input={v!r:>8}  outputs={run['outputs']}  status={run['status']}")


def main() -> None:
    storage = Path(os.environ.get("PROCESSOR_PLAYGROUND_STORAGE_DIR") or "storage/modules")
    data_types = Path(
        os.environ.get("PROCESSOR_PLAYGROUND_DATA_TYPES_DIR") or "storage/data-types"
    )
    env = os.environ.copy()
    env["PROCESSOR_PLAYGROUND_STORAGE_DIR"] = str(storage.resolve())
    env["PROCESSOR_PLAYGROUND_DATA_TYPES_DIR"] = str(data_types.resolve())

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "processor_playground.mcp_server"],
        env=env,
        cwd=str(Path(__file__).resolve().parent.parent),
    )

    async def _runner() -> None:
        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                await _drive(session)

    anyio.run(_runner)


if __name__ == "__main__":
    main()
