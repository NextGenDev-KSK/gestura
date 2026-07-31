"""MediaPipe HandLandmarker wrapper (ADR-0002).

Turns a raw BGR camera frame into a strongly-typed :class:`FrameResult` of hand landmarks. The
heavy MediaPipe import is deferred to construction so importing this module (e.g. in CI running
only pure-logic tests) doesn't require the native library.

Handedness note: MediaPipe labels handedness assuming a non-mirrored image. Gestura shows a
mirrored "selfie" view, so when ``mirrored=True`` we swap the label back to match the user's
actual hand — the intuitive behaviour for on-screen guidance.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from ..core.types import FrameResult, Handedness, HandObservation
from ..util.logging import get_logger
from ..util.paths import models_dir

_log = get_logger("gestura.vision.tracker")

DEFAULT_MODEL_FILENAME = "hand_landmarker.task"


class ModelNotFoundError(FileNotFoundError):
    """Raised when the hand-landmark model file is missing (run scripts/fetch_models.py)."""


class HandTracker:
    """Stateful, single-threaded hand-landmark detector.

    Not thread-safe: create and call it from a single worker thread (the pipeline owns one).
    """

    def __init__(
        self,
        *,
        model_path: Path | None = None,
        num_hands: int = 1,
        min_detection_confidence: float = 0.5,
        min_presence_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
        use_gpu: bool = False,
        mirrored: bool = True,
    ) -> None:
        self.mirrored = mirrored
        self._model_path = Path(model_path) if model_path else (models_dir() / DEFAULT_MODEL_FILENAME)
        if not self._model_path.exists():
            raise ModelNotFoundError(
                f"Hand-landmark model not found at {self._model_path}. "
                "Run: python scripts/fetch_models.py"
            )

        # Deferred heavy imports.
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision as mp_vision

        self._mp = mp
        self._mp_vision = mp_vision

        delegate = (
            mp_python.BaseOptions.Delegate.GPU if use_gpu else mp_python.BaseOptions.Delegate.CPU
        )
        base = mp_python.BaseOptions(
            model_asset_path=str(self._model_path), delegate=delegate
        )
        options = mp_vision.HandLandmarkerOptions(
            base_options=base,
            running_mode=mp_vision.RunningMode.VIDEO,
            num_hands=num_hands,
            min_hand_detection_confidence=min_detection_confidence,
            min_hand_presence_confidence=min_presence_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )
        try:
            self._landmarker = mp_vision.HandLandmarker.create_from_options(options)
        except Exception:  # noqa: BLE001 - GPU delegate can fail; fall back to CPU
            if use_gpu:
                _log.warning("GPU delegate failed to initialise; falling back to CPU")
                base = mp_python.BaseOptions(
                    model_asset_path=str(self._model_path),
                    delegate=mp_python.BaseOptions.Delegate.CPU,
                )
                options.base_options = base
                self._landmarker = mp_vision.HandLandmarker.create_from_options(options)
            else:
                raise

        self._last_ts_ms = -1
        _log.info("HandTracker ready (model=%s, gpu=%s, num_hands=%d)",
                  self._model_path.name, use_gpu, num_hands)

    # -- inference -----------------------------------------------------------------------------
    def process(self, image_bgr: np.ndarray, *, timestamp_ms: int | None = None,
                frame_index: int = 0) -> FrameResult:
        """Detect hands in one BGR frame and return a :class:`FrameResult`.

        Args:
            image_bgr: HxWx3 uint8 BGR image (as produced by OpenCV).
            timestamp_ms: Monotonic millisecond timestamp for MediaPipe's video tracker. If
                omitted, an internal strictly-increasing counter is used.
            frame_index: Value copied into the returned ``FrameResult.frame_index``.
        """
        height, width = image_bgr.shape[:2]

        # MediaPipe expects contiguous RGB.
        rgb = np.ascontiguousarray(image_bgr[:, :, ::-1])
        mp_image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)

        ts = self._next_timestamp(timestamp_ms)
        result = self._landmarker.detect_for_video(mp_image, ts)

        hands = self._to_observations(result)
        return FrameResult(hands=hands, width=width, height=height, frame_index=frame_index)

    def _next_timestamp(self, timestamp_ms: int | None) -> int:
        # detect_for_video requires strictly increasing timestamps.
        ts = self._last_ts_ms + 1 if timestamp_ms is None else int(timestamp_ms)
        if ts <= self._last_ts_ms:
            ts = self._last_ts_ms + 1
        self._last_ts_ms = ts
        return ts

    def _to_observations(self, result: object) -> tuple[HandObservation, ...]:
        landmarks_list = getattr(result, "hand_landmarks", None) or []
        handedness_list = getattr(result, "handedness", None) or []

        observations: list[HandObservation] = []
        for i, landmarks in enumerate(landmarks_list):
            coords = np.empty((21, 3), dtype=np.float32)
            for j, lm in enumerate(landmarks):
                coords[j] = (lm.x, lm.y, lm.z)

            handedness, score = self._resolve_handedness(handedness_list, i)
            observations.append(
                HandObservation(landmarks=coords, handedness=handedness, score=score)
            )

        # Highest-confidence hand first (FrameResult.primary relies on this ordering).
        observations.sort(key=lambda o: o.score, reverse=True)
        return tuple(observations)

    def _resolve_handedness(self, handedness_list: list, i: int) -> tuple[Handedness, float]:
        if i >= len(handedness_list) or not handedness_list[i]:
            return Handedness.RIGHT, 0.0
        category = handedness_list[i][0]
        label = category.category_name.lower()  # "left" / "right"
        score = float(category.score)
        hand = Handedness.LEFT if label == "left" else Handedness.RIGHT
        if self.mirrored:
            # Undo MediaPipe's non-mirrored assumption so the label matches the real hand.
            hand = Handedness.RIGHT if hand is Handedness.LEFT else Handedness.LEFT
        return hand, score

    # -- lifecycle -----------------------------------------------------------------------------
    def close(self) -> None:
        closer = getattr(self._landmarker, "close", None)
        if callable(closer):
            closer()

    def __enter__(self) -> HandTracker:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
