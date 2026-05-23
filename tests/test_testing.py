"""Tests for :class:`ScriptTestRunner`."""
from __future__ import annotations

from pathlib import Path

import pytest

from processor_playground.models import Module
from processor_playground.repository import ModuleRepository
from processor_playground.simulator import Simulator
from processor_playground.testing import ScriptTestRunner


@pytest.fixture()
def runner(tmp_path: Path) -> ScriptTestRunner:
    repo = ModuleRepository(tmp_path)
    repo.save(Module(module_id="m1", name="M1", flow=[{"type": "emit", "payload": {"ok": True}}]))
    return ScriptTestRunner(repo, Simulator())


class TestScriptTestRunner:
    def test_passing_script(self, runner: ScriptTestRunner) -> None:
        report = runner.run(
            "result = run_module('m1')\n"
            "assert_equal(result['outputs'][0]['ok'], True)\n"
        )
        assert report == {"assertions": 1, "status": "passed", "errors": []}

    def test_multiple_assertions_counted(self, runner: ScriptTestRunner) -> None:
        report = runner.run(
            "result = run_module('m1')\n"
            "assert_equal(1, 1)\n"
            "assert_equal(2, 2)\n"
            "assert_equal(result['outputs'][0]['ok'], True)\n"
        )
        assert report["assertions"] == 3
        assert report["status"] == "passed"

    def test_assertion_failure_records_error(self, runner: ScriptTestRunner) -> None:
        report = runner.run("assert_equal(1, 2, 'nope')")
        assert report["status"] == "failed"
        assert "AssertionError: nope" in report["errors"][0]
        assert report["assertions"] == 1  # counted before raising

    def test_assertion_failure_default_message(self, runner: ScriptTestRunner) -> None:
        report = runner.run("assert_equal(1, 2)")
        assert "Expected 2, got 1" in report["errors"][0]

    def test_unknown_module_reference(self, runner: ScriptTestRunner) -> None:
        report = runner.run("result = run_module('does-not-exist')")
        assert report["status"] == "failed"
        assert "does-not-exist" in report["errors"][0]

    def test_load_module_helper(self, runner: ScriptTestRunner) -> None:
        # The safe interpreter doesn't permit attribute access, so the script
        # asserts module identity by round-tripping it through assert_equal
        # (assert_equal uses `==`, which works on dataclasses).
        report = runner.run(
            "module = load_module('m1')\n"
            "again = load_module('m1')\n"
            "assert_equal(module, again)\n"
        )
        assert report["status"] == "passed"

    def test_unsafe_statement_blocked(self, runner: ScriptTestRunner) -> None:
        report = runner.run("import os")
        assert report["status"] == "failed"
        assert "Unsupported statement: Import" in report["errors"][0]

    def test_builtins_available(self, runner: ScriptTestRunner) -> None:
        report = runner.run(
            "result = run_module('m1')\n"
            "assert_equal(len(result['outputs']), 1)\n"
        )
        assert report["status"] == "passed"

    def test_runtime_error_reported_not_raised(self, runner: ScriptTestRunner) -> None:
        report = runner.run("x = items['missing']")
        # An interpreter error must show up in the report instead of propagating.
        assert report["status"] == "failed"
        assert report["errors"]
