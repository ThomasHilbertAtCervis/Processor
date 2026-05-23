from pathlib import Path

from processor_playground.models import Module
from processor_playground.repository import ModuleRepository


def test_save_and_get_module(tmp_path: Path) -> None:
    repo = ModuleRepository(tmp_path)
    module = Module(
        module_id="root",
        name="Root",
        interfaces={"inputs": ["a"], "outputs": ["b"]},
        flow=[{"type": "set_var", "name": "x", "value": 1}],
        submodules=[Module(module_id="child", name="Child", flow=[{"type": "emit", "payload": "ok"}])],
    )

    repo.save(module)
    loaded = repo.get("root")

    assert loaded is not None
    assert loaded.module_id == "root"
    assert loaded.submodules[0].module_id == "child"
