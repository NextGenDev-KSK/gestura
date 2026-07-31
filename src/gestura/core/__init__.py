"""Pure-logic primitives with no heavy or platform-specific dependencies.

Everything here depends only on the standard library and NumPy, is fully unit-tested, and forms
the deterministic foundation the rest of the app is built on.
"""

from __future__ import annotations

from .filters import ExponentialMovingAverage, OneEuroFilter, OneEuroFilter2D
from .geometry import (
    angle_between,
    clamp,
    distance,
    finger_extended,
    midpoint,
    normalized_distance,
    palm_width,
    remap,
)
from .timing import Cooldown, RateEstimator, SchmittTrigger, StabilityGate
from .types import (
    FINGERTIPS,
    NUM_LANDMARKS,
    FrameResult,
    GestureEvent,
    GesturePhase,
    Handedness,
    HandLandmark,
    HandObservation,
)

__all__ = [
    # types
    "FINGERTIPS",
    "NUM_LANDMARKS",
    "FrameResult",
    "GestureEvent",
    "GesturePhase",
    "Handedness",
    "HandLandmark",
    "HandObservation",
    # geometry
    "angle_between",
    "clamp",
    "distance",
    "finger_extended",
    "midpoint",
    "normalized_distance",
    "palm_width",
    "remap",
    # filters
    "ExponentialMovingAverage",
    "OneEuroFilter",
    "OneEuroFilter2D",
    # timing
    "Cooldown",
    "RateEstimator",
    "SchmittTrigger",
    "StabilityGate",
]
