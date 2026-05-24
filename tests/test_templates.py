"""Templates module: the default-module payload must be valid v2."""
from __future__ import annotations

from processor_playground.models import Module
from processor_playground.simulator import Simulator
from processor_playground.templates import (
    default_module,
    default_module_payload,
    new_module,
    new_module_payload,
)


def test_default_module_payload_round_trips() -> None:
    payload = default_module_payload()
    module = Module.from_dict(payload)
    assert module.module_id == "example-module"
    assert module.inputs and module.outputs
    assert module.nodes and module.edges


def test_default_module_actually_runs_end_to_end() -> None:
    # The example module ships with an identity Python node — running it
    # exercises every executable node kind needed for the demo.
    result = Simulator().run(default_module(), input_signal="input", input_value="hello")
    assert result["outputs"] == {"result": ["hello"]}


def test_default_module_payload_is_independent() -> None:
    a = default_module_payload()
    a["nodes"].append({"id": "extra", "type": "python"})
    b = default_module_payload()
    assert all(n.get("id") != "extra" for n in b["nodes"])


def test_new_module_payload_is_empty_skeleton() -> None:
    payload = new_module_payload("m1", "My Module")
    assert payload == {
        "module_id": "m1",
        "name": "My Module",
        "inputs": [],
        "outputs": [],
        "nodes": [],
        "edges": [],
        "submodules": [],
    }


def test_new_module_returns_valid_module() -> None:
    module = new_module("m2", "Another")
    assert isinstance(module, Module)
    assert module.module_id == "m2"
    assert module.nodes == [] and module.edges == []
