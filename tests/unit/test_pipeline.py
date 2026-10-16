"""Deterministic pipeline orchestration test using injected fakes (no camera/MediaPipe)."""

from __future__ import annotations

import time

import numpy as np

from gestura.config.models import AppSettings
from gestura.core.types import FrameResult
from gestura.engine.pipeline import GesturePipeline
from gestura.platform.base import MouseButton, RecordingAdapter
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


# --- In-app gesture trainer ---------------------------------------------------------------------
def _trainer_pipeline(tmp_path, adapter=None) -> GesturePipeline:
    frames = [CameraFrame(np.zeros((4, 4, 3), np.uint8), index=1, timestamp=0.0)]
    return GesturePipeline(
        AppSettings(), adapter or RecordingAdapter(),
        camera=_FakeCamera(frames), tracker_factory=lambda: _FakeTracker({}),
        custom_store=tmp_path / "custom_gestures.json",
    )


def test_recording_saves_a_gesture_that_is_then_recognised(tmp_path, hand_factory,
                                                           frame_factory) -> None:
    from gestura.engine.custom import CustomGestureClassifier

    pipe = _trainer_pipeline(tmp_path)
    pipe.start_recording("horns", samples=5, timeout=10.0)
    assert pipe.recording_status.active

    rock = hand_factory("rock")
    for i in range(5):
        assert pipe._feed_recording(frame_factory(rock, timestamp=i * 0.03), now=0.0)
    status = pipe.recording_status
    assert status.state == "done" and status.collected == 5
    assert pipe.custom_gestures() == {"horns": 5}

    # Persisted to the injected store...
    saved = CustomGestureClassifier.load(tmp_path / "custom_gestures.json")
    assert saved.sample_count("horns") == 5
    # ...and live in the interpreter without a restart.
    events = []
    for i in range(12):
        events += pipe._interpreter.update(frame_factory(rock, timestamp=1.0 + i * 0.05)).events
    assert any(e.name == "horns" for e in events)


def test_recording_ignores_frames_without_a_confident_hand(tmp_path, hand_factory,
                                                          frame_factory) -> None:
    pipe = _trainer_pipeline(tmp_path)
    pipe.start_recording("wave", samples=3, timeout=10.0)
    pipe._feed_recording(frame_factory(None, timestamp=0.0), now=0.0)
    pipe._feed_recording(frame_factory(hand_factory("open", score=0.2), timestamp=0.1), now=0.0)
    assert pipe.recording_status.collected == 0
    assert pipe.recording_status.active


def test_recording_times_out_without_saving(tmp_path, hand_factory, frame_factory) -> None:
    pipe = _trainer_pipeline(tmp_path)
    pipe.start_recording("wave", samples=40, timeout=5.0)
    deadline = time.perf_counter() + 5.0
    pipe._feed_recording(frame_factory(hand_factory("open"), timestamp=0.0), now=deadline + 1)
    assert pipe.recording_status.state == "failed"
    assert pipe.custom_gestures() == {}
    assert not (tmp_path / "custom_gestures.json").exists()
    assert not pipe._feed_recording(frame_factory(None, timestamp=0.1), now=0.0)  # session over


def test_cancel_and_delete_custom_gestures(tmp_path, hand_factory, frame_factory) -> None:
    pipe = _trainer_pipeline(tmp_path)
    pipe.start_recording("wave", samples=2)
    pipe.cancel_recording()
    assert pipe.recording_status.state == "cancelled"
    assert not pipe._feed_recording(frame_factory(hand_factory("open"), timestamp=0.0), now=0.0)

    pipe.start_recording("wave", samples=2)
    for i in range(2):
        pipe._feed_recording(frame_factory(hand_factory("open"), timestamp=i * 0.03), now=0.0)
    assert pipe.custom_gestures() == {"wave": 2}
    assert pipe.delete_custom_gesture("wave")
    assert pipe.custom_gestures() == {}
    assert not pipe.delete_custom_gesture("wave")


def test_rerecording_replaces_old_samples(tmp_path, hand_factory, frame_factory) -> None:
    pipe = _trainer_pipeline(tmp_path)
    for samples in (4, 2):
        pipe.start_recording("wave", samples=samples)
        for i in range(samples):
            pipe._feed_recording(frame_factory(hand_factory("open"), timestamp=i * 0.03), now=0.0)
    assert pipe.custom_gestures() == {"wave": 2}


