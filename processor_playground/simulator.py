"""Wire-and-port simulator for :class:`Module` graphs.

Execution model — synchronous, single-threaded, call-stack semantics:

1. ``run(module, input_data)`` fires each entry of ``input_data`` into the
   corresponding ``module_input`` node's output port.
2. Firing an output port walks every outgoing :class:`~models.Edge` and
   *delivers* the value to the target node's input port — synchronously, one
   wire at a time.
3. Delivering to a node activates its handler (see :data:`_ACTIVATORS`):
   - ``module_output`` records the value as a module-level emitted signal
     (top frame) or fires the parent ``submodule`` node's matching output
     port (nested frame);
   - ``submodule`` opens a nested frame and fires the submodule's
     ``module_input`` of the same name;
   - ``python`` runs the node's script as a generator. Each
     ``outputs[port] = value`` statement yields a fire that the simulator
     processes immediately (so any downstream chain runs to completion
     before the script resumes).
4. **Request / response.** A node may declare a paired
   ``request`` output and ``response`` input. Firing the request suspends
   the firing Python node until exactly one delivery arrives on the paired
   response port; the simulator then resumes the script with the response
   value visible at ``inputs[response_port]``.

This module imports ``models`` and ``scripting`` only; nothing about FastAPI,
the file system, or HTTP belongs here (see ARCHITECTURE.md §2).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from .models import Edge, Module, Node, Port
from .scripting import SafeScriptInterpreter, SafeScriptError


class SimulatorError(RuntimeError):
    """Raised when the wired graph is invalid or a node misbehaves at runtime."""


# A callback the parent frame installs on a child frame so that the child's
# ``module_output`` deliveries propagate as fires on the parent's enclosing
# ``submodule`` node. The top-level frame's callback records into the run
# result instead.
OnModuleOutput = Callable[[str, Any], None]


@dataclass
class _Frame:
    """One module's runtime context within the call stack."""

    module: Module
    on_module_output: OnModuleOutput
    nodes_by_id: dict[str, Node]
    edges_from: dict[tuple[str, str], list[Edge]]


@dataclass
class _PythonActivation:
    """Bookkeeping for one suspended-or-active Python-node activation.

    Holds the env (so the simulator can inject a response into ``inputs``)
    and the response port the activation is currently blocking on, if any.
    """

    node: Node
    env: dict[str, Any]
    waiting_on: str | None = None
    response_value: Any = None
    response_received: bool = False


@dataclass
class _RunResult:
    outputs: dict[str, list[Any]] = field(default_factory=dict)
    trace: list[dict[str, Any]] = field(default_factory=list)


