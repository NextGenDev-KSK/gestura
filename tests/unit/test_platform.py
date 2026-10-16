"""Tests for the OS-adapter layer (platform-independent parts + Windows key mapping)."""

from __future__ import annotations

import sys

import pytest

from gestura.platform import RecordingAdapter, get_adapter
from gestura.platform.base import MouseButton, WindowAction


def test_recording_adapter_tracks_cursor_and_buttons() -> None:
    a = RecordingAdapter(screen=(1920, 1080))
    assert a.screen_size() == (1920, 1080)

    a.move_cursor(0.25, 0.75)
    assert a.cursor == (0.25, 0.75)

    a.mouse_down(MouseButton.LEFT)
    assert MouseButton.LEFT in a.buttons_down
    a.mouse_up(MouseButton.LEFT)
    assert MouseButton.LEFT not in a.buttons_down

    a.window(WindowAction.SNAP_LEFT)
    assert a.names() == ["move_cursor", "mouse_down", "mouse_up", "window"]


def test_recording_adapter_screenshot_returns_placeholder() -> None:
    a = RecordingAdapter()
    assert a.screenshot() == "<recorded>"
    assert "screenshot" in a.names()


def test_get_adapter_dry_run_is_recording() -> None:
    assert isinstance(get_adapter(dry_run=True), RecordingAdapter)


@pytest.mark.windows
@pytest.mark.skipif(sys.platform != "win32", reason="Windows key mapping")
def test_windows_key_resolution() -> None:
    from gestura.platform.windows import _resolve_vk

    assert _resolve_vk("ctrl") == 0x11
    assert _resolve_vk("a") == 0x41
    assert _resolve_vk("f5") == 0x74
    assert _resolve_vk("left") == 0x25
    with pytest.raises(KeyError):
        _resolve_vk("nonsense-key")


@pytest.mark.parametrize(("text", "keys"), [
    ("ctrl+c", ["ctrl", "c"]),
    ("Ctrl + Shift + S", ["ctrl", "shift", "s"]),
    ("alt+F4", ["alt", "f4"]),
    ("win+d", ["win", "d"]),
    ("media_play_pause", ["media_play_pause"]),
])
def test_parse_shortcut_accepts_valid_chords(text, keys) -> None:
    from gestura.platform import parse_shortcut

    assert parse_shortcut(text) == keys


@pytest.mark.parametrize("text", [
    "", "ctrl+", "ctrl++c", "ctrl+banana", "ctrl+ctrl", "ctrl+,", "a+b+c+d+e",
])
def test_parse_shortcut_rejects_invalid_chords(text) -> None:
    from gestura.platform import parse_shortcut

    with pytest.raises(ValueError):
        parse_shortcut(text)


@pytest.mark.windows
@pytest.mark.skipif(sys.platform != "win32", reason="Windows key mapping")
def test_windows_resolves_every_shortcut_key_and_rejects_punctuation() -> None:
    from gestura.platform import SHORTCUT_KEYS
    from gestura.platform.windows import _resolve_vk

    for key in SHORTCUT_KEYS:
        _resolve_vk(key)  # must not raise: the editor promises these work
    assert _resolve_vk("7") == 0x37
    # ord(',') == 0x2C is VK_SNAPSHOT: this used to press PrintScreen instead of failing.
    with pytest.raises(KeyError):
        _resolve_vk(",")


@pytest.mark.windows
@pytest.mark.skipif(sys.platform != "win32", reason="Windows SendInput")
def test_windows_zoom_sends_ctrl_wheel_in_one_batch(monkeypatch) -> None:
    from gestura.platform import windows

    batches: list[tuple] = []
    monkeypatch.setattr(windows, "_send", lambda *inputs: batches.append(inputs))
    adapter = windows.WindowsAdapter.__new__(windows.WindowsAdapter)  # no COM/DPI setup needed

    adapter.zoom(1.0)
    assert len(batches) == 1
    ctrl_down, wheel, ctrl_up = batches[0]
    assert ctrl_down.u.ki.wVk == 0x11 and not ctrl_down.u.ki.dwFlags & windows._KEYEVENTF_KEYUP
    assert wheel.u.mi.dwFlags == windows._MOUSEEVENTF_WHEEL
    assert wheel.u.mi.mouseData == windows._WHEEL_DELTA
    assert ctrl_up.u.ki.wVk == 0x11 and ctrl_up.u.ki.dwFlags & windows._KEYEVENTF_KEYUP

    adapter.zoom(0.001)  # below one wheel step: nothing is sent
    assert len(batches) == 1


# --- Global pause hotkey -----------------------------------------------------------------------
def test_parse_hotkey_requires_a_modifier_and_one_key() -> None:
    from gestura.platform.hotkey import parse_hotkey

    assert parse_hotkey("Ctrl+Alt+G") == (0x2 | 0x1, "g")
    assert parse_hotkey("win+shift+f9") == (0x8 | 0x4, "f9")
    for bad in ("g", "ctrl+alt", "ctrl+a+b", "ctrl+banana"):
        with pytest.raises(ValueError):
            parse_hotkey(bad)


@pytest.mark.windows
@pytest.mark.skipif(sys.platform != "win32", reason="Windows RegisterHotKey")
def test_global_hotkey_fires_and_unregisters() -> None:
    import ctypes
    import threading

    from gestura.platform.hotkey import _WM_HOTKEY, GlobalHotkey

    fired = threading.Event()
    hk = GlobalHotkey("ctrl+alt+shift+f11", fired.set)
    assert hk.start(), hk.error
    try:
        # Simulate the key press: deliver WM_HOTKEY to the hotkey thread's message queue.
        ctypes.windll.user32.PostThreadMessageW(hk._thread_id, _WM_HOTKEY, GlobalHotkey._ID, 0)
        assert fired.wait(2.0)
    finally:
        hk.stop()
    assert hk._thread is None
    # Once released, the same chord can be registered again.
    again = GlobalHotkey("ctrl+alt+shift+f11", lambda: None)
    assert again.start(), again.error
    again.stop()


def test_global_hotkey_reports_a_bad_chord() -> None:
    from gestura.platform.hotkey import GlobalHotkey

    hk = GlobalHotkey("g", lambda: None)
    assert not hk.start()
    assert "Ctrl" in hk.error


# --- Start with Windows --------------------------------------------------------------------------
class _FakeRunKey:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, name):
        return self.values.get(name)

    def set(self, name, command):
        self.values[name] = command

    def delete(self, name):
        self.values.pop(name, None)


def test_autostart_writes_and_removes_the_run_entry() -> None:
    from gestura.platform.autostart import VALUE_NAME, AutoStart

    key = _FakeRunKey()
    auto = AutoStart(key)
    assert auto.supported and not auto.is_enabled()
    assert auto.apply(True)
    assert auto.is_enabled()
    assert key.values[VALUE_NAME].endswith("--minimized")
    assert "gestura" in key.values[VALUE_NAME].lower()
    assert auto.apply(False)
    assert not auto.is_enabled()


def test_autostart_reports_registry_failures() -> None:
    from gestura.platform.autostart import AutoStart

    class Broken(_FakeRunKey):
        def set(self, name, command):
            raise PermissionError("denied")

    assert not AutoStart(Broken()).apply(True)
