"""Templates module: the default-module payload must be valid."""
from __future__ import annotations

from processor_playground.models import Module
from processor_playground.templates import (
    default_module,
    default_module_payload,
    new_module,
    new_module_payload,
)


def test_default_module_payload_is_valid() -> None:
    payload = default_module_payload()
    module = Module.from_dict(payload)
    assert module.module_id == "example-module"
    assert module.inputs and module.outputs
    assert module.nodes
    assert module.edges
    assert module.flow


def test_default_module_round_trips() -> None:
    module = default_module()
    again = Module.from_dict(module.to_dict())
    assert again.module_id == module.module_id
    assert [n["id"] for n in again.nodes] == [n["id"] for n in module.nodes]


def test_default_module_payload_is_independent() -> None:
    """Two calls must not share mutable state."""
    a = default_module_payload()
    a["nodes"].append({"id": "extra"})
    b = default_module_payload()
    assert all(n.get("id") != "extra" for n in b["nodes"])


def test_new_module_payload_is_empty_skeleton() -> None:
    payload = new_module_payload("m1", "My Module")
    assert payload["module_id"] == "m1"
    assert payload["name"] == "My Module"
    assert payload["inputs"] == []
    assert payload["outputs"] == []
    assert payload["nodes"] == []
    assert payload["edges"] == []
    assert payload["flow"] == []
    assert payload["submodules"] == []


def test_new_module_returns_valid_module() -> None:
    module = new_module("m2", "Another")
    assert isinstance(module, Module)
    assert module.module_id == "m2"
    assert module.name == "Another"
    assert module.inputs == []
    assert module.outputs == []
