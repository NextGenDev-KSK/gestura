# Architecture

Gestura is a **layered** application. Each layer depends only on the layer(s) below it, through
small, explicit interfaces. This keeps every module independently testable (85+ tests run with no
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
| `engine` | Features, recognizers, cursor, interpreter, custom classifier, pipeline |
| `actions` | Action registry (data-driven) + dispatcher (owns pause) |
| `platform` | `OSAdapter` interface + Windows backend + `RecordingAdapter` (tests) |
| `app` | Qt bootstrap, `AppController` bridge, `CameraView`, QML UI |
| `util` | Cross-platform paths, logging |

## Extending

- **New action**: add one `ActionSpec` to `actions/registry.py`. It appears in the settings list
  automatically.
- **New built-in gesture**: add a recogniser in `engine/recognizers.py` and handle it in the
  interpreter; bind it in `config/models.py::DEFAULT_BINDINGS`.
- **New platform**: implement `platform/base.py::OSAdapter` for the OS and return it from
  `platform/__init__.py::get_adapter`. Nothing above the adapter changes.
