"""Deterministic pipeline orchestration test using injected fakes (no camera/MediaPipe)."""

from __future__ import annotations

import time

import numpy as np

from gestura.config.models import AppSettings
from gestura.core.types import FrameResult
from gestura.engine.pipeline import GesturePipeline
from gestura.platform.base import RecordingAdapter
from gestura.vision.camera import CameraFrame, CameraStatus


class _FakeCamera:
    """Serves a fixed list of frames once, then holds the last one."""

    def __init__(self, frames: list[CameraFrame]) -> None:
        self._frames = frames
        self._i = 0
        self.status = CameraStatus.STREAMING

    def start(self) -> None: ...
    def stop(self) -> None: ...

    def latest(self) -> CameraFrame | None:
        if not self._frames:
            return None
        if self._i < len(self._frames):
            frame = self._frames[self._i]
            self._i += 1
            return frame
        return self._frames[-1]


class _FakeTracker:
    """Returns a scripted FrameResult keyed by camera frame index."""

    def __init__(self, script: dict[int, FrameResult]) -> None:
        self._script = script

    def process(self, image, *, timestamp_ms=None, frame_index=0) -> FrameResult:
        return self._script[frame_index]

    def close(self) -> None: ...


def _wait_for(predicate, timeout=3.0) -> bool:
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_pipeline_drives_click_and_cursor(hand_factory, frame_factory) -> None:
    # Script: open hand (cursor moves) then a pinch (rising edge -> left click).
    script = {
        1: frame_factory(hand_factory("open"), timestamp=0.00, index=1),
        2: frame_factory(hand_factory("pinch"), timestamp=0.10, index=2),
        3: frame_factory(hand_factory("pinch"), timestamp=0.20, index=3),
    }
    blank = np.zeros((10, 10, 3), dtype=np.uint8)
    frames = [CameraFrame(blank, index=i, timestamp=i * 0.1) for i in (1, 2, 3)]

    adapter = RecordingAdapter()
    pipeline = GesturePipeline(
        AppSettings(),
        adapter,
        camera=_FakeCamera(frames),
        tracker_factory=lambda: _FakeTracker(script),
    )
    pipeline.start()
    try:
        assert _wait_for(lambda: "click" in adapter.names()), "expected a left click from the pinch"
        assert _wait_for(lambda: adapter.cursor != (0.5, 0.5)), "expected the cursor to move"
    finally:
        pipeline.stop()

    # Exactly one click for one pinch (no machine-gunning while held).
    assert adapter.names().count("click") == 1


def test_pipeline_reports_model_error_without_crashing() -> None:
    def boom() -> None:
        from gestura.vision.hand_tracker import ModelNotFoundError

        raise ModelNotFoundError("no model")

    frames = [CameraFrame(np.zeros((4, 4, 3), np.uint8), index=1, timestamp=0.0)]
    pipeline = GesturePipeline(
        AppSettings(), RecordingAdapter(),
        camera=_FakeCamera(frames), tracker_factory=boom,
    )
    pipeline.start()
    try:
        assert _wait_for(lambda: pipeline.init_error is not None)
        assert "no model" in pipeline.init_error
    finally:
        pipeline.stop()
