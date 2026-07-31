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
        ("thumb_up", Pose.THUMB_UP),
        ("thumb_down", Pose.THUMB_DOWN),
    ],
)
def test_static_pose_classification(hand_factory, pose, expected) -> None:
    hand = hand_factory(pose)
    name, conf = classify_static_pose(extract(hand))
    assert name == expected
    assert conf > 0.0


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
