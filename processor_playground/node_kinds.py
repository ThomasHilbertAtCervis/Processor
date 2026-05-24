"""Catalog of the executable node kinds (v2 wire-based model).

Under the v2 data-flow model every node is just a vertex with typed input
and output ports. Four built-in kinds are sufficient to model any process:

* ``module_input``  — a source for one of the module's declared input signals;
* ``module_output`` — a sink for one of the module's declared output signals;
* ``python``        — runs a user-supplied safe Python script that reads
                      ``inputs[port_name]`` and writes ``outputs[port_name]``;
* ``submodule``     — embeds another module, mapping the parent's port
                      activations into the submodule's module_input / output
                      nodes by name.

Visual-only kinds from earlier iterations (start / event / condition / …)
are gone with the v1 ``flow`` step list — any branching, looping or mapping
is expressed inside a Python node now.

See ``ARCHITECTURE.md`` ("Backend is the sole source of truth") and
``PRODUCT.md`` §2.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NodeKind:
    """One entry in the node-kind catalog."""

    type: str
    palette_label: str
    default_label: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "palette_label": self.palette_label,
            "default_label": self.default_label,
        }


# Order matters: this is the order the palette renders.
_NODE_KINDS: tuple[NodeKind, ...] = (
    NodeKind("module_input",  "▷ Module Input",  "Input"),
    NodeKind("module_output", "◉ Module Output", "Output"),
    NodeKind("python",        "λ Python",        "Python"),
    NodeKind("submodule",     "⊞ Sub-module",    "Sub-module"),
)


def list_node_kinds() -> list[NodeKind]:
    return list(_NODE_KINDS)
