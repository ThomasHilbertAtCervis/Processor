"""A sandboxed safe interpreter for user-supplied Python snippets.

The interpreter is the security perimeter: every AST form is allow-listed by
explicit ``isinstance`` checks. There are two driving modes:

* :meth:`SafeScriptInterpreter.run` — fire-and-forget. Used by script tests
  (``ScriptTestRunner``) and any other caller that just wants the script to
  run from top to bottom. Writes to a port output (``outputs['x'] = ...``)
  are rejected.

* :meth:`SafeScriptInterpreter.iter_run` — generator mode. Used by the
  simulator's Python node activator. Every ``outputs[port_name] = value``
  statement yields a ``("fire", port_name, value)`` event. The driver
  performs the wire-side effects (delivering to receivers, handling
  request/response suspension) and then resumes the generator. Reads from
  ``inputs`` see whatever the driver has stashed there by the time the
  script next touches them — this is how a paired response is surfaced.
"""
from __future__ import annotations

import ast
from typing import Any, Iterator, Tuple


class SafeScriptError(ValueError):
    pass


# Yielded by ``iter_run`` whenever the script writes to a port output.
FireEvent = Tuple[str, str, Any]


class SafeScriptInterpreter:
    """A whitelisting AST walker."""

    # Variable name that the simulator binds to a node's output-port write
    # dictionary. Writes to ``outputs[port]`` become fire events; everything
    # else is treated as ordinary subscript assignment.
    OUTPUTS_BINDING = "outputs"

    def __init__(self, env: dict[str, Any]) -> None:
        self.env = env

    # ----------------------------------------------------------- public API

    def run(self, script: str) -> None:
        """Execute ``script`` to completion. Reject port-fire attempts."""
        for event in self.iter_run(script):
            kind = event[0]
            if kind == "fire":
                raise SafeScriptError(
                    "Output port writes require generator mode (iter_run); "
                    "they are not allowed in this context."
                )
            raise SafeScriptError(f"Unsupported script event: {kind!r}")

    def evaluate_expression(self, expression: str) -> Any:
        """Parse and evaluate a single Python expression against ``env``.

        Used by nodes that take an expression as a static parameter (e.g.
        the ``branch`` node's ``condition``). Same allow-list as the rest
        of the interpreter — comparisons, boolean ops, arithmetic,
        subscripting, ``len/range/min/max/sum`` — no statements, no
        attribute access, no imports.
        """
        try:
            tree = ast.parse(expression, mode="eval")
        except SyntaxError as exc:
            raise SafeScriptError(f"Invalid expression: {exc.msg}") from exc
        return self._evaluate(tree.body)

    def iter_run(self, script: str) -> Iterator[FireEvent]:
        """Execute ``script``, yielding a ``('fire', port, value)`` event
        on every ``outputs[port] = value`` statement.

        The yielded fire is processed by the driver before the script makes
        any further progress; ``send()`` values are ignored (responses are
        surfaced to the script via the shared ``env['inputs']`` dict, which
        the driver mutates between yield points).
        """
        tree = ast.parse(script, mode="exec")
        for stmt in tree.body:
            yield from self._iter_stmt(stmt)

    # ----------------------------------------------------- statement walker

    def _iter_stmt(self, node: ast.stmt) -> Iterator[FireEvent]:
        if isinstance(node, ast.Assign):
            yield from self._iter_assign(node)
            return
        if isinstance(node, ast.Expr):
            self._evaluate(node.value)
            return
        if isinstance(node, ast.Assert):
            if not self._evaluate(node.test):
                message = self._evaluate(node.msg) if node.msg else "Assertion failed"
                raise AssertionError(str(message))
            return
        if isinstance(node, ast.If):
            branch = node.body if self._evaluate(node.test) else node.orelse
            for stmt in branch:
                yield from self._iter_stmt(stmt)
            return
        if isinstance(node, ast.For):
            if not isinstance(node.target, ast.Name):
                raise SafeScriptError(
                    "Only single-name for-loop targets are supported"
                )
            if node.orelse:
                raise SafeScriptError("for/else is not supported")
            iterable = self._evaluate(node.iter)
            for value in iterable:
                self.env[node.target.id] = value
                for stmt in node.body:
                    yield from self._iter_stmt(stmt)
            return
        raise SafeScriptError(f"Unsupported statement: {type(node).__name__}")

    def _iter_assign(self, node: ast.Assign) -> Iterator[FireEvent]:
        if len(node.targets) != 1:
            raise SafeScriptError("Only single-target assignments are supported")
        target = node.targets[0]
        value = self._evaluate(node.value)
        if isinstance(target, ast.Name):
            self.env[target.id] = value
            return
        if isinstance(target, ast.Subscript):
            index = self._evaluate(target.slice)
            if (
                isinstance(target.value, ast.Name)
                and target.value.id == self.OUTPUTS_BINDING
            ):
                # The simulator's Python-node activator listens for this.
                # We still mirror the write into the local outputs dict so
                # the script can read back what it last produced.
                container = self._evaluate(target.value)
                container[index] = value
                yield ("fire", str(index), value)
                return
            container = self._evaluate(target.value)
            container[index] = value
            return
        raise SafeScriptError("Only variable or subscript assignments are supported")

    # ---------------------------------------------------- expression walker

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
            raise SafeScriptError(
                f"Unsupported comparison operator: {type(op).__name__}"
            )
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
            raise SafeScriptError(
                f"Unsupported binary operator: {type(node.op).__name__}"
            )
        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                result: Any = True
                for value in node.values:
                    result = self._evaluate(value)
                    if not result:
                        return result
                return result
            if isinstance(node.op, ast.Or):
                result = False
                for value in node.values:
                    result = self._evaluate(value)
                    if result:
                        return result
                return result
            raise SafeScriptError(
                f"Unsupported boolean operator: {type(node.op).__name__}"
            )
        if isinstance(node, ast.UnaryOp):
            operand = self._evaluate(node.operand)
            if isinstance(node.op, ast.Not):
                return not operand
            if isinstance(node.op, ast.USub):
                return -operand
            if isinstance(node.op, ast.UAdd):
                return +operand
            raise SafeScriptError(
                f"Unsupported unary operator: {type(node.op).__name__}"
            )
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
