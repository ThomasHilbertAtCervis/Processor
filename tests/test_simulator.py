"""Tests for the v2 wire-and-port :class:`Simulator`.

Covers:
* module input → wire → module output (the bare minimum data path);
* Python node firing data outputs from a script (with if/for);
* the request/response handshake between two Python nodes;
* submodule composition (a parent's submodule node delegates to a child
  module's module_input / module_output nodes);
* error paths (unknown node type, missing module_input signal, undeclared
  output port, request with no response).
"""
from __future__ import annotations

import pytest

from processor_playground.models import Edge, Module, Node, Port, Signal
from processor_playground.simulator import Simulator, SimulatorError


# ----------------------------------------------------------- module builders

def _mod(
    *,
    module_id: str = "m",
    inputs: list[Signal] | None = None,
    outputs: list[Signal] | None = None,
    nodes: list[Node],
    edges: list[Edge],
    submodules: list[Module] | None = None,
) -> Module:
    return Module(
        module_id=module_id,
        name=module_id.title(),
        inputs=inputs or [],
        outputs=outputs or [],
        nodes=nodes,
        edges=edges,
        submodules=submodules or [],
    )


def _input(node_id: str, signal_name: str, type_ref: str = "any") -> Node:
    return Node(
        id=node_id,
        type="module_input",
        inputs=[],
        outputs=[Port(name="value", type_ref=type_ref)],
        data={"signal_name": signal_name},
    )


def _output(node_id: str, signal_name: str, type_ref: str = "any") -> Node:
    return Node(
        id=node_id,
        type="module_output",
        inputs=[Port(name="value", type_ref=type_ref)],
        outputs=[],
        data={"signal_name": signal_name},
    )


def _python(
    node_id: str,
    code: str,
    *,
    inputs: list[Port],
    outputs: list[Port],
) -> Node:
    return Node(
        id=node_id, type="python",
        inputs=inputs, outputs=outputs,
        data={"code": code},
    )


def _wire(edge_id: str, src: str, src_port: str, dst: str, dst_port: str) -> Edge:
    return Edge(
        id=edge_id,
        source=src, source_handle=src_port,
        target=dst, target_handle=dst_port,
    )


# ----------------------------------------------------------------- bare path

class TestModuleIO:
    def test_input_flows_directly_to_output(self) -> None:
        module = _mod(
            inputs=[Signal("in")],
            outputs=[Signal("out")],
            nodes=[_input("i", "in"), _output("o", "out")],
            edges=[_wire("e", "i", "value", "o", "value")],
        )
        result = Simulator().run(module, input_data={"in": 42})
        assert result["outputs"] == {"out": [42]}
        assert result["status"] == "complete"

    def test_unrouted_input_still_records_no_outputs(self) -> None:
        module = _mod(
            inputs=[Signal("in")], outputs=[Signal("out")],
            nodes=[_input("i", "in"), _output("o", "out")],
            edges=[],
        )
        result = Simulator().run(module, input_data={"in": 1})
        assert result["outputs"] == {"out": []}

    def test_missing_input_node_raises(self) -> None:
        module = _mod(
            inputs=[Signal("in")], outputs=[],
            nodes=[], edges=[],
        )
        with pytest.raises(SimulatorError, match="No module_input node"):
            Simulator().run(module, input_data={"in": 1})


# --------------------------------------------------------------- python node

