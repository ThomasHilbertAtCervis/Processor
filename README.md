# Processor Playground

A browser-based playground for modeling executable processes as nested modules.

## Features

- **Module-oriented modeling**: every process is a module with interfaces (`inputs`, `outputs`).
- **Composition**: modules may contain submodules recursively.
- **Persistence**: modules are stored as JSON under `storage/modules`.
- **Simulation runtime**: run modules manually (Play button / API) with support for:
  - variables
  - datastore read/write
  - file read/write emulation
  - output/events
  - dialogs/printing
  - email/api call emulation
  - Python-backed flow steps
- **Python script tests**: execute test scripts via API (`/api/tests/run`) that can:
  - load modules
  - run modules in isolation or composition
  - mock interface dependencies in `run_submodule` steps

## Architecture

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the architectural goals, layering
rules, and the do/don't list. **Read it before adding features.**

For the **product vision, the feature-request log, and "what is this software
supposed to do"**, see [`PRODUCT.md`](PRODUCT.md). Read it before *deciding*
what to build.

Layout at a glance:

- `processor_playground/models.py` — domain dataclasses (leaf, no I/O)
- `processor_playground/_json_repository.py` — generic JSON repository base
- `processor_playground/repository.py` / `data_type_repository.py` — thin concrete repositories
- `processor_playground/scripting.py` — safe AST-based Python interpreter
- `processor_playground/simulator.py` — simulation engine (step-handler registry)
- `processor_playground/testing.py` — Python script test runner
- `processor_playground/templates.py` — default/example payloads
- `processor_playground/api.py` — FastAPI routes + composition root (thin adapter)
- `processor_playground/static/` — frontend (entry `app.js`; `lib/`, `nodes.js`, `components.js`)

## Run

```bash
pip install -e .[dev]
python -m uvicorn processor_playground.api:app --host 0.0.0.0 --port 8000
```

Then open `http://localhost:8000`.

## Run MCP server (stdio)

The repository now includes an MCP server exposing the same backend capabilities
as the HTTP API (module/data-type CRUD, simulation, templates, catalogs, script
testing, health).

```bash
python -m processor_playground.mcp_server
```

Optional environment variables (useful for isolated agent/test runs):

- `PROCESSOR_PLAYGROUND_STORAGE_DIR` — modules storage directory
- `PROCESSOR_PLAYGROUND_DATA_TYPES_DIR` — data-types storage directory

## Run with Docker

Build the image:

```bash
docker build -t processor-playground .
```

Start the container (module definitions are persisted in a named volume so they survive restarts):

```bash
docker run -d \
  --name processor-playground \
  -p 8000:8000 \
  -v processor-playground-storage:/app/storage \
  processor-playground
```

Then open `http://localhost:8000`.

To stop and remove the container:

```bash
docker stop processor-playground && docker rm processor-playground
```

## Run in VS Code Dev Container

This repository includes `.devcontainer/devcontainer.json`, so you can launch it directly in VS Code.

1. Open the folder in VS Code.
2. Run **Dev Containers: Reopen in Container** from the Command Palette.
3. Once the container is created, dependencies are installed automatically via `pip install -e .[dev]`.
4. Start the API:

```bash
python -m uvicorn processor_playground.api:app --host 0.0.0.0 --port 8000
```

VS Code forwards port `8000` and will open the app in your browser.

If you opened the container before this devcontainer setup was updated, run **Dev Containers: Rebuild Container** once. If `python -m uvicorn ...` still reports `No module named uvicorn`, run the server with:

```bash
python3.11 -m uvicorn processor_playground.api:app --host 0.0.0.0 --port 8000
```

## Test

```bash
pytest
```

## Example script test

```python
result = run_module("example-module", mocks={"database": {"rows": 3}})
assert_equal(result["status"] if "status" in result else "ok", "ok")
```
