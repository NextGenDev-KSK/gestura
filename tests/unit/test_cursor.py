"""Tests for the cursor mapping/smoothing controller."""

from __future__ import annotations

import pytest

from gestura.config.models import CursorConfig
from gestura.engine.cursor import CursorController


def test_disabled_returns_none() -> None:
    ctrl = CursorController(CursorConfig(enabled=False))
    assert ctrl.update((0.5, 0.5), timestamp=0.0) is None


def test_center_maps_to_center() -> None:
    ctrl = CursorController(CursorConfig(region_margin_x=0.14, region_margin_y=0.14))
    out = None
    for i in range(30):
        out = ctrl.update((0.5, 0.5), timestamp=i / 60)
    assert out == pytest.approx((0.5, 0.5), abs=1e-2)


def test_active_region_edges_reach_screen_edges() -> None:
    cfg = CursorConfig(region_margin_x=0.2, region_margin_y=0.2)
    ctrl = CursorController(cfg)
    out = None
    for i in range(60):
        out = ctrl.update((0.2, 0.2), timestamp=i / 60)  # top-left of active region
    assert out == pytest.approx((0.0, 0.0), abs=2e-2)

    ctrl.reset()
    for i in range(60):
        out = ctrl.update((0.8, 0.8), timestamp=i / 60)  # bottom-right of active region
    assert out == pytest.approx((1.0, 1.0), abs=2e-2)


def test_dead_zone_holds_position() -> None:
    cfg = CursorConfig(dead_zone=0.05)
    ctrl = CursorController(cfg)
    for i in range(40):
        ctrl.update((0.5, 0.5), timestamp=i / 60)
    settled = ctrl.last_position
    # A jiggle smaller than the dead zone must not move the output.
    out = ctrl.update((0.505, 0.503), timestamp=1.0)
    assert out == pytest.approx(settled, abs=1e-3)


def test_reset_clears_state() -> None:
    ctrl = CursorController(CursorConfig())
    ctrl.update((0.3, 0.7), timestamp=0.0)
    ctrl.reset()
    assert ctrl.last_position is None
