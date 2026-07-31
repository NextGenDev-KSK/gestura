"""Shared test fixtures.

Provides a synthetic hand-landmark builder so the geometry/recognizer tests run deterministically
without a camera or MediaPipe. Coordinates are in the same normalized image space MediaPipe uses
(x right, y down, origin top-left).
"""

from __future__ import annotations

import numpy as np
import pytest

from gestura.core.types import Handedness, HandLandmark, HandObservation

_UP = np.array([0.0, -1.0])  # "up" in image space is -y
_PERP = np.array([1.0, 0.0])  # perpendicular used to bend curled fingers

# Fixed knuckle/wrist anchors for an upright right hand.
_ANCHORS: dict[HandLandmark, np.ndarray] = {
    HandLandmark.WRIST: np.array([0.50, 0.85]),
    HandLandmark.THUMB_CMC: np.array([0.40, 0.80]),
    HandLandmark.INDEX_MCP: np.array([0.42, 0.60]),
    HandLandmark.MIDDLE_MCP: np.array([0.50, 0.60]),
    HandLandmark.RING_MCP: np.array([0.58, 0.60]),
    HandLandmark.PINKY_MCP: np.array([0.64, 0.62]),
}

# (mcp, pip, dip, tip) landmark indices per finger, plus its pointing direction.
_FINGERS: dict[str, tuple[tuple[HandLandmark, ...], np.ndarray]] = {
    "index": (
        (HandLandmark.INDEX_MCP, HandLandmark.INDEX_PIP, HandLandmark.INDEX_DIP,
         HandLandmark.INDEX_TIP),
        _UP,
    ),
    "middle": (
        (HandLandmark.MIDDLE_MCP, HandLandmark.MIDDLE_PIP, HandLandmark.MIDDLE_DIP,
         HandLandmark.MIDDLE_TIP),
        _UP,
    ),
    "ring": (
        (HandLandmark.RING_MCP, HandLandmark.RING_PIP, HandLandmark.RING_DIP,
         HandLandmark.RING_TIP),
        _UP,
    ),
    "pinky": (
        (HandLandmark.PINKY_MCP, HandLandmark.PINKY_PIP, HandLandmark.PINKY_DIP,
         HandLandmark.PINKY_TIP),
        _UP,
    ),
}

_THUMB_CHAIN = (
    HandLandmark.THUMB_CMC, HandLandmark.THUMB_MCP, HandLandmark.THUMB_IP, HandLandmark.THUMB_TIP,
)


def _place_chain(base: np.ndarray, direction: np.ndarray, *, curled: bool, seg: float = 0.08):
    """Return four joint positions along a finger, straight or bent at ~right angles."""
    p0 = base
    p1 = p0 + direction * seg
    if curled:
        p2 = p1 + _PERP * seg
        p3 = p2 - direction * seg
    else:
        p2 = p1 + direction * seg
        p3 = p2 + direction * seg
    return [p0, p1, p2, p3]


def make_hand(pose: str = "open", *, handedness: Handedness = Handedness.RIGHT,
              score: float = 0.99) -> HandObservation:
    """Build a synthetic :class:`HandObservation` for a named ``pose``.

    Supported poses: ``"open"`` (all fingers extended), ``"fist"`` (all curled),
    ``"point"`` (index extended, rest curled), ``"pinch"`` (thumb tip touching index tip).
    """
    lm = np.zeros((21, 3), dtype=np.float32)
    for landmark, xy in _ANCHORS.items():
        lm[int(landmark), :2] = xy

    curled_all = pose == "fist"
    for name, (chain, direction) in _FINGERS.items():
        curled = curled_all or (pose == "point" and name != "index") or (
            pose == "pinch" and name != "index"
        )
        pts = _place_chain(_ANCHORS[chain[0]], direction, curled=curled)
        for idx, p in zip(chain, pts, strict=True):
            lm[int(idx), :2] = p

    # Thumb: build a straight chain from CMC toward the MCP anchor direction.
    thumb_dir = np.array([-0.55, -0.83])  # up-and-left
    thumb_dir = thumb_dir / np.linalg.norm(thumb_dir)
    thumb_pts = _place_chain(_ANCHORS[HandLandmark.THUMB_CMC], thumb_dir,
                             curled=(pose == "fist"), seg=0.07)
    for idx, p in zip(_THUMB_CHAIN, thumb_pts, strict=True):
        lm[int(idx), :2] = p

    if pose == "pinch":
        # Force the thumb tip onto the (curled) index fingertip.
        index_tip = lm[int(HandLandmark.INDEX_TIP), :2].copy()
        # Bring the index tip up to a natural pinch height first.
        index_tip = _ANCHORS[HandLandmark.INDEX_MCP] + _UP * 0.16
        lm[int(HandLandmark.INDEX_TIP), :2] = index_tip
        lm[int(HandLandmark.THUMB_TIP), :2] = index_tip + np.array([0.005, 0.0])

    return HandObservation(landmarks=lm, handedness=handedness, score=score)


@pytest.fixture
def hand_factory():
    """Return the :func:`make_hand` builder so tests can synthesise arbitrary poses."""
    return make_hand


@pytest.fixture
def open_hand() -> HandObservation:
    return make_hand("open")


@pytest.fixture
def fist() -> HandObservation:
    return make_hand("fist")


@pytest.fixture
def pinch() -> HandObservation:
    return make_hand("pinch")
