"""Tests for the custom (user-trained) gesture classifier and its interpreter integration."""

from __future__ import annotations

import math

import numpy as np

from gestura.config.models import Profile
from gestura.core.types import GesturePhase, HandObservation
from gestura.engine.custom import FEATURE_DIM, CustomGestureClassifier, landmark_feature
from gestura.engine.interpreter import GestureInterpreter


def _transform(hand: HandObservation, *, dx=0.0, dy=0.0, scale=1.0, angle=0.0) -> HandObservation:
    lm = hand.landmarks.copy()
    xy = lm[:, :2]
    wrist = xy[0].copy()
    xy -= wrist
    xy *= scale
    if angle:
        c, s = math.cos(angle), math.sin(angle)
        rot = np.array([[c, -s], [s, c]], dtype=xy.dtype)
        xy[:] = xy @ rot.T
    xy += wrist + np.array([dx, dy], dtype=xy.dtype)
    lm[:, :2] = xy
    return HandObservation(lm, hand.handedness, hand.score)


def test_feature_dim(hand_factory) -> None:
    assert landmark_feature(hand_factory("open")).shape == (FEATURE_DIM,)


def test_feature_is_invariant_to_translation_scale_rotation(hand_factory) -> None:
    base = hand_factory("open")
    moved = _transform(base, dx=0.2, dy=-0.1, scale=0.5, angle=math.radians(35))
    f0 = landmark_feature(base)
    f1 = landmark_feature(moved)
    assert np.linalg.norm(f0 - f1) < 0.05  # essentially identical after normalization


def test_classifier_distinguishes_poses(hand_factory) -> None:
    clf = CustomGestureClassifier()
    for _ in range(3):
        clf.add_sample("myopen", hand_factory("open"))
        clf.add_sample("myfist", hand_factory("fist"))

    open_match = clf.classify(hand_factory("open"))
    fist_match = clf.classify(hand_factory("fist"))
    assert open_match is not None and open_match[0] == "myopen"
    assert fist_match is not None and fist_match[0] == "myfist"
    assert 0.0 <= open_match[1] <= 1.0


def test_classifier_rejects_far_pose_when_strict(hand_factory) -> None:
    clf = CustomGestureClassifier(threshold=0.2)  # strict
    clf.add_sample("myopen", hand_factory("open"))
    # A fist is far from an open hand in feature space -> below threshold -> no match.
    assert clf.classify(hand_factory("fist")) is None


def test_classifier_empty_returns_none(hand_factory) -> None:
    assert CustomGestureClassifier().classify(hand_factory("open")) is None


def test_persistence_roundtrip(tmp_path, hand_factory) -> None:
    clf = CustomGestureClassifier(threshold=0.7)
    clf.add_sample("wave", hand_factory("open"))
    clf.add_sample("wave", hand_factory("open"))
    path = tmp_path / "custom.json"
    clf.save(path)

    loaded = CustomGestureClassifier.load(path)
    assert loaded.names == ["wave"]
    assert loaded.sample_count("wave") == 2
    assert loaded.threshold == 0.7
    assert loaded.classify(hand_factory("open"))[0] == "wave"


def test_interpreter_emits_custom_gesture(hand_factory, frame_factory) -> None:
    clf = CustomGestureClassifier()
    clf.add_sample("myopen", hand_factory("open"))
    interp = GestureInterpreter(Profile(), custom=clf)

    events = []
    for t in (0.0, 0.05, 0.13, 0.2):
        events += interp.update(frame_factory(hand_factory("open"), timestamp=t)).events
    began = [e.name for e in events if e.phase is GesturePhase.BEGAN]
    assert "myopen" in began
    # Fires once for a continuous hold (not every frame).
    assert began.count("myopen") == 1
