from __future__ import annotations

import json
from pathlib import Path

from .models import Module


class ModuleRepository:
    def __init__(self, base_path: Path) -> None:
        self.base_path = base_path
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _path(self, module_id: str) -> Path:
        return self.base_path / f"{module_id}.json"

    def save(self, module: Module) -> Module:
        self._path(module.module_id).write_text(
            json.dumps(module.to_dict(), indent=2), encoding="utf-8"
        )
        return module

    def get(self, module_id: str) -> Module | None:
        target = self._path(module_id)
        if not target.exists():
            return None
        return Module.from_dict(json.loads(target.read_text(encoding="utf-8")))

    def list(self) -> list[Module]:
        modules = []
        for item in sorted(self.base_path.glob("*.json")):
            modules.append(Module.from_dict(json.loads(item.read_text(encoding="utf-8"))))
        return modules
