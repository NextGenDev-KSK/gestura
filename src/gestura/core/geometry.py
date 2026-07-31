"""Small, dependency-free geometry helpers used by the gesture engine.

All functions operate on plain NumPy arrays so they can be composed cheaply on the hot path.
Landmark coordinates are normalized (see :class:`~gestura.core.types.HandObservation`); many
measurements are therefore expressed *relative to hand scale* (see :func:`palm_width`) so they
stay invariant to how close the hand is to the camera.
"""

from __future__ import annotations

import numpy as np

from .types import HandLandmark, HandObservation


def distance(a: np.ndarray, b: np.ndarray) -> float:
    """Euclidean distance between two coordinate vectors of equal length."""
    return float(np.linalg.norm(a - b))


def midpoint(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Component-wise midpoint of two vectors."""
    return (a + b) * 0.5


def angle_between(v1: np.ndarray, v2: np.ndarray) -> float:
    """Return the unsigned angle between two vectors in **radians**, in ``[0, π]``.

    Returns ``0.0`` if either vector has (near-)zero length, which is the safe, non-triggering
    default for degenerate hand poses.
    """
    n1 = float(np.linalg.norm(v1))
    n2 = float(np.linalg.norm(v2))
    if n1 < 1e-9 or n2 < 1e-9:
        return 0.0
    cosine = float(np.dot(v1, v2) / (n1 * n2))
    # Guard against tiny floating-point overshoots outside the valid arccos domain.
    return float(np.arccos(max(-1.0, min(1.0, cosine))))


def palm_width(hand: HandObservation) -> float:
    """A robust, scale-defining span: distance between the index and pinky knuckles (2-D).

    This is stable regardless of finger flexion and is used to normalize other distances so
    thresholds hold whether the hand is near or far from the camera. Uses only ``x``/``y`` to
    avoid the noisier ``z`` channel.
    """
    a = hand.point(HandLandmark.INDEX_MCP)[:2]
    b = hand.point(HandLandmark.PINKY_MCP)[:2]
    return distance(a, b)


def normalized_distance(hand: HandObservation, a: HandLandmark, b: HandLandmark) -> float:
    """Distance between two landmarks expressed in units of :func:`palm_width` (scale-invariant).

    Returns ``0.0`` if the palm span is degenerate, avoiding division by zero.
    """
    scale = palm_width(hand)
    if scale < 1e-6:
        return 0.0
    pa = hand.point(a)[:2]
    pb = hand.point(b)[:2]
    return distance(pa, pb) / scale


def finger_extended(hand: HandObservation, finger: str, *, straightness: float = 2.6) -> bool:
    """Heuristic: is ``finger`` ('index'|'middle'|'ring'|'pinky'|'thumb') extended?

    A finger is considered extended when its three bone segments are nearly colinear — i.e. the
    accumulated joint bend is small. This is orientation-independent (works for any hand
    rotation), unlike the common "tip is above the knuckle" test which assumes an upright hand.

    Args:
        straightness: Minimum sum-of-segment length as a multiple of the straight-line
            MCP→TIP distance's inverse... see implementation; larger = stricter.
    """
    chain = _FINGER_CHAINS[finger]
    pts = [hand.point(j)[:2] for j in chain]
    # Angle at each interior joint; sum of bends small => straight finger.
    total_bend = 0.0
    for i in range(1, len(pts) - 1):
        total_bend += np.pi - angle_between(pts[i - 1] - pts[i], pts[i + 1] - pts[i])
    # `straightness` is a bend budget in radians (default ≈ 0.54 rad total across joints scaled).
    return total_bend < (np.pi / straightness)


_FINGER_CHAINS: dict[str, tuple[HandLandmark, ...]] = {
    "thumb": (
        HandLandmark.THUMB_CMC,
        HandLandmark.THUMB_MCP,
        HandLandmark.THUMB_IP,
        HandLandmark.THUMB_TIP,
    ),
    "index": (
        HandLandmark.INDEX_MCP,
        HandLandmark.INDEX_PIP,
        HandLandmark.INDEX_DIP,
        HandLandmark.INDEX_TIP,
    ),
    "middle": (
        HandLandmark.MIDDLE_MCP,
        HandLandmark.MIDDLE_PIP,
        HandLandmark.MIDDLE_DIP,
        HandLandmark.MIDDLE_TIP,
    ),
    "ring": (
        HandLandmark.RING_MCP,
        HandLandmark.RING_PIP,
        HandLandmark.RING_DIP,
        HandLandmark.RING_TIP,
    ),
    "pinky": (
        HandLandmark.PINKY_MCP,
        HandLandmark.PINKY_PIP,
        HandLandmark.PINKY_DIP,
        HandLandmark.PINKY_TIP,
    ),
}


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    """Clamp ``value`` into the inclusive range ``[low, high]``."""
    return max(low, min(high, value))


def remap(
    value: float, in_lo: float, in_hi: float, out_lo: float, out_hi: float, *, clip: bool = True
) -> float:
    """Linearly remap ``value`` from one range to another, optionally clipping to the output."""
    if abs(in_hi - in_lo) < 1e-12:
        return out_lo
    t = (value - in_lo) / (in_hi - in_lo)
    result = out_lo + t * (out_hi - out_lo)
    if clip:
        lo, hi = (out_lo, out_hi) if out_lo <= out_hi else (out_hi, out_lo)
        result = max(lo, min(hi, result))
    return result
