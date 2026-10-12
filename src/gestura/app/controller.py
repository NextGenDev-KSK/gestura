"""``AppController`` — the QObject bridge between the engine and QML.

The gesture pipeline runs on a worker thread and calls :meth:`_on_update` from there. Qt objects
must be touched on the GUI thread, so the callback only stashes the latest frame/telemetry under a
lock; a GUI-thread :class:`QTimer` (~30 Hz) then publishes it to QML via properties and the
``frameReady`` signal. This cleanly decouples engine rate from UI rate and keeps all Qt access on
the right thread.
"""

from __future__ import annotations

import re
import threading
from enum import Enum
from typing import Any

import numpy as np
from pydantic import ValidationError
from PySide6.QtCore import Property, QObject, QPointF, QTimer, Signal, Slot
from PySide6.QtGui import QImage

from .. import __author__, __version__
from ..actions.registry import actions_for, get_action
from ..config.models import AppSettings, GestureBinding, Theme, default_bindings
from ..config.store import SettingsStore
from ..core.types import GestureKind
from ..engine.catalog import BUILTIN_GESTURES, builtin_gesture, gesture_kind
from ..engine.interpreter import InterpretationResult
from ..engine.pipeline import GesturePipeline, PipelineTelemetry, RecordingStatus
from ..platform import get_adapter, parse_shortcut
from ..util.logging import get_logger

_log = get_logger("gestura.app.controller")

_CUSTOM_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
_RECORD_SAMPLES = 40


def normalize_gesture_name(text: str) -> str:
    """Turn a user-typed name ("Peace Sign") into a gesture id ("peace_sign").

    Raises:
        ValueError: with a user-presentable message if the name is unusable.
    """
    name = re.sub(r"\s+", "_", text.strip().lower())
    if not name:
        raise ValueError("Give the gesture a name first")
    if not _CUSTOM_NAME.match(name):
        raise ValueError("Use up to 32 letters, digits, spaces, '-' or '_'")
    if builtin_gesture(name) is not None:
        raise ValueError(f"'{name}' is a built-in gesture — pick another name")
    return name


