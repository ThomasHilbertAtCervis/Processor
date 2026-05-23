from __future__ import annotations

from typing import Any

from .repository import ModuleRepository
from .simulator import Simulator


class ScriptTestRunner:
    def __init__(self, repository: ModuleRepository, simulator: Simulator) -> None:
        self.repository = repository
        self.simulator = simulator

    def run(self, script: str) -> dict[str, Any]:
        report: dict[str, Any] = {"assertions": 0, "status": "passed", "errors": []}

        def load_module(module_id: str):
            module = self.repository.get(module_id)
            if module is None:
                raise ValueError(f"Module '{module_id}' does not exist")
            return module

        def run_module(module_id: str, input_data=None, mocks=None):
            module = load_module(module_id)
            return self.simulator.run(module, input_data=input_data, mocks=mocks)

        def assert_equal(actual, expected, message: str = ""):
            report["assertions"] += 1
            if actual != expected:
                raise AssertionError(message or f"Expected {expected!r}, got {actual!r}")

        safe_builtins = {
            "len": len,
            "range": range,
            "min": min,
            "max": max,
            "sum": sum,
            "print": print,
        }
        local_env = {
            "load_module": load_module,
            "run_module": run_module,
            "assert_equal": assert_equal,
            "result": None,
        }
        try:
            exec(script, {"__builtins__": safe_builtins}, local_env)
            return report
        except Exception as exc:  # noqa: BLE001
            report["status"] = "failed"
            report["errors"].append(str(exc))
            return report
