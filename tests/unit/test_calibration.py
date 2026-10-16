"""Tests for reach calibration and the calibrated cursor region."""

from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError

from gestura.config.models import MIN_REGION_SPAN, CursorConfig
from gestura.engine.calibration import MIN_SAMPLES, CalibrationError, region_from_anchors
from gestura.engine.cursor import CursorController, active_region


def _sweep(x0, x1, y0, y1, n=200, seed=1):
    rng = np.random.default_rng(seed)
    return rng.uniform(x0, x1, n).tolist(), rng.uniform(y0, y1, n).tolist()


def test_region_covers_the_sweep_with_a_little_padding() -> None:
    xs, ys = _sweep(0.40, 0.80, 0.30, 0.70)
    x0, y0, x1, y1 = region_from_anchors(xs, ys)
    # Inside the trimmed spread plus padding: close to the sweep, never far outside it.
    assert 0.36 < x0 < 0.44 and 0.76 < x1 < 0.84
    assert 0.26 < y0 < 0.34 and 0.66 < y1 < 0.74


def test_outliers_cannot_stretch_the_region() -> None:
    xs, ys = _sweep(0.40, 0.60, 0.40, 0.60)
    xs += [0.0, 1.0]          # two tracking glitches at the frame edges
    ys += [0.0, 1.0]
    x0, y0, x1, y1 = region_from_anchors(xs, ys)
    assert x0 > 0.3 and x1 < 0.7 and y0 > 0.3 and y1 < 0.7


def test_small_sweep_is_grown_to_the_minimum_size() -> None:
    xs, ys = _sweep(0.48, 0.58, 0.45, 0.55)   # spread ~0.1 (allowed, but below the minimum)
    x0, y0, x1, y1 = region_from_anchors(xs, ys)
    assert x1 - x0 >= MIN_REGION_SPAN - 1e-9 and y1 - y0 >= MIN_REGION_SPAN - 1e-9
    assert x0 < 0.53 < x1  # still centred on the sweep


def test_region_is_kept_inside_the_frame() -> None:
    xs, ys = _sweep(0.85, 1.0, 0.0, 0.12)     # hand hugging the top-right corner
    x0, y0, x1, y1 = region_from_anchors(xs, ys)
    assert 0.0 <= x0 < x1 <= 1.0 and 0.0 <= y0 < y1 <= 1.0
    assert x1 - x0 >= MIN_REGION_SPAN - 1e-9 and y1 - y0 >= MIN_REGION_SPAN - 1e-9


def test_too_few_samples_or_no_movement_is_rejected() -> None:
    xs, ys = _sweep(0.3, 0.7, 0.3, 0.7, n=MIN_SAMPLES - 1)
    with pytest.raises(CalibrationError):
        region_from_anchors(xs, ys)
    with pytest.raises(CalibrationError, match="barely moved"):
        region_from_anchors([0.5] * 100, [0.5] * 100)


def test_config_validates_the_region() -> None:
    CursorConfig(region=[0.2, 0.2, 0.8, 0.8])
    for bad in ([0.2, 0.2, 0.8], [0.5, 0.5, 0.55, 0.9], [-0.1, 0.2, 0.8, 0.8]):
        with pytest.raises(ValidationError):
            CursorConfig(region=bad)


def test_cursor_maps_the_calibrated_region_to_the_full_screen() -> None:
    cfg = CursorConfig(region=[0.4, 0.3, 0.8, 0.7], smoothing_min_cutoff=1000, dead_zone=0)
    assert active_region(cfg) == (0.4, 0.3, 0.8, 0.7)
    cur = CursorController(cfg)
    assert cur.update((0.4, 0.3), 0.0) == pytest.approx((0.0, 0.0), abs=1e-3)
    cur.reset()
    assert cur.update((0.8, 0.7), 0.0) == pytest.approx((1.0, 1.0), abs=1e-3)
    # Without calibration the symmetric margins still apply.
    plain = CursorConfig(region_margin_x=0.1, region_margin_y=0.2)
    assert active_region(plain) == pytest.approx((0.1, 0.2, 0.9, 0.8))
