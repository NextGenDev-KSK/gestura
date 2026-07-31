"""Tests for the temporal gesture interpreter (the reliability core)."""

from __future__ import annotations

import numpy as np

from gestura.config.models import Profile
from gestura.core.types import GesturePhase, HandObservation
from gestura.engine.interpreter import GestureInterpreter, Mode


def _shift(hand: HandObservation, dy: float) -> HandObservation:
    """Return a copy of the hand translated vertically by ``dy`` (negative = up)."""
    lm = hand.landmarks.copy()
    lm[:, 1] += dy
    return HandObservation(lm, hand.handedness, hand.score)


def _names(events, phase=None):
    return [e.name for e in events if phase is None or e.phase is phase]


def test_pinch_emits_left_click_on_rising_edge(hand_factory, frame_factory) -> None:
    interp = GestureInterpreter(Profile())
    # Start open (pinch released), then close.
    interp.update(frame_factory(hand_factory("open"), timestamp=0.0, index=0))
    result = interp.update(frame_factory(hand_factory("pinch"), timestamp=0.1, index=1))
    assert "pinch" in _names(result.events, GesturePhase.BEGAN)


def test_pinch_does_not_repeat_while_held(hand_factory, frame_factory) -> None:
    interp = GestureInterpreter(Profile())
    interp.update(frame_factory(hand_factory("open"), timestamp=0.0))
    first = interp.update(frame_factory(hand_factory("pinch"), timestamp=0.1))
    held = interp.update(frame_factory(hand_factory("pinch"), timestamp=0.15))
    assert "pinch" in _names(first.events)
    assert "pinch" not in _names(held.events)  # still closed -> no new click


def test_middle_pinch_emits_right_click(hand_factory, frame_factory) -> None:
    interp = GestureInterpreter(Profile())
    interp.update(frame_factory(hand_factory("open"), timestamp=0.0))
    result = interp.update(frame_factory(hand_factory("middle_pinch"), timestamp=0.1))
    assert "middle_pinch" in _names(result.events, GesturePhase.BEGAN)


def test_fist_enters_and_exits_drag(hand_factory, frame_factory) -> None:
    interp = GestureInterpreter(Profile())
    # Hold a fist past the stability window.
    interp.update(frame_factory(hand_factory("fist"), timestamp=0.00))
    interp.update(frame_factory(hand_factory("fist"), timestamp=0.03))
    began = interp.update(frame_factory(hand_factory("fist"), timestamp=0.09))
    assert interp.mode is Mode.DRAG
    assert any(e.name == "fist" and e.phase is GesturePhase.BEGAN for e in began.events)

    # Release the fist -> drag ends.
    ended = interp.update(frame_factory(hand_factory("open"), timestamp=0.12))
    assert interp.mode is Mode.IDLE
    assert any(e.name == "fist" and e.phase is GesturePhase.ENDED for e in ended.events)


def test_no_click_during_fist(hand_factory, frame_factory) -> None:
    """A fist (fingers curled, tips near thumb) must never be read as a pinch/click."""
    interp = GestureInterpreter(Profile())
    saw_click = False
    for i in range(6):
        r = interp.update(frame_factory(hand_factory("fist"), timestamp=i * 0.03))
        if "pinch" in _names(r.events):
            saw_click = True
    assert not saw_click


def test_victory_scrolls_on_vertical_movement(hand_factory, frame_factory) -> None:
    interp = GestureInterpreter(Profile())
    victory = hand_factory("victory")
    # Stabilise the scroll pose.
    interp.update(frame_factory(victory, timestamp=0.00))
    interp.update(frame_factory(victory, timestamp=0.03))
    interp.update(frame_factory(victory, timestamp=0.09))
    assert interp.mode is Mode.SCROLL

    # Move the hand up -> a scroll UPDATED event with positive dy.
    moved = interp.update(frame_factory(_shift(victory, -0.05), timestamp=0.12))
    scrolls = [e for e in moved.events if e.name == "two_finger_scroll"
               and e.phase is GesturePhase.UPDATED]
    assert scrolls and scrolls[0].payload["dy"] > 0


def test_thumb_up_emits_volume(hand_factory, frame_factory) -> None:
    interp = GestureInterpreter(Profile())
    events = []
    for i in range(6):
        events += interp.update(frame_factory(hand_factory("thumb_up"), timestamp=i * 0.06)).events
    assert "thumb_up" in _names(events, GesturePhase.UPDATED)


def test_open_palm_hold_toggles_pause_once(hand_factory, frame_factory) -> None:
    interp = GestureInterpreter(Profile())
    began_count = 0
    for i in range(20):
        r = interp.update(frame_factory(hand_factory("open"), timestamp=i * 0.1))
        began_count += _names(r.events, GesturePhase.BEGAN).count("open_palm_hold")
    # Fires exactly once for a single continuous hold (must be released to re-arm).
    assert began_count == 1


def test_tracking_loss_ends_drag_and_resets(hand_factory, frame_factory) -> None:
    interp = GestureInterpreter(Profile())
    for t in (0.0, 0.03, 0.09):
        interp.update(frame_factory(hand_factory("fist"), timestamp=t))
    assert interp.mode is Mode.DRAG
    # Hand disappears.
    lost = interp.update(frame_factory(None, timestamp=0.12))
    assert interp.mode is Mode.IDLE
    assert any(e.name == "fist" and e.phase is GesturePhase.ENDED for e in lost.events)
    assert lost.tracking is False
    assert interp.cursor.last_position is None


def test_low_confidence_hand_is_ignored(hand_factory, frame_factory) -> None:
    interp = GestureInterpreter(Profile())
    weak = hand_factory("pinch", score=0.2)  # below default min_confidence 0.6
    interp.update(frame_factory(hand_factory("open"), timestamp=0.0))
    result = interp.update(frame_factory(weak, timestamp=0.1))
    assert result.tracking is False
    assert result.events == []


def test_scroll_and_click_are_mutually_exclusive(hand_factory, frame_factory) -> None:
    """While scrolling, a stray pinch-distance must not produce clicks."""
    interp = GestureInterpreter(Profile())
    victory = hand_factory("victory")
    for t in (0.0, 0.03, 0.09, 0.12, 0.15):
        r = interp.update(frame_factory(victory, timestamp=t))
    assert interp.mode is Mode.SCROLL
    assert "pinch" not in _names(r.events)
