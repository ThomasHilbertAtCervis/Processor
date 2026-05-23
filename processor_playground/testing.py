from __future__ import annotations

import ast
from typing import Any

from .repository import ModuleRepository
from .simulator import Simulator


class SafeScriptError(ValueError):
    pass


class SafeScriptInterpreter:
    def __init__(self, env: dict[str, Any]) -> None:
        self.env = env

    def run(self, script: str) -> None:
        tree = ast.parse(script, mode="exec")
        for node in tree.body:
            self._execute_stmt(node)

    def _execute_stmt(self, node: ast.stmt) -> None:
        if isinstance(node, ast.Assign):
            if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                raise SafeScriptError("Only simple variable assignments are supported")
            self.env[node.targets[0].id] = self._evaluate(node.value)
            return
        if isinstance(node, ast.Expr):
            self._evaluate(node.value)
            return
        if isinstance(node, ast.Assert):
            if not self._evaluate(node.test):
                message = self._evaluate(node.msg) if node.msg else "Assertion failed"
                raise AssertionError(str(message))
            return
        raise SafeScriptError(f"Unsupported statement: {type(node).__name__}")

    def _evaluate(self, node: ast.AST) -> Any:
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id not in self.env:
                raise SafeScriptError(f"Unknown identifier: {node.id}")
            return self.env[node.id]
        if isinstance(node, ast.Dict):
            return {
                self._evaluate(key): self._evaluate(value)
                for key, value in zip(node.keys, node.values)
            }
        if isinstance(node, ast.List):
            return [self._evaluate(el) for el in node.elts]
        if isinstance(node, ast.Tuple):
            return tuple(self._evaluate(el) for el in node.elts)
        if isinstance(node, ast.Subscript):
            container = self._evaluate(node.value)
            index = self._evaluate(node.slice)
            return container[index]
        if isinstance(node, ast.Compare):
            if len(node.ops) != 1 or len(node.comparators) != 1:
                raise SafeScriptError("Only single comparisons are supported")
            left = self._evaluate(node.left)
            right = self._evaluate(node.comparators[0])
            op = node.ops[0]
            if isinstance(op, ast.Eq):
                return left == right
            if isinstance(op, ast.NotEq):
                return left != right
            if isinstance(op, ast.Gt):
                return left > right
            if isinstance(op, ast.GtE):
                return left >= right
            if isinstance(op, ast.Lt):
                return left < right
            if isinstance(op, ast.LtE):
                return left <= right
            raise SafeScriptError(f"Unsupported comparison operator: {type(op).__name__}")
        if isinstance(node, ast.Call):
            fn = self._evaluate(node.func)
            if not callable(fn):
                raise SafeScriptError("Attempted to call a non-callable value")
            args = [self._evaluate(arg) for arg in node.args]
            kwargs = {kw.arg: self._evaluate(kw.value) for kw in node.keywords if kw.arg}
            return fn(*args, **kwargs)
        raise SafeScriptError(f"Unsupported expression: {type(node).__name__}")


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
            local_env.update(safe_builtins)
            SafeScriptInterpreter(local_env).run(script)
            return report
        except Exception as exc:  # noqa: BLE001
            report["status"] = "failed"
            report["errors"].append(f"{type(exc).__name__}: {exc}")
            return report
