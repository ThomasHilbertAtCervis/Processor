# Architecture

This document describes the architectural goals, layering rules and
non-negotiable constraints that govern this codebase. Every change to the
repository **must** be checked against these rules. When a rule no longer fits,
the rule is amended *first* in this document, in the same pull request that
changes the code.

## 1. Goals

1. **Modifiability.** Adding a new step type, a new node kind, a new persistence
   backend, or a new API endpoint must be a *local* change. Diffs that touch
   four layers to add one feature are a smell.
2. **Testability.** Every domain rule must be exercisable without spinning up
   FastAPI, without touching the file system, and without touching the browser.
3. **Substitutability.** Persistence, simulation, and scripting are dependencies
   that the API layer *receives*, not constructs. They can be replaced in tests
   and in future deployments.
4. **No business logic in views.** Routes and React components describe *what*
   the user sees and *which* service to call. They never decide *how* a module
   executes, *how* a JSON file is shaped, or *what* a default template contains.
5. **One source of truth per concern.** Persistence rules live in the
   repository layer. Execution rules live in the simulator. Wire-format rules
   live in the model classes. UI rules live in components.

## 2. Layers (backend)

The backend has four layers. Dependencies always point **downward**.

```
┌────────────────────────────────────────────────────────────────┐
│  API layer  (processor_playground/api.py, templates.py)        │
│  ─ FastAPI routes, Pydantic DTOs, composition root              │
│  ─ Translates HTTP ↔ service calls. No business logic.          │
└──────────────────────────────┬─────────────────────────────────┘
                               │ depends on
┌──────────────────────────────▼─────────────────────────────────┐
│  Service layer  (simulator.py, testing.py, scripting.py)       │
│  ─ Pure-Python business rules: how a module executes,           │
│    how a safe script is interpreted, how a test runs.           │
│  ─ Receives repositories via constructor. Never imports api.    │
└──────────────────────────────┬─────────────────────────────────┘
                               │ depends on
┌──────────────────────────────▼─────────────────────────────────┐
│  Repository layer  (repository.py, data_type_repository.py)    │
│  ─ Read/write domain objects to a backing store (today: JSON   │
│    files). Hides all I/O. Generic base in `_json_repository`.   │
└──────────────────────────────┬─────────────────────────────────┘
                               │ depends on
┌──────────────────────────────▼─────────────────────────────────┐
│  Domain model  (models.py)                                      │
│  ─ Dataclasses + serialization helpers. No I/O, no FastAPI,    │
│    no execution semantics. Pure data + light validation.        │
└────────────────────────────────────────────────────────────────┘
```

### Hard rules

- **`models.py` imports nothing from this package.** It is the leaf.
- **Repositories import only `models`.** They never know about FastAPI,
  simulation, or scripting.
- **Services (`simulator`, `scripting`, `testing`) import models and
  repositories, never the API.** A service must run inside a pytest unit
  test with zero HTTP scaffolding.
- **The API layer is a thin adapter.** It wires Pydantic DTOs to service
  calls and is the *only* place that knows about HTTP status codes.
- **No module-level mutable singletons inside route bodies.** A composition
  root at the bottom of `api.py` builds the default service graph; routes
  receive services through FastAPI `Depends`. Tests override these
  dependencies with `app.dependency_overrides`, never by mutating module
  globals.
- **Default templates, fixture data, and example payloads live in
  `templates.py`,** not inside route handlers.

## 3. Layers (frontend)

The frontend is intentionally small. It is split along the same separation of
concerns:

```
static/
├── app.js                ─ entry point: createRoot + <App/>
├── lib/
│   ├── html.js           ─ htm.bind(React.createElement); shared helpers
│   └── api.js            ─ HTTP client (the only file that calls fetch)
├── nodes.js              ─ ReactFlow node components + palette config
└── components.js         ─ Sidebar, PropertiesPanel, DataTypePanel,
                           ModuleSignalsPanel, DiagramCanvas, App
```

### Hard rules

- **Exactly one React instance.** Importmap pins explicit patch versions.
  Components import React from `'react'`, never from `'htm/react'` (that
  subpath bundles a second React copy and silently breaks hooks).
- **Only `lib/api.js` calls `fetch`.** Components receive callbacks and data;
  they do not know URLs.
- **No business defaults inside event handlers.** Default labels, default
  signal shapes, and palette content live as exported constants in
  `nodes.js`.
- **Components are stateless about persistence.** They render props and emit
  user intent via callbacks. The `App` component is the only place that
  decides when to `apiPut` / `apiDelete`.

## 4. Adding things — the cookbook

### A new flow step type (e.g. `wait_for_signal`)
1. Add a handler to `Simulator._STEP_HANDLERS` in `simulator.py`. Nothing else
   in the simulator needs to change.
2. Add a test in `tests/test_simulator.py` that exercises it.
3. *(Optional UI)* Add a node component in `static/nodes.js` and a palette entry.

### A new persisted entity (e.g. `Workflow`)
1. Add a dataclass + `from_dict`/`to_dict` to `models.py`.
2. Add a concrete repository in `processor_playground/repositories/` that
   inherits from `JsonRepository[Workflow]`. Implement nothing beyond a 3-line
   subclass.
3. Add a Pydantic DTO and routes in `api.py` that receive the repository via
   `Depends(get_workflow_repository)`.
4. Add tests at every layer.

### A new HTTP endpoint
1. Add the route to `api.py`. The function body must be ≤ ~10 lines: parse
   DTO → call a service → return its result.
2. If the body grows beyond that, the logic belongs in a service.

## 5. Forbidden patterns

These appear in pull requests from time to time. They are rejected on sight.

- ❌ `from processor_playground.api import repo` inside any non-API module.
- ❌ A FastAPI route that opens a file, parses JSON by hand, or runs a
      simulation step inline.
- ❌ A React component that hard-codes an API URL or path segment.
- ❌ A React component that imports another React copy
      (`'htm/react'`, `'react@17'`, etc.).
- ❌ A test that mutates a module-level singleton instead of using
      `app.dependency_overrides` or constructing its own service.
- ❌ An `if step_type == ...` chain growing inside `Simulator`. Extend
      `_STEP_HANDLERS` instead.

## 6. Testing strategy

- **Models:** round-trip `from_dict` / `to_dict`; legacy-format compatibility.
- **Repositories:** save → get → list → delete with a `tmp_path`.
- **Simulator:** one focused test per step type plus an unknown-step error
  test. Submodule mocking is exercised end-to-end.
- **Scripting:** every supported AST form (assignment, subscript, list, dict,
  tuple, compare, binop, call, assert) plus a representative sample of
  rejected forms (`import`, `for`, attribute access, augmented assign).
- **Test runner:** passing script, assertion failure, runtime error,
  unknown-module reference.
- **API:** every endpoint, using `app.dependency_overrides` to inject fresh
  repositories built on `tmp_path`. No test touches `processor_playground.api`
  module-level state.
- **Templates:** the default-module template must deserialize into a valid
  `Module`.

Every new feature must add tests at the layer it touches *and* one
black-box test at the API boundary if it is reachable from HTTP.
