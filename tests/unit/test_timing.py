"""Tests for the timing / false-positive-prevention primitives."""

from __future__ import annotations

import pytest

from gestura.core.timing import Cooldown, RateEstimator, SchmittTrigger, StabilityGate


def test_cooldown_blocks_within_interval() -> None:
    cd = Cooldown(interval=0.5)
    assert cd.try_fire(now=0.0) is True
    assert cd.try_fire(now=0.2) is False  # too soon
    assert cd.try_fire(now=0.5) is True  # exactly at interval
    assert cd.ready(now=0.6) is False
    assert cd.ready(now=1.0) is True


def test_cooldown_reset() -> None:
    cd = Cooldown(interval=1.0)
    assert cd.try_fire(now=0.0)
    cd.reset()
    assert cd.try_fire(now=0.1)  # allowed again after reset


def test_cooldown_rejects_negative() -> None:
    with pytest.raises(ValueError):
        Cooldown(interval=-1.0)


def test_schmitt_trigger_hysteresis() -> None:
    st = SchmittTrigger(low=0.35, high=0.5)
    assert st.update(0.4) is False  # in the dead-band, starts off
    assert st.update(0.6) is True  # crosses high -> on
    assert st.update(0.4) is True  # in dead-band -> holds on
    assert st.update(0.3) is False  # crosses low -> off
    assert st.update(0.45) is False  # dead-band -> holds off


def test_schmitt_requires_low_below_high() -> None:
    with pytest.raises(ValueError):
        SchmittTrigger(low=0.6, high=0.5)


def test_stability_gate_requires_sustained_condition() -> None:
    gate = StabilityGate(duration=0.12)
    assert gate.update(True, now=0.00) is False  # just started
    assert gate.update(True, now=0.10) is False  # not long enough
    assert gate.update(True, now=0.13) is True  # sustained past duration
    # Dropping the condition releases immediately.
    assert gate.update(False, now=0.14) is False
    # Must re-accumulate from scratch.
    assert gate.update(True, now=0.15) is False


def test_rate_estimator_reports_expected_fps() -> None:
    est = RateEstimator(window=1.0)
    rate = 0.0
    # Feed ticks 16 ms apart (~62.5 fps) for two seconds of history.
    for i in range(1, 130):
        rate = est.tick(now=i * 0.016)
    assert rate == pytest.approx(62.5, rel=0.05)


def test_rate_estimator_starts_at_zero() -> None:
    est = RateEstimator()
    assert est.tick(now=0.0) == 0.0
