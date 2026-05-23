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

- `processor_playground/models.py`: module model
- `processor_playground/repository.py`: JSON persistence layer
- `processor_playground/simulator.py`: simulation engine
- `processor_playground/testing.py`: Python script test runner
- `processor_playground/api.py`: FastAPI API + static UI host
- `processor_playground/static/index.html`: browser playground

## Run

```bash
pip install -e .[dev]
python -m uvicorn processor_playground.api:app --host 0.0.0.0 --port 8000
```

Then open `http://localhost:8000`.

## Test

```bash
pytest
```

## Example script test

```python
result = run_module("example-module", mocks={"database": {"rows": 3}})
assert_equal(result["status"] if "status" in result else "ok", "ok")
```
