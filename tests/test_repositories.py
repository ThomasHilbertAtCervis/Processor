"""Tests for the persistence layer (v2 schema)."""
from __future__ import annotations

from pathlib import Path

import pytest

from processor_playground.data_type_repository import DataTypeRepository
from processor_playground.models import (
    DataType,
    DataTypeField,
    Edge,
    Module,
    Node,
    Port,
    Signal,
)
from processor_playground.repository import ModuleRepository


# --------------------------------------------------------- ModuleRepository

class TestModuleRepository:
    def test_creates_storage_directory(self, tmp_path: Path) -> None:
        target = tmp_path / "does-not-exist-yet"
        ModuleRepository(target)
        assert target.is_dir()

    def test_save_then_get(self, tmp_path: Path) -> None:
        repo = ModuleRepository(tmp_path)
        module = Module(
            module_id="root",
            name="Root",
            inputs=[Signal("a", "string")],
            outputs=[Signal("b", "bool")],
            nodes=[
                Node(id="i", type="module_input", outputs=[Port("v")],
                     data={"signal_name": "a"}),
                Node(id="o", type="module_output", inputs=[Port("v")],
                     data={"signal_name": "b"}),
            ],
            edges=[Edge(id="e", source="i", source_handle="v",
                        target="o", target_handle="v")],
            submodules=[Module(module_id="child", name="Child")],
        )
        repo.save(module)

        loaded = repo.get("root")
        assert loaded is not None
        assert loaded.module_id == "root"
        assert loaded.nodes[0].type == "module_input"
        assert loaded.edges[0].source_handle == "v"
        assert loaded.submodules[0].module_id == "child"

    def test_get_missing_returns_none(self, tmp_path: Path) -> None:
        assert ModuleRepository(tmp_path).get("missing") is None

    def test_list_is_sorted_by_filename(self, tmp_path: Path) -> None:
        repo = ModuleRepository(tmp_path)
        repo.save(Module(module_id="zeta", name="Z"))
        repo.save(Module(module_id="alpha", name="A"))
        repo.save(Module(module_id="mid", name="M"))
        assert [m.module_id for m in repo.list()] == ["alpha", "mid", "zeta"]

    def test_rejects_legacy_v1_file_on_load(self, tmp_path: Path) -> None:
        # Any v1 file present must surface loudly — there is no automatic
        # migration; the storage format is reset on the v2 cut-over.
        (tmp_path / "legacy.json").write_text(
            '{"module_id": "legacy", "name": "Legacy", "flow": []}',
            encoding="utf-8",
        )
        repo = ModuleRepository(tmp_path)
        with pytest.raises(ValueError, match="format v1 'flow'"):
            repo.get("legacy")

    def test_delete_returns_true_then_false(self, tmp_path: Path) -> None:
        repo = ModuleRepository(tmp_path)
        repo.save(Module(module_id="root", name="Root"))
        assert repo.delete("root") is True
        assert repo.get("root") is None
        assert repo.delete("root") is False


# ------------------------------------------------------- DataTypeRepository

class TestDataTypeRepository:
    def test_save_get_list_delete(self, tmp_path: Path) -> None:
        repo = DataTypeRepository(tmp_path)
        repo.save(
            DataType(
                type_id="ShipmentEvent",
                name="Shipment Event",
                fields=[DataTypeField(name="location", type_ref="string")],
            )
        )
        loaded = repo.get("ShipmentEvent")
        assert loaded is not None
        assert loaded.fields[0].name == "location"
        assert [t.type_id for t in repo.list()] == ["ShipmentEvent"]
        assert repo.delete("ShipmentEvent") is True
        assert repo.list() == []
        assert repo.delete("ShipmentEvent") is False

    def test_array_kind_round_trip(self, tmp_path: Path) -> None:
        repo = DataTypeRepository(tmp_path)
        repo.save(DataType(type_id="Bag", name="Bag", kind="array", element_type="string"))
        loaded = repo.get("Bag")
        assert loaded is not None
        assert loaded.kind == "array"
        assert loaded.element_type == "string"


# ------------------------------------------------------- DatabaseRepository

from processor_playground.database_repository import DatabaseRepository
from processor_playground.models import Database


class TestDatabaseRepository:
    def test_creates_storage_directory(self, tmp_path: Path) -> None:
        target = tmp_path / "dbs"
        DatabaseRepository(target)
        assert target.is_dir()

    def test_round_trip(self, tmp_path: Path) -> None:
        repo = DatabaseRepository(tmp_path)
        repo.save(
            Database(
                name="shop",
                tables={
                    "customer": [{"id": 1, "name": "Alice"}],
                    "order": [],
                },
            )
        )
        loaded = repo.get("shop")
        assert loaded is not None
        assert loaded.name == "shop"
        assert loaded.tables == {
            "customer": [{"id": 1, "name": "Alice"}],
            "order": [],
        }

    def test_list_and_delete(self, tmp_path: Path) -> None:
        repo = DatabaseRepository(tmp_path)
        repo.save(Database(name="a"))
        repo.save(Database(name="b"))
        assert sorted(db.name for db in repo.list()) == ["a", "b"]
        assert repo.delete("a") is True
        assert [db.name for db in repo.list()] == ["b"]
        assert repo.delete("a") is False
