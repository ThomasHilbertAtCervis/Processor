"""Primitive data-type identifiers.

The set of primitive types that can appear in a ``DataTypeField.type_ref`` is
domain knowledge and is served by the backend so every client sees the same
list (see ``ARCHITECTURE.md`` — "Backend is the sole source of truth").
"""
from __future__ import annotations


# Order matters: this is the order primitives are presented to humans in the
# data-type editor and to other agents when they enumerate type identifiers.
PRIMITIVE_TYPE_IDS: tuple[str, ...] = (
    "int",
    "decimal",
    "string",
    "bool",
    "timestamp",
    "any",
)


def list_primitive_type_ids() -> list[str]:
    return list(PRIMITIVE_TYPE_IDS)
