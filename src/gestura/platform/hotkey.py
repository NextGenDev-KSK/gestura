"""System-wide hotkey: pause/resume gesture control from anywhere, even with the window hidden.

The keyboard is the one input a misbehaving gesture can't take away, so this is Gestura's
emergency brake. On Windows it uses ``RegisterHotKey`` on a dedicated thread that runs its own
message loop (``WM_HOTKEY`` is posted to the registering thread). Elsewhere it is a no-op.
"""

from __future__ import annotations

import sys
import threading
from collections.abc import Callable

from ..util.logging import get_logger
from .base import parse_shortcut

_log = get_logger("gestura.platform.hotkey")

_MODIFIERS = {"alt": 0x0001, "ctrl": 0x0002, "control": 0x0002, "shift": 0x0004,
              "win": 0x0008, "super": 0x0008, "meta": 0x0008, "cmd": 0x0008}
_MOD_NOREPEAT = 0x4000
_WM_HOTKEY = 0x0312
_WM_QUIT = 0x0012


def parse_hotkey(text: str) -> tuple[int, str]:
    """Split a chord into ``(modifier_flags, key)``; e.g. ``"Ctrl+Alt+G"`` -> ``(0x3, "g")``.

    Raises:
        ValueError: with a user-presentable message for an unusable chord. A global hotkey must
            have at least one modifier, so typing can't trigger it by accident.
    """
    keys = parse_shortcut(text)
    mods = [k for k in keys if k in _MODIFIERS]
    rest = [k for k in keys if k not in _MODIFIERS]
    if not mods:
        raise ValueError("Add Ctrl, Alt, Shift or Win, so normal typing can't trigger it")
    if len(rest) != 1:
        raise ValueError("Use modifiers plus exactly one key, e.g. ctrl+alt+g")
    flags = 0
    for m in mods:
        flags |= _MODIFIERS[m]
    return flags, rest[0]


class GlobalHotkey:
    """Calls ``callback`` (on its own thread) whenever the chord is pressed anywhere."""

    _ID = 0xC0DE

    def __init__(self, chord: str, callback: Callable[[], None]) -> None:
        self.chord = chord
        self._callback = callback
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._ready = threading.Event()
        self.error: str | None = None

    def start(self) -> bool:
        """Register the hotkey. Returns ``False`` (and sets :attr:`error`) if it couldn't be."""
        try:
            flags, key = parse_hotkey(self.chord)
        except ValueError as exc:
            self.error = str(exc)
            return False
        if sys.platform != "win32":
            self.error = "Global hotkeys are only supported on Windows"
            return False
        from .windows import _resolve_vk

        vk = _resolve_vk(key)
        self._ready.clear()
        self._thread = threading.Thread(target=self._loop, args=(flags | _MOD_NOREPEAT, vk),
                                        name="gestura-hotkey", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=2.0)
        return self.error is None

    def stop(self) -> None:
        if self._thread is None:
            return
        if self._thread_id is not None:
            import ctypes

            ctypes.windll.user32.PostThreadMessageW(self._thread_id, _WM_QUIT, 0, 0)
        self._thread.join(timeout=2.0)
        self._thread = None
        self._thread_id = None

    def _loop(self, flags: int, vk: int) -> None:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32")
        self._thread_id = kernel32.GetCurrentThreadId()
        if not user32.RegisterHotKey(None, self._ID, flags, vk):
            err = ctypes.get_last_error()
            self.error = (f"{self.chord} is already used by another app; pick another"
                          if err == 1409 else f"Couldn't register {self.chord} (error {err})")
            _log.warning("Global hotkey %s not registered: %s", self.chord, self.error)
            self._ready.set()
            return
        self.error = None
        _log.info("Global pause hotkey registered: %s", self.chord)
        self._ready.set()
        msg = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == _WM_HOTKEY and msg.wParam == self._ID:
                    try:
                        self._callback()
                    except Exception:
                        _log.exception("Hotkey callback failed")
        finally:
            user32.UnregisterHotKey(None, self._ID)
