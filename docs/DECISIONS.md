# Architecture Decision Records

Each ADR states the decision, the alternatives considered, and the rationale. Per the project's
Technology Selection Rules, **no dependency is added without a justification here.**

---

## ADR-0001 — Language: Python

**Decision.** Python 3.10–3.12 for the whole application.

**Alternatives.** C++ (max performance, but slow iteration, painful UI); C#/.NET + WPF (great
Windows UI, but weaker CV ecosystem, no first-class MediaPipe); Rust (excellent, but immature CV
bindings and steep gesture-ML tooling).

**Rationale.** The best-in-class hand-tracking stack (MediaPipe) is Python-first, and the CV/ML
ecosystem (NumPy, ONNX Runtime) is unrivaled for iteration speed. The real-time budget is met by
keeping the hot loop free of per-frame allocations and delegating heavy math to native code
(MediaPipe/OpenCV/NumPy are C++ under the hood). Where Python's GIL matters, capture, inference,
and UI run on separate threads.

---

## ADR-0002 — Vision & AI: MediaPipe Tasks (HandLandmarker)

**Decision.** Google MediaPipe `HandLandmarker` for 21-point hand landmarks.

**Alternatives.** OpenCV cascade/contour heuristics (brittle, no per-joint data); training a
custom CNN (huge data/eng cost, worse than MediaPipe); commercial SDKs (not offline, licensing).

**Rationale.** MediaPipe is offline, Apache-2.0, real-time on CPU, robust across lighting/skin
tones, and exposes normalized 3D landmarks + handedness + confidence — exactly the signal the
gesture engine needs. An optional GPU delegate is available without code changes to consumers.

---

## ADR-0003 — Custom-gesture classifier: prototype / nearest-neighbour

**Decision.** User-recorded gestures are recognised by a **nearest-prototype (k-NN) classifier**
over a normalized 42-D landmark feature vector (translation/scale/rotation invariant). "Training"
is simply storing the recorded example vectors; recognition is a nearest-neighbour distance test.

**Alternatives.** ONNX Runtime + a trained MLP (the original plan) — needs a training framework to
produce the model, adds a runtime dependency, and is overkill for static hand shapes; bundling
PyTorch/TF at runtime (heavy, blows the memory budget); rule-based only (can't learn arbitrary
user gestures).

**Rationale.** For static custom poses, a prototype classifier is *instant* to train, fully
offline, explainable ("nearest to your recorded ‘peace’ example"), needs **zero extra
dependencies** (just NumPy), and is easy to tune with a single distance threshold. The feature
normalization makes a gesture recognisable regardless of hand position, distance, or in-plane
rotation. This supersedes the earlier ONNX plan — we do not ship an unused inference runtime.
(A learned classifier can be revisited if dynamic, motion-based custom gestures are added.)

---

## ADR-0004 — UI: PySide6 (Qt6) + QML

**Decision.** PySide6 with a QML/Qt Quick front end.

**Alternatives.** Tauri (best web-CSS glassmorphism, but adds a Rust toolchain + a Python↔web IPC
boundary); Electron (familiar, but heavy baseline RAM fights the < 500 MB budget); Dear ImGui
(fast, but not the polished, themable look required); Tkinter (not commercial-grade).

**Rationale.** QML is GPU-accelerated (scene graph), supports real blur/shader effects for
glassmorphism, and native Windows Mica/Acrylic via the platform layer. Staying in one language
keeps the real-time engine and UI in the same process with zero IPC serialization, and PySide6's
LGPL license is friendly to both open-source and commercial distribution.

---

## ADR-0005 — Input synthesis: Win32 `SendInput` via `ctypes`

**Decision.** Cursor motion, clicks, scroll, and media/volume keys are injected with the Win32
`SendInput` API called directly through `ctypes`.

**Alternatives.** `pyautogui`/`pynput` (convenient, but add latency, use the slower legacy
`mouse_event`/`keybd_event`, and pull in extra deps).

**Rationale.** `SendInput` is the lowest-latency, most reliable injection path and supports
absolute cursor positioning, high-resolution scroll, and extended keys in a single batched call —
directly serving the < 20 ms latency and "no cursor jump" reliability goals. No extra dependency.

---

## ADR-0006 — Cursor smoothing: One-Euro Filter

**Decision.** The 1€ (One-Euro) filter for pointer smoothing.

**Alternatives.** Simple EMA (either laggy or jittery — can't have both); Kalman filter
(overkill, harder to tune, more latency).

**Rationale.** The 1€ filter is the standard for interactive pointing: it adapts its cutoff to
speed, giving rock-steady precision when the hand is still and low lag when it moves fast — the
exact trade-off cursor control needs. It's ~40 lines, dependency-free, and easy to tune.

---

## ADR-0007 — Configuration: Pydantic v2 + JSON in `%APPDATA%`

**Decision.** Typed Pydantic models, persisted as JSON under the OS user-config dir.

**Alternatives.** Raw `configparser`/TOML (no validation/migration), a database (overkill).

**Rationale.** Pydantic gives validation, defaults, and versioned schema migration for free, and
JSON round-trips losslessly for the gesture editor. Config lives in the per-user config directory
so it survives reinstalls and never needs admin rights.
