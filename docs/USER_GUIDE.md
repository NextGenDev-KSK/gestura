# User guide

## Installing

**Option A — installer (recommended).** Download `GesturaSetup.exe` from the Releases page and run
it. Launch Gestura from the Start menu.

**Option B — from source.**

```powershell
git clone https://github.com/your-org/gestura
cd gestura
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
python scripts\fetch_models.py
gestura
```

## First run

1. Allow camera access if Windows prompts.
2. Sit an arm's length from the webcam in reasonable light (see *Troubleshooting* for low-light
   frame-rate tips).
3. Raise your hand — you'll see the live skeleton overlay on the camera preview and the FPS /
   latency / confidence readouts update.

## Built-in gestures

| Gesture | Action |
|---------|--------|
| Move your hand (index/middle knuckles) | Move the cursor |
| **Pinch** index + thumb | Left click |
| **Pinch** middle + thumb (index out) | Right click |
| Two quick pinches | Double-click (via the OS) |
| **Fist** (hold) | Drag — grabs on close, drops on open |
| **Two fingers** (index + middle), move up/down | Scroll |
| **Thumb up / thumb down** | Volume up / down |
| **Open palm**, hold ~0.8 s | Pause / resume all control |

Tips:
- The cursor follows your **knuckles**, not your fingertip, so pinching to click never moves it.
- If control ever feels wrong, hold an open palm to **pause** instantly.

## The window

- **Camera card** — live preview + skeleton, with a status dot (green = streaming, amber =
  reconnecting, red = disconnected) and a badge showing the current pose or PAUSED.
- **Pause / Resume** — big button; also bound to the open-palm gesture.
- **Stat tiles** — frame rate, latency, mode (Idle/Drag/Scroll), and hand-tracked state.
- **Confidence meter** — detection confidence of the current hand.
- **Theme toggle** — light / dark (🌓 in the title bar).

## Custom gestures (the trainer)

Record your own static hand shapes and bind them to actions — fully offline.

```powershell
python scripts\record_gesture.py --name peace --samples 40
```

Hold the shape steady during the countdown and capture. Then bind it. Until the in-app editor
ships you can add a binding to `settings.json` (see below), e.g.:

```json
{ "gesture": "peace", "action": "screenshot" }
```

Available actions include: `left_click`, `right_click`, `middle_click`, `double_click`, `drag`,
`scroll`, `volume_up`, `volume_down`, `brightness_up`, `brightness_down`, `screenshot`,
`media_play_pause`, `media_next`, `media_prev`, `window_minimize`, `window_maximize`,
`window_snap_left`, `window_snap_right`, `window_close`, `switch_window`, `show_desktop`,
`pause_toggle`.

## Where your data lives

- **Settings:** `%APPDATA%\Gestura\settings.json`
- **Custom gestures:** `%LOCALAPPDATA%\Gestura\custom_gestures.json`
- **Screenshots:** `%LOCALAPPDATA%\Gestura\screenshots\`
- **Logs:** `%LOCALAPPDATA%\Gestura\logs\gestura.log`

Everything is local. Gestura makes no network connections.

## Troubleshooting

- **Low / choppy frame rate.** Usually lighting — a webcam lengthens exposure in the dark, which
  drops FPS. Add light. Gestura already uses 640×480 + MJPG for speed (see
  [`PERFORMANCE.md`](PERFORMANCE.md)).
- **Camera won't start / "reconnecting".** Close other apps using the webcam (Teams, Zoom). The
  status dot goes green once it recovers.
- **Cursor too jittery / too laggy.** Tune `cursor.smoothing_min_cutoff` (lower = steadier) and
  `cursor.smoothing_beta` (higher = less lag) in `settings.json`.
- **Accidental clicks.** Raise `thresholds.pinch_on` slightly, or increase
  `thresholds.stability_time`.
- **Brightness does nothing.** Many external monitors don't support software (DDC/CI) brightness.
- **Diagnostics.** Run `python scripts\diagnose.py` for a camera + tracker health/perf report.
