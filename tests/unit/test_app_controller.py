"""Tests for the QML bridge's pure helpers (no event loop / display needed)."""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("PySide6")

from gestura.app.controller import AppController


def test_to_qimage_preserves_size_and_converts_bgr_to_rgb() -> None:
    bgr = np.zeros((48, 64, 3), dtype=np.uint8)
    bgr[:, :, 2] = 200  # red channel in BGR
    img = AppController._to_qimage(bgr)
    assert (img.width(), img.height()) == (64, 48)
    px = img.pixelColor(10, 10)
    assert px.red() == 200 and px.green() == 0 and px.blue() == 0


def test_landmark_points_returns_21_for_a_hand(hand_factory, frame_factory) -> None:
    frame = frame_factory(hand_factory("open"), timestamp=0.0)
    pts = AppController._landmark_points(frame)
    assert len(pts) == 21
    # Points are normalized [0, 1].
    assert all(0.0 <= p.x() <= 1.0 and 0.0 <= p.y() <= 1.0 for p in pts)


def test_landmark_points_empty_without_hand(frame_factory) -> None:
    assert AppController._landmark_points(frame_factory(None, timestamp=0.0)) == []
