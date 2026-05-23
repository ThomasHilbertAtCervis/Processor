"""Round-trip and legacy-format tests for the domain models.

Concern: keep the wire format stable so that older module JSON on disk
continues to load and so that the UI keeps seeing the legacy `interfaces`
shorthand it depends on.
"""
from __future__ import annotations

from processor_playground.models import DataType, DataTypeField, Module, Signal


# ----------------------------------------------------------------- Signal

class TestSignal:
    def test_from_string_uses_any_type(self) -> None:
        signal = Signal.from_dict("shipment")
        assert signal.name == "shipment"
        assert signal.type_ref == "any"
        assert signal.filter is None

    def test_from_dict_full(self) -> None:
        signal = Signal.from_dict({"name": "in", "type_ref": "Event", "filter": "x>0"})
        assert signal.name == "in"
        assert signal.type_ref == "Event"
        assert signal.filter == "x>0"

    def test_to_dict_omits_empty_filter(self) -> None:
        assert "filter" not in Signal(name="x").to_dict()

    def test_to_dict_includes_filter(self) -> None:
        assert Signal(name="x", filter="ok").to_dict()["filter"] == "ok"


# ------------------------------------------------------------- DataTypeField

class TestDataTypeField:
    def test_round_trip(self) -> None:
        original = DataTypeField(name="age", type_ref="int")
        assert DataTypeField.from_dict(original.to_dict()) == original

    def test_defaults_to_any(self) -> None:
        assert DataTypeField.from_dict({"name": "x"}).type_ref == "any"


# ----------------------------------------------------------------- DataType

class TestDataType:
    def test_struct_round_trip(self) -> None:
        original = DataType(
            type_id="Shipment",
            name="Shipment",
            kind="struct",
            fields=[DataTypeField("location", "string"), DataTypeField("count", "int")],
        )
        restored = DataType.from_dict(original.to_dict())
        assert restored == original

    def test_array_round_trip(self) -> None:
        original = DataType(type_id="Bag", name="Bag", kind="array", element_type="string")
        restored = DataType.from_dict(original.to_dict())
        assert restored.kind == "array"
        assert restored.element_type == "string"
        assert restored.fields == []

    def test_dict_round_trip(self) -> None:
        original = DataType(type_id="Map", name="Map", kind="dict", element_type="int")
        assert DataType.from_dict(original.to_dict()) == original


# ------------------------------------------------------------------- Module

class TestModule:
    def test_round_trip_preserves_shape(self) -> None:
        module = Module(
            module_id="m",
            name="M",
            inputs=[Signal("a", "string")],
            outputs=[Signal("b")],
            nodes=[{"id": "n1", "type": "start"}],
            edges=[{"id": "e1", "source": "n1", "target": "n2"}],
            flow=[{"type": "emit", "payload": 1}],
            submodules=[Module(module_id="child", name="Child")],
        )
        restored = Module.from_dict(module.to_dict())
        assert restored.module_id == "m"
        assert restored.inputs[0].type_ref == "string"
        assert restored.outputs[0].name == "b"
        assert restored.nodes[0]["type"] == "start"
        assert restored.submodules[0].module_id == "child"

    def test_legacy_interfaces_are_lifted_into_signals(self) -> None:
        """Modules saved before the inputs/outputs split must still load."""
        module = Module.from_dict(
            {
                "module_id": "legacy",
                "name": "Legacy",
                "interfaces": {"inputs": ["incoming"], "outputs": ["done"]},
                "flow": [],
                "submodules": [],
            }
        )
        assert [s.name for s in module.inputs] == ["incoming"]
        assert [s.name for s in module.outputs] == ["done"]

    def test_to_dict_always_emits_legacy_interfaces_block(self) -> None:
        """Frontend code still reads `interfaces` — don't drop it silently."""
        module = Module(
            module_id="m",
            name="M",
            inputs=[Signal("in", "Event")],
            outputs=[Signal("out")],
        )
        payload = module.to_dict()
        assert payload["interfaces"] == {"inputs": ["in"], "outputs": ["out"]}
        assert payload["inputs"][0]["type_ref"] == "Event"

    def test_explicit_inputs_override_legacy_interfaces(self) -> None:
        module = Module.from_dict(
            {
                "module_id": "m",
                "name": "M",
                "inputs": [{"name": "new"}],
                "interfaces": {"inputs": ["old"], "outputs": []},
            }
        )
        assert [s.name for s in module.inputs] == ["new"]
