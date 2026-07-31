"""Custom, user-recorded gesture recognition (the "gesture trainer" backend).

Users record examples of a hand shape, name it, and bind it to an action — no code, no cloud, no
GPU. Recognition uses a **prototype / nearest-neighbour classifier** over a normalized landmark
feature vector rather than a trained neural net (see revised ADR-0003):

* it is instant ("training" = storing examples), fully offline, and trivially explainable;
* the feature vector is made invariant to where the hand is, how far away it is, and how it's
  rotated in-plane, so a gesture is recognised regardless of hand position/scale/tilt.

Feature vector: 21 landmarks → translate so the wrist is the origin → scale by palm width →
rotate so the wrist→middle-knuckle axis is canonical → flatten the 21 (x, y) pairs to 42 numbers.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..core.geometry import palm_width
from ..core.types import HandLandmark, HandObservation
from ..util.logging import get_logger

_log = get_logger("gestura.engine.custom")

FEATURE_DIM = 42  # 21 landmarks × (x, y)


def landmark_feature(hand: HandObservation) -> np.ndarray:
    """Return a translation/scale/rotation-invariant 42-D feature vector for a hand."""
    lm = hand.landmarks[:, :2].astype(np.float64).copy()
    lm -= lm[int(HandLandmark.WRIST)]  # translate: wrist at origin

    scale = palm_width(hand)
    if scale > 1e-6:
        lm /= scale  # scale: palm width == 1

    # Rotate so the wrist -> middle-knuckle axis points "up" (canonical orientation).
    axis = lm[int(HandLandmark.MIDDLE_MCP)]
    angle = math.atan2(axis[1], axis[0])
    theta = -angle - math.pi / 2  # bring the axis to -y (up)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    rot = np.array([[cos_t, -sin_t], [sin_t, cos_t]])
    lm = lm @ rot.T
    return lm.reshape(-1)


@dataclass
class CustomGestureClassifier:
    """Nearest-prototype classifier over :func:`landmark_feature` vectors.

    Args:
        threshold: Maximum feature distance to accept a match. Smaller = stricter. The default is
            tuned for the normalized feature space (a different static pose is typically well
            beyond this).
    """

    threshold: float = 0.85
    _prototypes: dict[str, list[np.ndarray]] = field(default_factory=dict)

    # -- training ------------------------------------------------------------------------------
    def add_sample(self, name: str, hand: HandObservation) -> None:
        self._prototypes.setdefault(name, []).append(landmark_feature(hand))

    def add_feature(self, name: str, feature: np.ndarray) -> None:
        if feature.shape != (FEATURE_DIM,):
            raise ValueError(f"feature must be {FEATURE_DIM}-D, got {feature.shape}")
        self._prototypes.setdefault(name, []).append(feature.astype(np.float64))

    def remove(self, name: str) -> None:
        self._prototypes.pop(name, None)

    @property
    def names(self) -> list[str]:
        return list(self._prototypes)

    def sample_count(self, name: str) -> int:
        return len(self._prototypes.get(name, []))

    # -- inference -----------------------------------------------------------------------------
    def classify(self, hand: HandObservation) -> tuple[str, float] | None:
        """Return ``(name, confidence)`` of the best match, or ``None`` if none is close enough."""
        if not self._prototypes:
            return None
        feat = landmark_feature(hand)
        best_name: str | None = None
        best_dist = math.inf
        for name, protos in self._prototypes.items():
            for proto in protos:
                dist = float(np.linalg.norm(feat - proto))
                if dist < best_dist:
                    best_dist, best_name = dist, name
        if best_name is None or best_dist > self.threshold:
            return None
        confidence = 1.0 - (best_dist / self.threshold)  # 1 at exact match, 0 at the boundary
        return best_name, confidence

    # -- persistence ---------------------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "threshold": self.threshold,
            "gestures": {
                name: [p.tolist() for p in protos] for name, protos in self._prototypes.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> CustomGestureClassifier:
        clf = cls(threshold=float(data.get("threshold", 0.85)))
        for name, protos in data.get("gestures", {}).items():
            clf._prototypes[name] = [np.asarray(p, dtype=np.float64) for p in protos]
        return clf

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        _log.info("Saved %d custom gesture(s) to %s", len(self._prototypes), path)

    @classmethod
    def load(cls, path: Path) -> CustomGestureClassifier:
        if not path.exists():
            return cls()
        try:
            return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, ValueError):
            _log.exception("Failed to load custom gestures from %s; starting empty", path)
            return cls()
