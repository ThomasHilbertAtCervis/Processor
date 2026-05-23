from __future__ import annotations

import json
from pathlib import Path

from .models import DataType


class DataTypeRepository:
    def __init__(self, base_path: Path) -> None:
        self.base_path = base_path
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _path(self, type_id: str) -> Path:
        return self.base_path / f"{type_id}.json"

    def save(self, data_type: DataType) -> DataType:
        self._path(data_type.type_id).write_text(
            json.dumps(data_type.to_dict(), indent=2), encoding="utf-8"
        )
        return data_type

    def get(self, type_id: str) -> DataType | None:
        target = self._path(type_id)
        if not target.exists():
            return None
        return DataType.from_dict(json.loads(target.read_text(encoding="utf-8")))

    def list(self) -> list[DataType]:
        types = []
        for item in sorted(self.base_path.glob("*.json")):
            types.append(DataType.from_dict(json.loads(item.read_text(encoding="utf-8"))))
        return types

    def delete(self, type_id: str) -> bool:
        target = self._path(type_id)
        if target.exists():
            target.unlink()
            return True
        return False
