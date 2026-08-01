"""Tests for feature extraction and static-pose classification."""

from __future__ import annotations

import pytest

from gestura.engine.features import extract
from gestura.engine.recognizers import Pose, classify_static_pose


@pytest.mark.parametrize(
    ("pose", "expected"),
    [
        ("open", Pose.OPEN_PALM),
        ("fist", Pose.FIST),
        ("point", Pose.POINT),
        ("victory", Pose.VICTORY),
        ("three_fingers", Pose.THREE_FINGERS),
        ("rock", Pose.ROCK),
        ("pinky", Pose.PINKY),
        ("thumb_up", Pose.THUMB_UP),
        ("thumb_down", Pose.THUMB_DOWN),
        ("thumb_left", Pose.THUMB_LEFT),
        ("thumb_right", Pose.THUMB_RIGHT),
    ],
)
def test_static_pose_classification(hand_factory, pose, expected) -> None:
    hand = hand_factory(pose)
    name, conf = classify_static_pose(extract(hand))
    assert name == expected
    assert conf > 0.0


def test_every_shape_pose_is_distinct(hand_factory) -> None:
    """No two shape poses classify the same — the core 'don't relate too well' guarantee."""
    shape_poses = ["fist", "point", "victory", "three_fingers", "rock", "pinky",
                   "thumb_up", "thumb_down", "thumb_left", "thumb_right", "open"]
    labels = [classify_static_pose(extract(hand_factory(p)))[0] for p in shape_poses]
    assert len(set(labels)) == len(labels), dict(zip(shape_poses, labels, strict=True))


def test_diagonal_thumb_is_rejected(hand_factory) -> None:
    """A thumb held diagonally (ambiguous between up and sideways) must fire nothing."""
    import numpy as np

    from gestura.core.types import HandLandmark, HandObservation

    hand = hand_factory("thumb_up")
    lm = hand.landmarks.copy()
    # Drag the thumb tip to a 45-degree diagonal from the knuckle so no axis dominates.
    knuckle = lm[int(HandLandmark.MIDDLE_MCP), :2]
    lm[int(HandLandmark.THUMB_TIP), :2] = knuckle + np.array([-0.18, -0.18], dtype=np.float32)
    name, _ = classify_static_pose(extract(HandObservation(lm, hand.handedness, hand.score)))
    assert name == Pose.NONE


def test_pinch_distances(hand_factory) -> None:
    # In a pinch, index/thumb tips are close; in an open hand they are far.
    pinch_f = extract(hand_factory("pinch"))
    open_f = extract(hand_factory("open"))
    assert pinch_f.pinch_index_norm < 0.2
    assert open_f.pinch_index_norm > 0.5


def test_middle_pinch_distances(hand_factory) -> None:
    mp = extract(hand_factory("middle_pinch"))
    assert mp.pinch_middle_norm < 0.2
    assert mp.extended["index"] is True  # index stays out => distinguishes from a fist


def test_feature_is_only(hand_factory) -> None:
    # When pointing, the thumb is naturally out too, so index+thumb are the extended set.
    f = extract(hand_factory("point"))
    assert f.is_only("index", "thumb")
    assert not f.is_only("index")
    assert not f.is_only("index", "middle")
