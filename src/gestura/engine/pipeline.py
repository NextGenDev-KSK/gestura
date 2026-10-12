"""End-to-end gesture pipeline orchestration.

Ties the layers together on a dedicated worker thread:

    CameraSource (capture thread) --> HandTracker --> GestureInterpreter --> ActionDispatcher

MediaPipe is not thread-safe, so the tracker is created and used **only** on the worker thread.
The UI (or the CLI demo) subscribes via ``on_update`` to receive each frame's result and live
telemetry (FPS, inference time, pose, mode) without ever touching the engine internals.

Run the headless demo to verify the whole stack against your webcam::

    python -m gestura.engine.pipeline --demo          # dry-run: prints gestures, moves nothing
    python -m gestura.engine.pipeline --demo --live   # actually controls the cursor
"""

from __future__ import annotations

import argparse
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..actions.dispatcher import ActionDispatcher
from ..config.models import AppSettings
from ..core.timing import RateEstimator
from ..core.types import FrameResult, GesturePhase
from ..platform.base import OSAdapter
from ..util.logging import get_logger
from ..util.paths import data_dir
from ..vision.camera import CameraSource, CameraStatus
from ..vision.hand_tracker import HandTracker, ModelNotFoundError
from .custom import CustomGestureClassifier, landmark_feature
from .interpreter import GestureInterpreter, InterpretationResult

_log = get_logger("gestura.pipeline")

CUSTOM_GESTURES_FILENAME = "custom_gestures.json"
_RECORD_MIN_CONFIDENCE = 0.6  # only learn from confidently-tracked frames


@dataclass(frozen=True)
class PipelineTelemetry:
    """Live health/perf numbers for the HUD."""

    fps: float
    inference_ms: float
    hand_present: bool
    pose: str
    mode: str
    paused: bool
    camera_status: str


@dataclass(frozen=True)
class RecordingStatus:
    """Progress of an in-app custom-gesture recording, for the trainer UI.

    ``state`` is one of ``idle``, ``recording``, ``done``, ``failed`` or ``cancelled``.
    """

    state: str = "idle"
    name: str = ""
    collected: int = 0
    target: int = 0
    message: str = ""

    @property
    def active(self) -> bool:
        return self.state == "recording"


@dataclass
class _Recording:
    name: str
    target: int
    deadline: float
    features: list[np.ndarray] = field(default_factory=list)


# on_update(source_bgr_image, tracking_result, interpretation, telemetry)
UpdateCallback = Callable[
    [np.ndarray, FrameResult, InterpretationResult, PipelineTelemetry], None
]


