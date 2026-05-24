"""Tests for :class:`ScriptTestRunner` against the v2 simulator."""
from __future__ import annotations

from pathlib import Path

import pytest

from processor_playground.models import Edge, Module, Node, Port, Signal
from processor_playground.repository import ModuleRepository
from processor_playground.simulator import Simulator
from processor_playground.testing import ScriptTestRunner


def _echo_module() -> Module:
    """A module that emits whatever value arrives on its input signal."""
    return Module(
        module_id="m1",
        name="M1",
        inputs=[Signal("in")],
        outputs=[Signal("out")],
        nodes=[
            Node(id="i", type="module_input", outputs=[Port("v")],
                 data={"signal_name": "in"}),
            Node(id="o", type="module_output", inputs=[Port("v")],
                 data={"signal_name": "out"}),
        ],
        edges=[Edge(id="e", source="i", source_handle="v",
                    target="o", target_handle="v")],
    )


@pytest.fixture()
def runner(tmp_path: Path) -> ScriptTestRunner:
    repo = ModuleRepository(tmp_path)
    repo.save(_echo_module())
    return ScriptTestRunner(repo, Simulator())


class TestScriptTestRunner:
    def test_passing_script(self, runner: ScriptTestRunner) -> None:
        report = runner.run(
            "result = run_module('m1', {'in': 7})\n"
            "assert_equal(result['outputs']['out'][0], 7)\n"
        )
        assert report == {"assertions": 1, "status": "passed", "errors": []}

    def test_multiple_assertions_counted(self, runner: ScriptTestRunner) -> None:
        report = runner.run(
            "assert_equal(1, 1)\n"
            "assert_equal(2, 2)\n"
            "assert_equal(3, 3)\n"
        )
        assert report["assertions"] == 3
        assert report["status"] == "passed"

    def test_assertion_failure_records_error(self, runner: ScriptTestRunner) -> None:
        report = runner.run("assert_equal(1, 2, 'nope')")
        assert report["status"] == "failed"
        assert "AssertionError: nope" in report["errors"][0]
        assert report["assertions"] == 1

    def test_unknown_module_reference(self, runner: ScriptTestRunner) -> None:
        report = runner.run("result = run_module('does-not-exist', {})")
        assert report["status"] == "failed"
        assert "does-not-exist" in report["errors"][0]

    def test_load_module_helper(self, runner: ScriptTestRunner) -> None:
        report = runner.run(
            "a = load_module('m1')\n"
            "b = load_module('m1')\n"
            "assert_equal(a, b)\n"
        )
        assert report["status"] == "passed"

    def test_unsafe_statement_blocked(self, runner: ScriptTestRunner) -> None:
        report = runner.run("import os")
        assert report["status"] == "failed"
        assert "Unsupported statement: Import" in report["errors"][0]

    def test_builtins_available(self, runner: ScriptTestRunner) -> None:
        report = runner.run(
            "result = run_module('m1', {'in': 'abc'})\n"
            "assert_equal(len(result['outputs']['out']), 1)\n"
        )
        assert report["status"] == "passed"

    def test_runtime_error_reported_not_raised(self, runner: ScriptTestRunner) -> None:
        report = runner.run("x = items['missing']")
        assert report["status"] == "failed"
        assert report["errors"]
