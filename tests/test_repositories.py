"""Tests for the persistence layer.

Covers the generic :class:`JsonRepository` base and both concrete
repositories (modules, data types). The repositories must:

* round-trip values through disk,
* tolerate the directory not existing yet (auto-create),
* list entries deterministically (sorted by id),
* report deletion of unknown ids as ``False``.
"""
from __future__ import annotations

from pathlib import Path

from processor_playground.data_type_repository import DataTypeRepository
from processor_playground.models import DataType, DataTypeField, Module, Signal
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
            nodes=[{"id": "n1", "type": "start"}],
            flow=[{"type": "set_var", "name": "x", "value": 1}],
            submodules=[Module(module_id="child", name="Child")],
        )
        repo.save(module)

        loaded = repo.get("root")
        assert loaded is not None
        assert loaded.module_id == "root"
        assert loaded.nodes[0]["type"] == "start"
        assert loaded.submodules[0].module_id == "child"

    def test_get_missing_returns_none(self, tmp_path: Path) -> None:
        assert ModuleRepository(tmp_path).get("missing") is None

    def test_list_is_sorted_by_filename(self, tmp_path: Path) -> None:
        repo = ModuleRepository(tmp_path)
        repo.save(Module(module_id="zeta", name="Z"))
        repo.save(Module(module_id="alpha", name="A"))
        repo.save(Module(module_id="mid", name="M"))
        assert [m.module_id for m in repo.list()] == ["alpha", "mid", "zeta"]

    def test_list_loads_legacy_files(self, tmp_path: Path) -> None:
        repo = ModuleRepository(tmp_path)
        (tmp_path / "legacy.json").write_text(
            '{"module_id": "legacy", "name": "Legacy",'
            ' "interfaces": {"inputs": ["i"], "outputs": ["o"]},'
            ' "flow": [], "submodules": []}',
            encoding="utf-8",
        )
        loaded = repo.get("legacy")
        assert loaded is not None
        assert loaded.inputs[0].name == "i"

    def test_delete_returns_true_then_false(self, tmp_path: Path) -> None:
        repo = ModuleRepository(tmp_path)
        repo.save(Module(module_id="root", name="Root"))
        assert repo.delete("root") is True
        assert repo.get("root") is None
        assert repo.delete("root") is False

    def test_save_overwrites(self, tmp_path: Path) -> None:
        repo = ModuleRepository(tmp_path)
        repo.save(Module(module_id="m", name="First"))
        repo.save(Module(module_id="m", name="Second"))
        loaded = repo.get("m")
        assert loaded is not None and loaded.name == "Second"


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

    def test_get_missing_returns_none(self, tmp_path: Path) -> None:
        assert DataTypeRepository(tmp_path).get("nope") is None

    def test_array_kind_round_trip(self, tmp_path: Path) -> None:
        repo = DataTypeRepository(tmp_path)
        repo.save(DataType(type_id="Bag", name="Bag", kind="array", element_type="string"))
        loaded = repo.get("Bag")
        assert loaded is not None
        assert loaded.kind == "array"
        assert loaded.element_type == "string"
