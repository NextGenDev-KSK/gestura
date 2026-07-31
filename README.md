<div align="center">

# Gestura

**Control your computer with your hands — fully offline, privacy-first.**

Gestura turns any webcam into a low-latency gesture controller: move the cursor, click,
scroll, zoom, adjust volume and brightness, manage windows, and fire your own custom
gestures — all processed locally on your machine. No cloud, no account, no telemetry.

*(Working title — the package name `gestura` is trivial to rename; see `docs/DEVELOPER_GUIDE.md`.)*

</div>

---

## Why Gestura

- **Offline by default.** Every frame is processed on-device with Google MediaPipe. Nothing
  leaves your computer.
- **Fast.** CPU-first pipeline targeting **60 FPS** capture and **< 20 ms** gesture-to-action
  latency, with an optional GPU delegate.
- **Trustworthy.** Aggressive false-positive prevention: temporal smoothing, confidence gating,
  per-gesture cooldowns, and tracking-loss recovery so the cursor never "jumps" or misclicks.
- **Yours.** Record, name, and bind your own gestures with no code. Multiple profiles.
- **Beautiful.** A native Qt6/QML interface with real glassmorphism, live camera preview,
  landmark overlay, and an FPS/confidence HUD.

## Status

Early development. The architecture, core pipeline, and Windows integration are the current
focus. See the roadmap in `docs/ARCHITECTURE.md` and progress in the repo's issues/milestones.

## Requirements

- Windows 10/11 (a Linux port is an explicit architectural goal; see the platform layer)
- Python 3.10 – 3.12
- A webcam

## Quick start (from source)

```powershell
git clone https://github.com/your-org/gestura
cd gestura
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python scripts\fetch_models.py      # downloads the MediaPipe hand-landmark model
gestura                             # launch the app
```

Run the headless pipeline smoke test (no UI, proves camera → tracking → cursor):

```powershell
python -m gestura.engine.pipeline --demo
```

## Architecture at a glance

```
Presentation (Qt6/QML)  ─┐
Application (controller) ─┤   each layer depends only on the one below,
Gesture Engine           ─┤   through explicit interfaces — see ARCHITECTURE.md
AI Recognition (MediaPipe)┤
Gesture Interpreter      ─┤
Action Dispatcher        ─┤
OS Adapter (Windows)     ─┘
```

## Documentation

| Doc | Purpose |
|-----|---------|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | System design, layers, data flow |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Architecture Decision Records (why each library) |
| [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md) | Installing and using the app |
| [`docs/DEVELOPER_GUIDE.md`](docs/DEVELOPER_GUIDE.md) | Building, testing, extending |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | How to contribute |

## License

Apache License 2.0 — see [`LICENSE`](LICENSE).
