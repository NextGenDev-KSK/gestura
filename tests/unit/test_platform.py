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
