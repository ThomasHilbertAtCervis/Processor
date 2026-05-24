# Product Specification — Processor Playground

> **Purpose of this file.** This document captures the product vision, every
> feature request, every description of how the software is supposed to work,
> and every use-case the owner has expressed. It is the single place that
> agents (and humans) should read first to understand *what* this software is
> for and *what* it is supposed to do.
>
> **Companion docs.**
> - [`ARCHITECTURE.md`](ARCHITECTURE.md) — *how* the code is organised.
> - [`README.md`](README.md) — how to run it.
>
> **How to maintain this file.**
> - Every new feature request, clarification, or product decision from the
>   owner is recorded here, in the relevant section, with a brief reference to
>   the PR / issue / comment it came from.
> - When a request is implemented, do **not** delete it — mark it ✅ and keep
>   the description. This file is the long-term memory of *intent*, not a
>   to-do list.
> - When a later request contradicts an earlier one, leave both, mark the
>   superseded one, and explain the change.

---

## 1. Product vision

A browser-based, WYSIWYG platform for modelling **executable processes**
together with the **data that flows through them**, so that the platform can
*tell the user where data is incompatible, missing, or arriving at the wrong
time* — and the user can then change the process to fix it.

It is both:

- a **process modeller** — flow charts of business processes built from
  nested, reusable modules, and
- a **data-flow modeller** — every signal carries a typed payload, every
  module declares typed inputs and outputs, and the platform reasons about
  type compatibility along the wires.

The platform additionally lets the user *simulate* a model (run it with mock
inputs, see what is emitted, write Python test scripts against it).

---

## 2. Core concepts

### 2.1 Modules

- A **module** represents a process. It has:
  - typed **input signals** and typed **output signals** (its interface),
  - an **implementation**, which is a **wire graph** of nodes connected by
    typed ports. Logic-bearing nodes may run **Python** (with `if`, `for`,
    `foreach`); composition with other modules is done with **submodule**
    nodes.
- Modules can **contain sub-modules**. Composition is recursive.
- **No circular dependencies** are allowed: if A uses B and B uses C, then C
  may not use A.
- When a sub-module appears on the parent's canvas, only its **inputs and
  outputs are shown** — the implementation is hidden. The user can
  **open / drill into** a sub-module to see and edit its implementation.

### 2.2 Signals, ports, and wires (data-flow model)

The execution model is **data-flow, not control-flow**. There are no
shared variables. All a node ever sees is **data arriving on one of its
inputs**; all a node ever does is **fire data out of one of its outputs**.

- A **module's interface** is its named, typed **input signals** and
  **output signals**. The interface is **derived from the canvas**:
  each `module_input` node on the canvas contributes one entry to the
  module's `inputs`, and each `module_output` node contributes one entry
  to its `outputs`. The node's `signal_name` and selected data type
  (edited from the properties panel) become the signal's name and type.
  There is no separate "Signals" catalog — the canvas is the single
  source of truth for a module's interface.
- Inside a module, every node declares **typed input ports** and **typed
  output ports**. A **wire** (edge) connects one output port of a source
  node to one input port of a target node, and so represents both *a path
  of execution* and *a path of data*.
- **Firing** an output port transfers control (and the carried value) to
  every node attached to that wire. Execution is synchronous and
  single-threaded — there is a single path of execution at any time.
- A node can be **paused** while it asks another node for data: an output
  port marked as a **request** is paired (`pair="<response_port>"`) with
  one of the node's input ports. Firing the request suspends the node
  until the paired response arrives.
- **Incoming signals can carry a filter** so they only trigger when the
  filter condition is met (e.g. `event.location == "Berlin"`).
- **Type compatibility is enforced.** Two ports with different data types
  may only be connected through an explicit **translation node** (a
  data-mapping node) that converts one type into the other.

### 2.3 Data types

Data types are a **first-class, global** concept — they are shared across
all modules, not owned by any one module.

- **Primitive types**: `int`, `decimal`, `string`, `bool`, `timestamp`,
  `any`.
- **Struct types**: named, hierarchical records made of fields, where each
  field has its own data type. Fields may themselves reference struct types,
  so types are arbitrarily nested.
- **Container types**: arrays and dictionaries, with an **explicit element
  type** (e.g. `StockItem[]`, `dict<string, Person>`).
- Data types are used **everywhere data is worked with** — signal payloads,
  variables, file I/O, database I/O, API responses, etc. There is one type
  system, used uniformly.

### 2.4 The canvas (WYSIWYG)

The reference look-and-feel is captured in the screenshot shared by the
owner in PR #1 (see "Berlin Warehouse" example below). Key visual rules:

- The **module currently being edited** is shown as a labelled dashed frame
  on the canvas (the example: `Berlin Warehouse`).