class TestPythonNode:
    def test_python_node_reads_input_writes_output(self) -> None:
        module = _mod(
            inputs=[Signal("v")], outputs=[Signal("r")],
            nodes=[
                _input("i", "v"),
                _python(
                    "p",
                    "outputs['out'] = inputs['in'] * 2",
                    inputs=[Port("in")], outputs=[Port("out")],
                ),
                _output("o", "r"),
            ],
            edges=[
                _wire("e1", "i", "value", "p", "in"),
                _wire("e2", "p", "out", "o", "value"),
            ],
        )
        result = Simulator().run(module, input_data={"v": 7})
        assert result["outputs"] == {"r": [14]}

    def test_python_node_if_else_branching(self) -> None:
        code = (
            "if inputs['x'] < 10:\n"
            "    outputs['y'] = inputs['x'] * 2\n"
            "else:\n"
            "    outputs['y'] = inputs['x'] / 2\n"
        )
        module = _mod(
            inputs=[Signal("x")], outputs=[Signal("y")],
            nodes=[
                _input("i", "x"),
                _python("p", code, inputs=[Port("x")], outputs=[Port("y")]),
                _output("o", "y"),
            ],
            edges=[
                _wire("e1", "i", "value", "p", "x"),
                _wire("e2", "p", "y", "o", "value"),
            ],
        )
        assert Simulator().run(module, input_data={"x": 4})["outputs"]["y"] == [8]
        assert Simulator().run(module, input_data={"x": 20})["outputs"]["y"] == [10]

    def test_python_node_for_loop_emits_per_iteration(self) -> None:
        code = (
            "for item in inputs['items']:\n"
            "    outputs['each'] = item\n"
        )
        module = _mod(
            inputs=[Signal("items")], outputs=[Signal("each")],
            nodes=[
                _input("i", "items"),
                _python("p", code, inputs=[Port("items")], outputs=[Port("each")]),
                _output("o", "each"),
            ],
            edges=[
                _wire("e1", "i", "value", "p", "items"),
                _wire("e2", "p", "each", "o", "value"),
            ],
        )
        result = Simulator().run(module, input_data={"items": [1, 2, 3]})
        assert result["outputs"]["each"] == [1, 2, 3]

    def test_python_node_current_input_tracks_trigger_port(self) -> None:
        # current_input is recorded back into outputs so the test can observe it
        code = "outputs['tag'] = current_input"
        module = _mod(
            inputs=[Signal("a"), Signal("b")],
            outputs=[Signal("tag")],
            nodes=[
                _input("ia", "a"),
                _input("ib", "b"),
                _python("p", code,
                        inputs=[Port("a"), Port("b")],
                        outputs=[Port("tag")]),
                _output("o", "tag"),
            ],
            edges=[
                _wire("e1", "ia", "value", "p", "a"),
                _wire("e2", "ib", "value", "p", "b"),
                _wire("e3", "p", "tag", "o", "value"),
            ],
        )
        result = Simulator().run(module, input_data={"a": 1, "b": 2})
        # Each input fires its own activation; current_input reflects each in turn.
        assert result["outputs"]["tag"] == ["a", "b"]

    def test_python_node_undeclared_output_port_raises(self) -> None:
        module = _mod(
            inputs=[Signal("v")], outputs=[],
            nodes=[
                _input("i", "v"),
                _python("p", "outputs['ghost'] = inputs['v']",
                        inputs=[Port("v")], outputs=[Port("real")]),
            ],
            edges=[_wire("e", "i", "value", "p", "v")],
        )
        with pytest.raises(SimulatorError, match="undeclared output port 'ghost'"):
            Simulator().run(module, input_data={"v": 1})


# ----------------------------------------------------------- request/response

class TestRequestResponse:
    def test_paired_request_suspends_until_response_arrives(self) -> None:
        # caller asks storage for a value, doubles it, and emits the result.
        caller_code = (
            "outputs['ask'] = inputs['key']\n"
            "outputs['result'] = inputs['answer'] * 2\n"
        )
        store_code = (
            # Toy "lookup": returns the length of the requested key.
            "outputs['answer'] = len(inputs['query'])\n"
        )
        module = _mod(
            inputs=[Signal("key")], outputs=[Signal("result")],
            nodes=[
                _input("in", "key"),
                _python(
                    "caller", caller_code,
                    inputs=[Port("key"), Port("answer", kind="response")],
                    outputs=[
                        Port("ask", kind="request", pair="answer"),
                        Port("result"),
                    ],
                ),
                _python(
                    "store", store_code,
                    inputs=[Port("query")],
                    outputs=[Port("answer")],
                ),
                _output("out", "result"),
            ],
            edges=[
                _wire("e1", "in", "value", "caller", "key"),
                _wire("e2", "caller", "ask", "store", "query"),
                _wire("e3", "store", "answer", "caller", "answer"),
                _wire("e4", "caller", "result", "out", "value"),
            ],
        )
        result = Simulator().run(module, input_data={"key": "hi"})
        assert result["outputs"]["result"] == [4]  # len("hi") * 2

    def test_request_without_response_raises(self) -> None:
        # caller fires a request but nothing is wired back.
        module = _mod(
            inputs=[Signal("k")], outputs=[Signal("r")],
            nodes=[
                _input("i", "k"),
                _python(
                    "caller", "outputs['ask'] = inputs['k']",
                    inputs=[Port("k"), Port("answer", kind="response")],
                    outputs=[Port("ask", kind="request", pair="answer")],
                ),
            ],
            edges=[_wire("e1", "i", "value", "caller", "k")],
        )
        with pytest.raises(SimulatorError, match="no value was delivered"):
            Simulator().run(module, input_data={"k": "x"})

    def test_request_without_pair_raises(self) -> None:
        module = _mod(
            inputs=[Signal("k")], outputs=[],
            nodes=[
                _input("i", "k"),
                _python(
                    "caller", "outputs['ask'] = inputs['k']",
                    inputs=[Port("k")],
                    outputs=[Port("ask", kind="request")],  # no pair
                ),
            ],
            edges=[_wire("e1", "i", "value", "caller", "k")],
        )
        with pytest.raises(SimulatorError, match="has no 'pair' set"):
            Simulator().run(module, input_data={"k": "x"})


