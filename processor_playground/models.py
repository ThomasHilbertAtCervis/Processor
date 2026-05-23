from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class DataTypeField:
    name: str
    type_ref: str

    @staticmethod
    def from_dict(payload: dict[str, Any]) -> "DataTypeField":
        return DataTypeField(
            name=payload["name"],
            type_ref=payload.get("type_ref", "any"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "type_ref": self.type_ref}


@dataclass
class DataType:
    type_id: str
    name: str
    kind: Literal["struct", "array", "dict"] = "struct"
    fields: list[DataTypeField] = field(default_factory=list)
    element_type: str | None = None

    @staticmethod
    def from_dict(payload: dict[str, Any]) -> "DataType":
        return DataType(
            type_id=payload["type_id"],
            name=payload["name"],
            kind=payload.get("kind", "struct"),
            fields=[DataTypeField.from_dict(item) for item in payload.get("fields", [])],
            element_type=payload.get("element_type"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "type_id": self.type_id,
            "name": self.name,
            "kind": self.kind,
            "fields": [item.to_dict() for item in self.fields],
            "element_type": self.element_type,
        }


@dataclass
class Signal:
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
        payload: dict[str, Any] = {"name": self.name, "type_ref": self.type_ref}
        if self.filter:
            payload["filter"] = self.filter
        return payload


@dataclass
class Module:
    module_id: str
    name: str
    inputs: list[Signal] = field(default_factory=list)
    outputs: list[Signal] = field(default_factory=list)
    nodes: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    flow: list[dict[str, Any]] = field(default_factory=list)
    submodules: list["Module"] = field(default_factory=list)

    @staticmethod
    def from_dict(payload: dict[str, Any]) -> "Module":
        legacy_interfaces = payload.get("interfaces", {})
        raw_inputs = payload.get("inputs")
        raw_outputs = payload.get("outputs")
        if raw_inputs is None:
            raw_inputs = legacy_interfaces.get("inputs", [])
        if raw_outputs is None:
            raw_outputs = legacy_interfaces.get("outputs", [])
        return Module(
            module_id=payload["module_id"],
            name=payload["name"],
            inputs=[Signal.from_dict(item) for item in raw_inputs],
            outputs=[Signal.from_dict(item) for item in raw_outputs],
            nodes=payload.get("nodes", []),
            edges=payload.get("edges", []),
            flow=payload.get("flow", []),
            submodules=[Module.from_dict(item) for item in payload.get("submodules", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        inputs = [item.to_dict() for item in self.inputs]
        outputs = [item.to_dict() for item in self.outputs]
        return {
            "module_id": self.module_id,
            "name": self.name,
            "inputs": inputs,
            "outputs": outputs,
            "nodes": self.nodes,
            "edges": self.edges,
            "flow": self.flow,
            "submodules": [item.to_dict() for item in self.submodules],
            "interfaces": {
                "inputs": [item["name"] for item in inputs],
                "outputs": [item["name"] for item in outputs],
            },
        }
