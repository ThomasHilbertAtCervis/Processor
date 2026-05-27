"""Round-trip + rejection tests for the v2 domain models."""
from __future__ import annotations

import pytest

from processor_playground.models import (
    DataType,
    DataTypeField,
    Edge,
    Module,
    Node,
    Port,
    Signal,
)


class TestSignal:
    def test_from_string_uses_any_type(self) -> None:
        signal = Signal.from_dict("shipment")
        assert signal.name == "shipment"
        assert signal.type_ref == "any"

    def test_from_dict_full(self) -> None:
        signal = Signal.from_dict({"name": "in", "type_ref": "Event", "filter": "x>0"})
        assert signal.name == "in"
        assert signal.type_ref == "Event"
        assert signal.filter == "x>0"

    def test_to_dict_omits_empty_filter(self) -> None:
        assert "filter" not in Signal(name="x").to_dict()


class TestDataTypeField:
    def test_round_trip(self) -> None:
        original = DataTypeField(name="age", type_ref="int")
        assert DataTypeField.from_dict(original.to_dict()) == original

    def test_defaults_to_any(self) -> None:
        assert DataTypeField.from_dict({"name": "x"}).type_ref == "any"

    def test_array_field_round_trip(self) -> None:
        original = DataTypeField(name="items", type_ref="Item", kind="array")
        restored = DataTypeField.from_dict(original.to_dict())
        assert restored.name == "items"
        assert restored.type_ref == "Item"
        assert restored.kind == "array"

    def test_dict_field_round_trip(self) -> None:
        original = DataTypeField(name="lookup", type_ref="string", kind="dict")
        restored = DataTypeField.from_dict(original.to_dict())
        assert restored.name == "lookup"
        assert restored.type_ref == "string"
        assert restored.kind == "dict"

    def test_to_dict_omits_primitive_kind(self) -> None:
        # Primitive is the default; omit it to keep payloads smaller
        field = DataTypeField(name="x", type_ref="int", kind="primitive")
        assert "kind" not in field.to_dict()

    def test_to_dict_includes_nonprimitive_kind(self) -> None:
        field = DataTypeField(name="x", type_ref="Item", kind="array")
        assert field.to_dict()["kind"] == "array"


class TestDataType:
    def test_struct_round_trip(self) -> None:
        original = DataType(
            type_id="Shipment",
            name="Shipment",
            kind="struct",
            fields=[DataTypeField("location", "string")],
        )
        assert DataType.from_dict(original.to_dict()) == original

    def test_struct_with_compound_fields_round_trip(self) -> None:
        original = DataType(
            type_id="Order",
            name="Order",
            kind="struct",
            fields=[
                DataTypeField("items", "Item", kind="array"),
                DataTypeField("metadata", "string", kind="dict"),
                DataTypeField("customer", "Customer", kind="primitive"),
            ],
        )
        restored = DataType.from_dict(original.to_dict())
        assert restored.type_id == "Order"
        assert len(restored.fields) == 3
        assert restored.fields[0].name == "items"
        assert restored.fields[0].type_ref == "Item"
        assert restored.fields[0].kind == "array"
        assert restored.fields[1].name == "metadata"
        assert restored.fields[1].kind == "dict"
        assert restored.fields[2].kind == "primitive"

    def test_array_round_trip(self) -> None:
        original = DataType(type_id="Bag", name="Bag", kind="array", element_type="string")
        restored = DataType.from_dict(original.to_dict())
        assert restored.kind == "array"
        assert restored.element_type == "string"
        assert restored.fields == []

    def test_struct_payload_drops_stray_element_type(self) -> None:
        result = DataType.from_dict({
            "type_id": "S", "name": "S", "kind": "struct",
            "fields": [{"name": "x", "type_ref": "int"}],
            "element_type": "ignored",
        })
        assert result.element_type is None

    def test_array_payload_drops_stray_fields_and_defaults_element_type(self) -> None:
        result = DataType.from_dict({
            "type_id": "A", "name": "A", "kind": "array",
            "fields": [{"name": "ghost", "type_ref": "int"}],
        })
        assert result.fields == []
        assert result.element_type == "any"


