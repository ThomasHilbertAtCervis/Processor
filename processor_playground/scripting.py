from __future__ import annotations

import ast
from typing import Any


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
            if len(node.targets) != 1:
                raise SafeScriptError("Only single-target assignments are supported")
            value = self._evaluate(node.value)
            target = node.targets[0]
            if isinstance(target, ast.Name):
                self.env[target.id] = value
                return
            if isinstance(target, ast.Subscript):
                container = self._evaluate(target.value)
                index = self._evaluate(target.slice)
                container[index] = value
                return
            raise SafeScriptError("Only variable or subscript assignments are supported")
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
        if isinstance(node, ast.BinOp):
            left = self._evaluate(node.left)
            right = self._evaluate(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            raise SafeScriptError(f"Unsupported binary operator: {type(node.op).__name__}")
        if isinstance(node, ast.Call):
            fn = self._evaluate(node.func)
            if not callable(fn):
                raise SafeScriptError("Attempted to call a non-callable value")
            args = [self._evaluate(arg) for arg in node.args]
            kwargs = {}
            for kw in node.keywords:
                if kw.arg is None:
                    raise SafeScriptError("Keyword unpacking is not supported")
                kwargs[kw.arg] = self._evaluate(kw.value)
            return fn(*args, **kwargs)
        raise SafeScriptError(f"Unsupported expression: {type(node).__name__}")
