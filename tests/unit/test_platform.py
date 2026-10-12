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
