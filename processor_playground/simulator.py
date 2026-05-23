from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import Module
from .scripting import SafeScriptInterpreter


@dataclass
class SimulationState:
    variables: dict[str, Any] = field(default_factory=dict)
    datastore: dict[str, Any] = field(default_factory=dict)
    files: dict[str, str] = field(default_factory=dict)
    outputs: list[Any] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)


class Simulator:
    def __init__(self, modules_root: Path | None = None) -> None:
        self.modules_root = modules_root or Path.cwd()

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

    def _execute_module(
        self, module: Module, state: SimulationState, mocks: dict[str, Any]
    ) -> Any:
        last: Any = None
        submodules = {sub.module_id: sub for sub in module.submodules}
        for step in module.flow:
            step_type = step.get("type")
            if step_type == "set_var":
                state.variables[step["name"]] = step.get("value")
                last = state.variables[step["name"]]
            elif step_type == "emit":
                payload = step.get("payload")
                state.outputs.append(payload)
                state.events.append({"event": step.get("event", "emit"), "payload": payload})
                last = payload
            elif step_type == "datastore_write":
                state.datastore[step["key"]] = step.get("value")
                last = state.datastore[step["key"]]
            elif step_type == "datastore_read":
                last = state.datastore.get(step["key"])
                state.variables[step.get("target", step["key"])] = last
            elif step_type == "file_write":
                state.files[step["path"]] = str(step.get("content", ""))
                last = state.files[step["path"]]
            elif step_type == "file_read":
                last = state.files.get(step["path"], "")
                state.variables[step.get("target", "file_content")] = last
            elif step_type == "dialog":
                payload = {"dialog": step.get("message", ""), "response": step.get("response", "ok")}
                state.events.append(payload)
                last = payload["response"]
            elif step_type == "print":
                message = step.get("message", "")
                state.events.append({"print": message})
                last = message
            elif step_type == "email_send":
                payload = {
                    "email": {
                        "to": step.get("to"),
                        "subject": step.get("subject", ""),
                        "body": step.get("body", ""),
                    }
                }
                state.events.append(payload)
                last = payload
            elif step_type == "api_call":
                payload = {
                    "api_call": {
                        "url": step.get("url", ""),
                        "method": step.get("method", "GET"),
                        "response": step.get("mock_response", {"status": 200}),
                    }
                }
                state.events.append(payload)
                last = payload["api_call"]["response"]
            elif step_type == "run_submodule":
                interface = step.get("interface")
                if interface and interface in mocks:
                    last = mocks[interface]
                    state.events.append({"mocked_interface": interface, "response": last})
                    continue
                sub_id = step["module_id"]
                if sub_id not in submodules:
                    raise ValueError(f"Submodule '{sub_id}' not found in module '{module.module_id}'")
                last = self._execute_module(submodules[sub_id], state, mocks)
            elif step_type == "python":
                local_env = {
                    "variables": state.variables,
                    "datastore": state.datastore,
                    "files": state.files,
                    "outputs": state.outputs,
                    "events": state.events,
                    "result": None,
                }
                SafeScriptInterpreter(local_env).run(step.get("code", "result = None"))
                last = local_env.get("result")
            else:
                raise ValueError(f"Unknown step type: {step_type}")
        return last
