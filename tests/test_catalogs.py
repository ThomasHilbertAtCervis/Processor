"""Domain catalogs served by the backend so every client (UI, MCP) shares them."""
from __future__ import annotations

from processor_playground.node_kinds import list_node_kinds
from processor_playground.primitives import list_primitive_type_ids


def test_node_kinds_catalog_has_all_eight_kinds_in_palette_order() -> None:
    kinds = list_node_kinds()
    assert [k.type for k in kinds] == [
        "start", "event", "condition", "foreach",
        "submodule", "emit", "datamapping", "end",
    ]


def test_each_node_kind_has_palette_and_default_label() -> None:
    for kind in list_node_kinds():
        assert kind.palette_label.strip(), f"missing palette_label for {kind.type}"
        assert kind.default_label.strip(), f"missing default_label for {kind.type}"


def test_node_kind_to_dict_is_serialisable() -> None:
    entry = list_node_kinds()[0].to_dict()
    assert set(entry) == {"type", "palette_label", "default_label"}


def test_primitive_type_ids_are_stable() -> None:
    # PRODUCT.md §2 promises: int, decimal, string, bool, timestamp, any.
    assert list_primitive_type_ids() == [
        "int", "decimal", "string", "bool", "timestamp", "any",
    ]
