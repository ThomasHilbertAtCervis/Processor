"""Simulation engine for :class:`Module` flows.

Step dispatch is implemented as a registry of handler methods rather than a
single ``if/elif`` ladder. Adding a step type means adding one method and one
entry to ``_STEP_HANDLERS`` — nothing else in this file changes (Open/Closed).
See ARCHITECTURE.md ("Adding things — A new flow step type").
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .models import Module
from .scripting import SafeScriptInterpreter


@dataclass
class SimulationState:
    variables: dict[str, Any] = field(default_factory=dict)
    datastore: dict[str, Any] = field(default_factory=dict)
    files: dict[str, str] = field(default_factory=dict)
    outputs: list[Any] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class _StepContext:
    """Everything a step handler may inspect or mutate.

    Bundling these into a single value keeps handler signatures uniform and
    makes it trivial to add new context (e.g. clock, logger) without touching
    every handler.
    """

    step: dict[str, Any]
    state: SimulationState
    mocks: dict[str, Any]
    module: Module
    simulator: "Simulator"


StepHandler = Callable[[_StepContext], Any]


class Simulator:
    def __init__(self, modules_root: Path | None = None) -> None:
        self.modules_root = modules_root or Path.cwd()

    # ---------------------------------------------------------------- public

    def run(
        self,
        module: Module,
        input_data: dict[str, Any] | None = None,
        mocks: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        state = SimulationState(variables=dict(input_data or {}))
        result = self._execute_module(module, state, mocks or {})
        return {
            "result": result,
            "variables": state.variables,
            "datastore": state.datastore,
            "files": state.files,
            "outputs": state.outputs,
            "events": state.events,
        }

    # --------------------------------------------------------------- private

    def _execute_module(
        self, module: Module, state: SimulationState, mocks: dict[str, Any]
    ) -> Any:
        last: Any = None
        for step in module.flow:
            step_type = step.get("type")
            handler = self._STEP_HANDLERS.get(step_type)
            if handler is None:
                raise ValueError(f"Unknown step type: {step_type}")
            ctx = _StepContext(
                step=step, state=state, mocks=mocks, module=module, simulator=self
            )
            last = handler(ctx)
        return last

    # ------------------------------------------------------------- handlers

    @staticmethod
    def _set_var(ctx: _StepContext) -> Any:
        ctx.state.variables[ctx.step["name"]] = ctx.step.get("value")
        return ctx.state.variables[ctx.step["name"]]

    @staticmethod
    def _emit(ctx: _StepContext) -> Any:
        payload = ctx.step.get("payload")
        ctx.state.outputs.append(payload)
        ctx.state.events.append({"event": ctx.step.get("event", "emit"), "payload": payload})
        return payload

    @staticmethod
    def _datastore_write(ctx: _StepContext) -> Any:
        ctx.state.datastore[ctx.step["key"]] = ctx.step.get("value")
        return ctx.state.datastore[ctx.step["key"]]

    @staticmethod
    def _datastore_read(ctx: _StepContext) -> Any:
        value = ctx.state.datastore.get(ctx.step["key"])
        ctx.state.variables[ctx.step.get("target", ctx.step["key"])] = value
        return value

    @staticmethod
    def _file_write(ctx: _StepContext) -> Any:
        ctx.state.files[ctx.step["path"]] = str(ctx.step.get("content", ""))
        return ctx.state.files[ctx.step["path"]]

    @staticmethod
    def _file_read(ctx: _StepContext) -> Any:
        value = ctx.state.files.get(ctx.step["path"], "")
        ctx.state.variables[ctx.step.get("target", "file_content")] = value
        return value

    @staticmethod
    def _dialog(ctx: _StepContext) -> Any:
        payload = {
            "dialog": ctx.step.get("message", ""),
            "response": ctx.step.get("response", "ok"),
        }
        ctx.state.events.append(payload)
        return payload["response"]

    @staticmethod
    def _print(ctx: _StepContext) -> Any:
        message = ctx.step.get("message", "")
        ctx.state.events.append({"print": message})
        return message

    @staticmethod
    def _email_send(ctx: _StepContext) -> Any:
        payload = {
            "email": {
                "to": ctx.step.get("to"),
                "subject": ctx.step.get("subject", ""),
                "body": ctx.step.get("body", ""),
            }
        }
        ctx.state.events.append(payload)
        return payload

    @staticmethod
    def _api_call(ctx: _StepContext) -> Any:
        payload = {
            "api_call": {
                "url": ctx.step.get("url", ""),
                "method": ctx.step.get("method", "GET"),
                "response": ctx.step.get("mock_response", {"status": 200}),
            }
        }
        ctx.state.events.append(payload)
        return payload["api_call"]["response"]

    @staticmethod
    def _run_submodule(ctx: _StepContext) -> Any:
        interface = ctx.step.get("interface")
        if interface and interface in ctx.mocks:
            response = ctx.mocks[interface]
            ctx.state.events.append({"mocked_interface": interface, "response": response})
            return response
        submodules = {sub.module_id: sub for sub in ctx.module.submodules}
        sub_id = ctx.step["module_id"]
        if sub_id not in submodules:
            raise ValueError(
                f"Submodule '{sub_id}' not found in module '{ctx.module.module_id}'"
            )
        return ctx.simulator._execute_module(submodules[sub_id], ctx.state, ctx.mocks)

    @staticmethod
    def _python(ctx: _StepContext) -> Any:
        local_env = {
            "variables": ctx.state.variables,
            "datastore": ctx.state.datastore,
            "files": ctx.state.files,
            "outputs": ctx.state.outputs,
            "events": ctx.state.events,
            "result": None,
        }
        SafeScriptInterpreter(local_env).run(ctx.step.get("code", "result = None"))
        return local_env.get("result")

    # Registry — extend this when adding a new step type.
    _STEP_HANDLERS: dict[str | None, StepHandler] = {
        "set_var": _set_var,
        "emit": _emit,
        "datastore_write": _datastore_write,
        "datastore_read": _datastore_read,
        "file_write": _file_write,
        "file_read": _file_read,
        "dialog": _dialog,
        "print": _print,
        "email_send": _email_send,
        "api_call": _api_call,
        "run_submodule": _run_submodule,
        "python": _python,
    }
