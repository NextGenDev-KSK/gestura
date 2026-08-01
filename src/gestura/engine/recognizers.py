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
    """Canonical static-pose ids (kept as plain strings to match config bindings).

    The vocabulary is deliberately chosen so **no two poses are one small perturbation apart**:
    each shape has a unique extended-finger pattern, and the four thumb directions are separated
    by a dominant-axis test with a dead-zone (see :func:`classify_static_pose`).
    """

    NONE: Final = "none"
    FIST: Final = "fist"
    OPEN_PALM: Final = "open_palm"
    POINT: Final = "point"
    VICTORY: Final = "victory"           # index + middle
    THREE_FINGERS: Final = "three_fingers"  # index + middle + ring
    ROCK: Final = "rock"                 # index + pinky ("horns")
    PINKY: Final = "pinky"               # pinky only
    THUMB_UP: Final = "thumb_up"
    THUMB_DOWN: Final = "thumb_down"
    THUMB_LEFT: Final = "thumb_left"
    THUMB_RIGHT: Final = "thumb_right"


# Thumb-direction thresholds (palm-width units). A thumb pose requires the thumb to reach clearly
# past THUMB_DIR_MIN in one dominant axis; below THUMB_TUCK_MAX it's a plain fist. The gap between
# them is a dead-zone that returns NONE, so a resting/ambiguous thumb never flickers a gesture.
_THUMB_DIR_MIN = 0.85
_THUMB_TUCK_MAX = 0.55
#: The dominant axis must exceed the other by this ratio, so "up" can't bleed into "left" etc.
_THUMB_AXIS_RATIO = 1.35


def classify_static_pose(f: FeatureSet) -> tuple[str, float]:
    """Return the dominant static pose and a confidence in ``[0, 1]``.

    The confidence is the detector's own hand score. Ambiguous hands (transitional shapes, a
    diagonally-held thumb, a half-curled finger) return :attr:`Pose.NONE` so the interpreter does
    nothing — the safe default that prevents false triggers.
    """
    ext = f.extended
    index, middle, ring, pinky = ext["index"], ext["middle"], ext["ring"], ext["pinky"]

    # Open palm: all four fingers extended (thumb optional).
    if index and middle and ring and pinky:
        return Pose.OPEN_PALM, f.score

    # No fingers extended: a fist, or a directional thumb pose.
    if not (index or middle or ring or pinky):
        return _classify_thumb(f)

    # Single-finger poses.
    if index and not middle and not ring and not pinky:
        return Pose.POINT, f.score
    if pinky and not index and not middle and not ring:
        return Pose.PINKY, f.score

    # Two-finger poses (distinct patterns).
    if index and middle and not ring and not pinky:
        return Pose.VICTORY, f.score
    if index and pinky and not middle and not ring:
        return Pose.ROCK, f.score

    # Three-finger pose.
    if index and middle and ring and not pinky:
        return Pose.THREE_FINGERS, f.score

    # Anything else (e.g. an unusual/ambiguous combination) is intentionally ignored.
    return Pose.NONE, 0.0


def _classify_thumb(f: FeatureSet) -> tuple[str, float]:
    """Classify the all-fingers-curled hand as a fist or a directional thumb pose."""
    dx, dy = f.thumb_offset
    magnitude = (dx * dx + dy * dy) ** 0.5

    # Thumb clearly tucked -> a plain fist (used for drag).
    if not f.extended["thumb"] or magnitude < _THUMB_TUCK_MAX:
        return Pose.FIST, f.score
    # Between the two thresholds: ambiguous -> do nothing (prevents fist<->thumb chatter).
    if magnitude < _THUMB_DIR_MIN:
        return Pose.NONE, 0.0

    # Pick the dominant axis; require it to clearly beat the other so diagonals fire nothing.
    if abs(dy) >= abs(dx) * _THUMB_AXIS_RATIO:
        return (Pose.THUMB_UP if dy < 0 else Pose.THUMB_DOWN), f.score
    if abs(dx) >= abs(dy) * _THUMB_AXIS_RATIO:
        return (Pose.THUMB_LEFT if dx < 0 else Pose.THUMB_RIGHT), f.score
    return Pose.NONE, 0.0
