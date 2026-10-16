# User guide

## Installing

**Option A — installer (recommended).** Download `GesturaSetup-<version>.exe` from the
[Releases page](https://github.com/NextGenDev-KSK/gestura/releases/latest) and run it. It installs
for your Windows account without needing admin rights (the wizard can install for all users
instead). Launch Gestura from the Start menu; uninstall it from *Settings → Apps*. Your settings
are kept on uninstall.

Windows may show *"Windows protected your PC"* the first time, because the app isn't code-signed yet. Click **More info → Run anyway**.

**Portable.** Prefer not to install? Download `Gestura-<version>-windows-x64-portable.zip`, extract
it anywhere, and run `Gestura\Gestura.exe`.

**Option B — from source.**

```powershell
git clone https://github.com/NextGenDev-KSK/gestura
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

Each sign uses a distinct hand shape, so they don't get confused with one another. The three
pinches are told apart by **which finger meets the thumb**; the four thumb signs by **which way
the thumb points** (a diagonal thumb is deliberately ignored).

| Gesture | Action |
|---------|--------|
| Move your hand (index/middle knuckles) | Move the cursor |
| **Pinch** — index + thumb | Left click |
| **Pinch** — middle + thumb (index out) | Right click |
| **Pinch** — pinky + thumb (index out) | Middle click |
| Two quick index pinches | Double-click (via the OS) |
| **Fist** (hold) | Drag — grabs on close, drops on open |
| **Two fingers** (index + middle), move up/down | Scroll |
| **Two-hand pinch** — pinch with both hands, move them apart / together | Zoom in / out (Ctrl + wheel) |
| **Rock** 🤘 (index + pinky) | Switch window (Alt-Tab) |
| **Three fingers** (index + middle + ring) | Screenshot |
| **Pinky** only | Media play / pause |
| **Thumb up** (fist, thumb ↑) | Volume up |
| **Thumb down** (fist, thumb ↓) | Volume down |
| **Thumb left** (fist, thumb ←) | Previous track |
| **Thumb right** (fist, thumb →) | Next track |
| **Open palm** | Neutral — a natural rest pose that does nothing |

Tips:
- The cursor follows your **knuckles**, not your fingertip, so pinching to click never moves it.
- Every sign is a *deliberately distinct* shape; hold it briefly and steadily to trigger. One-shot
  signs (screenshot, switch window, media) fire once and re-arm only after you drop the pose.
- Want more? The **gesture trainer** lets you record your own signs — see below.

Every row above is just the default — rebind any of them in the **Gestures** panel (below).

> **Changed from earlier builds:** the open-palm "pause" hold was removed (open palm is now just a
> neutral rest pose). Pause/resume lives on the in-app button and can be re-bound to any gesture.
> Settings saved by older builds are upgraded automatically on first launch: new gestures are
> added, the retired open-palm binding is dropped, two-hand tracking is switched on, and
> everything you had changed is kept.

## The window

- **Camera card** — live preview + skeleton, with a status dot (green = streaming, amber =
  reconnecting, red = disconnected) and a badge showing the current pose or PAUSED.
- **Pause / Resume** — big button (the instant kill-switch for all control).
- **Stat tiles** — frame rate, latency, mode (Idle/Drag/Scroll), and hand-tracked state.
- **Confidence meter** — detection confidence of the current hand.
- **Gestures list** — what each active gesture currently does; **Edit ›** opens the editor.
- **✋ Gestures** — the gesture editor and trainer (below).
- **⚙ Settings** — searchable camera, cursor, recognition, startup and interface settings,
  applied live.
- **Theme toggle** — light / dark (🌓 in the title bar).
- **✕** — hides the window; gesture control keeps running in the system tray (see below).

## Running in the background

Gestura is meant to stay out of your way:

- **Closing the window doesn't stop it.** Gesture control keeps running and Gestura sits in the
  system tray. The tray icon is coloured while control is on and grey with a pause symbol while
  paused. Click it to bring the window back; right-click for *Pause/Resume* and *Quit Gestura*.
  (Prefer closing to quit? Turn off *Keep running in the tray when closed* in Settings.)
- **Ctrl+Alt+G pauses or resumes from anywhere**, even when the window is hidden. If a gesture
  ever misbehaves, the keyboard always gets you back in control. Change the keys under
  Settings → Background & startup (it needs Ctrl, Alt, Shift or Win plus one key).
- **Start with Windows** (Settings → Background & startup) starts Gestura quietly in the tray when
  you sign in. *Start minimized to the tray* does the same for every launch.
- **Only one copy runs.** Opening Gestura again while it's running just brings its window forward.

## Calibrating your reach

The cursor follows the part of the camera image your hand moves in, and that part is stretched
over the whole screen. By default it's the middle of the frame. Calibration fits it to *you*:

1. Settings → Cursor → **Calibrate**.
2. For about six seconds, slowly sweep your hand left, right, up and down over the area that feels
   comfortable. Nothing gets clicked while you do this.
3. Done: that area now covers the whole screen. The camera preview shows it as a dashed frame.

Re-run it if you change where you sit; **Reset** goes back to the default area.

## Choosing a camera

Settings → Camera lists your webcams (press **Detect** after plugging one in) and switches
between them live. *Mirror camera* and *Show camera preview* are there too. With the preview off,
gesture control keeps running and Gestura does less work per frame.

## Changing what gestures do (the gesture editor)

Click **✋** in the title bar (or **Edit ›** on the gestures list). Every gesture has a card:

- **Action picker** — choose what the gesture does, or *Not bound* to switch it off entirely.
  Only actions the gesture can actually drive are listed: a *held* fist can drag, the thumb
  up/down signs *repeat* while held (volume, brightness), two fingers scroll, the two-hand pinch
  zooms, and everything else fires once (clicks, screenshot, media, windows, shortcuts…).
- **On/off switch** — temporarily disable a gesture without losing its binding.
- **Keyboard shortcut** — pick this action, type the keys joined with `+` (for example
  `ctrl+shift+s`, `alt+f4`, `win+d`, `ctrl+alt+t`) and press **Enter**. Accepted keys: letters,
  digits, `ctrl` `alt` `shift` `win`, `tab` `enter` `esc` `space` `backspace` `delete` `insert`
  `home` `end` `pageup` `pagedown`, the arrows `left` `up` `right` `down`, `printscreen`,
  `f1`–`f12`, and the media/volume keys. An unknown key is rejected with a message rather than
  saved.
- **Reset to default gestures** restores the built-in map (your recorded gestures are kept).

Changes apply instantly and are saved automatically.

## Custom gestures (the trainer)

Teach Gestura your own static hand shapes — fully offline.

1. Open **✋ Gestures** and scroll to **Teach a new gesture**.
2. Type a name (for example *peace sign*) and press **● Record**.
3. After the 3-2-1 countdown, hold the shape steady in view. Gestura captures 40 frames (about a
   second) and saves the gesture. Nothing you do while recording triggers an action.
4. The new gesture appears in the list — choose its action.

Recording a name that already exists replaces its samples, which is the fix if a gesture
misfires. Delete a custom gesture with its 🗑 button. You can also record from a terminal:

```powershell
python scripts\record_gesture.py --name peace --samples 40
```

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
- **Hard to reach the screen edges, or the cursor feels too fast.** Run *Calibrate* (Settings →
  Cursor) from where you normally sit.
- **Cursor too jittery / too laggy.** Adjust *Smoothing* (steadier) and *Responsiveness* (less
  lag) in Settings → Cursor.
- **Ctrl+Alt+G doesn't work.** Another app already uses it; Settings → Background & startup shows
  this. Pick a different combination there.
- **Accidental clicks.** Raise `thresholds.pinch_on` slightly, or increase
  `thresholds.stability_time`.
- **Brightness does nothing.** Many external monitors don't support software (DDC/CI) brightness.
- **Diagnostics.** Run `python scripts\diagnose.py` for a camera + tracker health/perf report.