class Simulator:
    """Stateless except for the single in-flight ``run`` call.

    A fresh ``Simulator`` is safe to reuse across runs; per-run state lives
    on the local stack of ``run``.
    """

    # ----------------------------------------------------------- public API

    def run(
        self,
        module: Module,
        *,
        input_signal: str,
        input_value: Any,
        databases: dict[str, dict[str, list[dict[str, Any]]]] | None = None,
    ) -> dict[str, Any]:
        """Run ``module`` by firing a single value into one of its inputs.

        Execution is always initiated through **one** input signal: pick
        which ``module_input`` to wake up, supply the value it carries,
        and the simulator walks the wires from there. Multiple inputs are
        not delivered in one call — if you need that, run the module
        twice.

        ``databases`` is an optional snapshot mapping ``db_name -> {table:
        rows}`` made visible to ``db_read`` / ``db_create`` nodes. Mutations
        performed by ``db_create`` happen *in place* on the supplied dict
        — the caller decides whether to persist them.

        Returns ``{ "outputs": {signal: [values]}, "trace": [...],
        "status": "complete" }``.
        """
        result = _RunResult(outputs={sig.name: [] for sig in module.outputs})

        def record_top_level_output(signal_name: str, value: Any) -> None:
            result.outputs.setdefault(signal_name, []).append(value)
            result.trace.append(
                {"event": "module_output", "signal": signal_name, "value": value}
            )

        # Per-run state (kept on the simulator instance for the duration of
        # this call only — ``run`` is the only public entry point that
        # touches it).
        self._result = result
        # Maps node-object-identity -> the currently suspended activation on
        # that node. Single path of execution means at most one activation
        # waiting per node at any moment.
        self._waiting: dict[int, _PythonActivation] = {}
        # Nodes that accumulate input fires across activator calls until every
        # declared input port has a value — then their "ready" semantic fires
        # once. Used by db_read / db_create / branch / counted_loop.
        self._input_buffers: dict[str, dict[str, Any]] = {}
        self._databases: dict[str, dict[str, list[dict[str, Any]]]] = databases or {}

        frame = self._make_frame(module, record_top_level_output)
        self._fire_module_input(frame, input_signal, input_value)

        return {
            "outputs": result.outputs,
            "trace": result.trace,
            "status": "complete",
        }

    # -------------------------------------------------------- frame helpers

    def _make_frame(self, module: Module, on_output: OnModuleOutput) -> _Frame:
        nodes_by_id = {n.id: n for n in module.nodes}
        edges_from: dict[tuple[str, str], list[Edge]] = {}
        for edge in module.edges:
            edges_from.setdefault((edge.source, edge.source_handle), []).append(edge)
        return _Frame(
            module=module,
            on_module_output=on_output,
            nodes_by_id=nodes_by_id,
            edges_from=edges_from,
        )

    def _fire_module_input(
        self, frame: _Frame, signal_name: str, value: Any
    ) -> None:
        for node in frame.module.nodes:
            if node.type == "module_input" and node.data.get("signal_name") == signal_name:
                if not node.outputs:
                    raise SimulatorError(
                        f"module_input node '{node.id}' has no output port declared"
                    )
                port_name = node.outputs[0].name
                self._result.trace.append(
                    {"event": "module_input", "signal": signal_name, "value": value}
                )
                self._fire_from_node(frame, node.id, port_name, value)
                return
        raise SimulatorError(
            f"No module_input node declared for signal '{signal_name}' "
            f"in module '{frame.module.module_id}'"
        )

    # ------------------------------------------------------ fire / deliver

    def _fire_from_node(
        self, frame: _Frame, node_id: str, port_name: str, value: Any
    ) -> None:
        edges = frame.edges_from.get((node_id, port_name), [])
        for edge in edges:
            self._deliver(frame, edge.target, edge.target_handle, value)

    def _deliver(
        self,
        frame: _Frame,
        target_node_id: str,
        target_port_name: str,
        value: Any,
    ) -> None:
        target = frame.nodes_by_id.get(target_node_id)
        if target is None:
            raise SimulatorError(
                f"Edge target node '{target_node_id}' not found in module "
                f"'{frame.module.module_id}'"
            )
        # If a Python node on this very target is currently suspended waiting
        # for its paired response, this delivery is that response — stash it
        # and unwind, do NOT start a fresh activation.
        activation = self._waiting.get(id(target))
        if activation is not None and activation.waiting_on == target_port_name:
            activation.response_value = value
            activation.response_received = True
            activation.env["inputs"][target_port_name] = value
            self._result.trace.append(
                {
                    "event": "response",
                    "module": frame.module.module_id,
                    "node": target_node_id,
                    "port": target_port_name,
                    "value": value,
                }
            )
            return

        self._result.trace.append(
            {
                "event": "deliver",
                "module": frame.module.module_id,
                "node": target_node_id,
                "port": target_port_name,
                "value": value,
            }
        )
        activator = _ACTIVATORS.get(target.type)
        if activator is None:
            raise SimulatorError(
                f"Unknown node type '{target.type}' on node '{target_node_id}'"
            )
        activator(self, frame, target, target_port_name, value)

    # ---------------------------------------------------- python activator

    def _activate_python(
        self, frame: _Frame, node: Node, port_name: str, value: Any
    ) -> None:
        env: dict[str, Any] = {
            "inputs": {port_name: value},
            "outputs": {},
            "current_input": port_name,
            # A small, safe builtins surface — same set the script-test
            # runner exposes — so node scripts can compute against
            # collections without reaching for attribute access.
            "len": len,
            "range": range,
            "min": min,
            "max": max,
            "sum": sum,
        }
        code = node.data.get("code", "")
        gen = SafeScriptInterpreter(env).iter_run(code)
        try:
            event = next(gen)
            while True:
                kind = event[0]
                if kind != "fire":
                    raise SimulatorError(f"Unexpected script event: {event!r}")
                _, fire_port, fire_value = event
                self._process_python_fire(frame, node, env, fire_port, fire_value)
                event = next(gen)
        except StopIteration:
            return

    def _process_python_fire(
        self,
        frame: _Frame,
        node: Node,
        env: dict[str, Any],
        fire_port: str,
        fire_value: Any,
    ) -> None:
        port = _find_port(node.outputs, fire_port)
        if port is None:
            raise SimulatorError(
                f"Python node '{node.id}' fired undeclared output port "
                f"'{fire_port}'"
            )
        if port.kind == "request":
            if not port.pair:
                raise SimulatorError(
                    f"Request output port '{fire_port}' on node '{node.id}' "
                    f"has no 'pair' set — set it to the response input port name."
                )
            response_input = _find_port(node.inputs, port.pair)
            if response_input is None or response_input.kind != "response":
                raise SimulatorError(
                    f"Node '{node.id}' declares request '{fire_port}' paired "
                    f"with response '{port.pair}', but no matching response "
                    f"input port is declared."
                )
            activation = _PythonActivation(
                node=node, env=env, waiting_on=port.pair
            )
            self._waiting[id(node)] = activation
            try:
                self._fire_from_node(frame, node.id, fire_port, fire_value)
            finally:
                self._waiting.pop(id(node), None)
            if not activation.response_received:
                raise SimulatorError(
                    f"Node '{node.id}' fired request '{fire_port}' but no "
                    f"value was delivered to paired response port "
                    f"'{port.pair}'."
                )
            # Re-tag current_input so the script can dispatch on the resume.
            env["current_input"] = port.pair
        else:
            self._fire_from_node(frame, node.id, fire_port, fire_value)

    # -------------------------------------------------- submodule activator

    def _activate_submodule(
        self, frame: _Frame, node: Node, port_name: str, value: Any
    ) -> None:
        # Accept both ``module_id`` (current) and ``moduleId`` (legacy
        # camelCase written by older UI builds) so existing storage files
        # don't have to be migrated to be runnable.
        submodule_id = node.data.get("module_id") or node.data.get("moduleId")
        if not submodule_id:
            raise SimulatorError(
                f"submodule node '{node.id}' has no 'module_id' in its data"
            )
        submodule = next(
            (s for s in frame.module.submodules if s.module_id == submodule_id),
            None,
        )
        if submodule is None:
            raise SimulatorError(
                f"Submodule '{submodule_id}' not found in module "
                f"'{frame.module.module_id}'"
            )

        # When the nested module fires one of its module_output nodes,
        # propagate the value as a fire on the parent's submodule node's
        # output port of the same name.
        def on_sub_output(signal_name: str, sub_value: Any) -> None:
            self._fire_from_node(frame, node.id, signal_name, sub_value)

        sub_frame = self._make_frame(submodule, on_sub_output)
        self._fire_module_input(sub_frame, port_name, value)

    # ----------------------------------------------- module_output activator

    def _activate_module_output(
        self, frame: _Frame, node: Node, port_name: str, value: Any
    ) -> None:
        signal_name = node.data.get("signal_name")
        if not signal_name:
            raise SimulatorError(
                f"module_output node '{node.id}' has no 'signal_name' in its data"
            )
        frame.on_module_output(signal_name, value)

    # ----------------------------------------------- module_input activator

    def _activate_module_input(
        self, frame: _Frame, node: Node, port_name: str, value: Any
    ) -> None:
        # module_input is a source, not a sink. Edges should never target it.
        raise SimulatorError(
            f"module_input node '{node.id}' was wired as an edge target; "
            f"it is a source-only node."
        )

    # --------------------------------------------------- db_* activators

    def _db_collect(
        self, node: Node, port_name: str, value: Any
    ) -> dict[str, Any] | None:
        """Buffer one input fire for a db node. Returns the complete
        ``{port_name: value}`` dict once every declared input port has
        received a value (and clears the buffer), else ``None``."""
        buffer = self._input_buffers.setdefault(node.id, {})
        buffer[port_name] = value
        needed = {port.name for port in node.inputs}
        if needed and needed.issubset(buffer.keys()):
            params = dict(buffer)
            self._input_buffers.pop(node.id, None)
            return params
        return None

    def _db_resolve_table(
        self, node: Node, query_text: str
    ) -> tuple[str, str, "Statement", list[dict[str, Any]]]:
        from . import sql as _sql

        db_name = node.data.get("database_name") or ""
        if not db_name:
            raise SimulatorError(
                f"{node.type} node '{node.id}' has no 'database_name' in its data"
            )
        if db_name not in self._databases:
            raise SimulatorError(
                f"{node.type} node '{node.id}' references unknown database "
                f"'{db_name}'"
            )
        if not query_text:
            raise SimulatorError(
                f"{node.type} node '{node.id}' has no 'query' in its data"
            )
        try:
            stmt = _sql.parse(query_text)
        except ValueError as exc:
            raise SimulatorError(
                f"{node.type} node '{node.id}' query parse error: {exc}"
            ) from exc
        tables = self._databases[db_name]
        rows = tables.setdefault(stmt.table, [])
        return db_name, stmt.table, stmt, rows

    def _activate_db_read(
        self, frame: _Frame, node: Node, port_name: str, value: Any
    ) -> None:
        from . import sql as _sql

        params = self._db_collect(node, port_name, value)
        if params is None:
            return
        query_text = node.data.get("query") or ""
        db_name, table, stmt, rows = self._db_resolve_table(node, query_text)
        if not isinstance(stmt, _sql.SelectStmt):
            raise SimulatorError(
                f"db_read node '{node.id}' expects a SELECT statement"
            )
        try:
            result_rows = _sql.execute(stmt, table_rows=rows, params=params)
        except (KeyError, ValueError) as exc:
            raise SimulatorError(
                f"db_read node '{node.id}' query error: {exc}"
            ) from exc
        self._result.trace.append(
            {
                "event": "db_read",
                "node": node.id,
                "database": db_name,
                "table": table,
                "row_count": len(result_rows),
            }
        )
        out_port = node.outputs[0].name if node.outputs else "rows"
        self._fire_from_node(frame, node.id, out_port, result_rows)

    def _activate_db_create(
        self, frame: _Frame, node: Node, port_name: str, value: Any
    ) -> None:
        from . import sql as _sql

        params = self._db_collect(node, port_name, value)
        if params is None:
            return
        query_text = node.data.get("query") or ""
        db_name, table, stmt, rows = self._db_resolve_table(node, query_text)
        if not isinstance(stmt, _sql.InsertStmt):
            raise SimulatorError(
                f"db_create node '{node.id}' expects an INSERT statement"
            )
        try:
            inserted = _sql.execute(stmt, table_rows=rows, params=params)
        except (KeyError, ValueError) as exc:
            raise SimulatorError(
                f"db_create node '{node.id}' query error: {exc}"
            ) from exc
        self._result.trace.append(
            {
                "event": "db_create",
                "node": node.id,
                "database": db_name,
                "table": table,
                "row": inserted,
            }
        )
        out_port = node.outputs[0].name if node.outputs else "created"
        self._fire_from_node(frame, node.id, out_port, inserted)

    # ----------------------------------------------- control-flow activators

    def _activate_branch(
        self, frame: _Frame, node: Node, port_name: str, value: Any
    ) -> None:
        """Route ``value`` to ``true`` or ``false`` based on a static
        Python expression stored in ``data['condition']``.

        The expression sees the incoming value as ``value`` and the same
        read-only builtins available to ``python`` nodes
        (``len/range/min/max/sum``). The branch is one-shot per fire:
        whichever output matches the expression result emits ``value``
        unchanged.
        """
        if port_name != "value":
            raise SimulatorError(
                f"branch node '{node.id}' received a fire on undeclared "
                f"input port '{port_name}' (only 'value' is supported)"
            )
        expression = (node.data.get("condition") or "").strip()
        if not expression:
            raise SimulatorError(
                f"branch node '{node.id}' has no 'condition' expression in "
                f"its data"
            )
        env: dict[str, Any] = {
            "value": value,
            "len": len, "range": range,
            "min": min, "max": max, "sum": sum,
        }
        try:
            result = SafeScriptInterpreter(env).evaluate_expression(expression)
        except SafeScriptError as exc:
            raise SimulatorError(
                f"branch node '{node.id}' condition error: {exc}"
            ) from exc
        taken = "true" if bool(result) else "false"
        self._result.trace.append(
            {"event": "branch", "node": node.id, "taken": taken,
             "condition": expression}
        )
        self._fire_from_node(frame, node.id, taken, value)

    def _activate_join(
        self, frame: _Frame, node: Node, port_name: str, value: Any
    ) -> None:
        """Merge alternative branches: forward every input arrival to
        the ``value`` output as it arrives (no buffering).
        """
        self._result.trace.append(
            {"event": "join", "node": node.id, "from_port": port_name}
        )
        self._fire_from_node(frame, node.id, "value", value)

    def _activate_counted_loop(
        self, frame: _Frame, node: Node, port_name: str, value: Any
    ) -> None:
        """``for i in range(from, to): fire('index', i)``; then fire ``done``.

        Both ``from`` and ``to`` inputs must arrive before the loop runs.
        Iterations are dispatched synchronously — the downstream chain of
        each ``index`` fire runs to completion before the next iteration
        begins.
        """
        buffer = self._input_buffers.setdefault(node.id, {})
        buffer[port_name] = value
        if "from" not in buffer or "to" not in buffer:
            return
        start_raw = buffer["from"]
        stop_raw = buffer["to"]
        self._input_buffers.pop(node.id, None)
        try:
            start = int(start_raw)
            stop = int(stop_raw)
        except (TypeError, ValueError) as exc:
            raise SimulatorError(
                f"counted_loop node '{node.id}' requires integer 'from' and "
                f"'to' inputs; got from={start_raw!r}, to={stop_raw!r}"
            ) from exc
        self._result.trace.append(
            {"event": "counted_loop", "node": node.id,
             "from": start, "to": stop}
        )
        count = 0
        for index in range(start, stop):
            count += 1
            self._fire_from_node(frame, node.id, "index", index)
        self._fire_from_node(frame, node.id, "done", count)

    def _activate_foreach(
        self, frame: _Frame, node: Node, port_name: str, value: Any
    ) -> None:
        """Iterate ``collection`` (list/tuple or dict); fire ``item`` and
        ``key`` per element, then ``done`` with the original collection.

        For sequences ``key`` is the integer index; for dicts ``key`` is
        the mapping key and ``item`` is the value.
        """
        if isinstance(value, dict):
            entries = list(value.items())
        elif isinstance(value, (list, tuple)):
            entries = list(enumerate(value))
        else:
            raise SimulatorError(
                f"foreach node '{node.id}' expects a list, tuple or dict "
                f"on its 'collection' input; got {type(value).__name__}"
            )
        self._result.trace.append(
            {"event": "foreach", "node": node.id, "count": len(entries)}
        )
        for key, item in entries:
            self._fire_from_node(frame, node.id, "key", key)
            self._fire_from_node(frame, node.id, "item", item)
        self._fire_from_node(frame, node.id, "done", value)


def _find_port(ports: Iterable[Port], name: str) -> Port | None:
    for port in ports:
        if port.name == name:
            return port
    return None


# Registry mapping node ``type`` to activator method. Extend this when
# adding a new node kind — nothing else in this file needs to change.
_ACTIVATORS: dict[str, Callable[[Simulator, _Frame, Node, str, Any], None]] = {
    "module_input": Simulator._activate_module_input,
    "module_output": Simulator._activate_module_output,
    "python": Simulator._activate_python,
    "submodule": Simulator._activate_submodule,
    "db_read": Simulator._activate_db_read,
    "db_create": Simulator._activate_db_create,
    "branch": Simulator._activate_branch,
    "join": Simulator._activate_join,
    "counted_loop": Simulator._activate_counted_loop,
    "foreach": Simulator._activate_foreach,
}
