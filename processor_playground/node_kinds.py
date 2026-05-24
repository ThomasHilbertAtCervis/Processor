"""Domain catalog of the diagram node kinds.

The set of node kinds (Start, Event Trigger, Condition, …) and their
human-readable presentation defaults are **domain knowledge** — they describe
*what kinds of building blocks a process is made of*. They are therefore
served by the backend so every client (the React UI today, the future MCP
server, and any other consumer) sees the same catalog.

See ``ARCHITECTURE.md`` ("Backend is the sole source of truth") and
``PRODUCT.md`` §2 ("The eight node kinds").
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NodeKind:
    """One entry in the node-kind catalog."""

    type: str
    """Stable identifier used in stored module JSON (e.g. ``"foreach"``)."""

    palette_label: str
    """Label shown in the palette, with its glyph (e.g. ``"‖ For Each"``)."""

    default_label: str
    """Initial ``data.label`` for a freshly placed node of this kind."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "palette_label": self.palette_label,
            "default_label": self.default_label,
        }


# Order matters: this is the order the palette renders.
_NODE_KINDS: tuple[NodeKind, ...] = (
    NodeKind("start",       "● Start",                 "Start"),
    NodeKind("event",       "▷ Event Trigger",         "Event Trigger"),
    NodeKind("condition",   "□ Condition / Action",    "Condition"),
    NodeKind("foreach",     "‖ For Each",              "foreach"),
    NodeKind("submodule",   "⊞ Sub-module",            "Sub-module"),
    NodeKind("emit",        "▶ Emit Event",            "Emit Event"),
    NodeKind("datamapping", "⇄ Data Mapping",          "Data Mapping"),
    NodeKind("end",         "◉ End",                   "End"),
)


def list_node_kinds() -> list[NodeKind]:
    """Return the full catalog in palette order."""
    return list(_NODE_KINDS)
