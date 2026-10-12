"""Tests for the built-in gesture catalogue and gesture/action compatibility."""

from __future__ import annotations

from gestura.actions.registry import ACTIONS, actions_for, get_action
from gestura.config.models import DEFAULT_BINDINGS
from gestura.core.types import GestureKind
from gestura.engine.catalog import BUILTIN_GESTURES, builtin_gesture, gesture_kind


def test_catalogue_ids_are_unique() -> None:
    ids = [g.id for g in BUILTIN_GESTURES]
    assert len(ids) == len(set(ids))


def test_every_default_binding_is_a_catalogued_gesture_with_a_compatible_action() -> None:
    for binding in DEFAULT_BINDINGS:
        info = builtin_gesture(binding.gesture)
        assert info is not None, f"default binding for unknown gesture {binding.gesture!r}"
        spec = get_action(binding.action)
        assert spec is not None, f"default binding to unknown action {binding.action!r}"
        assert spec.accepts_kind(info.kind), f"{binding.gesture} can't drive {binding.action}"


def test_every_action_is_bindable_to_at_least_one_kind() -> None:
    for spec in ACTIONS.values():
        assert spec.accepts, f"{spec.id} accepts no gesture kind"


def test_unknown_gestures_are_custom_taps() -> None:
    assert builtin_gesture("my_wave") is None
    assert gesture_kind("my_wave") is GestureKind.TAP


def test_actions_for_offers_only_what_a_kind_can_drive() -> None:
    tap = {s.id for s in actions_for(GestureKind.TAP)}
    assert {"left_click", "screenshot", "run_shortcut"} <= tap
    # Drag needs a later release; volume needs repeated updates — a tap provides neither.
    assert "drag" not in tap
    assert "volume_up" not in tap

    hold = {s.id for s in actions_for(GestureKind.HOLD)}
    assert "drag" in hold and "left_click" in hold

    assert {s.id for s in actions_for(GestureKind.REPEAT)} == {
        "volume_up", "volume_down", "brightness_up", "brightness_down"}
    assert {s.id for s in actions_for(GestureKind.SCROLL)} == {"scroll"}
    assert {s.id for s in actions_for(GestureKind.ZOOM)} == {"zoom"}
