"""Default templates and example payloads for the v2 wire-based model.

These are *data*, not view logic. Keeping them out of ``api.py`` /
``mcp_server.py`` means those layers can stay thin adapters — see
ARCHITECTURE.md ("Hard rules").
"""
from __future__ import annotations

from typing import Any

from .models import Module


def default_module_payload() -> dict[str, Any]:
    """Raw dict for the example/default module surfaced by the UI.

    A minimal showcase of the v2 model: one input signal flows through a
    Python identity node into one output signal.
    """
    return {
        "module_id": "example-module",
        "name": "Example Module",
        "inputs": [{"name": "input", "type_ref": "any"}],
        "outputs": [{"name": "result", "type_ref": "any"}],
        "nodes": [
            {
                "id": "input-1",
                "type": "module_input",
                "inputs": [],
                "outputs": [{"name": "value", "type_ref": "any", "kind": "data"}],
                "data": {"signal_name": "input", "label": "input"},
                "position": {"x": 80, "y": 160},
            },
            {
                "id": "logic-1",
                "type": "python",
                "inputs": [{"name": "value", "type_ref": "any", "kind": "data"}],
                "outputs": [{"name": "result", "type_ref": "any", "kind": "data"}],
                "data": {
                    "label": "Identity",
                    "code": "outputs['result'] = inputs['value']\n",
                },
                "position": {"x": 360, "y": 160},
            },
            {
                "id": "output-1",
                "type": "module_output",
                "inputs": [{"name": "value", "type_ref": "any", "kind": "data"}],
                "outputs": [],
                "data": {"signal_name": "result", "label": "result"},
                "position": {"x": 640, "y": 160},
            },
        ],
        "edges": [
            {
                "id": "e1",
                "source": "input-1",
                "source_handle": "value",
                "target": "logic-1",
                "target_handle": "value",
            },
            {
                "id": "e2",
                "source": "logic-1",
                "source_handle": "result",
                "target": "output-1",
                "target_handle": "value",
            },
        ],
        "submodules": [],
    }


def default_module() -> Module:
    return Module.from_dict(default_module_payload())


def new_module_payload(module_id: str, name: str) -> dict[str, Any]:
    """Raw dict for a freshly created empty module (v2 schema)."""
    return {
        "module_id": module_id,
        "name": name,
        "inputs": [],
        "outputs": [],
        "nodes": [],
        "edges": [],
        "submodules": [],
    }


def new_module(module_id: str, name: str) -> Module:
    return Module.from_dict(new_module_payload(module_id, name))
