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

    def test_if_then_branch(self) -> None:
        env = _run("x = 0\nif 1 < 2:\n    x = 5", {})
        assert env["x"] == 5

    def test_if_else_branch(self) -> None:
        env = _run("x = 0\nif 1 > 2:\n    x = 5\nelse:\n    x = 9", {})
        assert env["x"] == 9

    def test_if_elif_chain(self) -> None:
        script = (
            "if v < 0:\n    label = 'neg'\n"
            "elif v == 0:\n    label = 'zero'\n"
            "else:\n    label = 'pos'\n"
        )
        assert _run(script, {"v": 0})["label"] == "zero"
        assert _run(script, {"v": -3})["label"] == "neg"
        assert _run(script, {"v": 7})["label"] == "pos"

    def test_for_loop_accumulates(self) -> None:
        env = _run(
            "total = 0\nfor n in items:\n    total = total + n",
            {"items": [1, 2, 3, 4]},
        )
        assert env["total"] == 10

    def test_for_loop_with_inner_if(self) -> None:
        env = _run(
            (
                "kept = []\n"
                "for n in items:\n"
                "    if n >= 2 and n <= 4:\n"
                "        kept = kept + [n]\n"
            ),
            {"items": [1, 2, 3, 4, 5, 6]},
        )
        assert env["kept"] == [2, 3, 4]

    def test_bool_and_short_circuits(self) -> None:
        env = _run("x = a and b", {"a": 0, "b": "untouched"})
        assert env["x"] == 0

    def test_bool_or_short_circuits(self) -> None:
        env = _run("x = a or b", {"a": "first", "b": "second"})
        assert env["x"] == "first"

    def test_unary_not(self) -> None:
        assert _run("x = not False")["x"] is True

    def test_unary_negative(self) -> None:
        assert _run("x = -3")["x"] == -3


# ---------------------------------------------------------------- rejected

class TestRejectedConstructs:
    @pytest.mark.parametrize(
        "script,message",
        [
            ("import os", "Unsupported statement: Import"),
            ("from os import path", "Unsupported statement: ImportFrom"),
            ("while True:\n    pass", "Unsupported statement: While"),
            ("def f():\n    pass", "Unsupported statement: FunctionDef"),
            ("class C:\n    pass", "Unsupported statement: ClassDef"),
            ("x += 1", "Unsupported statement: AugAssign"),
            ("a, b = 1, 2", "Only variable or subscript assignments"),
            (
                "for a, b in pairs:\n    pass",
                "Only single-name for-loop targets",
            ),
            (
                "for i in [1]:\n    pass\nelse:\n    pass",
                "for/else is not supported",
            ),
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


# ----------------------------------------------------------------- iter_run

class TestIterRunFireEvents:
    def test_assigning_to_outputs_yields_fire_event(self) -> None:
        env: dict = {"outputs": {}, "inputs": {"v": 3}}
        events = list(SafeScriptInterpreter(env).iter_run("outputs['result'] = inputs['v']"))
        assert events == [("fire", "result", 3)]
        assert env["outputs"] == {"result": 3}

    def test_multiple_fires_are_yielded_in_order(self) -> None:
        env: dict = {"outputs": {}}
        events = list(SafeScriptInterpreter(env).iter_run(
            "outputs['a'] = 1\noutputs['b'] = 2\n"
        ))
        assert events == [("fire", "a", 1), ("fire", "b", 2)]

    def test_fire_inside_if_branch(self) -> None:
        env: dict = {"outputs": {}, "inputs": {"v": 5}}
        script = (
            "if inputs['v'] < 10:\n"
            "    outputs['small'] = inputs['v']\n"
            "else:\n"
            "    outputs['big'] = inputs['v']\n"
        )
        events = list(SafeScriptInterpreter(env).iter_run(script))
        assert events == [("fire", "small", 5)]

    def test_fire_inside_for_loop(self) -> None:
        env: dict = {"outputs": {}, "items": [1, 2, 3]}
        events = list(SafeScriptInterpreter(env).iter_run(
            "for n in items:\n    outputs['each'] = n\n"
        ))
        assert events == [
            ("fire", "each", 1), ("fire", "each", 2), ("fire", "each", 3),
        ]

    def test_run_rejects_script_that_fires(self) -> None:
        env: dict = {"outputs": {}}
        with pytest.raises(SafeScriptError, match="generator mode"):
            SafeScriptInterpreter(env).run("outputs['x'] = 1")

    def test_iter_run_yields_nothing_when_no_fire(self) -> None:
        env: dict = {}
        assert list(SafeScriptInterpreter(env).iter_run("x = 1")) == []
        assert env["x"] == 1

