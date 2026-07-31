"""``CameraView`` — a QML item that paints the live camera frame + hand-landmark overlay.

Implemented as a :class:`QQuickPaintedItem` so we can draw the glassmorphism-styled skeleton
(glowing joints and bones) directly over the video with full control, letterboxing the frame to
preserve aspect ratio. The controller pushes frames via :meth:`update_frame` on the GUI thread.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Slot
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtQml import QmlElement
from PySide6.QtQuick import QQuickPaintedItem

QML_IMPORT_NAME = "Gestura"
QML_IMPORT_MAJOR_VERSION = 1

# MediaPipe 21-point hand skeleton (pairs of landmark indices).
_HAND_CONNECTIONS: tuple[tuple[int, int], ...] = (
    (0, 1), (1, 2), (2, 3), (3, 4),          # thumb
    (0, 5), (5, 6), (6, 7), (7, 8),          # index
    (9, 10), (10, 11), (11, 12),             # middle
    (13, 14), (14, 15), (15, 16),            # ring
    (0, 17), (17, 18), (18, 19), (19, 20),   # pinky
    (5, 9), (9, 13), (13, 17),               # palm knuckle bridge
)


@QmlElement
class CameraView(QQuickPaintedItem):
    """Paints the most recent frame and hand skeleton. No state beyond the current frame."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._image = QImage()
        self._points: list[QPointF] = []
        self._accent = QColor(80, 220, 220)
        self.setOpaquePainting(False)

    @Slot(QImage, list)
    def update_frame(self, image: QImage, points: list) -> None:
        """Replace the displayed frame and landmark points (normalized 0..1), then repaint."""
        self._image = image
        self._points = points
        self.update()

    def paint(self, painter: QPainter) -> None:  # noqa: N802 (Qt override)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        w, h = self.width(), self.height()
        if self._image.isNull():
            painter.fillRect(QRectF(0, 0, w, h), QColor(18, 20, 28))
            painter.setPen(QColor(150, 160, 180))
            painter.drawText(QRectF(0, 0, w, h), Qt.AlignCenter, "Waiting for camera…")
            return

        # Letterbox the frame into the item, preserving aspect ratio.
        iw, ih = self._image.width(), self._image.height()
        scale = min(w / iw, h / ih)
        dw, dh = iw * scale, ih * scale
        ox, oy = (w - dw) / 2, (h - dh) / 2
        target = QRectF(ox, oy, dw, dh)
        painter.fillRect(QRectF(0, 0, w, h), QColor(12, 14, 20))
        painter.drawImage(target, self._image)

        if not self._points:
            return
        self._draw_skeleton(painter, ox, oy, dw, dh)

    def _draw_skeleton(self, painter: QPainter, ox: float, oy: float, dw: float, dh: float) -> None:
        pts = [QPointF(ox + p.x() * dw, oy + p.y() * dh) for p in self._points]
        if len(pts) < 21:
            return

        # Bones: a soft outer glow then a bright core line.
        glow = QColor(self._accent)
        glow.setAlpha(70)
        painter.setPen(QPen(glow, 7, Qt.SolidLine, Qt.RoundCap))
        for a, b in _HAND_CONNECTIONS:
            painter.drawLine(pts[a], pts[b])
        painter.setPen(QPen(self._accent, 2.2, Qt.SolidLine, Qt.RoundCap))
        for a, b in _HAND_CONNECTIONS:
            painter.drawLine(pts[a], pts[b])

        # Joints.
        painter.setPen(Qt.NoPen)
        for i, p in enumerate(pts):
            painter.setBrush(QColor(255, 255, 255) if i in (4, 8, 12, 16, 20) else self._accent)
            r = 4.0 if i in (4, 8, 12, 16, 20) else 3.0
            painter.drawEllipse(p, r, r)
