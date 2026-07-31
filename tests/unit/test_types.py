"""Tests for the core domain types."""

from __future__ import annotations

import numpy as np
import pytest

from gestura.core.types import (
    FrameResult,
    GestureEvent,
    GesturePhase,
    Handedness,
    HandLandmark,
    HandObservation,
)


def test_hand_observation_rejects_wrong_shape() -> None:
    with pytest.raises(ValueError):
        HandObservation(np.zeros((5, 3)), Handedness.RIGHT, 0.9)


def test_hand_observation_point_and_wrist(open_hand) -> None:
    wrist = open_hand.point(HandLandmark.WRIST)
    assert wrist.shape == (3,)
    np.testing.assert_allclose(open_hand.wrist, wrist)


def test_frame_result_primary_and_flags(open_hand) -> None:
    empty = FrameResult(hands=(), width=640, height=480, frame_index=1)
    assert empty.has_hand is False
    assert empty.primary is None

    populated = FrameResult(hands=(open_hand,), width=640, height=480, frame_index=2)
    assert populated.has_hand is True
    assert populated.primary is open_hand


def test_frame_result_primary_is_highest_score() -> None:
    lm = np.zeros((21, 3), dtype=np.float32)
    strong = HandObservation(lm, Handedness.RIGHT, 0.95)
    weak = HandObservation(lm.copy(), Handedness.LEFT, 0.60)
    # The vision layer is responsible for ordering; primary just returns the first.
    frame = FrameResult(hands=(strong, weak), width=1, height=1, frame_index=0)
    assert frame.primary is strong


def test_gesture_event_defaults() -> None:
    ev = GestureEvent(name="pinch", phase=GesturePhase.BEGAN, confidence=0.8)
    assert ev.payload == {}
    assert ev.position is None
    assert ev.timestamp > 0
    # payload dicts must be independent between instances (no shared mutable default).
    ev.payload["scroll"] = 1.0
    ev2 = GestureEvent(name="scroll", phase=GesturePhase.UPDATED, confidence=0.5)
    assert ev2.payload == {}
