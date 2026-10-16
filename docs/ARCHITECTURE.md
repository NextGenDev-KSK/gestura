# Architecture

Gestura is a **layered** application. Each layer depends only on the layer(s) below it, through
small, explicit interfaces. This keeps every module independently testable (150+ tests run with no
camera, GPU, or display) and makes the Windows-specific code swappable for a future Linux port.

```
┌─────────────────────────────────────────────────────────────┐
│ Presentation      gestura.app        Qt6/QML window, preview │
│                                       overlay, HUD, controller│
├─────────────────────────────────────────────────────────────┤
│ Application        gestura.engine.pipeline   threaded runner  │
│                                              + telemetry      │
├─────────────────────────────────────────────────────────────┤
│ Gesture Engine     gestura.engine    features → recognizers → │
│                                       interpreter → cursor     │
├─────────────────────────────────────────────────────────────┤
│ AI Recognition     gestura.vision    MediaPipe HandLandmarker │
│                    + camera          resilient capture        │
├─────────────────────────────────────────────────────────────┤
│ Action Dispatch    gestura.actions   gesture → action mapping │
├─────────────────────────────────────────────────────────────┤
│ OS Adapter         gestura.platform  Win32 SendInput, volume… │
└─────────────────────────────────────────────────────────────┘
        Cross-cutting: gestura.core (types, geometry, filters, timing),
                       gestura.config (typed settings), gestura.util (paths, logging)
```

## Data flow (one frame)

```
webcam ──► CameraSource ──► HandTracker ──► FrameResult
(capture thread)  │           (MediaPipe)      │
                  │ latest frame               ▼
                  └──────────────► GestureInterpreter
                                    │  • features (finger states, pinch dist, anchor)
                                    │  • static-pose recogniser
                                    │  • temporal state machine (hysteresis, gates,
                                    │    cooldowns, DRAG/SCROLL modes)
                                    │  • cursor mapping + One-Euro smoothing
                                    ▼
                         InterpretationResult (cursor pos + GestureEvents)
                                    │
                                    ▼
                         ActionDispatcher ──► OSAdapter ──► Windows
                                    │
                                    └──► on_update ──► AppController ──► QML (preview + HUD)
```

## Threading model

Three cooperating threads, chosen to keep the UI responsive and latency low:

1. **Capture thread** (`CameraSource`): continuously grabs frames, keeping only the newest, and
   auto-reconnects on device loss. Decouples camera I/O from processing so a slow consumer never
   sees stale frames.
2. **Engine thread** (`GesturePipeline._run`): owns the MediaPipe tracker (which is not
   thread-safe), runs tracking → interpretation → dispatch, and publishes telemetry. A watchdog
   wraps inference so a single bad frame can't kill the loop.
3. **GUI thread** (Qt): the `AppController` stashes the latest frame/telemetry under a lock; a
   ~30 Hz `QTimer` publishes it to QML. Qt objects are only ever touched here.

## Key design decisions

See [`DECISIONS.md`](DECISIONS.md) for the full ADR log. Highlights:

- **MediaPipe** for hand landmarks (offline, CPU-real-time, robust) — ADR-0002.
- **PySide6/QML** for a single-process, GPU-accelerated glass UI within the memory budget — 0004.
- **Win32 `SendInput` via ctypes** for lowest-latency, dependency-free input injection — 0005.
- **One-Euro filter** for cursor smoothing that's steady when still and low-lag when fast — 0006.
- **Prototype/k-NN** custom-gesture classifier: instant, offline, zero extra deps — 0003.

## Reliability & false-positive prevention

Trustworthiness is a *temporal* property, concentrated in
[`engine/interpreter.py`](../src/gestura/engine/interpreter.py) and the primitives in
[`core/timing.py`](../src/gestura/core/timing.py):

- **Hysteresis** on pinch distances (close/open at different thresholds) → no click chatter.
- **Stability gates**: a shape must persist briefly before it's accepted → no momentary misfires.
- **Cooldowns**: a held gesture can't machine-gun an action.
- **Exclusive modes**: while dragging/scrolling, unrelated triggers are suppressed; "pinch to
  click" is gated to poses where a pinch is unambiguous (never during a fist).
- **Tracking-loss recovery**: losing the hand cleanly releases held buttons and resets cursor
  smoothing so the pointer never leaps on re-acquire.
- **Click-immune cursor**: the pointer follows a knuckle midpoint, so pinching to click doesn't
  nudge the cursor.

## Module map

| Package | Responsibility |
|---------|----------------|
| `core` | Pure logic: domain types, geometry, filters, timing (no heavy deps) |
| `config` | Pydantic settings models + atomic, self-healing JSON store |
| `vision` | Threaded camera + MediaPipe tracker → typed `FrameResult` |
| `engine` | Features, recognizers, gesture catalogue, cursor + reach calibration, interpreter, custom classifier, pipeline (in-app recording, live camera restarts) |
| `actions` | Action registry (data-driven, declares which gesture kinds each action accepts) + dispatcher (owns pause) |
| `platform` | `OSAdapter` interface + Windows backend + `RecordingAdapter` (tests); global pause hotkey; start-with-Windows entry |
| `app` | Qt bootstrap (system tray, single instance, start minimized), `AppController` bridge, `CameraView`, QML UI |
| `util` | Cross-platform paths, logging |

## Extending

- **New action**: add one `ActionSpec` to `actions/registry.py`, declaring in `accepts` which
  `GestureKind`s can drive it. It appears in the gesture editor for every compatible gesture
  automatically.
- **New built-in gesture**: add a recogniser in `engine/recognizers.py` and handle it in the
  interpreter; list it (label, icon, `GestureKind`) in `engine/catalog.py`; bind it in
  `config/models.py::DEFAULT_BINDINGS` — and add a settings migration in `config/store.py` so
  existing installs receive it.

## Gesture kinds

A binding only works if the gesture emits the event phases its action listens for, so every
gesture declares a `GestureKind` (`core/types.py`) and every action declares the kinds it
accepts:

| Kind | Events | Gestures | Actions |
|------|--------|----------|---------|
| `TAP` | `BEGAN`+`ENDED` together | pinches, one-shot signs, custom | clicks, screenshot, media, window, shortcut, pause |
| `HOLD` | `BEGAN` … `ENDED` | fist | drag, plus everything a tap can do |
| `REPEAT` | repeated `UPDATED` | thumb up / down | volume, brightness |
| `SCROLL` | `UPDATED` with `dy` | two fingers | scroll |
| `ZOOM` | `UPDATED` with `scale` | two-hand pinch | zoom |

The gesture editor offers only compatible actions, and the controller rejects anything else.

## Settings migrations

`config/store.py` upgrades older `settings.json` files step by step (`_MIGRATIONS`), then saves
the result so each step runs once. v1 → v2 adds newly-introduced default gestures without
touching bindings the user already has, drops bindings to retired gestures, and enables two-hand
tracking for zoom.
- **New platform**: implement `platform/base.py::OSAdapter` for the OS and return it from
  `platform/__init__.py::get_adapter`. Nothing above the adapter changes.