- **Sub-modules** appear as dashed boxes inside the frame, each showing
  their inputs (left) and outputs (right). In the example: `DHL Parcel
  Service` and `Move Stock Item`.
- **Event triggers** are chevron shapes labelled with the event name, the
  signal type in `[brackets]`, and any filter expression in parentheses,
  e.g. `Shipment arrived [ShipmentHandoverEvent] (if event.location == "Berlin")`.
- **For-each** nodes are vertical bars with an iterator expression
  (`foreach stockItem in event.contents`).
- **Edges/wires are labelled** with the signal name flowing along them
  (`shipmentArrivedEvent`, `stockItem`, `stockMoveEvent`, …).
- **Data-mapping nodes** show their mapping expressions inline, e.g.

  ```
  StockItemMoveEvent:
    stock_item = stockItem
    mover      = shipmentArrivedEvent.handed_to
    timestamp  = NOW
  ```
- **Global data types** are documented as small struct cards (above the
  canvas in the screenshot), each listing their fields with types — e.g.
  `ShipmentHandoverEvent { location (Location); delivery_note
  (DeliveryNote); contents (StockItem[]); handed_from (Person); handed_to
  (Person); timestamp (Timestamp) }`.

### 2.5 Node palette

The core executable palette is intentionally small — branching, looping,
and data-shaping are expressed *inside* `python` nodes (which support
`if`, `for`, and `foreach`), and composition is expressed via `submodule`
nodes. Richer palette entries (event-trigger, data-mapping, condition,
for-each, …) are layered on top of this core in later iterations.

| Symbol | Kind            | Purpose                                                                 |
| ------ | --------------- | ----------------------------------------------------------------------- |
|  ▷     | Module Input    | Source-only node; emits values arriving on a module input signal.       |
|  ◉     | Module Output   | Sink-only node; whatever arrives on its input becomes a module output.  |
|  λ     | Python          | Runs a sandboxed Python script. Reads `inputs[port]`; firing an output port is `outputs[port] = value`. Supports `if`, `for`, `foreach`. |
|  ⊞     | Sub-module      | Embeds another module; its declared signals appear as ports. Double-click to drill in. |

> Historical note: an earlier iteration used a control-flow palette of 8
> kinds (Start, Event Trigger, Condition, For Each, Sub-module, Emit
> Event, Data Mapping, End). That model was superseded by the wire-based
> data-flow model in §2.2 — the storage format was bumped to v2 and any
> v1 module files are rejected on load.

### 2.6 Simulation

- **Execution is always initiated through a single input signal.** To
  run a module the user picks one of the module's `inputs` and supplies
  a single value for it; the simulator fires only that input port and
  the run proceeds from there. There is no way to start a run by
  injecting several inputs simultaneously — running with a second value
  is a second, separate run.
- The same single-input contract is exposed identically by the **UI**
  (Run panel above the canvas), the **HTTP API**
  (`POST /api/modules/{id}/run` with `{input_signal, input_value}`) and
  the **MCP** tool (`run_module(module_id, input_signal, input_value)`).
- A run returns `{"outputs": {signal_name: [values…]}, "trace": […],
  "status": "complete"}`. An output may be fired multiple times in one
  run — the list preserves order.
- Execution is synchronous: firing a port walks every outgoing wire,
  activates the receiving node, and only returns once that activation
  (and any descendants) has completed.
- `python` nodes use **generator semantics**: the script body is driven
  step-by-step, and every `outputs[port] = value` assignment yields a
  fire event that the simulator dispatches. This is how a single Python
  node can fire multiple outputs in sequence while still being a single
  path of execution.
- The Python sandbox supports `if`, `for`, `foreach`, comparisons,
  boolean operators, arithmetic, kwargs in calls, and the read-only
  builtins `len`/`range`/`min`/`max`/`sum`. It rejects `import`,
  attribute access, `while`, `def`, `class`, augmented assignment,
  tuple-unpacking targets, and chained comparisons.
- Sub-module calls execute by opening a nested simulation frame; mocking
  by interface name is on the backlog.

### 2.7 Test scripts

The user can write Python test scripts (`/api/tests/run`) that:

- load modules (`load_module(...)`),
- run modules in isolation or composition
  (`run_module(module_id, input_signal, input_value)` — same
  single-input contract as the UI/API/MCP),
- mock interface dependencies (`mocks={"database": …}`),
- assert against the resulting state (`assert_equal(...)`).

---

## 3. Worked example — "Berlin Warehouse"

