# Developer guide

## Setup

```powershell
git clone https://github.com/your-org/gestura
cd gestura
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python scripts\fetch_models.py
```

Requires Python 3.10–3.12.

## Day-to-day commands

| Task | Command |
|------|---------|
| Run the app | `gestura` (or `python -m gestura`) |
| Run the app, no real input | `python -m gestura --dry-run` |
| Verify the UI loads (no camera) | `python -m gestura --self-test 2` |
| Headless engine demo | `python -m gestura.engine.pipeline --demo` |
| Hardware/perf diagnostics | `python scripts\diagnose.py` |
| Record a custom gesture | `python scripts\record_gesture.py --name NAME` |
| Tests | `pytest` |
| Tests + coverage | `pytest --cov=gestura --cov-report=term-missing` |
| Lint | `ruff check src tests scripts` |
| Auto-fix lint | `ruff check --fix src tests scripts` |
| Types | `mypy` |

## Testing philosophy

The whole engine is testable **without hardware**. Synthetic hands are built in
`tests/conftest.py` (`make_hand("pinch")`, `make_frame(...)`), and the OS layer has a
`RecordingAdapter` that records intended actions instead of performing them. The pipeline accepts
an injected fake camera + tracker, so even end-to-end orchestration is deterministic. Integration
tests that need real hardware are marked `@pytest.mark.integration` (skipped by default in CI).

Run only fast unit tests: `pytest tests/unit`.

## Code standards

- **Type hints** everywhere; `mypy` runs in `strict` mode (third-party stubs are excluded).
- **Docstrings** on public modules/classes/functions explaining the *why*.
- **Ruff** enforces style (E/F/I/N/UP/B/SIM/RUF). Keep it green.
- **No hot-path allocations**: the per-frame loop uses `slots` dataclasses and preallocated arrays.
- **Layering**: never import a higher layer from a lower one (see `ARCHITECTURE.md`). `core` and
  `config` must stay dependency-light.

## Common extension points

- **Add an action** → one `ActionSpec` in `actions/registry.py`.
- **Add a built-in gesture** → recogniser in `engine/recognizers.py`, handling in
  `engine/interpreter.py`, default binding in `config/models.py`.
- **Tune recognition** → `GestureThresholds` / `CursorConfig` in `config/models.py` (all live in
  `settings.json` and hot-reload via `pipeline.apply_settings`).
- **Port to another OS** → implement `platform/base.py::OSAdapter`, wire it in
  `platform/__init__.py::get_adapter`. Everything above is platform-agnostic.

## Renaming the project

The package is `gestura`. To rename: change `[project].name` and `[project.scripts]` in
`pyproject.toml`, rename `src/gestura/`, update `APP_NAME` in `util/paths.py`, the QML module name
(`QML_IMPORT_NAME` in `app/camera_view.py` + `import Gestura` in the QML), and the packaging files.

## Building a release

See [`RELEASE.md`](RELEASE.md). In short: `python scripts\build_exe.py` →
`iscc packaging\gestura_installer.iss`.