def test_while_recording_actions_are_suppressed_but_drags_still_release(
        tmp_path, hand_factory, frame_factory) -> None:
    """Posing for the trainer must never click/drag — yet a drag already held must drop."""
    adapter = RecordingAdapter()
    hands = [hand_factory("fist")] * 6 + [hand_factory("pinch")] * 4
    script = {i + 1: frame_factory(h, timestamp=i * 0.05, index=i + 1) for i, h in enumerate(hands)}
    frames = [CameraFrame(np.zeros((4, 4, 3), np.uint8), index=i, timestamp=0.0)
              for i in script]

    class _GatedCamera(_FakeCamera):
        """Holds at the last fist frame until released, so the test can start recording there."""

        def __init__(self, frames) -> None:
            super().__init__(frames)
            self.hold_at = 6

        def latest(self):
            if self._i >= self.hold_at:
                return self._frames[self._i - 1]
            return super().latest()

    camera = _GatedCamera(frames)
    pipe = GesturePipeline(
        AppSettings(), adapter, camera=camera, tracker_factory=lambda: _FakeTracker(script),
        custom_store=tmp_path / "custom_gestures.json",
    )
    pipe.start()
    try:
        assert _wait_for(lambda: MouseButton.LEFT in adapter.buttons_down), "fist should grab"
        pipe.start_recording("pose", samples=100, timeout=30.0)
        moves_before = adapter.names().count("move_cursor")
        camera.hold_at = len(frames)  # release the pinch frames
        assert _wait_for(lambda: MouseButton.LEFT not in adapter.buttons_down), "drag must drop"
        assert _wait_for(lambda: pipe.recording_status.collected >= 4)
    finally:
        pipe.stop()
    assert "click" not in adapter.names()                     # the pinch did not click
    assert adapter.names().count("move_cursor") == moves_before  # and the cursor stayed put


# --- Reach calibration & live restarts -----------------------------------------------------------
def test_calibration_fits_a_region_from_the_sweep(tmp_path, hand_factory, frame_factory,
                                                  shift) -> None:
    pipe = _trainer_pipeline(tmp_path)
    pipe.start_calibration(duration=1.0)
    t0 = pipe._calibration.started
    base = hand_factory("open")
    for i in range(60):                       # sweep: a grid of hand positions
        dx, dy = (i % 6) * 0.04 - 0.1, (i // 6 % 5) * 0.04 - 0.08
        assert pipe._feed_calibration(frame_factory(shift(base, dx, dy), timestamp=0.0),
                                      now=t0 + i * 0.015)
    assert pipe.calibration_status.active
    assert 0.8 < pipe.calibration_status.progress < 1.0
    pipe._feed_calibration(frame_factory(base, timestamp=0.0), now=t0 + 1.0)
    status = pipe.calibration_status
    assert status.state == "done" and status.samples == 61
    x0, y0, x1, y1 = status.region
    assert 0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1
    assert not pipe._feed_calibration(frame_factory(base, timestamp=0.0), now=t0 + 2)  # finished


def test_calibration_without_a_hand_fails_cleanly(tmp_path, frame_factory) -> None:
    pipe = _trainer_pipeline(tmp_path)
    pipe.start_calibration(duration=0.5)
    t0 = pipe._calibration.started
    pipe._feed_calibration(frame_factory(None, timestamp=0.0), now=t0 + 0.6)
    status = pipe.calibration_status
    assert status.state == "failed" and status.region is None and status.message
    pipe.start_calibration(duration=5)
    pipe.cancel_calibration()
    assert pipe.calibration_status.state == "cancelled"


class _CountingCamera(_FakeCamera):
    def __init__(self, frames) -> None:
        super().__init__(frames)
        self.starts = 0

    def start(self) -> None:
        self.starts += 1


def test_camera_settings_reopen_the_camera_but_tuning_does_not(tmp_path, hand_factory,
                                                              frame_factory) -> None:
    script = {1: frame_factory(hand_factory("open"), timestamp=0.0, index=1)}
    camera = _CountingCamera([CameraFrame(np.zeros((4, 4, 3), np.uint8), index=1, timestamp=0.0)])
    settings = AppSettings()
    pipe = GesturePipeline(settings, RecordingAdapter(), camera=camera,
                           tracker_factory=lambda: _FakeTracker(script),
                           custom_store=tmp_path / "c.json")
    pipe.start()
    try:
        assert camera.starts == 1
        settings.profile().cursor.smoothing_beta = 0.2       # tuning: applied in place
        pipe.apply_settings(settings)
        time.sleep(0.3)
        assert camera.starts == 1
        settings.profile().camera.mirror = not settings.profile().camera.mirror
        pipe.apply_settings(settings)                       # hardware: reopen in the background
        assert _wait_for(lambda: camera.starts == 2)
        assert _wait_for(lambda: pipe.running)
    finally:
        pipe.stop()
