"""Domain dataclasses for the Processor Playground.

Storage format v2: a module is a graph of typed-port **nodes** wired by
**edges**. There is no top-level ``flow`` list any more; control and data
travel together along the wires. See ARCHITECTURE.md §2 and PRODUCT.md §2 for
the model.

These dataclasses know nothing about FastAPI, persistence or execution — they
are the leaf layer of the dependency stack.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


# --------------------------------------------------------------- DataTypeField

@dataclass
class DataTypeField:
    name: str
    type_ref: str

    @staticmethod
    def from_dict(payload: dict[str, Any]) -> "DataTypeField":
        return DataTypeField(name=payload["name"], type_ref=payload.get("type_ref", "any"))

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "type_ref": self.type_ref}


# ------------------------------------------------------------------- DataType

@dataclass
class DataType:
    type_id: str
    name: str
    kind: Literal["struct", "array", "dict"] = "struct"
    fields: list[DataTypeField] = field(default_factory=list)
    element_type: str | None = None

    @staticmethod
    def from_dict(payload: dict[str, Any]) -> "DataType":
        kind = payload.get("kind", "struct")
        if kind == "struct":
            fields = [DataTypeField.from_dict(item) for item in payload.get("fields", [])]
            element_type = None
        else:
            fields = []
            element_type = payload.get("element_type") or "any"
        return DataType(
            type_id=payload["type_id"],
            name=payload["name"],
            kind=kind,
            fields=fields,
            element_type=element_type,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "type_id": self.type_id,
            "name": self.name,
            "kind": self.kind,
            "fields": [item.to_dict() for item in self.fields],
            "element_type": self.element_type,
        }


# --------------------------------------------------------------------- Signal

@dataclass
class Signal:
    """A module's externally-visible input/output (its 'pin' on its frame)."""

    name: str
    type_ref: str = "any"
    filter: str | None = None

    @staticmethod
    def from_dict(payload: str | dict[str, Any]) -> "Signal":
        if isinstance(payload, str):
            return Signal(name=payload)
        return Signal(
            name=payload["name"],
            type_ref=payload.get("type_ref", "any"),
            filter=payload.get("filter"),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"name": self.name, "type_ref": self.type_ref}
        if self.filter:
            out["filter"] = self.filter
        return out


# ----------------------------------------------------------------------- Port

PortKind = Literal["data", "request", "response"]


@dataclass
class Port:
    """A typed pin on a node.

    ``kind`` lets a node declare that an output / input pair forms a
    request/response handshake. A ``request`` output's ``pair`` is the name
    of the same node's ``response`` input — and vice-versa. The simulator
    uses this pairing to suspend the firing node until the matching value
    arrives back on its paired input.
    """

    name: str
    type_ref: str = "any"
    kind: PortKind = "data"
    pair: str | None = None

    @staticmethod
    def from_dict(payload: dict[str, Any]) -> "Port":
        return Port(
            name=payload["name"],
            type_ref=payload.get("type_ref", "any"),
            kind=payload.get("kind", "data"),
            pair=payload.get("pair"),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "name": self.name,
            "type_ref": self.type_ref,
            "kind": self.kind,
        }
        if self.pair:
            out["pair"] = self.pair
        return out


# ----------------------------------------------------------------------- Node

@dataclass
class Node:
    """One vertex in a module's wiring diagram.

    ``type`` selects the activator (see ``simulator._ACTIVATORS``). ``data``
    is the kind-specific configuration blob (the Python node stores its
    ``code`` here; the submodule node stores its ``module_id``; the
    module_input / module_output nodes store their ``signal_name``).
    """

    id: str
    type: str
    inputs: list[Port] = field(default_factory=list)
    outputs: list[Port] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    # Canvas coordinates (consumed by the ReactFlow editor). The simulator
    # ignores them; they round-trip so a hand-arranged diagram stays put.
    position: dict[str, float] = field(default_factory=lambda: {"x": 0.0, "y": 0.0})

    @staticmethod
    def from_dict(payload: dict[str, Any]) -> "Node":
        raw_pos = payload.get("position") or {}
        position = {
            "x": float(raw_pos.get("x", 0.0)),
            "y": float(raw_pos.get("y", 0.0)),
        }
        return Node(
            id=payload["id"],
            type=payload["type"],
            inputs=[Port.from_dict(p) for p in payload.get("inputs", [])],
            outputs=[Port.from_dict(p) for p in payload.get("outputs", [])],
            data=dict(payload.get("data", {})),
            position=position,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "inputs": [p.to_dict() for p in self.inputs],
            "outputs": [p.to_dict() for p in self.outputs],
            "data": self.data,
            "position": dict(self.position),
        }


# ----------------------------------------------------------------------- Edge

