from pathlib import Path

from processor_playground.models import Module, Signal
from processor_playground.repository import ModuleRepository


def test_save_and_get_module(tmp_path: Path) -> None:
    repo = ModuleRepository(tmp_path)
    module = Module(
        module_id="root",
        name="Root",
        inputs=[Signal(name="a", type_ref="string")],
        outputs=[Signal(name="b", type_ref="bool")],
        nodes=[{"id": "n1", "type": "start", "position": {"x": 0, "y": 0}, "data": {"label": "Start"}}],
        edges=[],
        flow=[{"type": "set_var", "name": "x", "value": 1}],
        submodules=[Module(module_id="child", name="Child", flow=[{"type": "emit", "payload": "ok"}])],
    )

    repo.save(module)
    loaded = repo.get("root")

    assert loaded is not None
    assert loaded.module_id == "root"
    assert loaded.nodes[0]["type"] == "start"
    assert loaded.submodules[0].module_id == "child"


def test_load_legacy_module_interfaces(tmp_path: Path) -> None:
    repo = ModuleRepository(tmp_path)
    repo._path("legacy").write_text(
        '{\n'
        '  "module_id": "legacy",\n'
        '  "name": "Legacy",\n'
        '  "interfaces": {"inputs": ["incoming"], "outputs": ["done"]},\n'
        '  "flow": [],\n'
        '  "submodules": []\n'
        '}',
        encoding="utf-8",
    )

    loaded = repo.get("legacy")

    assert loaded is not None
    assert loaded.inputs[0].name == "incoming"
    assert loaded.outputs[0].name == "done"


def test_delete_module(tmp_path: Path) -> None:
    repo = ModuleRepository(tmp_path)
    repo.save(Module(module_id="root", name="Root"))

    assert repo.delete("root") is True
    assert repo.get("root") is None
    assert repo.delete("root") is False
