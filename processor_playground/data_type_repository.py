"""Persistence for :class:`DataType` objects.

Thin subclass of :class:`JsonRepository` — see ARCHITECTURE.md.
"""
from __future__ import annotations

from pathlib import Path

from ._json_repository import JsonRepository
from .models import DataType


class DataTypeRepository(JsonRepository[DataType]):
    def __init__(self, base_path: Path) -> None:
        super().__init__(
            base_path,
            from_dict=DataType.from_dict,
            to_dict=DataType.to_dict,
            id_attr="type_id",
        )
