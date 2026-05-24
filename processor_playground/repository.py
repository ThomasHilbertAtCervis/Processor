"""Persistence for :class:`Module` objects.

Thin subclass of :class:`JsonRepository` — see ARCHITECTURE.md for why nothing
beyond binding the entity type belongs here.
"""
from __future__ import annotations

from pathlib import Path

from ._json_repository import JsonRepository
from .models import Module


class ModuleRepository(JsonRepository[Module]):
    def __init__(self, base_path: Path) -> None:
        super().__init__(
            base_path,
            from_dict=Module.from_dict,
            to_dict=Module.to_dict,
            id_attr="module_id",
        )
