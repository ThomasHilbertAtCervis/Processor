from processor_playground.models import Module
from processor_playground.simulator import Simulator


def test_run_module_with_submodule_mock_interface() -> None:
    child = Module(module_id="db-module", name="DB", flow=[{"type": "emit", "payload": {"rows": 99}}])
    parent = Module(
        module_id="parent",
        name="Parent",
        flow=[
            {"type": "set_var", "name": "status", "value": "start"},
            {"type": "run_submodule", "module_id": "db-module", "interface": "database"},
            {"type": "emit", "payload": {"done": True}},
        ],
        submodules=[child],
    )

    run = Simulator().run(parent, mocks={"database": {"rows": 3}})

    assert run["events"][0]["mocked_interface"] == "database"
    assert run["events"][0]["response"] == {"rows": 3}
    assert run["outputs"][-1] == {"done": True}


def test_run_python_step() -> None:
    module = Module(
        module_id="python-step",
        name="Python Step",
        flow=[
            {"type": "set_var", "name": "a", "value": 2},
            {"type": "python", "code": "variables['b'] = variables['a'] + 3\nresult = variables['b']"},
        ],
    )

    run = Simulator().run(module)

    assert run["result"] == 5
    assert run["variables"]["b"] == 5
