"""Catalog of the executable node kinds (v2 wire-based model).

Under the v2 data-flow model every node is just a vertex with typed input
and output ports. The built-in kinds are:

* ``module_input``  — a source for one of the module's declared input signals;
* ``module_output`` — a sink for one of the module's declared output signals;
* ``python``        — runs a user-supplied safe Python script that reads
                      ``inputs[port_name]`` and writes ``outputs[port_name]``;
* ``submodule``     — embeds another module, mapping the parent's port
                      activations into the submodule's module_input / output
                      nodes by name;
* ``db_read`` / ``db_create`` — query / insert against a global database;
* ``branch``        — routes its ``value`` input down ``true`` or ``false``
                      based on a static ``condition`` Python expression
                      stored on the node;
* ``join``          — merges several inputs into one ``value`` output
                      (first arrival wins; fires once per arrival);
* ``counted_loop``  — iterates ``from..to`` (exclusive); fires ``index``
                      per iteration, then ``done``;
* ``foreach``       — iterates an array or dict; fires ``item`` + ``key``
                      per element, then ``done``.

The Python node still supports inline ``if``/``for``/``foreach`` for one-off
expressions; the dedicated branch/loop nodes exist so non-trivial control
flow (sub-module calls, db nodes, multi-step pipelines per iteration) can
live in the wire graph instead of being hidden inside a script.

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
    NodeKind("db_read",       "▤ DB Read",       "DB Read"),
    NodeKind("db_create",     "▥ DB Create",     "DB Create"),
    NodeKind("branch",        "◆ Branch",        "Branch"),
    NodeKind("join",          "◇ Join",          "Join"),
    NodeKind("counted_loop",  "↻ Counted Loop",  "Counted Loop"),
    NodeKind("foreach",       "⇄ For Each",      "For Each"),
)


def list_node_kinds() -> list[NodeKind]:
    return list(_NODE_KINDS)