class GesturePipeline:
    """Owns the camera, tracker, interpreter, and dispatcher and runs the processing loop."""

    def __init__(
        self,
        settings: AppSettings,
        adapter: OSAdapter,
        *,
        on_update: UpdateCallback | None = None,
        on_camera_status: Callable[[CameraStatus], None] | None = None,
        camera: CameraSource | None = None,
        tracker_factory: Callable[[], HandTracker] | None = None,
        custom_store: Path | None = None,
    ) -> None:
        # ``camera``, ``tracker_factory`` and ``custom_store`` are injection points for tests;
        # production code omits them and the real webcam/MediaPipe tracker and the per-user
        # custom-gesture library are used.
        self._settings = settings
        self._profile = settings.profile()
        self._adapter = adapter
        self._on_update = on_update
        self._external_status_cb = on_camera_status
        self._tracker_factory = tracker_factory

        self._custom_path = custom_store or (data_dir() / CUSTOM_GESTURES_FILENAME)
        self._custom = CustomGestureClassifier.load(self._custom_path)
        self._interpreter = GestureInterpreter(self._profile, custom=self._custom)
        # Guards the interpreter's classifier and the recording session, which the GUI thread
        # edits while the engine thread reads them every frame.
        self._engine_lock = threading.Lock()
        self._recording: _Recording | None = None
        self._recording_status = RecordingStatus()
        self._dispatcher = ActionDispatcher(
            adapter, self._profile, paused=settings.paused
        )
        cam = self._profile.camera
        self._camera = camera or CameraSource(
            cam.device_index, width=cam.width, height=cam.height, fps=cam.target_fps,
            mirror=cam.mirror, on_status=self._on_camera_status,
        )

        self._tracker: HandTracker | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._fps = RateEstimator(window=1.0)
        self._last_telemetry = PipelineTelemetry(
            0, 0, False, "none", "IDLE", settings.paused, "idle")
        self._camera_status = CameraStatus.IDLE
        self._init_error: str | None = None

    # -- lifecycle -----------------------------------------------------------------------------
    def start(self) -> None:
        """Open the camera and start the processing thread (idempotent)."""
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._init_error = None
        self._camera.start()
        self._thread = threading.Thread(target=self._run, name="gestura-engine", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop processing and release the camera/tracker."""
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3.0)
            self._thread = None
        self._camera.stop()
        if self._tracker is not None:
            self._tracker.close()
            self._tracker = None

    # -- controls ------------------------------------------------------------------------------
    @property
    def paused(self) -> bool:
        return self._dispatcher.paused

    def toggle_pause(self) -> None:
        self._dispatcher.toggle_pause()

    def set_paused(self, value: bool) -> None:
        self._dispatcher.set_paused(value)

    @property
    def telemetry(self) -> PipelineTelemetry:
        return self._last_telemetry

    @property
    def init_error(self) -> str | None:
        """Non-``None`` if the tracker failed to initialise (e.g. missing model)."""
        return self._init_error

    # -- custom gestures (the in-app trainer) --------------------------------------------------
    def custom_gestures(self) -> dict[str, int]:
        """Recorded custom gestures as ``{name: sample_count}``."""
        clf = self._custom
        return {name: clf.sample_count(name) for name in clf.names}

    @property
    def recording_status(self) -> RecordingStatus:
        return self._recording_status

    def start_recording(self, name: str, *, samples: int = 40, timeout: float = 20.0) -> None:
        """Begin capturing ``samples`` frames of the current hand pose as custom gesture ``name``.

        Frames are collected on the engine thread as they arrive; poll :attr:`recording_status`
        for progress. Recording an existing name replaces its samples. While recording, no new
        gesture actions fire (so posing can't trigger anything), but held ones still release.
        """
        if samples < 1:
            raise ValueError("samples must be >= 1")
        with self._engine_lock:
            self._recording = _Recording(name, samples, deadline=time.perf_counter() + timeout)
            self._recording_status = RecordingStatus(
                "recording", name, 0, samples, "Hold the pose steady in view…")

    def cancel_recording(self) -> None:
        with self._engine_lock:
            if self._recording is not None:
                name = self._recording.name
                self._recording = None
                self._recording_status = RecordingStatus("cancelled", name, message="Cancelled")

    def delete_custom_gesture(self, name: str) -> bool:
        """Forget a recorded gesture. Returns ``False`` if there was no gesture of that name."""
        with self._engine_lock:
            if name not in self._custom.names:
                return False
            clf = CustomGestureClassifier.from_dict(self._custom.to_dict())
            clf.remove(name)
            self._install_custom(clf)
        return True

    def _install_custom(self, clf: CustomGestureClassifier) -> None:
        """Persist ``clf`` and make it live. Caller must hold ``_engine_lock``."""
        clf.save(self._custom_path)
        self._custom = clf
        self._interpreter.set_custom(clf)

    def _feed_recording(self, frame: FrameResult, now: float) -> bool:
        """Advance an active recording with one tracked frame. Caller must hold ``_engine_lock``.

        Returns ``True`` if a recording consumed this frame (so the caller suppresses actions).
        """
        rec = self._recording
        if rec is None:
            return False
        hand = frame.primary
        if hand is not None and hand.score >= _RECORD_MIN_CONFIDENCE:
            rec.features.append(landmark_feature(hand))
        collected = len(rec.features)

        if collected >= rec.target:
            self._recording = None
            clf = CustomGestureClassifier.from_dict(self._custom.to_dict())
            clf.remove(rec.name)  # re-recording replaces, rather than blends, the old samples
            for feat in rec.features:
                clf.add_feature(rec.name, feat)
            try:
                self._install_custom(clf)
            except OSError as exc:
                _log.exception("Could not save custom gesture '%s'", rec.name)
                self._recording_status = RecordingStatus(
                    "failed", rec.name, collected, rec.target, f"Couldn't save: {exc}")
            else:
                _log.info("Recorded custom gesture '%s' (%d samples)", rec.name, collected)
                self._recording_status = RecordingStatus(
                    "done", rec.name, collected, rec.target, "Saved — now bind it to an action")
        elif now >= rec.deadline:
            self._recording = None
            self._recording_status = RecordingStatus(
                "failed", rec.name, collected, rec.target,
                "Couldn't see a steady hand — keep it in view and try again")
        else:
            self._recording_status = RecordingStatus(
                "recording", rec.name, collected, rec.target, "Hold the pose steady in view…")
        return True

    def apply_settings(self, settings: AppSettings) -> None:
        """Hot-reload profile settings (thresholds, cursor tuning, bindings)."""
        self._settings = settings
        self._profile = settings.profile()
        self._interpreter.apply_profile(self._profile)
        self._dispatcher.set_profile(self._profile)

    # -- worker --------------------------------------------------------------------------------
    def _run(self) -> None:
        try:
            if self._tracker_factory is not None:
                self._tracker = self._tracker_factory()
            else:
                t = self._profile.tracking
                self._tracker = HandTracker(
                    num_hands=t.max_hands,
                    min_detection_confidence=t.min_detection_confidence,
                    min_presence_confidence=t.min_presence_confidence,
                    min_tracking_confidence=t.min_tracking_confidence,
                    use_gpu=t.use_gpu,
                    mirrored=self._profile.camera.mirror,
                )
        except ModelNotFoundError as exc:
            self._init_error = str(exc)
            _log.error("%s", exc)
            return
        except Exception as exc:
            self._init_error = f"Tracker init failed: {exc}"
            _log.exception("Tracker initialisation failed")
            return

        last_index = -1
        while not self._stop.is_set():
            frame = self._camera.latest()
            if frame is None or frame.index == last_index:
                time.sleep(0.001)
                continue
            last_index = frame.index

            t0 = time.perf_counter()
            try:
                result = self._tracker.process(
                    frame.image,
                    timestamp_ms=int(frame.timestamp * 1000),
                    frame_index=frame.index,
                )
            except Exception:
                _log.exception("Tracker.process failed; skipping frame")
                continue
            inference_ms = (time.perf_counter() - t0) * 1000.0

            with self._engine_lock:
                recording = self._feed_recording(result, time.perf_counter())
                interpretation = self._interpreter.update(result)
            try:
                self._dispatcher.dispatch(
                    _releases_only(interpretation) if recording else interpretation)
            except Exception:
                _log.exception("Dispatch failed")

            fps = self._fps.tick()
            telemetry = PipelineTelemetry(
                fps=fps,
                inference_ms=inference_ms,
                hand_present=result.has_hand,
                pose=interpretation.pose,
                mode=self._interpreter.mode.name,
                paused=self._dispatcher.paused,
                camera_status=self._camera_status.value,
            )
            self._last_telemetry = telemetry
            if self._on_update is not None:
                try:
                    self._on_update(frame.image, result, interpretation, telemetry)
                except Exception:
                    _log.exception("on_update callback raised")

    def _on_camera_status(self, status: CameraStatus) -> None:
        self._camera_status = status
        if self._external_status_cb is not None:
            self._external_status_cb(status)


def _releases_only(interp: InterpretationResult) -> InterpretationResult:
    """A copy of ``interp`` that can only *release* things: no cursor motion, ``ENDED`` events only.

    Used while recording a custom gesture, so the pose being taught never triggers an action,
    yet a drag that was already in progress still drops its mouse button cleanly.
    """
    return InterpretationResult(
        cursor=None,
        events=[e for e in interp.events if e.phase is GesturePhase.ENDED],
        pose=interp.pose,
        features=interp.features,
        tracking=interp.tracking,
    )


# --- Headless demo / smoke test ----------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gestura headless pipeline demo")
    parser.add_argument("--demo", action="store_true", help="Run the console demo")
    parser.add_argument("--live", action="store_true",
                        help="Actually control the mouse/system (default is a safe dry run)")
    parser.add_argument("--seconds", type=float, default=0.0,
                        help="Run for N seconds (0 = until Ctrl+C)")
    args = parser.parse_args(argv)

    from ..config.store import SettingsStore
    from ..platform import get_adapter
    from ..util.logging import configure

    configure(to_file=False)
    settings = SettingsStore().load()
    adapter = get_adapter(dry_run=not args.live)

    mode_word = "LIVE (controlling your computer)" if args.live else "DRY-RUN (no input injected)"
    print(f"Gestura demo — {mode_word}. Show your hand to the camera. Ctrl+C to stop.\n")

    def on_update(_img, _frame, interp, tele) -> None:
        for ev in interp.events:
            print(f"  [{tele.fps:4.0f} fps] gesture: {ev.name:<18} {ev.phase.value}")

    pipeline = GesturePipeline(settings, adapter, on_update=on_update)
    pipeline.start()

    start = time.perf_counter()
    last_beat = 0.0
    try:
        while True:
            if pipeline.init_error:
                print(f"\nERROR: {pipeline.init_error}")
                return 1
            now = time.perf_counter()
            if now - last_beat >= 1.0:
                last_beat = now
                t = pipeline.telemetry
                print(f"  status: {t.camera_status:<11} {t.fps:4.0f} fps | "
                      f"infer {t.inference_ms:4.1f} ms | hand={t.hand_present} | "
                      f"pose={t.pose:<10} mode={t.mode:<6} paused={t.paused}")
            if args.seconds and (now - start) >= args.seconds:
                break
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("\nStopping…")
    finally:
        pipeline.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