class AppController(QObject):
    """Exposes live engine state and controls to QML."""

    # Notify signals (property change).
    telemetryChanged = Signal()
    pausedChanged = Signal()
    cameraStatusChanged = Signal()
    themeChanged = Signal()
    initErrorChanged = Signal()
    settingsChanged = Signal()
    # Per-frame preview payload: (QImage frame, list[QPointF] normalized landmarks).
    frameReady = Signal(QImage, list)
    # A recognised gesture fired (name), for transient UI feedback.
    gestureFired = Signal(str)
    # The gesture -> action map or the custom-gesture library changed.
    gesturesChanged = Signal()
    # In-app recording progressed / finished.
    recordingChanged = Signal()

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
        self._recording = RecordingStatus()

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

        recording = self._pipeline.recording_status
        if recording != self._recording:
            finished = recording.state == "done" and self._recording.state != "done"
            self._recording = recording
            self.recordingChanged.emit()
            if finished:
                self.gesturesChanged.emit()  # the new gesture now appears in the editor

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
        """Normalized landmark points of every tracked hand, 21 per hand (empty if none)."""
        return [QPointF(float(p[0]), float(p[1])) for hand in result.hands for p in hand.landmarks]

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

    @Property(bool, notify=settingsChanged)
    def showOverlay(self) -> bool:
        return self._settings.ui.show_overlay

    @Property(str, notify=settingsChanged)
    def activeProfile(self) -> str:
        return self._settings.active_profile

    @Property(str, constant=True)
    def appVersion(self) -> str:
        return __version__

    @Property(str, constant=True)
    def appAuthor(self) -> str:
        return __author__

    @Property(list, notify=gesturesChanged)
    def gestureRows(self) -> list[dict[str, Any]]:
        """One row per gesture (built-in, then custom) with its binding and bindable actions."""
        return self._gesture_rows()

    @Property(str, notify=recordingChanged)
    def recordingState(self) -> str:
        return self._recording.state

    @Property(str, notify=recordingChanged)
    def recordingName(self) -> str:
        return self._recording.name

    @Property(float, notify=recordingChanged)
    def recordingProgress(self) -> float:
        r = self._recording
        return r.collected / r.target if r.target else 0.0

    @Property(str, notify=recordingChanged)
    def recordingMessage(self) -> str:
        return self._recording.message

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
        self._persist()
        self.themeChanged.emit()

    # -- gesture editor ------------------------------------------------------------------------
    @Slot(str, str, result=bool)
    def setGestureAction(self, gesture: str, action: str) -> bool:
        """Bind ``gesture`` to ``action``; an empty ``action`` unbinds it.

        Rejects actions the gesture can't drive (see :class:`GestureKind`), so the editor can never
        create a binding that silently does nothing.
        """
        if not action:
            self._replace_binding(gesture, None)
            return True
        spec = get_action(action)
        if spec is None or not spec.accepts_kind(gesture_kind(gesture)):
            _log.warning("Rejected binding %s -> %s (incompatible)", gesture, action)
            return False
        current = self._binding_for(gesture)
        same_action = current is not None and current.action == action
        binding = GestureBinding(
            gesture=gesture,
            action=action,
            enabled=current.enabled if current is not None else True,
            # Params/cooldown are action-specific ("amount" is a % for volume but steps for
            # scroll), so they reset when the action changes. The shortcut is kept so switching
            # away from "Keyboard shortcut" and back doesn't lose what the user typed.
            params=dict(current.params) if same_action and current is not None else {},
            cooldown=current.cooldown if same_action and current is not None else None,
            shortcut=list(current.shortcut) if current is not None else [],
        )
        self._replace_binding(gesture, binding)
        return True

    @Slot(str, bool)
    def setGestureEnabled(self, gesture: str, enabled: bool) -> None:
        binding = self._binding_for(gesture)
        if binding is None or binding.enabled == enabled:
            return
        binding.enabled = enabled
        self._bindings_changed()

    @Slot(str, str, result=str)
    def setGestureShortcut(self, gesture: str, text: str) -> str:
        """Set the key chord of a "Keyboard shortcut" binding. Returns an error or ``""``."""
        binding = self._binding_for(gesture)
        if binding is None:
            return "Bind the gesture to Keyboard shortcut first"
        try:
            keys = parse_shortcut(text)
        except ValueError as exc:
            return str(exc)
        binding.shortcut = keys
        self._bindings_changed()
        return ""

    @Slot()
    def resetGestures(self) -> None:
        """Restore the built-in gesture map (custom-gesture recordings are kept, but unbound)."""
        self._settings.profile().bindings = default_bindings()
        self._bindings_changed()

    # -- gesture trainer -----------------------------------------------------------------------
    @Slot(str, result=str)
    def checkRecording(self, name: str) -> str:
        """Why recording ``name`` can't start now, or ``""`` if it can (checked pre-countdown)."""
        return self._prepare_recording(name)[1]

    @Slot(str, result=str)
    def startRecording(self, name: str) -> str:
        """Start recording a custom gesture. Returns an error message, or ``""`` on success."""
        gesture, error = self._prepare_recording(name)
        if gesture is None:
            return error
        self._pipeline.start_recording(gesture, samples=_RECORD_SAMPLES)
        return ""

    def _prepare_recording(self, name: str) -> tuple[str | None, str]:
        try:
            gesture = normalize_gesture_name(name)
        except ValueError as exc:
            return None, str(exc)
        if self._pipeline.init_error:
            return None, "Hand tracking isn't running"
        if self._camera_status != "streaming":
            return None, "The camera isn't streaming yet"
        return gesture, ""

    @Slot()
    def cancelRecording(self) -> None:
        self._pipeline.cancel_recording()

    @Slot(str)
    def deleteCustomGesture(self, name: str) -> None:
        """Delete a recorded gesture and any binding that pointed at it."""
        self._pipeline.delete_custom_gesture(name)
        profile = self._settings.profile()
        if any(b.gesture == name for b in profile.bindings):
            profile.bindings = [b for b in profile.bindings if b.gesture != name]
            self._persist()
            self._pipeline.apply_settings(self._settings)
        self.gesturesChanged.emit()

    # -- gesture helpers -----------------------------------------------------------------------
    def _binding_for(self, gesture: str) -> GestureBinding | None:
        return next((b for b in self._settings.profile().bindings if b.gesture == gesture), None)

    def _replace_binding(self, gesture: str, binding: GestureBinding | None) -> None:
        """Make ``binding`` the only binding for ``gesture`` (or remove it), keeping list order."""
        profile = self._settings.profile()
        old = profile.bindings
        index = next((i for i, b in enumerate(old) if b.gesture == gesture), len(old))
        kept = [b for b in old if b.gesture != gesture]
        if binding is not None:
            kept.insert(min(index, len(kept)), binding)
        profile.bindings = kept
        self._bindings_changed()

    def _bindings_changed(self) -> None:
        self._persist()
        self._pipeline.apply_settings(self._settings)
        self.gesturesChanged.emit()

    def _gesture_rows(self) -> list[dict[str, Any]]:
        bound: dict[str, GestureBinding] = {}
        for b in self._settings.profile().bindings:
            bound.setdefault(b.gesture, b)
        custom = self._pipeline.custom_gestures()

        entries: list[tuple[str, str, str, str, GestureKind, bool]] = [
            (g.id, g.label, g.icon, g.hint, g.kind, False) for g in BUILTIN_GESTURES
        ]
        entries += [
            (name, name.replace("_", " ").capitalize(), "✋", f"Your gesture · {count} samples",
             GestureKind.TAP, True)
            for name, count in custom.items()
        ]
        # Bindings whose gesture isn't recorded on this PC (e.g. settings copied from another
        # machine) still show up, so they can be seen and unbound.
        known = {e[0] for e in entries}
        entries += [
            (gid, gid.replace("_", " ").capitalize(), "✋", "Not recorded on this PC",
             GestureKind.TAP, True)
            for gid in bound if gid not in known
        ]

        rows: list[dict[str, Any]] = []
        for gid, label, icon, hint, kind, is_custom in entries:
            binding = bound.get(gid)
            choices = [{"id": "", "label": "Not bound"}] + [
                {"id": spec.id, "label": spec.label} for spec in actions_for(kind)
            ]
            action = binding.action if binding is not None else ""
            spec = get_action(action) if action else None
            rows.append({
                "id": gid,
                "label": label,
                "icon": icon,
                "hint": hint,
                "custom": is_custom,
                "recorded": gid in custom,
                "action": action,
                "actionLabel": spec.label if spec is not None else action,
                "enabled": binding.enabled if binding is not None else False,
                "shortcut": "+".join(binding.shortcut) if binding is not None else "",
                "choices": choices,
                "choiceIndex": next((i for i, c in enumerate(choices) if c["id"] == action), 0),
            })
        return rows

    # -- generic settings access for the settings panel ----------------------------------------
    @Slot(str, result="QVariant")
    def getSetting(self, path: str) -> object:
        """Read a dotted settings path, e.g. ``profile.cursor.smoothing_beta``."""
        try:
            parent, attr = self._resolve(path)
            value = getattr(parent, attr)
        except (AttributeError, KeyError):
            return None
        return value.value if isinstance(value, Enum) else value

    @Slot(str, float)
    def setNumber(self, path: str, value: float) -> None:
        self._set(path, value)

    @Slot(str, bool)
    def setBool(self, path: str, value: bool) -> None:
        self._set(path, value)

    def _set(self, path: str, value: object) -> None:
        try:
            parent, attr = self._resolve(path)
            setattr(parent, attr, value)  # validate_assignment enforces ranges/types
        except (AttributeError, KeyError, ValidationError):
            _log.warning("Rejected settings write %s = %r", path, value)
            return
        self._persist()
        self._pipeline.apply_settings(self._settings)
        self.settingsChanged.emit()

    def _resolve(self, path: str) -> tuple[object, str]:
        """Return ``(parent_object, attribute_name)`` for a dotted path.

        The ``profile.`` prefix targets the active profile; other roots (``ui``, ``paused``) are
        looked up on the settings tree directly.
        """
        parts = path.split(".")
        obj: object
        if parts[0] == "profile":
            obj = self._settings.profile()
            parts = parts[1:]
        else:
            obj = self._settings
        for name in parts[:-1]:
            obj = getattr(obj, name)
        return obj, parts[-1]

    def _persist(self) -> None:
        if self._store is not None:
            self._store.save(self._settings)
