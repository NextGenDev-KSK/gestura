"""Per-frame feature extraction from a single hand.

Recognisers should never touch raw landmarks directly; they consume a :class:`FeatureSet` of
derived, mostly scale-invariant measurements computed once here. Centralising this keeps the
recognisers small, testable, and consistent, and means an expensive computation (e.g. finger
extension) happens exactly once per frame.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..core.geometry import finger_extended, midpoint, normalized_distance, palm_width
from ..core.types import Handedness, HandLandmark, HandObservation

FINGER_NAMES = ("thumb", "index", "middle", "ring", "pinky")


@dataclass(slots=True, frozen=True)
class FeatureSet:
    """Derived, recogniser-ready features for one hand.

    Distances suffixed ``_norm`` are in palm-width units (invariant to camera distance).
    Positions are normalized frame coordinates in ``[0, 1]`` (origin top-left).
    """

    handedness: Handedness
    score: float

    extended: dict[str, bool]
    num_extended: int

    pinch_index_norm: float   # thumb tip <-> index tip
    pinch_middle_norm: float  # thumb tip <-> middle tip

    pinch_pinky_norm: float   # thumb tip <-> pinky tip

    anchor: tuple[float, float]        # stable cursor anchor (knuckle-based, click-immune)
    palm_center: tuple[float, float]
    index_tip: tuple[float, float]

    # Thumb tip position relative to the knuckle, in palm-width units, for thumb-direction poses.
    # x: negative => thumb left of knuckles; y: negative => thumb above knuckles.
    thumb_offset: tuple[float, float]

    @property
    def thumb_vertical_offset(self) -> float:
        """Vertical component of :attr:`thumb_offset` (negative = thumb above the knuckles)."""
        return self.thumb_offset[1]

    def is_only(self, *fingers: str) -> bool:
        """True iff exactly the named fingers are extended and no others."""
        want = set(fingers)
        got = {f for f, up in self.extended.items() if up}
        return got == want


def extract(hand: HandObservation) -> FeatureSet:
    """Compute the :class:`FeatureSet` for a detected hand."""
    extended = {name: finger_extended(hand, name) for name in FINGER_NAMES}
    num_extended = sum(extended.values())

    pinch_index = normalized_distance(hand, HandLandmark.THUMB_TIP, HandLandmark.INDEX_TIP)
    pinch_middle = normalized_distance(hand, HandLandmark.THUMB_TIP, HandLandmark.MIDDLE_TIP)
    pinch_pinky = normalized_distance(hand, HandLandmark.THUMB_TIP, HandLandmark.PINKY_TIP)

    # Cursor anchor: midpoint of the index & middle knuckles. Unlike a fingertip this barely
    # moves when the user pinches or curls fingers, so clicking never nudges the cursor.
    anchor_xy = midpoint(
        hand.point(HandLandmark.INDEX_MCP)[:2], hand.point(HandLandmark.MIDDLE_MCP)[:2]
    )

    mcp_points = np.stack(
        [
            hand.point(HandLandmark.INDEX_MCP)[:2],
            hand.point(HandLandmark.MIDDLE_MCP)[:2],
            hand.point(HandLandmark.RING_MCP)[:2],
            hand.point(HandLandmark.PINKY_MCP)[:2],
            hand.point(HandLandmark.WRIST)[:2],
        ]
    )
    palm_center = mcp_points.mean(axis=0)

    index_tip = hand.point(HandLandmark.INDEX_TIP)[:2]

    scale = palm_width(hand) or 1.0
    knuckle = hand.point(HandLandmark.MIDDLE_MCP)[:2]
    thumb_tip = hand.point(HandLandmark.THUMB_TIP)[:2]
    thumb_offset = (thumb_tip - knuckle) / scale

    return FeatureSet(
        handedness=hand.handedness,
        score=hand.score,
        extended=extended,
        num_extended=num_extended,
        pinch_index_norm=pinch_index,
        pinch_middle_norm=pinch_middle,
        pinch_pinky_norm=pinch_pinky,
        anchor=(float(anchor_xy[0]), float(anchor_xy[1])),
        palm_center=(float(palm_center[0]), float(palm_center[1])),
        index_tip=(float(index_tip[0]), float(index_tip[1])),
        thumb_offset=(float(thumb_offset[0]), float(thumb_offset[1])),
    )
