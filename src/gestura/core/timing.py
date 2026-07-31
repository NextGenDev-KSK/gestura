"""Timing utilities for false-positive prevention and performance measurement.

Gesture reliability depends far more on *temporal* logic than on any single-frame classifier:
a raw per-frame decision will flicker and misfire. These primitives — cooldowns, hysteresis, and
stability debouncing — are what turn a jittery classification stream into trustworthy triggers.
"""

from __future__ import annotations

import time
from collections import deque


class Cooldown:
    """Rate-limits an action so it cannot fire again within ``interval`` seconds.

    Prevents machine-gun repeats (e.g. a single pinch producing dozens of clicks).
    """

    __slots__ = ("_last_fired", "interval")

    def __init__(self, interval: float) -> None:
        if interval < 0:
            raise ValueError("interval must be non-negative")
        self.interval = interval
        self._last_fired: float | None = None

    def ready(self, now: float | None = None) -> bool:
        """Return whether enough time has elapsed since the last fire."""
        t = time.perf_counter() if now is None else now
        return self._last_fired is None or (t - self._last_fired) >= self.interval

    def try_fire(self, now: float | None = None) -> bool:
        """Atomically check-and-fire: returns ``True`` and starts the cooldown, else ``False``."""
        t = time.perf_counter() if now is None else now
        if self.ready(t):
            self._last_fired = t
            return True
        return False

    def reset(self) -> None:
        self._last_fired = None


class SchmittTrigger:
    """Boolean signal with hysteresis to eliminate chatter near a threshold.

    The output turns **on** only when the input rises above ``high`` and turns **off** only when
    it falls below ``low`` (``low < high``). Between the two thresholds the state is held, so a
    noisy signal hovering around a single cutoff won't rapidly toggle.

    Example — a pinch is "closed" below 0.35 palm-widths and "open" above 0.5, and anything in
    between keeps its current state.
    """

    __slots__ = ("_state", "high", "low")

    def __init__(self, low: float, high: float, *, initial: bool = False) -> None:
        if not low < high:
            raise ValueError("low must be strictly less than high")
        self.low = low
        self.high = high
        self._state = initial

    def update(self, value: float) -> bool:
        """Feed a new value; return the (possibly unchanged) boolean state."""
        if self._state and value < self.low:
            self._state = False
        elif not self._state and value > self.high:
            self._state = True
        return self._state

    @property
    def state(self) -> bool:
        return self._state

    def reset(self, state: bool = False) -> None:
        self._state = state


class StabilityGate:
    """Requires a boolean condition to hold continuously for ``duration`` before latching true.

    This debounces momentary false positives: a gesture must be *sustained* (e.g. an open palm
    held for 120 ms) before it is accepted. Releasing is immediate so control feels responsive.
    """

    __slots__ = ("_active", "_true_since", "duration")

    def __init__(self, duration: float) -> None:
        if duration < 0:
            raise ValueError("duration must be non-negative")
        self.duration = duration
        self._true_since: float | None = None
        self._active = False

    def update(self, condition: bool, now: float | None = None) -> bool:
        """Update with the current raw condition; return whether it is stably active."""
        t = time.perf_counter() if now is None else now
        if condition:
            if self._true_since is None:
                self._true_since = t
            if (t - self._true_since) >= self.duration:
                self._active = True
        else:
            self._true_since = None
            self._active = False
        return self._active

    @property
    def active(self) -> bool:
        return self._active

    def reset(self) -> None:
        self._true_since = None
        self._active = False


class RateEstimator:
    """Sliding-window rate estimator — used for the live FPS/throughput readouts.

    Tracks timestamps of recent events within ``window`` seconds and reports events-per-second.
    """

    __slots__ = ("_events", "window")

    def __init__(self, window: float = 1.0) -> None:
        if window <= 0:
            raise ValueError("window must be positive")
        self.window = window
        self._events: deque[float] = deque()

    def tick(self, now: float | None = None) -> float:
        """Record one event and return the current estimated rate (events/second)."""
        t = time.perf_counter() if now is None else now
        self._events.append(t)
        cutoff = t - self.window
        while self._events and self._events[0] < cutoff:
            self._events.popleft()
        # Rate = count over the actual span covered (robust while the window fills).
        if len(self._events) < 2:
            return 0.0
        span = self._events[-1] - self._events[0]
        return (len(self._events) - 1) / span if span > 0 else 0.0

    def reset(self) -> None:
        self._events.clear()
