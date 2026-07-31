"""Vision layer: webcam capture and MediaPipe hand tracking.

Importing this package pulls in OpenCV; the MediaPipe import is deferred until a
:class:`HandTracker` is actually constructed.
"""

from __future__ import annotations

from .camera import CameraFrame, CameraSource, CameraStatus, list_cameras
from .hand_tracker import DEFAULT_MODEL_FILENAME, HandTracker, ModelNotFoundError

__all__ = [
    "CameraFrame",
    "CameraSource",
    "CameraStatus",
    "list_cameras",
    "DEFAULT_MODEL_FILENAME",
    "HandTracker",
    "ModelNotFoundError",
]
