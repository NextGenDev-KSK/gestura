"""Core domain types shared across every layer.

These are deliberately lightweight (``dataclass`` with ``slots``, no Pydantic) because
instances of :class:`HandObservation` and :class:`FrameResult` are created on the hot path —
up to 60 times per second. Validated/persisted models live in :mod:`gestura.config`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, IntEnum

import numpy as np


class HandLandmark(IntEnum):
    """Indices of the 21 landmarks produced by MediaPipe HandLandmarker.

    Reference: https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker
    """

    WRIST = 0
    THUMB_CMC = 1
    THUMB_MCP = 2
    THUMB_IP = 3
    THUMB_TIP = 4
    INDEX_MCP = 5
    INDEX_PIP = 6
    INDEX_DIP = 7
    INDEX_TIP = 8
    MIDDLE_MCP = 9
    MIDDLE_PIP = 10
    MIDDLE_DIP = 11
    MIDDLE_TIP = 12
    RING_MCP = 13
    RING_PIP = 14
    RING_DIP = 15
    RING_TIP = 16
    PINKY_MCP = 17
    PINKY_PIP = 18
    PINKY_DIP = 19
    PINKY_TIP = 20


#: Landmark index of each finger's tip, keyed by a stable finger name.
FINGERTIPS: dict[str, HandLandmark] = {
    "thumb": HandLandmark.THUMB_TIP,
    "index": HandLandmark.INDEX_TIP,
    "middle": HandLandmark.MIDDLE_TIP,
    "ring": HandLandmark.RING_TIP,
    "pinky": HandLandmark.PINKY_TIP,
}

#: Number of landmarks in a single hand.
NUM_LANDMARKS = 21


class Handedness(Enum):
    """Which hand was detected, from the camera's point of view."""

    LEFT = "left"
    RIGHT = "right"


@dataclass(slots=True, frozen=True)
class HandObservation:
    """A single hand detected in one frame.

    Attributes:
        landmarks: ``(21, 3)`` float32 array of normalized coordinates. ``x`` and ``y`` are in
            ``[0, 1]`` relative to the frame (origin top-left); ``z`` is relative depth with the
            wrist near ``0`` and smaller (more negative) values closer to the camera.
        handedness: Detected :class:`Handedness`.
        score: Detection/handedness confidence in ``[0, 1]``.
    """

    landmarks: np.ndarray
    handedness: Handedness
    score: float

    def __post_init__(self) -> None:
        if self.landmarks.shape != (NUM_LANDMARKS, 3):
            raise ValueError(
                f"landmarks must have shape ({NUM_LANDMARKS}, 3), got {self.landmarks.shape}"
            )

    def point(self, landmark: HandLandmark) -> np.ndarray:
        """Return the ``(3,)`` coordinate of a named landmark."""
        return self.landmarks[int(landmark)]

    @property
    def wrist(self) -> np.ndarray:
        """The wrist coordinate — a convenient stable anchor for the hand."""
        return self.landmarks[int(HandLandmark.WRIST)]


@dataclass(slots=True, frozen=True)
class FrameResult:
    """The full hand-tracking result for one camera frame.

    Attributes:
        hands: Zero or more detected hands, ordered by descending detection score.
        width: Source frame width in pixels.
        height: Source frame height in pixels.
        frame_index: Monotonic counter assigned by the capture loop.
        timestamp: ``time.perf_counter()`` seconds when the frame was captured.
    """

    hands: tuple[HandObservation, ...]
    width: int
    height: int
    frame_index: int
    timestamp: float = field(default_factory=time.perf_counter)

    @property
    def has_hand(self) -> bool:
        return len(self.hands) > 0

    @property
    def primary(self) -> HandObservation | None:
        """The highest-confidence hand, or ``None`` if tracking is lost."""
        return self.hands[0] if self.hands else None


class GesturePhase(Enum):
    """Lifecycle phase of a gesture, enabling press/hold/release semantics.

    A momentary gesture (e.g. a click) fires ``BEGAN`` then ``ENDED``; a continuous one
    (e.g. drag or scroll) emits ``BEGAN`` → repeated ``UPDATED`` → ``ENDED``.
    """

    BEGAN = "began"
    UPDATED = "updated"
    ENDED = "ended"


@dataclass(slots=True, frozen=True)
class GestureEvent:
    """A recognised gesture emitted by the engine for the dispatcher to act on.

    Attributes:
        name: Canonical gesture id (e.g. ``"pinch"``, ``"open_palm"``) or a custom-gesture name.
        phase: :class:`GesturePhase` of this event.
        confidence: Recognition confidence in ``[0, 1]``.
        position: Optional normalized ``(x, y)`` anchor (e.g. cursor target) in ``[0, 1]``.
        payload: Gesture-specific extras (e.g. scroll delta, zoom scale). Never ``None``.
        timestamp: ``time.perf_counter()`` seconds when the event was produced.
    """

    name: str
    phase: GesturePhase
    confidence: float
    position: tuple[float, float] | None = None
    payload: dict[str, float] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.perf_counter)
