"""Drive the Processor Playground MCP server to demonstrate request/response.

A toy *price-list lookup* module:

    module_input(sku)
        └─► caller(python) ──ask──► store(python)
                  ▲                     │
                  └──── price ◄─────────┘
                  │
                  └──total──► module_output(total)

The ``caller`` node receives a SKU, fires its ``ask`` request port carrying
the SKU, **suspends** until the paired ``price`` response port receives a
delivery, then computes ``price * 0.9`` (a 10%% discount) and fires
``total``. The ``store`` node is a stand-in for a database: it looks up the
SKU in an in-line dict and fires the price on its ``answer`` output, which
is wired back to the caller's ``price`` response input.

Run this from the repository root::

    python scripts/build_request_response_demo.py
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

MODULE_ID = "discount_price_lookup"

CALLER_CODE = (
    # Fire request — execution suspends here until 'price' is delivered.
    "outputs['ask'] = inputs['sku']\n"
    # Once resumed, inputs['price'] holds the value delivered on the
    # paired response port.
    "outputs['total'] = inputs['price'] * 9 / 10\n"
)

STORE_CODE = (
    "prices = {'A': 100, 'B': 200, 'C': 50}\n"
    "outputs['answer'] = prices[inputs['query']]\n"
)

MODULE_PAYLOAD: dict[str, Any] = {
    "module_id": MODULE_ID,
    "name": "Discount Price Lookup",
    "inputs": [{"name": "sku", "type_ref": "string"}],
    "outputs": [{"name": "total", "type_ref": "decimal"}],
    "nodes": [
        {
            "id": "in-sku",
            "type": "module_input",
            "inputs": [],
            "outputs": [{"name": "v", "type_ref": "string"}],
            "data": {"signal_name": "sku"},
            "position": {"x": 60, "y": 200},
        },
        {
            "id": "caller",
            "type": "python",
            "inputs": [
                {"name": "sku", "type_ref": "string"},
                # Paired response input — receives the price from 'store'.
                {"name": "price", "type_ref": "decimal", "kind": "response"},
            ],
            "outputs": [
                # Paired request output — firing this suspends the node
                # until 'price' is delivered.
                {"name": "ask", "type_ref": "string",
                 "kind": "request", "pair": "price"},
                {"name": "total", "type_ref": "decimal"},
            ],
            "data": {"code": CALLER_CODE},
            "position": {"x": 320, "y": 200},
        },
        {
            "id": "store",
            "type": "python",
            "inputs": [{"name": "query", "type_ref": "string"}],
            "outputs": [{"name": "answer", "type_ref": "decimal"}],
            "data": {"code": STORE_CODE},
            "position": {"x": 620, "y": 60},
        },
        {
            "id": "out-total",
            "type": "module_output",
            "inputs": [{"name": "v", "type_ref": "decimal"}],
            "outputs": [],
            "data": {"signal_name": "total"},
            "position": {"x": 620, "y": 340},
        },
    ],
    "edges": [
        {"id": "e1", "source": "in-sku", "source_handle": "v",
         "target": "caller", "target_handle": "sku"},
        {"id": "e2", "source": "caller", "source_handle": "ask",
         "target": "store", "target_handle": "query"},
        {"id": "e3", "source": "store", "source_handle": "answer",
         "target": "caller", "target_handle": "price"},
        {"id": "e4", "source": "caller", "source_handle": "total",
         "target": "out-total", "target_handle": "v"},
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

    _decode(
        await session.call_tool(
            "create_module",
            {"module_id": MODULE_ID, "name": "Discount Price Lookup"},
        )
    )
    saved = _decode(
        await session.call_tool(
            "upsert_module", {"module_id": MODULE_ID, "payload": MODULE_PAYLOAD}
        )
    )
    print("SAVED nodes:", [n["id"] for n in saved["nodes"]])
    print("SAVED edges:", [(e["source"], e["target"]) for e in saved["edges"]])

    # Sticker prices: A=100 → 90, B=200 → 180, C=50 → 45.
    for sku in ["A", "B", "C"]:
        run = _decode(
            await session.call_tool(
                "run_module", {"module_id": MODULE_ID, "input_data": {"sku": sku}}
            )
        )
        print(f"sku={sku!r}  outputs={run['outputs']}  status={run['status']}")

    # Unknown SKU surfaces as a simulator error → script failure.
    err = await session.call_tool(
        "run_module", {"module_id": MODULE_ID, "input_data": {"sku": "ZZZ"}}
    )
    print(
        "sku='ZZZ' (unknown) → isError=", err.isError,
        " message=",
        next((b.text for b in (err.content or []) if hasattr(b, "text")), None),
    )


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