@dataclass
class Edge:
    """A wire from one node's output port to another node's input port.

    Both endpoints are identified by ``(node_id, port_name)``. The port name
    is also persisted under ReactFlow's ``sourceHandle`` / ``targetHandle``
    aliases on round-trip so the UI keeps working without a translation
    layer.
    """

    id: str
    source: str
    source_handle: str
    target: str
    target_handle: str
    data: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_dict(payload: dict[str, Any]) -> "Edge":
        source_handle = (
            payload.get("source_handle")
            or payload.get("sourceHandle")
            or ""
        )
        target_handle = (
            payload.get("target_handle")
            or payload.get("targetHandle")
            or ""
        )
        return Edge(
            id=payload["id"],
            source=payload["source"],
            source_handle=source_handle,
            target=payload["target"],
            target_handle=target_handle,
            data=dict(payload.get("data", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "source_handle": self.source_handle,
            "sourceHandle": self.source_handle,
            "target": self.target,
            "target_handle": self.target_handle,
            "targetHandle": self.target_handle,
            "data": self.data,
        }


# --------------------------------------------------------------------- Module

def _derive_signals_from_nodes(
    nodes: list["Node"],
) -> tuple[list["Signal"], list["Signal"]]:
    """Derive a module's external (inputs, outputs) Signal lists from its
    ``module_input`` / ``module_output`` nodes.

    The canvas is the single source of truth for the module interface:
    each ``module_input`` node becomes one entry in ``Module.inputs``
    (signal name from ``data.signal_name``, type from the node's sole
    output port) and likewise for ``module_output`` nodes. Nodes
    without a ``signal_name`` are skipped — they're treated as
    works-in-progress that the UI lets the user finish naming.
    """
    inputs: list[Signal] = []
    outputs: list[Signal] = []
    seen_in: set[str] = set()
    seen_out: set[str] = set()
    for node in nodes:
        if node.type == "module_input":
            name = node.data.get("signal_name", "")
            if not name or name in seen_in:
                continue
            type_ref = node.outputs[0].type_ref if node.outputs else "any"
            inputs.append(Signal(name=name, type_ref=type_ref))
            seen_in.add(name)
        elif node.type == "module_output":
            name = node.data.get("signal_name", "")
            if not name or name in seen_out:
                continue
            type_ref = node.inputs[0].type_ref if node.inputs else "any"
            outputs.append(Signal(name=name, type_ref=type_ref))
            seen_out.add(name)
    return inputs, outputs


@dataclass
class Module:
    """A process: typed external signals, an internal node/edge graph,
    and optional reusable submodules.

    Storage format v2 deliberately omits the old ``flow`` list and the
    ``interfaces`` mirror. Modules persisted in the old format raise on
    load — see ``from_dict``.
    """

    module_id: str
    name: str
    inputs: list[Signal] = field(default_factory=list)
    outputs: list[Signal] = field(default_factory=list)
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    submodules: list["Module"] = field(default_factory=list)

    @staticmethod
    def from_dict(payload: dict[str, Any]) -> "Module":
        # v1 modules carry a top-level ``flow`` list and/or an ``interfaces``
        # mirror. They cannot be auto-migrated to the wire-based model — the
        # graph topology was never represented. Reject loudly so a stale
        # stored module isn't silently truncated.
        if "flow" in payload:
            raise ValueError(
                "Module storage format v1 'flow' field is no longer supported; "
                "model the process as nodes + edges instead."
            )
        if "interfaces" in payload:
            raise ValueError(
                "Module storage format v1 'interfaces' mirror is no longer "
                "supported; declare 'inputs'/'outputs' directly."
            )
        nodes = [Node.from_dict(item) for item in payload.get("nodes", [])]
        # Single source of truth: the module's external interface is whatever
        # ``module_input`` / ``module_output`` nodes the canvas contains.
        # Any ``inputs``/``outputs`` keys in the payload are ignored — they
        # were a duplicate the UI used to maintain through a separate
        # Signals panel. Falling back to payload values is only used if no
        # interface nodes exist yet (e.g. a freshly-created module).
        derived_inputs, derived_outputs = _derive_signals_from_nodes(nodes)
        if not derived_inputs and "inputs" in payload:
            derived_inputs = [Signal.from_dict(item) for item in payload["inputs"]]
        if not derived_outputs and "outputs" in payload:
            derived_outputs = [Signal.from_dict(item) for item in payload["outputs"]]
        return Module(
            module_id=payload["module_id"],
            name=payload["name"],
            inputs=derived_inputs,
            outputs=derived_outputs,
            nodes=nodes,
            edges=[Edge.from_dict(item) for item in payload.get("edges", [])],
            submodules=[Module.from_dict(item) for item in payload.get("submodules", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        # Re-derive on the way out too so that an in-memory edit to the
        # nodes list is reflected without needing a round-trip through the
        # repository.
        derived_inputs, derived_outputs = _derive_signals_from_nodes(self.nodes)
        inputs = derived_inputs or self.inputs
        outputs = derived_outputs or self.outputs
        return {
            "module_id": self.module_id,
            "name": self.name,
            "inputs": [s.to_dict() for s in inputs],
            "outputs": [s.to_dict() for s in outputs],
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "submodules": [m.to_dict() for m in self.submodules],
        }
