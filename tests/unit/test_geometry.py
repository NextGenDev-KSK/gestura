"""Tests for geometry helpers using synthetic hands from conftest."""

from __future__ import annotations

import math

import numpy as np
import pytest

from gestura.core.geometry import (
    angle_between,
    clamp,
    distance,
    finger_extended,
    midpoint,
    normalized_distance,
    palm_width,
    remap,
)
from gestura.core.types import HandLandmark


def test_distance_and_midpoint() -> None:
    a = np.array([0.0, 0.0])
    b = np.array([3.0, 4.0])
    assert distance(a, b) == pytest.approx(5.0)
    assert midpoint(a, b) == pytest.approx([1.5, 2.0])


def test_angle_between_orthogonal_and_parallel() -> None:
    x = np.array([1.0, 0.0])
    y = np.array([0.0, 1.0])
    assert angle_between(x, y) == pytest.approx(math.pi / 2)
    assert angle_between(x, x) == pytest.approx(0.0)
    assert angle_between(x, -x) == pytest.approx(math.pi)


def test_angle_between_zero_vector_is_safe() -> None:
    assert angle_between(np.zeros(2), np.array([1.0, 1.0])) == 0.0


def test_palm_width_positive(open_hand) -> None:
    assert palm_width(open_hand) > 0.1


def test_finger_extended_open_hand(open_hand) -> None:
    for finger in ("index", "middle", "ring", "pinky"):
        assert finger_extended(open_hand, finger), f"{finger} should read as extended"


def test_fingers_curled_in_fist(fist) -> None:
    for finger in ("index", "middle", "ring", "pinky"):
        assert not finger_extended(fist, finger), f"{finger} should read as curled"


def test_point_pose_only_index_extended(hand_factory) -> None:
    hand = hand_factory("point")
    assert finger_extended(hand, "index")
    assert not finger_extended(hand, "middle")
    assert not finger_extended(hand, "ring")
    assert not finger_extended(hand, "pinky")


def test_normalized_distance_is_scale_invariant(hand_factory) -> None:
    hand = hand_factory("open")
    d1 = normalized_distance(hand, HandLandmark.INDEX_TIP, HandLandmark.WRIST)

    # Scale every landmark toward the origin by 0.5 (hand "further away"): the *normalized*
    # distance must be unchanged even though raw pixel distance halves.
    shrunk_lm = hand.landmarks.copy()
    shrunk_lm[:, :2] *= 0.5
    from gestura.core.types import HandObservation

    shrunk = HandObservation(shrunk_lm, hand.handedness, hand.score)
    d2 = normalized_distance(shrunk, HandLandmark.INDEX_TIP, HandLandmark.WRIST)
    assert d1 == pytest.approx(d2, rel=1e-5)


def test_clamp_and_remap() -> None:
    assert clamp(1.5) == 1.0
    assert clamp(-0.2) == 0.0
    assert clamp(0.3) == 0.3
    assert remap(5, 0, 10, 0, 100) == pytest.approx(50)
    assert remap(-1, 0, 10, 0, 100) == pytest.approx(0)  # clipped
    assert remap(11, 0, 10, 0, 100, clip=False) == pytest.approx(110)
    # Inverted output range still clips correctly.
    assert remap(20, 0, 10, 100, 0) == pytest.approx(0)


def test_remap_degenerate_input_range() -> None:
    assert remap(5, 3, 3, 0, 100) == 0
