from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Module:
    module_id: str
    name: str
    interfaces: dict[str, list[str]] = field(
        default_factory=lambda: {"inputs": [], "outputs": []}
    )
    flow: list[dict[str, Any]] = field(default_factory=list)
    submodules: list["Module"] = field(default_factory=list)

    @staticmethod
    def from_dict(payload: dict[str, Any]) -> "Module":
        return Module(
            module_id=payload["module_id"],
            name=payload["name"],
            interfaces=payload.get("interfaces", {"inputs": [], "outputs": []}),
            flow=payload.get("flow", []),
            submodules=[Module.from_dict(m) for m in payload.get("submodules", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "module_id": self.module_id,
            "name": self.name,
            "interfaces": self.interfaces,
            "flow": self.flow,
            "submodules": [m.to_dict() for m in self.submodules],
        }
