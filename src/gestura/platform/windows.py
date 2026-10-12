"""Windows implementation of :class:`OSAdapter` (ADR-0005).

Input (cursor, clicks, scroll, keys) is injected through the Win32 ``SendInput`` API called
directly via ``ctypes`` — the lowest-latency, most reliable path, batching a full gesture
(e.g. down+up for a click) into one syscall. Volume uses the Core Audio endpoint through pycaw,
brightness uses ``screen_brightness_control`` (DDC/CI), and screen capture uses Pillow's
``ImageGrab``. Window management uses ``user32`` directly.

Everything degrades gracefully: a monitor that doesn't support DDC brightness, or a machine with
no default audio endpoint, logs a warning instead of raising into the gesture loop.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from datetime import datetime, timezone

from ..core.geometry import clamp
from ..util.logging import get_logger
from ..util.paths import data_dir
from .base import MediaAction, MouseButton, OSAdapter, WindowAction

_log = get_logger("gestura.platform.windows")

user32 = ctypes.WinDLL("user32", use_last_error=True)

# --- SendInput plumbing -----------------------------------------------------------------------
_INPUT_MOUSE = 0
_INPUT_KEYBOARD = 1

_MOUSEEVENTF_MOVE = 0x0001
_MOUSEEVENTF_LEFTDOWN = 0x0002
_MOUSEEVENTF_LEFTUP = 0x0004
_MOUSEEVENTF_RIGHTDOWN = 0x0008
_MOUSEEVENTF_RIGHTUP = 0x0010
_MOUSEEVENTF_MIDDLEDOWN = 0x0020
_MOUSEEVENTF_MIDDLEUP = 0x0040
_MOUSEEVENTF_WHEEL = 0x0800
_MOUSEEVENTF_HWHEEL = 0x1000
_MOUSEEVENTF_ABSOLUTE = 0x8000
_MOUSEEVENTF_VIRTUALDESK = 0x4000
_WHEEL_DELTA = 120

_KEYEVENTF_EXTENDEDKEY = 0x0001
_KEYEVENTF_KEYUP = 0x0002

_SM_XVIRTUALSCREEN = 76
_SM_YVIRTUALSCREEN = 77
_SM_CXVIRTUALSCREEN = 78
_SM_CYVIRTUALSCREEN = 79

_SW_MAXIMIZE = 3
_SW_MINIMIZE = 6
_SW_RESTORE = 9


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


def _send(*inputs: _INPUT) -> None:
    n = len(inputs)
    arr = (_INPUT * n)(*inputs)
    sent = user32.SendInput(n, arr, ctypes.sizeof(_INPUT))
    if sent != n:
        raise ctypes.WinError(ctypes.get_last_error())


def _mouse_input(flags: int, dx: int = 0, dy: int = 0, data: int = 0) -> _INPUT:
    mi = _MOUSEINPUT(dx, dy, data & 0xFFFFFFFF, flags, 0, 0)
    return _INPUT(_INPUT_MOUSE, _INPUTUNION(mi=mi))


def _key_input(vk: int, up: bool, extended: bool) -> _INPUT:
    flags = 0
    if extended:
        flags |= _KEYEVENTF_EXTENDEDKEY
    if up:
        flags |= _KEYEVENTF_KEYUP
    ki = _KEYBDINPUT(vk, 0, flags, 0, 0)
    return _INPUT(_INPUT_KEYBOARD, _INPUTUNION(ki=ki))


# --- Virtual-key map --------------------------------------------------------------------------
_VK = {
    "ctrl": 0x11, "control": 0x11, "alt": 0x12, "shift": 0x10,
    "win": 0x5B, "super": 0x5B, "meta": 0x5B, "cmd": 0x5B,
    "tab": 0x09, "enter": 0x0D, "return": 0x0D, "esc": 0x1B, "escape": 0x1B,
    "space": 0x20, "backspace": 0x08, "delete": 0x2E, "del": 0x2E, "insert": 0x2D,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "printscreen": 0x2C, "prtscn": 0x2C,
    "volume_up": 0xAF, "volume_down": 0xAE, "volume_mute": 0xAD,
    "media_next": 0xB0, "media_prev": 0xB1, "media_stop": 0xB2, "media_play_pause": 0xB3,
}
for _i in range(1, 13):  # F1..F12
    _VK[f"f{_i}"] = 0x70 + (_i - 1)

# Keys that must carry the EXTENDEDKEY flag for correct behaviour.
_EXTENDED = {0x25, 0x26, 0x27, 0x28, 0x2E, 0x2D, 0x24, 0x23, 0x21, 0x22, 0x2C,
             0xAF, 0xAE, 0xAD, 0xB0, 0xB1, 0xB2, 0xB3}


def _resolve_vk(key: str) -> int:
    key = key.lower()
    if key in _VK:
        return _VK[key]
    # Virtual-key codes equal the ASCII code only for A-Z and 0-9. Punctuation does NOT map this
    # way (e.g. ord(',') == 0x2C is VK_SNAPSHOT / PrintScreen), so it's rejected rather than
    # silently pressing the wrong key.
    if len(key) == 1 and key.isascii() and key.isalnum():
        return ord(key.upper())
    raise KeyError(f"unknown key {key!r}")


class WindowsAdapter(OSAdapter):
    """Concrete OS control for Windows 10/11."""

    def __init__(self) -> None:
        self._volume = None
        self._volume_failed = False
        self._screens_dir = data_dir() / "screenshots"

    # -- geometry ------------------------------------------------------------------------------
    def screen_size(self) -> tuple[int, int]:
        w = user32.GetSystemMetrics(_SM_CXVIRTUALSCREEN)
        h = user32.GetSystemMetrics(_SM_CYVIRTUALSCREEN)
        return int(w), int(h)

    # -- pointer -------------------------------------------------------------------------------
    def move_cursor(self, x: float, y: float) -> None:
        # Absolute normalized coordinates span the whole virtual desktop (0..65535).
        ax = round(clamp(x) * 65535)
        ay = round(clamp(y) * 65535)
        _send(_mouse_input(
            _MOUSEEVENTF_MOVE | _MOUSEEVENTF_ABSOLUTE | _MOUSEEVENTF_VIRTUALDESK, ax, ay
        ))

    _BTN_DOWN = {
        MouseButton.LEFT: _MOUSEEVENTF_LEFTDOWN,
        MouseButton.RIGHT: _MOUSEEVENTF_RIGHTDOWN,
        MouseButton.MIDDLE: _MOUSEEVENTF_MIDDLEDOWN,
    }
    _BTN_UP = {
        MouseButton.LEFT: _MOUSEEVENTF_LEFTUP,
        MouseButton.RIGHT: _MOUSEEVENTF_RIGHTUP,
        MouseButton.MIDDLE: _MOUSEEVENTF_MIDDLEUP,
    }

    def mouse_down(self, button: MouseButton = MouseButton.LEFT) -> None:
        _send(_mouse_input(self._BTN_DOWN[button]))

    def mouse_up(self, button: MouseButton = MouseButton.LEFT) -> None:
        _send(_mouse_input(self._BTN_UP[button]))

    def click(self, button: MouseButton = MouseButton.LEFT) -> None:
        _send(_mouse_input(self._BTN_DOWN[button]), _mouse_input(self._BTN_UP[button]))

    def double_click(self, button: MouseButton = MouseButton.LEFT) -> None:
        down, up = self._BTN_DOWN[button], self._BTN_UP[button]
        _send(_mouse_input(down), _mouse_input(up), _mouse_input(down), _mouse_input(up))

    def scroll(self, dy: float, dx: float = 0.0) -> None:
        inputs = []
        if dy:
            inputs.append(_mouse_input(_MOUSEEVENTF_WHEEL, data=int(dy * _WHEEL_DELTA)))
        if dx:
            inputs.append(_mouse_input(_MOUSEEVENTF_HWHEEL, data=int(dx * _WHEEL_DELTA)))
        if inputs:
            _send(*inputs)

    def zoom(self, delta: float) -> None:
        # Ctrl + mouse wheel is the near-universal zoom (browsers, editors, image viewers, maps).
        steps = int(delta * _WHEEL_DELTA)
        if steps == 0:
            return
        ctrl = _resolve_vk("ctrl")
        # One batched SendInput call so the Ctrl press, wheel and release can't be interleaved
        # with real input (which could otherwise leave Ctrl logically held down).
        _send(
            _key_input(ctrl, up=False, extended=False),
            _mouse_input(_MOUSEEVENTF_WHEEL, data=steps),
            _key_input(ctrl, up=True, extended=False),
        )

    # -- keyboard ------------------------------------------------------------------------------
    def _tap(self, vk: int) -> None:
        ext = vk in _EXTENDED
        _send(_key_input(vk, up=False, extended=ext), _key_input(vk, up=True, extended=ext))

    def hotkey(self, *keys: str) -> None:
        vks = [_resolve_vk(k) for k in keys]
        downs = [_key_input(vk, up=False, extended=vk in _EXTENDED) for vk in vks]
        ups = [_key_input(vk, up=True, extended=vk in _EXTENDED) for vk in reversed(vks)]
        _send(*downs)
        _send(*ups)

    # -- volume (pycaw / Core Audio) -----------------------------------------------------------
    def _get_volume(self):
        if self._volume is not None or self._volume_failed:
            return self._volume
        try:
            import comtypes
            from pycaw.pycaw import AudioUtilities

            comtypes.CoInitialize()
            speakers = AudioUtilities.GetSpeakers()
            # Modern pycaw returns an AudioDevice wrapper exposing the already-cast endpoint
            # volume interface. Fall back to the legacy IMMDevice.Activate path for older pycaw.
            endpoint = getattr(speakers, "EndpointVolume", None)
            if endpoint is not None:
                self._volume = endpoint
            else:
                from ctypes import POINTER, cast

                from pycaw.pycaw import IAudioEndpointVolume

                interface = speakers.Activate(
                    IAudioEndpointVolume._iid_, comtypes.CLSCTX_ALL, None
                )
                self._volume = cast(interface, POINTER(IAudioEndpointVolume))
        except Exception:
            _log.exception("Volume control unavailable; falling back to media keys")
            self._volume_failed = True
        return self._volume

    def adjust_volume(self, delta_percent: float) -> None:
        vol = self._get_volume()
        if vol is None:
            # Fallback: tap the hardware volume key(s).
            key = 0xAF if delta_percent >= 0 else 0xAE
            for _ in range(max(1, round(abs(delta_percent) / 2))):
                self._tap(key)
            return
        current = vol.GetMasterVolumeLevelScalar()
        vol.SetMasterVolumeLevelScalar(clamp(current + delta_percent / 100.0), None)

    def set_mute(self, muted: bool) -> None:
        vol = self._get_volume()
        if vol is None:
            self._tap(0xAD)  # VK_VOLUME_MUTE toggles
            return
        vol.SetMute(bool(muted), None)

    # -- brightness ----------------------------------------------------------------------------
    def adjust_brightness(self, delta_percent: float) -> None:
        try:
            import screen_brightness_control as sbc

            current = sbc.get_brightness()
            base = current[0] if isinstance(current, list) else current
            target = int(clamp((base + delta_percent) / 100.0) * 100)
            sbc.set_brightness(target)
        except Exception:
            _log.warning("Brightness control unavailable on this display")

    # -- media ---------------------------------------------------------------------------------
    _MEDIA_VK = {
        MediaAction.PLAY_PAUSE: 0xB3,
        MediaAction.NEXT: 0xB0,
        MediaAction.PREVIOUS: 0xB1,
        MediaAction.STOP: 0xB2,
    }

    def media(self, action: MediaAction) -> None:
        self._tap(self._MEDIA_VK[action])

    # -- windows -------------------------------------------------------------------------------
    def window(self, action: WindowAction) -> None:
        if action is WindowAction.MINIMIZE:
            self._show(_SW_MINIMIZE)
        elif action is WindowAction.MAXIMIZE:
            self._show(_SW_MAXIMIZE)
        elif action is WindowAction.RESTORE:
            self._show(_SW_RESTORE)
        elif action is WindowAction.SNAP_LEFT:
            self.hotkey("win", "left")
        elif action is WindowAction.SNAP_RIGHT:
            self.hotkey("win", "right")
        elif action is WindowAction.CLOSE:
            hwnd = user32.GetForegroundWindow()
            if hwnd:
                user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
        elif action is WindowAction.SWITCH:
            self.hotkey("alt", "tab")
        elif action is WindowAction.SHOW_DESKTOP:
            self.hotkey("win", "d")

    def _show(self, cmd: int) -> None:
        hwnd = user32.GetForegroundWindow()
        if hwnd:
            user32.ShowWindow(hwnd, cmd)

    # -- screenshot ----------------------------------------------------------------------------
    def screenshot(self) -> str:
        from PIL import ImageGrab

        self._screens_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).astimezone().strftime("%Y%m%d_%H%M%S")
        path = self._screens_dir / f"gestura_{stamp}.png"
        img = ImageGrab.grab(all_screens=True)
        img.save(path)
        _log.info("Saved screenshot to %s", path)
        return str(path)

    def close(self) -> None:
        # comtypes/pycaw handles teardown; nothing to explicitly release.
        pass
