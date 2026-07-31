"""``AppController`` — the QObject bridge between the engine and QML.

The gesture pipeline runs on a worker thread and calls :meth:`_on_update` from there. Qt objects
must be touched on the GUI thread, so the callback only stashes the latest frame/telemetry under a
lock; a GUI-thread :class:`QTimer` (~30 Hz) then publishes it to QML via properties and the
``frameReady`` signal. This cleanly decouples engine rate from UI rate and keeps all Qt access on
the right thread.
"""

from __future__ import annotations

import threading

import numpy as np
from PySide6.QtCore import Property, QObject, QPointF, QTimer, Signal, Slot
from PySide6.QtGui import QImage

from ..config.models import AppSettings, Theme
from ..config.store import SettingsStore
from ..engine.interpreter import InterpretationResult
from ..engine.pipeline import GesturePipeline, PipelineTelemetry
from ..platform import get_adapter
from ..util.logging import get_logger

_log = get_logger("gestura.app.controller")


class AppController(QObject):
    """Exposes live engine state and controls to QML."""

    # Notify signals (property change).
    telemetryChanged = Signal()
    pausedChanged = Signal()
    cameraStatusChanged = Signal()
    themeChanged = Signal()
    initErrorChanged = Signal()
    # Per-frame preview payload: (QImage frame, list[QPointF] normalized landmarks).
    frameReady = Signal(QImage, list)
    # A recognised gesture fired (name), for transient UI feedback.
    gestureFired = Signal(str)

    def __init__(self, settings: AppSettings, store: SettingsStore | None = None,
                 *, dry_run: bool = False, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._store = store
        self._adapter = get_adapter(dry_run=dry_run)

        self._pipeline = GesturePipeline(
            settings, self._adapter,
            on_update=self._on_update,
            on_camera_status=self._on_camera_status,
        )

        self._lock = threading.Lock()
        self._pending: tuple[QImage, list, PipelineTelemetry, InterpretationResult] | None = None
        self._pending_gestures: list[str] = []
        self._camera_status_pending: str | None = None

        # Published state.
        self._fps = 0.0
        self._inference_ms = 0.0
        self._pose = "none"
        self._mode = "IDLE"
        self._confidence = 0.0
        self._hand_present = False
        self._paused = settings.paused
        self._camera_status = "idle"

        self._timer = QTimer(self)
        self._timer.setInterval(33)  # ~30 Hz UI refresh
        self._timer.timeout.connect(self._tick)

    # -- lifecycle -----------------------------------------------------------------------------
    def start(self) -> None:
        self._pipeline.start()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self._pipeline.stop()

    # -- worker-thread callbacks (do minimal work, no Qt object mutation) ----------------------
    def _on_update(self, image_bgr: np.ndarray, result, interp: InterpretationResult,
                   tele: PipelineTelemetry) -> None:
        qimg = self._to_qimage(image_bgr)
        points = self._landmark_points(result)
        with self._lock:
            self._pending = (qimg, points, tele, interp)
            self._pending_gestures.extend(
                e.name for e in interp.events if e.phase.value == "began"
            )

    def _on_camera_status(self, status) -> None:
        # Called from the camera thread; just stash the string, publish on the UI tick.
        with self._lock:
            self._camera_status_pending = status.value

    # -- GUI-thread publish ---------------------------------------------------------------------
    def _tick(self) -> None:
        with self._lock:
            pending = self._pending
            self._pending = None
            gestures = self._pending_gestures
            self._pending_gestures = []
            status = getattr(self, "_camera_status_pending", None)
            self._camera_status_pending = None

        if status is not None and status != self._camera_status:
            self._camera_status = status
            self.cameraStatusChanged.emit()

        if self._pipeline.init_error:
            self.initErrorChanged.emit()

        for name in gestures:
            self.gestureFired.emit(name)

        if pending is None:
            return
        qimg, points, tele, interp = pending
        self._fps = tele.fps
        self._inference_ms = tele.inference_ms
        self._pose = tele.pose
        self._mode = tele.mode
        self._hand_present = tele.hand_present
        self._confidence = interp.features.score if interp.features else 0.0
        if tele.paused != self._paused:
            self._paused = tele.paused
            self.pausedChanged.emit()
        self.telemetryChanged.emit()
        self.frameReady.emit(qimg, points)

    # -- helpers -------------------------------------------------------------------------------
    @staticmethod
    def _to_qimage(image_bgr: np.ndarray) -> QImage:
        rgb = np.ascontiguousarray(image_bgr[:, :, ::-1])
        h, w = rgb.shape[:2]
        # Copy so the QImage owns its buffer (the numpy frame is reused next iteration).
        return QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()

    @staticmethod
    def _landmark_points(result) -> list[QPointF]:
        """All 21 normalized landmark points of the primary hand (empty if none tracked)."""
        hand = result.primary
        if hand is None:
            return []
        return [QPointF(float(p[0]), float(p[1])) for p in hand.landmarks]

    # -- QML properties ------------------------------------------------------------------------
    @Property(float, notify=telemetryChanged)
    def fps(self) -> float:
        return self._fps

    @Property(float, notify=telemetryChanged)
    def inferenceMs(self) -> float:
        return self._inference_ms

    @Property(str, notify=telemetryChanged)
    def pose(self) -> str:
        return self._pose

    @Property(str, notify=telemetryChanged)
    def mode(self) -> str:
        return self._mode

    @Property(float, notify=telemetryChanged)
    def confidence(self) -> float:
        return self._confidence

    @Property(bool, notify=telemetryChanged)
    def handPresent(self) -> bool:
        return self._hand_present

    @Property(bool, notify=pausedChanged)
    def paused(self) -> bool:
        return self._paused

    @Property(str, notify=cameraStatusChanged)
    def cameraStatus(self) -> str:
        return self._camera_status

    @Property(str, notify=initErrorChanged)
    def initError(self) -> str:
        return self._pipeline.init_error or ""

    @Property(str, notify=themeChanged)
    def theme(self) -> str:
        return self._settings.ui.theme.value

    # -- QML-invokable slots -------------------------------------------------------------------
    @Slot()
    def togglePause(self) -> None:
        self._pipeline.toggle_pause()

    @Slot(str)
    def setTheme(self, theme: str) -> None:
        try:
            self._settings.ui.theme = Theme(theme)
        except ValueError:
            return
        if self._store is not None:
            self._store.save(self._settings)
        self.themeChanged.emit()
