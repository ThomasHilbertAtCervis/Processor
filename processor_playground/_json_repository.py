"""Generic JSON file repository.

This is the **only** place in the package that knows how a domain object is
turned into a file on disk. Concrete repositories (modules, data types) are
three-line subclasses that bind the entity type and the id attribute.

See ARCHITECTURE.md ("Repository layer") for the rules this module embodies.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Generic, TypeVar

T = TypeVar("T")


class JsonRepository(Generic[T]):
    """Persist a single kind of domain object as one JSON file per id.

    Subclasses provide ``from_dict``/``to_dict`` callables and the name of the
    id attribute on ``T``. Behavior (filenames, directory creation, atomic-ish
    writes, sorted listing) is implemented exactly once here so that every
    storable entity behaves identically.
    """

    def __init__(
        self,
        base_path: Path,
        *,
        from_dict: Callable[[dict[str, Any]], T],
        to_dict: Callable[[T], dict[str, Any]],
        id_attr: str,
    ) -> None:
        self.base_path = base_path
        self._from_dict = from_dict
        self._to_dict = to_dict
        self._id_attr = id_attr
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _path(self, entity_id: str) -> Path:
        return self.base_path / f"{entity_id}.json"

    def save(self, entity: T) -> T:
        entity_id = getattr(entity, self._id_attr)
        self._path(entity_id).write_text(
            json.dumps(self._to_dict(entity), indent=2), encoding="utf-8"
        )
        return entity

    def get(self, entity_id: str) -> T | None:
        target = self._path(entity_id)
        if not target.exists():
            return None
        return self._from_dict(json.loads(target.read_text(encoding="utf-8")))

    def list(self) -> list[T]:
        return [
            self._from_dict(json.loads(item.read_text(encoding="utf-8")))
            for item in sorted(self.base_path.glob("*.json"))
        ]

    def delete(self, entity_id: str) -> bool:
        target = self._path(entity_id)
        if target.exists():
            target.unlink()
            return True
        return False
