"""Tests for :class:`SafeScriptInterpreter`.

The interpreter is the security perimeter for user-supplied scripts; every
AST form is explicitly allow-listed. This file pins both the allow-list
and the reject-list.
"""
from __future__ import annotations

import pytest

from processor_playground.scripting import SafeScriptError, SafeScriptInterpreter


def _run(script: str, env: dict | None = None) -> dict:
    env = env if env is not None else {}
    SafeScriptInterpreter(env).run(script)
    return env


# ----------------------------------------------------------------- allowed

class TestAllowedConstructs:
    def test_constant_assignment(self) -> None:
        env = _run("x = 5")
        assert env["x"] == 5

    def test_list_literal(self) -> None:
        assert _run("x = [1, 2, 3]")["x"] == [1, 2, 3]

    def test_dict_literal(self) -> None:
        assert _run("x = {'k': 1}")["x"] == {"k": 1}

    def test_tuple_literal(self) -> None:
        assert _run("x = (1, 2)")["x"] == (1, 2)

    def test_subscript_read(self) -> None:
        env = _run("y = container['k']", {"container": {"k": 7}})
        assert env["y"] == 7

    def test_subscript_assignment(self) -> None:
        env = _run("container['k'] = 9", {"container": {}})
        assert env["container"] == {"k": 9}

    def test_binary_arithmetic(self) -> None:
        env = _run("a = 1 + 2\nb = a * 3\nc = b - 1\nd = c / 2")
        assert env["a"] == 3 and env["b"] == 9 and env["c"] == 8 and env["d"] == 4

    @pytest.mark.parametrize(
        "expr,expected",
        [
            ("1 == 1", True),
            ("1 != 2", True),
            ("3 > 2", True),
            ("2 >= 2", True),
            ("1 < 2", True),
            ("2 <= 2", True),
        ],
    )
    def test_comparisons(self, expr: str, expected: bool) -> None:
        assert _run(f"x = {expr}")["x"] is expected

    def test_call(self) -> None:
        env = _run("x = double(3)", {"double": lambda v: v * 2})
        assert env["x"] == 6

    def test_call_with_kwargs(self) -> None:
        env = _run("x = make(a=1, b=2)", {"make": lambda **kw: kw})
        assert env["x"] == {"a": 1, "b": 2}

    def test_assert_passes(self) -> None:
        _run("assert 1 == 1")  # no raise

    def test_expression_statement(self) -> None:
        side_effects: list[int] = []
        _run("note(1)", {"note": lambda v: side_effects.append(v)})
        assert side_effects == [1]


# ---------------------------------------------------------------- rejected

class TestRejectedConstructs:
    @pytest.mark.parametrize(
        "script,message",
        [
            ("import os", "Unsupported statement: Import"),
            ("from os import path", "Unsupported statement: ImportFrom"),
            ("for i in [1]:\n    pass", "Unsupported statement: For"),
            ("while True:\n    pass", "Unsupported statement: While"),
            ("def f():\n    pass", "Unsupported statement: FunctionDef"),
            ("class C:\n    pass", "Unsupported statement: ClassDef"),
            ("x += 1", "Unsupported statement: AugAssign"),
            ("a, b = 1, 2", "Only variable or subscript assignments"),
        ],
    )
    def test_disallowed_statements(self, script: str, message: str) -> None:
        with pytest.raises((SafeScriptError, ValueError)) as exc:
            _run(script)
        assert message in str(exc.value)

    def test_assert_fail_raises_assertion_error(self) -> None:
        with pytest.raises(AssertionError, match="boom"):
            _run("assert 0, 'boom'")

    def test_unknown_identifier(self) -> None:
        with pytest.raises(SafeScriptError, match="Unknown identifier"):
            _run("x = undefined")

    def test_calling_non_callable(self) -> None:
        with pytest.raises(SafeScriptError, match="non-callable"):
            _run("x = thing()", {"thing": 5})

    def test_kwargs_unpacking_rejected(self) -> None:
        with pytest.raises(SafeScriptError, match="Keyword unpacking"):
            _run("x = fn(**d)", {"fn": lambda **k: None, "d": {}})

    def test_attribute_access_rejected(self) -> None:
        with pytest.raises(SafeScriptError, match="Unsupported expression"):
            _run("x = obj.name", {"obj": object()})

    def test_chained_comparison_rejected(self) -> None:
        with pytest.raises(SafeScriptError, match="single comparisons"):
            _run("x = 1 < 2 < 3")

    def test_unsupported_binary_operator(self) -> None:
        with pytest.raises(SafeScriptError, match="Unsupported binary operator"):
            _run("x = 1 % 2")
