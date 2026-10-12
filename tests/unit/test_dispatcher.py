"""Tests for the action dispatcher using the side-effect-free RecordingAdapter."""

from __future__ import annotations

from gestura.actions import ActionDispatcher
from gestura.config.models import GestureBinding, Profile
from gestura.core.types import GestureEvent, GesturePhase
from gestura.engine.interpreter import InterpretationResult
from gestura.platform.base import MouseButton, RecordingAdapter


def _result(*events: GestureEvent, cursor=None) -> InterpretationResult:
    return InterpretationResult(cursor=cursor, events=list(events))


def _ev(name: str, phase: GesturePhase, **payload) -> GestureEvent:
    return GestureEvent(name=name, phase=phase, confidence=0.9, payload=payload)


def test_pinch_triggers_left_click() -> None:
    adapter = RecordingAdapter()
    disp = ActionDispatcher(adapter, Profile())
    disp.dispatch(_result(_ev("pinch", GesturePhase.BEGAN)))
    assert adapter.names() == ["click"]
    assert adapter.actions[0].args == (MouseButton.LEFT,)


def test_click_only_on_began_not_ended() -> None:
    adapter = RecordingAdapter()
    disp = ActionDispatcher(adapter, Profile())
    disp.dispatch(_result(_ev("pinch", GesturePhase.ENDED)))
    assert adapter.names() == []  # ENDED phase must not click


def test_drag_maps_to_button_down_then_up() -> None:
    adapter = RecordingAdapter()
    disp = ActionDispatcher(adapter, Profile())
    disp.dispatch(_result(_ev("fist", GesturePhase.BEGAN)))
    disp.dispatch(_result(_ev("fist", GesturePhase.ENDED)))
    assert adapter.names() == ["mouse_down", "mouse_up"]
    assert MouseButton.LEFT not in adapter.buttons_down  # released cleanly


def test_scroll_passes_delta() -> None:
    adapter = RecordingAdapter()
    disp = ActionDispatcher(adapter, Profile())
    disp.dispatch(_result(_ev("two_finger_scroll", GesturePhase.UPDATED, dy=1.5)))
    assert adapter.actions[0].name == "scroll"
    assert adapter.actions[0].args == (1.5, 0.0)


def test_volume_up_on_thumb() -> None:
    adapter = RecordingAdapter()
    disp = ActionDispatcher(adapter, Profile())
    disp.dispatch(_result(_ev("thumb_up", GesturePhase.UPDATED)))
    assert adapter.actions[0].name == "adjust_volume"
    assert adapter.actions[0].args[0] > 0  # positive delta


def test_cursor_moves_when_active_but_not_when_paused() -> None:
    adapter = RecordingAdapter()
    disp = ActionDispatcher(adapter, Profile())
    disp.dispatch(_result(cursor=(0.3, 0.7)))
    assert adapter.cursor == (0.3, 0.7)

    disp.set_paused(True)
    disp.dispatch(_result(cursor=(0.9, 0.9)))
    assert adapter.cursor == (0.3, 0.7)  # unchanged while paused


def test_pause_toggle_and_suppression() -> None:
    adapter = RecordingAdapter()
    # pause_toggle is no longer bound to a default gesture; bind it explicitly here.
    profile = Profile(bindings=[
        GestureBinding(gesture="pinch", action="left_click"),
        GestureBinding(gesture="pause_sign", action="pause_toggle"),
    ])
    disp = ActionDispatcher(adapter, profile)

    # A pause-bound gesture toggles pause on.
    disp.dispatch(_result(_ev("pause_sign", GesturePhase.BEGAN)))
    assert disp.paused is True

    # While paused, a pinch does nothing.
    disp.dispatch(_result(_ev("pinch", GesturePhase.BEGAN), cursor=(0.5, 0.5)))
    assert "click" not in adapter.names()

    # The same gesture resumes.
    disp.dispatch(_result(_ev("pause_sign", GesturePhase.BEGAN)))
    assert disp.paused is False


def test_middle_and_pinky_pinch_map_to_distinct_clicks() -> None:
    adapter = RecordingAdapter()
    disp = ActionDispatcher(adapter, Profile())
    disp.dispatch(_result(_ev("middle_pinch", GesturePhase.BEGAN)))
    disp.dispatch(_result(_ev("pinky_pinch", GesturePhase.BEGAN)))
    assert adapter.actions[0].args == (MouseButton.RIGHT,)
    assert adapter.actions[1].args == (MouseButton.MIDDLE,)


def test_zoom_action_passes_scale() -> None:
    adapter = RecordingAdapter()
    disp = ActionDispatcher(adapter, Profile())
    disp.dispatch(_result(_ev("zoom", GesturePhase.UPDATED, scale=2.0)))
    assert adapter.actions[0].name == "zoom"
    assert adapter.actions[0].args == (2.0,)


def test_run_shortcut_sends_the_bound_key_chord() -> None:
    adapter = RecordingAdapter()
    profile = Profile(bindings=[
        GestureBinding(gesture="rock", action="run_shortcut", shortcut=["ctrl", "c"])])
    disp = ActionDispatcher(adapter, profile)
    disp.dispatch(_result(_ev("rock", GesturePhase.BEGAN)))
    assert adapter.actions[0].name == "hotkey"
    assert adapter.actions[0].args == ("ctrl", "c")


def test_unknown_action_is_ignored_gracefully() -> None:
    adapter = RecordingAdapter()
    profile = Profile(bindings=[GestureBinding(gesture="pinch", action="does_not_exist")])
    disp = ActionDispatcher(adapter, profile)
    disp.dispatch(_result(_ev("pinch", GesturePhase.BEGAN)))  # must not raise
    assert adapter.names() == []


def test_disabled_binding_is_skipped() -> None:
    adapter = RecordingAdapter()
    profile = Profile(
        bindings=[GestureBinding(gesture="pinch", action="left_click", enabled=False)])
    disp = ActionDispatcher(adapter, profile)
    disp.dispatch(_result(_ev("pinch", GesturePhase.BEGAN)))
    assert adapter.names() == []
