"""Rule-based static-pose recognition (ADR-0002/0003).

These deterministic recognisers cover the built-in gesture vocabulary with zero latency and no
training. Custom, user-recorded gestures are handled separately by the ONNX classifier; this
module is intentionally the "known-good, explainable" path.

A *static pose* is the hand's shape in a single frame (fist, open palm, pointing, …). Dynamic and
contact gestures (pinch to click, drag, scroll) are derived by the temporal
:mod:`~gestura.engine.interpreter` from these poses plus the raw distances in the
:class:`~gestura.engine.features.FeatureSet` — because, for example, a "pinch" can happen while
the hand is otherwise pointing, so it is not mutually exclusive with a shape.
"""

from __future__ import annotations

from typing import Final

from .features import FeatureSet


class Pose:
    """Canonical static-pose ids (kept as plain strings to match config bindings)."""

    NONE: Final = "none"
    FIST: Final = "fist"
    OPEN_PALM: Final = "open_palm"
    POINT: Final = "point"
    VICTORY: Final = "victory"
    THUMB_UP: Final = "thumb_up"
    THUMB_DOWN: Final = "thumb_down"


#: How far (palm-width units) the thumb tip must be above/below the knuckles for up/down.
_THUMB_UPDOWN_MARGIN = 0.6


def classify_static_pose(f: FeatureSet) -> tuple[str, float]:
    """Return the dominant static pose and a confidence in ``[0, 1]``.

    The confidence is the detector's own hand score gated by how cleanly the finger pattern
    matches; ambiguous hands return :attr:`Pose.NONE` so the interpreter simply does nothing
    (a safe default that avoids false triggers).
    """
    ext = f.extended
    fingers_up = (ext["index"], ext["middle"], ext["ring"], ext["pinky"])

    # Open palm: all four fingers extended (thumb optional).
    if all(fingers_up):
        return Pose.OPEN_PALM, f.score

    # Fist: no fingers extended (thumb ignored — it often reads ambiguously when curled).
    if not any(fingers_up):
        # Distinguish a plain fist from a thumb up/down by the thumb's vertical placement.
        if ext["thumb"] and f.thumb_vertical_offset < -_THUMB_UPDOWN_MARGIN:
            return Pose.THUMB_UP, f.score
        if ext["thumb"] and f.thumb_vertical_offset > _THUMB_UPDOWN_MARGIN:
            return Pose.THUMB_DOWN, f.score
        return Pose.FIST, f.score

    # Pointing: only the index finger up.
    if ext["index"] and not ext["middle"] and not ext["ring"] and not ext["pinky"]:
        return Pose.POINT, f.score

    # Victory / two-finger: index and middle up, ring and pinky down.
    if ext["index"] and ext["middle"] and not ext["ring"] and not ext["pinky"]:
        return Pose.VICTORY, f.score

    return Pose.NONE, 0.0