The canonical reference example (shared by the owner as a screenshot in
PR #1, comment immediately preceding commit `d5b6c79`):

![Berlin Warehouse reference diagram](docs/images/berlin-warehouse-reference.png)

> *Reference diagram for the "Berlin Warehouse" example. Source: PR #1
> comment by @ThomasHilbertAtCervis.
> Original attachment: <https://github.com/user-attachments/assets/dfbaa517-485a-41b1-acba-57d32acefbec>.*

- **Module being edited:** `Berlin Warehouse`.
- **Global types in scope:** `ShipmentHandoverEvent`, `StockItemMoveEvent`
  (and the supporting types they reference: `Location`, `DeliveryNote`,
  `StockItem`, `Person`, `Timestamp`).
- **Sub-modules used:** `DHL Parcel Service`, `Move Stock Item`.
- **Flow:**
  1. *Outside* the warehouse frame, `DHL Parcel Service` emits two events —
     `Shipment delivered [ShipmentHandoverEvent]` and `Shipment returned to
     sender [ShipmentHandoverEvent]` — into the warehouse via the wire
     `event`.
  2. The warehouse's first node is `Shipment arrived
     [ShipmentHandoverEvent]` with the filter
     `event.location == "Berlin"`. Only Berlin shipments proceed.
  3. A **for-each** iterates `stockItem in event.contents`.
  4. A **data-mapping node** builds a `StockItemMoveEvent` from the
     iterated `stockItem` and fields read from the triggering
     `shipmentArrivedEvent`.
  5. The mapped event is sent to the `Move Stock Item` sub-module; the
     sub-module returns a `StockItemMovedEvent`.
  6. Finally, "some other process" hands the shipment to a downstream
     consumer via `Hand over shipment to [ShipmentHandoverEvent]`.

Every later product decision should be checked against this example: can
this be modelled clearly? does the platform help me catch missing data or a
type mismatch?

---

## 4. Feature requests log

Each entry references the source comment, summarises the request, and
tracks status. Status uses ✅ done, 🚧 in progress, 📋 backlog,
🛑 superseded.

### From PR #1 (the inception PR for the playground)

| ID    | Source                                | Request                                                                                                   | Status |
| ----- | ------------------------------------- | --------------------------------------------------------------------------------------------------------- | ------ |
| F-001 | PR #1 initial scope                   | Browser-based playground for modular process simulation (modules, signals, simulation, Python tests).      | ✅     |
| F-002 | PR #1 comment — "Add a Dockerfile…"   | Provide a `Dockerfile` and document how to launch the app via Docker.                                      | ✅ (commit `3f83c66`) |
| F-003 | PR #1 comment with attached screenshot| WYSIWYG editor matching the "Berlin Warehouse" reference look (see §2.4 and §3).                          | ✅ (commit `d5b6c79`) |
| F-004 | Same comment                          | Modules have typed input/output signals; signals carry data types.                                         | ✅     |
| F-005 | Same comment                          | Incompatible signals can only be connected through **translation nodes** (data-mapping nodes).             | 🚧 — Data-mapping node exists; type-compatibility *enforcement* still to be added. |
| F-006 | Same comment                          | Platform must help the user spot **incompatible or missing data**.                                         | 📋     |
| F-007 | Same comment                          | Sub-modules show only inputs/outputs on the parent canvas; can be **opened** to edit implementation.       | ✅ — Submodule node renders signals; double-click opens. |
| F-008 | Same comment                          | A module's implementation may be either a **flow chart** or a **Python script**.                           | 🚧 — Flow chart ✅; Python-script-as-implementation ✅ via the `python` step; needs first-class "this whole module is a script" mode. |
| F-009 | Same comment                          | **No circular dependencies** between modules.                                                              | 📋 — Validation not yet enforced. |
| F-010 | Same comment                          | **Filters on incoming signals** — they only trigger when the condition is met.                             | ✅ — `filter` field on event/condition nodes. |
| F-011 | Same comment                          | Data types are **global** and hierarchical: primitives + structs of named fields + arrays/dicts with explicit element type. | ✅ |
| F-012 | Same comment                          | Use existing flow-chart libraries if they give a good UX and allow heavy customisation; otherwise build. | ✅ — React Flow chosen. |
| F-013 | PR #1 owner clarification             | Data types should be **global** (sidebar), not a per-module overlay.                                       | ✅ (commit `d5b6c79`) |
| F-014 | Repo state                            | Define clear architectural rules, separate concerns, no business logic in views, document the rules.       | ✅ — see `ARCHITECTURE.md`. |
| F-015 | Repo state                            | Add unit tests for all main components so behaviour doesn't deteriorate during ongoing development.        | ✅ — 132 tests across 8 files. |
| F-016 | PR #1 comment 4526108586              | **Track all feature requests and product descriptions in a file** so agents can always refer back to it.   | ✅ — this file. |
| F-017 | PR #1 comment 4528722855              | **Mirror every reference image the owner shares into the repo** and embed/link them from `PRODUCT.md`, so meaning is conveyed by the artwork instead of by description alone. | 🚧 — convention in place (`docs/images/`, §6); Berlin Warehouse image referenced. Local binary still to be committed (sandbox egress blocks the S3-backed user-attachment URL). |
| F-018 | PR #1 comment 4528891051              | **All relevant business logic must execute in the backend.** The frontend is one of many clients (an MCP server is planned so other agents can drive the platform). The UI must never own domain catalogs, normalisation rules, or default-template shapes. | ✅ — moved node-kinds catalog, primitive types, new-module template, and DataType normalisation to the backend behind `/api/node-kinds`, `/api/data-types/primitives`, `POST /api/modules`. ARCHITECTURE.md §1 Goal 6 codifies the rule. |
| F-019 | Owner direction, May 2026             | **Python steps must support `if`, `for`, and `foreach`** so non-trivial business logic (e.g. half-or-double) reads naturally instead of being expressed as a sequence of mini-steps. | ✅ — `SafeScriptInterpreter` allow-lists `If` and `For`; covered by tests. |
| F-020 | Owner direction, May 2026             | **Data-flow execution model.** Data flows along wires; there is no direct variable access. A node only ever receives values on its inputs and fires values on its outputs. Firing an output may suspend the node until a paired response arrives (request/response). Single path of execution, generator-style ergonomics for Python nodes. | ✅ — storage format bumped to v2, v1 files rejected on load; simulator rebuilt around frames + request/response handshake; demo `scripts/build_half_or_double.py` rewritten as `module_input → python (if/else) → module_output`. |
| F-021 | Owner direction, May 2026             | **Single-input execution contract.** *"Execution of any node or flow is always initiated through a single input. So for execution, we need to first select an input, then specify its value (based on its data type) and then start the execution. This should be possible through UI, Api and MCP."* | ✅ — `Simulator.run(module, *, input_signal, input_value)`; `POST /api/modules/{id}/run` takes `{input_signal, input_value}`; MCP `run_module(module_id, input_signal, input_value)`; UI Run panel above the canvas lets the user pick an input signal, enter a JSON value, and execute. |
| F-022 | Owner direction, May 2026             | *"there is currently a weird duplication: inputs/outputs are created through the palette AND through the model tab. It should only be possible through the palette by dragging the nodes onto the workflow. Name and data type should be parameters on the node."* | ✅ — `Module.inputs`/`outputs` are now **derived** from `module_input`/`module_output` nodes on the canvas (`models._derive_signals_from_nodes`, applied in both `from_dict` and `to_dict`). The Sidebar "Signals" tab is gone; the PropertiesPanel exposes a *Signal name* + *Data type* editor on those nodes, and palette drops seed a default port so the node is immediately connectable. |

### Cross-cutting / always-on requirements

| ID    | Requirement                                                                                                         |
| ----- | ------------------------------------------------------------------------------------------------------------------- |
| X-001 | Adhere to established best practices and the layering rules in `ARCHITECTURE.md`.                                   |
| X-002 | Aggressively fix architectural violations as they are noticed.                                                      |
| X-003 | Keep this document up to date — every new owner request goes in §4 with status, every clarification goes in §2/§3.  |

---

## 5. Open questions / things to clarify before building

These are not yet answered by the owner — leave them open and ask before
making large decisions.

- **Type-compatibility enforcement (F-005, F-006):** should the editor
  *prevent* an incompatible connection, *warn* about it, or *auto-insert*
  a translation node placeholder?
- **Script-as-implementation (F-008):** should a module choose its mode
  (flow vs script) up front, or can a flow optionally collapse to a single
  script step?
- **Circular-dependency detection (F-009):** detected at save time (block
  save), at design time (live warning), or at simulation time?
- **Persistence / multi-user:** today everything is JSON files under
  `storage/`. Is a database backend in scope later?

When in doubt, ask the owner on the PR rather than guessing.

---

## 6. Reference images

Every image the owner shares (PR comments, issues, discussions) is mirrored
into [`docs/images/`](docs/images/) so the description above is backed up by
the artwork the owner actually drew. See
[`docs/images/README.md`](docs/images/README.md) for the convention and how
to add new ones.

| File                                                             | Source                                                                                                          | Used in       | Shows                                                              |
| ---------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- | ------------- | ------------------------------------------------------------------ |
| [`docs/images/berlin-warehouse-reference.png`](docs/images/berlin-warehouse-reference.png) | PR #1 comment by @ThomasHilbertAtCervis ([attachment](https://github.com/user-attachments/assets/dfbaa517-485a-41b1-acba-57d32acefbec)) | §3 (this doc) | The "Berlin Warehouse" canonical WYSIWYG layout — module frame, sub-modules with input/output signals, typed signal wires, filtered event trigger, for-each, data-mapping node, global data-type cards. |
