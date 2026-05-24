"""Persistence for :class:`Database` objects.

Thin subclass of :class:`JsonRepository` — see ARCHITECTURE.md. Each
database is stored as ``storage/databases/{name}.json``.
"""
from __future__ import annotations

from pathlib import Path

from ._json_repository import JsonRepository
from .models import Database


class DatabaseRepository(JsonRepository[Database]):
    def __init__(self, base_path: Path) -> None:
        super().__init__(
            base_path,
            from_dict=Database.from_dict,
            to_dict=Database.to_dict,
            id_attr="name",
        )