class TestPort:
    def test_defaults(self) -> None:
        port = Port.from_dict({"name": "value"})
        assert port.type_ref == "any"
        assert port.kind == "data"
        assert port.pair is None

    def test_request_port_round_trip(self) -> None:
        port = Port(name="ask", type_ref="string", kind="request", pair="answer")
        restored = Port.from_dict(port.to_dict())
        assert restored == port

    def test_to_dict_omits_pair_when_unset(self) -> None:
        assert "pair" not in Port(name="x").to_dict()


class TestNode:
    def test_round_trip(self) -> None:
        node = Node(
            id="n1",
            type="python",
            inputs=[Port("value", "int")],
            outputs=[Port("doubled", "int")],
            data={"code": "outputs['doubled'] = inputs['value'] * 2"},
            position={"x": 120.0, "y": -40.0},
        )
        restored = Node.from_dict(node.to_dict())
        assert restored == node

    def test_position_defaults_to_origin_when_missing(self) -> None:
        # Older payloads (and demo scripts that don't bother laying out the
        # canvas) omit ``position``; the model fills in (0, 0) so ReactFlow
        # doesn't crash on first paint.
        node = Node.from_dict({"id": "n", "type": "python"})
        assert node.position == {"x": 0.0, "y": 0.0}
        assert node.to_dict()["position"] == {"x": 0.0, "y": 0.0}


class TestEdge:
    def test_round_trip(self) -> None:
        edge = Edge(
            id="e1", source="a", source_handle="out",
            target="b", target_handle="in",
        )
        restored = Edge.from_dict(edge.to_dict())
        assert restored == edge

    def test_accepts_reactflow_camelcase_handles(self) -> None:
        edge = Edge.from_dict({
            "id": "e1", "source": "a", "sourceHandle": "out",
            "target": "b", "targetHandle": "in",
        })
        assert edge.source_handle == "out"
        assert edge.target_handle == "in"

    def test_emits_both_handle_aliases(self) -> None:
        edge = Edge(id="e1", source="a", source_handle="o",
                   target="b", target_handle="i")
        payload = edge.to_dict()
        assert payload["source_handle"] == payload["sourceHandle"] == "o"
        assert payload["target_handle"] == payload["targetHandle"] == "i"


class TestModule:
    def test_round_trip_preserves_graph(self) -> None:
        # ``Module.inputs``/``outputs`` are derived from the
        # ``module_input``/``module_output`` nodes — the port's ``type_ref``
        # is the signal's type. So the explicit Signal lists passed to the
        # constructor are ignored on round-trip; what matters is the canvas.
        module = Module(
            module_id="m",
            name="M",
            nodes=[
                Node(id="i", type="module_input",
                     outputs=[Port("v", type_ref="string")],
                     data={"signal_name": "a"}),
                Node(id="o", type="module_output",
                     inputs=[Port("v", type_ref="int")],
                     data={"signal_name": "b"}),
            ],
            edges=[Edge(id="e", source="i", source_handle="v",
                        target="o", target_handle="v")],
            submodules=[Module(module_id="child", name="Child")],
        )
        restored = Module.from_dict(module.to_dict())
        assert restored.inputs == [Signal("a", "string")]
        assert restored.outputs == [Signal("b", "int")]
        assert restored.nodes == module.nodes
        assert restored.edges == module.edges

    def test_rejects_legacy_flow_field(self) -> None:
        with pytest.raises(ValueError, match="format v1 'flow'"):
            Module.from_dict({
                "module_id": "old", "name": "Old", "flow": [],
            })

    def test_rejects_legacy_interfaces_field(self) -> None:
        with pytest.raises(ValueError, match="format v1 'interfaces'"):
            Module.from_dict({
                "module_id": "old", "name": "Old",
                "interfaces": {"inputs": [], "outputs": []},
            })

    def test_to_dict_does_not_emit_legacy_interfaces_mirror(self) -> None:
        payload = Module(
            module_id="m", name="M",
            inputs=[Signal("in")], outputs=[Signal("out")],
        ).to_dict()
        assert "interfaces" not in payload
        assert "flow" not in payload
