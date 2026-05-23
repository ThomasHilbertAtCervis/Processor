from processor_playground.models import Module
from processor_playground.repository import ModuleRepository
from processor_playground.simulator import Simulator
from processor_playground.testing import ScriptTestRunner


def test_python_script_test_runner(tmp_path) -> None:
    repo = ModuleRepository(tmp_path)
    repo.save(Module(module_id="m1", name="M1", flow=[{"type": "emit", "payload": {"ok": True}}]))

    runner = ScriptTestRunner(repo, Simulator())
    report = runner.run(
        """
result = run_module('m1')
assert_equal(result['outputs'][0]['ok'], True)
"""
    )

    assert report["status"] == "passed"
    assert report["assertions"] == 1
