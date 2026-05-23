"""Tests for the :class:`Simulator`.

There is one focused test per supported step type, an error test for an
unknown step type, and a couple of integration tests for the more involved
behaviours (submodule mocking, nested submodules, the safe Python step).

When a new step type is added, a new test belongs in this file (see
ARCHITECTURE.md "Adding things — A new flow step type").
"""
from __future__ import annotations

import pytest

from processor_playground.models import Module
from processor_playground.simulator import Simulator


def _run(flow, **kwargs):
    return Simulator().run(Module(module_id="t", name="T", flow=flow), **kwargs)


class TestSimulatorStepTypes:
    def test_set_var(self) -> None:
        out = _run([{"type": "set_var", "name": "x", "value": 7}])
        assert out["variables"]["x"] == 7
        assert out["result"] == 7

    def test_emit_appends_output_and_event(self) -> None:
        out = _run([{"type": "emit", "event": "done", "payload": {"ok": True}}])
        assert out["outputs"] == [{"ok": True}]
        assert out["events"] == [{"event": "done", "payload": {"ok": True}}]

    def test_emit_defaults_event_name(self) -> None:
        out = _run([{"type": "emit", "payload": 1}])
        assert out["events"][0]["event"] == "emit"

    def test_datastore_write_then_read(self) -> None:
        out = _run([
            {"type": "datastore_write", "key": "counter", "value": 5},
            {"type": "datastore_read", "key": "counter", "target": "c"},
        ])
        assert out["datastore"]["counter"] == 5
        assert out["variables"]["c"] == 5

    def test_datastore_read_missing_key(self) -> None:
        out = _run([{"type": "datastore_read", "key": "absent"}])
        assert out["variables"]["absent"] is None

    def test_file_write_then_read(self) -> None:
        out = _run([
            {"type": "file_write", "path": "/a.txt", "content": "hi"},
            {"type": "file_read", "path": "/a.txt", "target": "data"},
        ])
        assert out["files"]["/a.txt"] == "hi"
        assert out["variables"]["data"] == "hi"

    def test_file_read_missing_returns_empty(self) -> None:
        out = _run([{"type": "file_read", "path": "/nope"}])
        assert out["variables"]["file_content"] == ""

    def test_dialog(self) -> None:
        out = _run([{"type": "dialog", "message": "Continue?", "response": "yes"}])
        assert out["events"][0] == {"dialog": "Continue?", "response": "yes"}
        assert out["result"] == "yes"

    def test_dialog_defaults(self) -> None:
        out = _run([{"type": "dialog"}])
        assert out["events"][0]["response"] == "ok"

    def test_print(self) -> None:
        out = _run([{"type": "print", "message": "hi"}])
        assert out["events"] == [{"print": "hi"}]

    def test_email_send(self) -> None:
        out = _run([{"type": "email_send", "to": "a@b", "subject": "s", "body": "b"}])
        assert out["events"][0] == {"email": {"to": "a@b", "subject": "s", "body": "b"}}

    def test_api_call_with_mock_response(self) -> None:
        out = _run([{"type": "api_call", "url": "u", "mock_response": {"x": 1}}])
        assert out["events"][0]["api_call"]["response"] == {"x": 1}
        assert out["result"] == {"x": 1}

    def test_api_call_defaults_method_and_response(self) -> None:
        out = _run([{"type": "api_call"}])
        assert out["events"][0]["api_call"]["method"] == "GET"
        assert out["events"][0]["api_call"]["response"] == {"status": 200}

    def test_unknown_step_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown step type: nope"):
            _run([{"type": "nope"}])

    def test_input_data_seeds_variables(self) -> None:
        out = _run([], input_data={"seed": 42})
        assert out["variables"]["seed"] == 42


class TestSubmoduleStep:
    def test_runs_submodule_when_no_mock(self) -> None:
        child = Module(module_id="c", name="C", flow=[{"type": "emit", "payload": "from-child"}])
        parent = Module(
            module_id="p",
            name="P",
            flow=[{"type": "run_submodule", "module_id": "c"}],
            submodules=[child],
        )
        out = Simulator().run(parent)
        assert out["outputs"] == ["from-child"]

    def test_uses_mock_when_interface_matches(self) -> None:
        child = Module(module_id="db", name="DB", flow=[{"type": "emit", "payload": "real"}])
        parent = Module(
            module_id="p",
            name="P",
            flow=[{"type": "run_submodule", "module_id": "db", "interface": "database"}],
            submodules=[child],
        )
        out = Simulator().run(parent, mocks={"database": {"rows": 3}})
        # When mocked, the real child must NOT be executed.
        assert out["outputs"] == []
        assert out["events"][0]["mocked_interface"] == "database"
        assert out["events"][0]["response"] == {"rows": 3}

    def test_unknown_submodule_raises(self) -> None:
        parent = Module(
            module_id="p", name="P", flow=[{"type": "run_submodule", "module_id": "ghost"}],
        )
        with pytest.raises(ValueError, match="Submodule 'ghost' not found"):
            Simulator().run(parent)

    def test_nested_submodule_execution(self) -> None:
        leaf = Module(module_id="leaf", name="Leaf", flow=[{"type": "emit", "payload": "leaf"}])
        mid = Module(
            module_id="mid", name="Mid",
            flow=[{"type": "run_submodule", "module_id": "leaf"}],
            submodules=[leaf],
        )
        root = Module(
            module_id="root", name="Root",
            flow=[{"type": "run_submodule", "module_id": "mid"}],
            submodules=[mid],
        )
        assert Simulator().run(root)["outputs"] == ["leaf"]


class TestPythonStep:
    def test_can_read_and_write_variables(self) -> None:
        out = _run(
            [
                {"type": "set_var", "name": "a", "value": 2},
                {"type": "python", "code": "variables['b'] = variables['a'] + 3\nresult = variables['b']"},
            ]
        )
        assert out["result"] == 5
        assert out["variables"]["b"] == 5

    def test_python_step_with_no_code_yields_none(self) -> None:
        out = _run([{"type": "python"}])
        assert out["result"] is None

    def test_python_step_can_record_via_subscript(self) -> None:
        # The safe interpreter rejects attribute access (`.append`) by design,
        # but subscript assignment into mutable container values is allowed.
        out = _run([
            {"type": "python", "code": "variables['mark'] = 1\nresult = variables['mark']"}
        ])
        assert out["result"] == 1
        assert out["variables"]["mark"] == 1
