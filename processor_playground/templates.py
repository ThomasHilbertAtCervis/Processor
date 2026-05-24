"""Default templates and example payloads.

These are *data*, not view logic. Keeping them out of `api.py` means the API
layer can stay a thin adapter — see ARCHITECTURE.md ("Hard rules").
"""
from __future__ import annotations

from typing import Any

from .models import Module


def default_module_payload() -> dict[str, Any]:
    """Raw dict for the example/default module surfaced by the UI.

    Returned as a plain dict so it can be passed straight into
    :meth:`Module.from_dict` and serialised back through :meth:`Module.to_dict`.
    """
    return {
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


def default_module() -> Module:
    """Return the default module as a fully constructed :class:`Module`."""
    return Module.from_dict(default_module_payload())


def new_module_payload(module_id: str, name: str) -> dict[str, Any]:
    """Raw dict for a freshly created empty module.

    Shared by every client (UI, MCP server, scripts) so that "create a new
    module" means the same thing everywhere — see ARCHITECTURE.md.
    """
    return {
        "module_id": module_id,
        "name": name,
        "inputs": [],
        "outputs": [],
        "nodes": [],
        "edges": [],
        "flow": [],
        "submodules": [],
    }


def new_module(module_id: str, name: str) -> Module:
    """Return a freshly constructed, empty :class:`Module`."""
    return Module.from_dict(new_module_payload(module_id, name))