# --------------------------------------------------------------- submodules

class TestSubmodules:
    def test_submodule_input_output_pass_through(self) -> None:
        child = _mod(
            module_id="child",
            inputs=[Signal("inp")], outputs=[Signal("outp")],
            nodes=[
                _input("ci", "inp"),
                _python("cp", "outputs['o'] = inputs['i'] + 1",
                        inputs=[Port("i")], outputs=[Port("o")]),
                _output("co", "outp"),
            ],
            edges=[
                _wire("ce1", "ci", "value", "cp", "i"),
                _wire("ce2", "cp", "o", "co", "value"),
            ],
        )
        parent = _mod(
            module_id="parent",
            inputs=[Signal("n")], outputs=[Signal("r")],
            nodes=[
                _input("i", "n"),
                Node(
                    id="sub", type="submodule",
                    inputs=[Port("inp")], outputs=[Port("outp")],
                    data={"module_id": "child"},
                ),
                _output("o", "r"),
            ],
            edges=[
                _wire("e1", "i", "value", "sub", "inp"),
                _wire("e2", "sub", "outp", "o", "value"),
            ],
            submodules=[child],
        )
        result = Simulator().run(parent, input_data={"n": 10})
        assert result["outputs"] == {"r": [11]}

    def test_unknown_submodule_raises(self) -> None:
        parent = _mod(
            inputs=[Signal("n")], outputs=[],
            nodes=[
                _input("i", "n"),
                Node(
                    id="sub", type="submodule",
                    inputs=[Port("inp")], outputs=[],
                    data={"module_id": "ghost"},
                ),
            ],
            edges=[_wire("e1", "i", "value", "sub", "inp")],
        )
        with pytest.raises(SimulatorError, match="Submodule 'ghost' not found"):
            Simulator().run(parent, input_data={"n": 1})


# -------------------------------------------------------------------- errors

class TestErrorPaths:
    def test_unknown_node_type_raises(self) -> None:
        module = _mod(
            inputs=[Signal("v")], outputs=[],
            nodes=[
                _input("i", "v"),
                Node(id="x", type="totally-made-up",
                     inputs=[Port("v")], outputs=[]),
            ],
            edges=[_wire("e1", "i", "value", "x", "v")],
        )
        with pytest.raises(SimulatorError, match="Unknown node type 'totally-made-up'"):
            Simulator().run(module, input_data={"v": 1})

    def test_module_input_as_edge_target_raises(self) -> None:
        # Wiring something INTO a module_input is invalid; it's a source-only node.
        module = _mod(
            inputs=[Signal("a")], outputs=[],
            nodes=[
                _input("ia", "a"),
                _python("p", "outputs['o'] = inputs['v']",
                        inputs=[Port("v")], outputs=[Port("o")]),
            ],
            edges=[_wire("e1", "ia", "value", "p", "v"),
                   _wire("e2", "p", "o", "ia", "value")],  # bad: back into input
        )
        with pytest.raises(SimulatorError, match="source-only node"):
            Simulator().run(module, input_data={"a": 1})
