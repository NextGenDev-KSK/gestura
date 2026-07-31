"""Gesture engine: features -> recognisers -> temporal interpretation -> cursor + events."""

from __future__ import annotations

from .cursor import CursorController
from .features import FeatureSet, extract
from .interpreter import GestureInterpreter, InterpretationResult, Mode
from .pipeline import GesturePipeline, PipelineTelemetry
from .recognizers import Pose, classify_static_pose

__all__ = [
    "CursorController",
    "FeatureSet",
    "extract",
    "GestureInterpreter",
    "InterpretationResult",
    "Mode",
    "GesturePipeline",
    "PipelineTelemetry",
    "Pose",
    "classify_static_pose",
]
