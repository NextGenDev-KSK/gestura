"""Shared test fixtures.

Provides a synthetic hand-landmark builder so the geometry/recognizer tests run deterministically
without a camera or MediaPipe. Coordinates are in the same normalized image space MediaPipe uses
(x right, y down, origin top-left).
"""

from __future__ import annotations

import numpy as np
import pytest

from gestura.core.types import FrameResult, Handedness, HandLandmark, HandObservation

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


# Which of the four fingers are curled for each pose (thumb handled separately).
_ALL_FINGERS = {"index", "middle", "ring", "pinky"}
_CURLED_FINGERS: dict[str, set[str]] = {
    "open": set(),
    "fist": set(_ALL_FINGERS),
    "point": {"middle", "ring", "pinky"},
    "victory": {"ring", "pinky"},
    "three_fingers": {"pinky"},
    "rock": {"middle", "ring"},
    "pinky": {"index", "middle", "ring"},
    "pinch": set(),          # fingers stay open; index/thumb tips overridden to touch
    "middle_pinch": set(),   # index stays extended; middle/thumb tips overridden to touch
    "pinky_pinch": {"middle", "ring"},  # index extended; pinky/thumb tips overridden to touch
    "thumb_up": set(_ALL_FINGERS),
    "thumb_down": set(_ALL_FINGERS),
    "thumb_left": set(_ALL_FINGERS),
    "thumb_right": set(_ALL_FINGERS),
}


def make_hand(pose: str = "open", *, handedness: Handedness = Handedness.RIGHT,
              score: float = 0.99) -> HandObservation:
    """Build a synthetic :class:`HandObservation` for a named ``pose``.

    Supported poses: ``open``, ``fist``, ``point``, ``victory``, ``three_fingers``, ``rock``,
    ``pinky``, ``pinch`` (index+thumb touch), ``middle_pinch``, ``pinky_pinch``,
    ``thumb_up``, ``thumb_down``, ``thumb_left``, ``thumb_right``.
    """
    if pose not in _CURLED_FINGERS:
        raise ValueError(f"unknown pose {pose!r}")

    lm = np.zeros((21, 3), dtype=np.float32)
    for landmark, xy in _ANCHORS.items():
        lm[int(landmark), :2] = xy

    curled_set = _CURLED_FINGERS[pose]
    for name, (chain, direction) in _FINGERS.items():
        pts = _place_chain(_ANCHORS[chain[0]], direction, curled=name in curled_set)
        for idx, p in zip(chain, pts, strict=True):
            lm[int(idx), :2] = p

    # Thumb: direction + length depend on the pose. Directional thumbs use a longer, cardinal
    # vector (with a slight upward bias on left/right to clear the CMC's low starting point).
    if pose == "thumb_up":
        thumb_dir, thumb_seg = np.array([0.0, -1.0]), 0.14
    elif pose == "thumb_down":
        thumb_dir, thumb_seg = np.array([0.0, 1.0]), 0.14
    elif pose == "thumb_left":
        thumb_dir, thumb_seg = np.array([-1.0, -0.2]), 0.14
    elif pose == "thumb_right":
        thumb_dir, thumb_seg = np.array([1.0, -0.2]), 0.14
    else:
        thumb_dir, thumb_seg = np.array([-0.55, -0.83]), 0.07
    thumb_dir = thumb_dir / np.linalg.norm(thumb_dir)
    thumb_pts = _place_chain(_ANCHORS[HandLandmark.THUMB_CMC], thumb_dir,
                             curled=(pose == "fist"), seg=thumb_seg)
    for idx, p in zip(_THUMB_CHAIN, thumb_pts, strict=True):
        lm[int(idx), :2] = p

    # Contact overrides: place the two pinching tips on a common point.
    if pose == "pinch":
        p = _ANCHORS[HandLandmark.INDEX_MCP] + _UP * 0.13
        lm[int(HandLandmark.INDEX_TIP), :2] = p
        lm[int(HandLandmark.THUMB_TIP), :2] = p + np.array([0.004, 0.0])
    elif pose == "middle_pinch":
        p = _ANCHORS[HandLandmark.MIDDLE_MCP] + _UP * 0.13
        lm[int(HandLandmark.MIDDLE_TIP), :2] = p
        lm[int(HandLandmark.THUMB_TIP), :2] = p + np.array([0.004, 0.0])
    elif pose == "pinky_pinch":
        p = _ANCHORS[HandLandmark.PINKY_MCP] + _UP * 0.10
        lm[int(HandLandmark.PINKY_TIP), :2] = p
        lm[int(HandLandmark.THUMB_TIP), :2] = p + np.array([0.004, 0.0])

    return HandObservation(landmarks=lm, handedness=handedness, score=score)


def make_frame(hand: HandObservation | None, *, timestamp: float, index: int = 0,
               width: int = 640, height: int = 480) -> FrameResult:
    """Wrap a hand (or ``None`` for tracking loss) in a :class:`FrameResult`."""
    hands = (hand,) if hand is not None else ()
    return FrameResult(hands=hands, width=width, height=height, frame_index=index,
                       timestamp=timestamp)


def make_multi_frame(hands: list[HandObservation], *, timestamp: float, index: int = 0,
                     width: int = 640, height: int = 480) -> FrameResult:
    """Wrap several hands in one :class:`FrameResult` (for two-hand gestures like zoom)."""
    return FrameResult(hands=tuple(hands), width=width, height=height, frame_index=index,
                       timestamp=timestamp)


def shift_hand(hand: HandObservation, dx: float = 0.0, dy: float = 0.0) -> HandObservation:
    """Return a copy of ``hand`` translated in the frame (for building multi-hand layouts)."""
    lm = hand.landmarks.copy()
    lm[:, 0] += dx
    lm[:, 1] += dy
    return HandObservation(lm, hand.handedness, hand.score)


@pytest.fixture
def hand_factory():
    """Return the :func:`make_hand` builder so tests can synthesise arbitrary poses."""
    return make_hand


@pytest.fixture
def frame_factory():
    """Return the :func:`make_frame` builder for wrapping hands into frames."""
    return make_frame


@pytest.fixture
def multi_frame_factory():
    """Return the :func:`make_multi_frame` builder for multi-hand frames."""
    return make_multi_frame


@pytest.fixture
def shift():
    """Return the :func:`shift_hand` translate helper."""
    return shift_hand


@pytest.fixture
def open_hand() -> HandObservation:
    return make_hand("open")


@pytest.fixture
def fist() -> HandObservation:
    return make_hand("fist")


@pytest.fixture
def pinch() -> HandObservation:
    return make_hand("pinch")
