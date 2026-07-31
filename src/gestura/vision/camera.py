"""Resilient webcam capture.

Two reliability problems this module solves, both called out in the product requirements
("automatic camera recovery", "no UI freezes"):

1. **Latency / staleness.** OpenCV's ``VideoCapture`` buffers frames internally, so a slow
   consumer ends up processing frames that are hundreds of milliseconds old. We run capture on a
   dedicated thread that continuously grabs and keeps only the *latest* frame; the pipeline always
   reads fresh data and never blocks the UI thread.

2. **Device loss.** Webcams disconnect, get grabbed by other apps, or hiccup. The capture thread
   detects read failures and transparently reconnects with exponential backoff, surfacing status
   changes through a callback so the UI can show an honest "reconnecting…" state.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

import cv2
import numpy as np

from ..util.logging import get_logger

_log = get_logger("gestura.vision.camera")


class CameraStatus(Enum):
    """Lifecycle state of the capture device, surfaced to the UI."""

    IDLE = "idle"
    CONNECTING = "connecting"
    STREAMING = "streaming"
    RECOVERING = "recovering"
    FAILED = "failed"


@dataclass(frozen=True)
class CameraFrame:
    """One captured frame plus metadata."""

    image: np.ndarray  # BGR uint8, shape (H, W, 3)
    index: int
    timestamp: float  # perf_counter seconds at capture


StatusCallback = Callable[[CameraStatus], None]


class CameraSource:
    """Threaded, self-healing camera reader.

    Usage::

        cam = CameraSource(device_index=0, width=1280, height=720, fps=60)
        cam.start()
        frame = cam.latest()          # newest CameraFrame or None
        ...
        cam.stop()

    or as a context manager (``with CameraSource(...) as cam:``).
    """

    #: Consecutive failed reads before we treat the device as lost and reconnect.
    _MAX_READ_FAILURES = 15
    #: Backoff schedule (seconds) for reconnection attempts; last value repeats.
    _BACKOFF = (0.2, 0.5, 1.0, 2.0, 3.0)

    def __init__(
        self,
        device_index: int = 0,
        *,
        width: int = 1280,
        height: int = 720,
        fps: int = 60,
        mirror: bool = True,
        on_status: StatusCallback | None = None,
    ) -> None:
        self.device_index = device_index
        self.width = width
        self.height = height
        self.fps = fps
        self.mirror = mirror
        self._on_status = on_status

        self._cap: cv2.VideoCapture | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._latest: CameraFrame | None = None
        self._frame_counter = 0
        self._status = CameraStatus.IDLE

    # -- public API ----------------------------------------------------------------------------
    @property
    def status(self) -> CameraStatus:
        return self._status

    @property
    def is_streaming(self) -> bool:
        return self._status is CameraStatus.STREAMING

    def start(self) -> None:
        """Begin capturing on a background thread (idempotent)."""
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="gestura-camera", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop capturing and release the device."""
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._release()
        self._set_status(CameraStatus.IDLE)

    def latest(self) -> CameraFrame | None:
        """Return the most recent frame without blocking, or ``None`` if none yet."""
        with self._lock:
            return self._latest

    def __enter__(self) -> CameraSource:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()

    # -- capture thread ------------------------------------------------------------------------
    def _run(self) -> None:
        backoff_i = 0
        failures = 0
        while not self._stop.is_set():
            if self._cap is None or not self._cap.isOpened():
                self._set_status(
                    CameraStatus.CONNECTING if backoff_i == 0 else CameraStatus.RECOVERING
                )
                if not self._open():
                    delay = self._BACKOFF[min(backoff_i, len(self._BACKOFF) - 1)]
                    backoff_i += 1
                    if backoff_i > 20:  # ~1 min of failures -> declare failure but keep trying
                        self._set_status(CameraStatus.FAILED)
                    self._stop.wait(delay)
                    continue
                backoff_i = 0
                failures = 0

            ok, image = self._cap.read()
            if not ok or image is None:
                failures += 1
                if failures >= self._MAX_READ_FAILURES:
                    _log.warning("Camera %s read failed %dx; reconnecting",
                                 self.device_index, failures)
                    self._release()
                    failures = 0
                    backoff_i = 1
                continue

            failures = 0
            if self.mirror:
                image = cv2.flip(image, 1)
            with self._lock:
                self._frame_counter += 1
                self._latest = CameraFrame(
                    image=image, index=self._frame_counter, timestamp=time.perf_counter()
                )
            self._set_status(CameraStatus.STREAMING)

        self._release()

    # -- device helpers ------------------------------------------------------------------------
    def _open(self) -> bool:
        # CAP_DSHOW gives much faster startup and better property support on Windows.
        backend = cv2.CAP_DSHOW if hasattr(cv2, "CAP_DSHOW") else cv2.CAP_ANY
        cap = cv2.VideoCapture(self.device_index, backend)
        if not cap.isOpened():
            cap.release()
            return False
        # Request MJPG *before* resolution: most webcams only deliver HD at full frame-rate in
        # compressed MJPG; the uncompressed default (YUY2) throttles 720p to a few FPS.
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_FPS, self.fps)
        # Minimise internal buffering so we always process the freshest frame.
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self._cap = cap
        actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        actual_fps = cap.get(cv2.CAP_PROP_FPS)
        _log.info(
            "Opened camera %s at %dx%d @%.0ffps (requested %dx%d @%dfps)",
            self.device_index, actual_w, actual_h, actual_fps, self.width, self.height, self.fps,
        )
        return True

    def _release(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def _set_status(self, status: CameraStatus) -> None:
        if status is self._status:
            return
        self._status = status
        _log.debug("Camera status -> %s", status.value)
        if self._on_status is not None:
            try:
                self._on_status(status)
            except Exception:
                _log.exception("Camera status callback raised")


def list_cameras(max_probe: int = 5) -> list[int]:
    """Return indices of cameras that can currently be opened (best-effort probe)."""
    found: list[int] = []
    backend = cv2.CAP_DSHOW if hasattr(cv2, "CAP_DSHOW") else cv2.CAP_ANY
    for idx in range(max_probe):
        cap = cv2.VideoCapture(idx, backend)
        if cap.isOpened():
            found.append(idx)
        cap.release()
    return found
