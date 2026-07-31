"""Tests for the smoothing filters (ADR-0006)."""

from __future__ import annotations

import math

import pytest

from gestura.core.filters import (
    ExponentialMovingAverage,
    OneEuroFilter,
    OneEuroFilter2D,
)


def test_one_euro_passes_first_sample_through() -> None:
    f = OneEuroFilter(min_cutoff=1.0, beta=0.0)
    assert f(3.14, timestamp=0.0) == pytest.approx(3.14)


def test_one_euro_converges_to_constant_signal() -> None:
    f = OneEuroFilter(min_cutoff=1.0, beta=0.01)
    t = 0.0
    out = 0.0
    for _ in range(200):
        t += 1 / 60
        out = f(10.0, timestamp=t)
    assert out == pytest.approx(10.0, abs=1e-3)


def test_one_euro_smooths_noise_below_input_variance() -> None:
    """Filtered output of a noisy but stationary signal has lower variance than the input."""
    f = OneEuroFilter(min_cutoff=0.5, beta=0.0)
    # Deterministic pseudo-noise around a constant mean.
    inputs = [5.0 + math.sin(i * 12.9898) * 0.5 for i in range(300)]
    t = 0.0
    outputs = []
    for x in inputs:
        t += 1 / 60
        outputs.append(f(x, timestamp=t))
    tail_in = inputs[100:]
    tail_out = outputs[100:]
    var_in = _variance(tail_in)
    var_out = _variance(tail_out)
    assert var_out < var_in


def test_one_euro_low_lag_when_fast_beta_helps() -> None:
    """With a higher beta, a fast ramp is tracked more closely (less lag)."""
    slow = OneEuroFilter(min_cutoff=1.0, beta=0.0)
    fast = OneEuroFilter(min_cutoff=1.0, beta=1.0)
    t = 0.0
    slow_out = fast_out = 0.0
    for i in range(60):
        t += 1 / 60
        x = float(i)  # steadily increasing ramp
        slow_out = slow(x, timestamp=t)
        fast_out = fast(x, timestamp=t)
    target = 59.0
    assert abs(fast_out - target) < abs(slow_out - target)


def test_one_euro_reset_clears_history() -> None:
    f = OneEuroFilter()
    for i in range(10):
        f(float(i), timestamp=i / 60)
    f.reset()
    assert f(99.0, timestamp=0.0) == pytest.approx(99.0)


def test_one_euro_handles_nonmonotonic_time_without_error() -> None:
    f = OneEuroFilter()
    f(1.0, timestamp=1.0)
    # Same/earlier timestamp must not divide by zero or raise.
    assert f(2.0, timestamp=1.0) == pytest.approx(2.0, abs=1.0)


def test_one_euro_rejects_bad_params() -> None:
    with pytest.raises(ValueError):
        OneEuroFilter(min_cutoff=0.0)
    with pytest.raises(ValueError):
        OneEuroFilter(beta=-1.0)


def test_one_euro_2d_filters_both_axes() -> None:
    f = OneEuroFilter2D(min_cutoff=1.0, beta=0.5)
    x, y = f(0.2, 0.8, timestamp=0.0)
    assert (x, y) == pytest.approx((0.2, 0.8))
    for i in range(1, 30):
        x, y = f(0.5, 0.5, timestamp=i / 60)
    assert x == pytest.approx(0.5, abs=1e-2)
    assert y == pytest.approx(0.5, abs=1e-2)


def test_ema_basic_and_validation() -> None:
    ema = ExponentialMovingAverage(alpha=0.5)
    assert ema(10.0) == pytest.approx(10.0)  # first sample seeds
    assert ema(20.0) == pytest.approx(15.0)  # 0.5*20 + 0.5*10
    with pytest.raises(ValueError):
        ExponentialMovingAverage(alpha=0.0)
    with pytest.raises(ValueError):
        ExponentialMovingAverage(alpha=1.5)


def _variance(xs: list[float]) -> float:
    n = len(xs)
    mean = sum(xs) / n
    return sum((x - mean) ** 2 for x in xs) / n
