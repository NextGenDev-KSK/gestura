"""Tests for the temporal gesture interpreter (the reliability core)."""

from __future__ import annotations

import pytest

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


def test_open_palm_does_nothing(hand_factory, frame_factory) -> None:
    """Open palm is now a neutral rest pose — it must emit no gesture events."""
    interp = GestureInterpreter(Profile())
    events = []
    for i in range(10):
        events += interp.update(frame_factory(hand_factory("open"), timestamp=i * 0.1)).events
    assert events == []


@pytest.mark.parametrize("pose", ["three_fingers", "rock", "pinky", "thumb_left", "thumb_right"])
def test_oneshot_pose_fires_once_per_hold(hand_factory, frame_factory, pose) -> None:
    interp = GestureInterpreter(Profile())
    began = 0
    for i in range(15):  # hold the pose continuously
        r = interp.update(frame_factory(hand_factory(pose), timestamp=i * 0.05))
        began += _names(r.events, GesturePhase.BEGAN).count(pose)
    assert began == 1  # one-shot: exactly one fire for a continuous hold


def test_oneshot_rearms_after_release(hand_factory, frame_factory) -> None:
    interp = GestureInterpreter(Profile())
    t = 0.0

    def hold(pose, n):
        nonlocal t
        fired = 0
        for _ in range(n):
            fired += _names(interp.update(frame_factory(hand_factory(pose), timestamp=t)).events,
                            GesturePhase.BEGAN).count(pose)
            t += 0.05
        return fired

    assert hold("rock", 5) == 1
    hold("open", 5)          # release to a neutral pose
    assert hold("rock", 5) == 1  # re-arms and fires again


def test_pinky_pinch_emits_middle_click(hand_factory, frame_factory) -> None:
    interp = GestureInterpreter(Profile())
    interp.update(frame_factory(hand_factory("point"), timestamp=0.0))  # index out, no contact
    result = interp.update(frame_factory(hand_factory("pinky_pinch"), timestamp=0.1))
    assert "pinky_pinch" in _names(result.events, GesturePhase.BEGAN)


def test_middle_and_pinky_pinch_do_not_cross_fire(hand_factory, frame_factory) -> None:
    """A middle pinch must never also emit a pinky pinch and vice-versa."""
    interp = GestureInterpreter(Profile())
    interp.update(frame_factory(hand_factory("point"), timestamp=0.0))
    r_mid = interp.update(frame_factory(hand_factory("middle_pinch"), timestamp=0.1))
    assert "middle_pinch" in _names(r_mid.events)
    assert "pinky_pinch" not in _names(r_mid.events)

    interp2 = GestureInterpreter(Profile())
    interp2.update(frame_factory(hand_factory("point"), timestamp=0.0))
    r_pky = interp2.update(frame_factory(hand_factory("pinky_pinch"), timestamp=0.1))
    assert "pinky_pinch" in _names(r_pky.events)
    assert "middle_pinch" not in _names(r_pky.events)


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


def test_two_hand_pinch_zooms(hand_factory, multi_frame_factory, shift) -> None:
    interp = GestureInterpreter(Profile())
    a = hand_factory("pinch")
    b = shift(hand_factory("pinch"), dx=0.35)  # second hand to the right
    r0 = interp.update(multi_frame_factory([a, b], timestamp=0.0))
    assert interp.mode is Mode.ZOOM
    assert "zoom" in _names(r0.events, GesturePhase.BEGAN)

    # Spread the hands apart -> zoom in (positive scale); cursor suppressed while zooming.
    b2 = shift(hand_factory("pinch"), dx=0.55)
    r1 = interp.update(multi_frame_factory([a, b2], timestamp=0.05))
    zooms = [e for e in r1.events if e.name == "zoom" and e.phase is GesturePhase.UPDATED]
    assert zooms and zooms[0].payload["scale"] > 0
    assert r1.cursor is None


def test_zoom_needs_both_hands_pinched(hand_factory, multi_frame_factory, shift) -> None:
    interp = GestureInterpreter(Profile())
    # Two open hands (not pinched) must NOT start a zoom.
    a = hand_factory("open")
    b = shift(hand_factory("open"), dx=0.35)
    interp.update(multi_frame_factory([a, b], timestamp=0.0))
    assert interp.mode is not Mode.ZOOM


def test_zoom_ends_when_a_hand_leaves(hand_factory, multi_frame_factory, frame_factory, shift):
    interp = GestureInterpreter(Profile())
    a = hand_factory("pinch")
    b = shift(hand_factory("pinch"), dx=0.35)
    interp.update(multi_frame_factory([a, b], timestamp=0.0))
    assert interp.mode is Mode.ZOOM
    r = interp.update(frame_factory(hand_factory("open"), timestamp=0.05))  # back to one hand
    assert interp.mode is Mode.IDLE
    assert "zoom" in _names(r.events, GesturePhase.ENDED)


def test_scroll_and_click_are_mutually_exclusive(hand_factory, frame_factory) -> None:
    """While scrolling, a stray pinch-distance must not produce clicks."""
    interp = GestureInterpreter(Profile())
    victory = hand_factory("victory")
    for t in (0.0, 0.03, 0.09, 0.12, 0.15):
        r = interp.update(frame_factory(victory, timestamp=t))
    assert interp.mode is Mode.SCROLL
    assert "pinch" not in _names(r.events)
