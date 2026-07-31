"""Signal-smoothing filters for noisy landmark streams.

The star here is the **One-Euro filter** (Casiez, Roussel & Vogel, CHI 2012), the de-facto
standard for smoothing interactive pointing input. Unlike a fixed low-pass/EMA it *adapts* its
cutoff to movement speed: heavy smoothing (steady cursor) when the hand is slow, light smoothing
(low lag) when it moves fast. This directly serves Gestura's "no jitter, no lag" cursor goal.

See ADR-0006 in ``docs/DECISIONS.md``.
"""

from __future__ import annotations

import math
import time


def _smoothing_alpha(cutoff: float, dt: float) -> float:
    """Compute the EMA smoothing factor for a given cutoff frequency and time step."""
    tau = 1.0 / (2.0 * math.pi * cutoff)
    return 1.0 / (1.0 + tau / dt)


class _LowPass:
    """First-order low-pass (EMA) filter with settable per-step alpha."""

    __slots__ = ("_value", "_initialized")

    def __init__(self) -> None:
        self._value: float = 0.0
        self._initialized = False

    @property
    def initialized(self) -> bool:
        return self._initialized

    @property
    def value(self) -> float:
        return self._value

    def apply(self, x: float, alpha: float) -> float:
        self._value = x if not self._initialized else alpha * x + (1.0 - alpha) * self._value
        self._initialized = True
        return self._value

    def reset(self) -> None:
        self._value = 0.0
        self._initialized = False


class OneEuroFilter:
    """Adaptive One-Euro low-pass filter for a single scalar channel.

    Args:
        min_cutoff: Baseline cutoff frequency (Hz). Lower = smoother/steadier when slow.
        beta: Speed coefficient. Higher = less lag during fast motion (but more jitter).
        d_cutoff: Cutoff for the internal speed estimate. Rarely needs changing.

    Call the filter with a new sample and an optional timestamp (seconds). If no timestamp is
    given, ``time.perf_counter()`` is used. The first sample is returned unchanged.
    """

    __slots__ = ("min_cutoff", "beta", "d_cutoff", "_x", "_dx", "_last_t")

    def __init__(self, min_cutoff: float = 1.0, beta: float = 0.0, d_cutoff: float = 1.0) -> None:
        if min_cutoff <= 0 or d_cutoff <= 0:
            raise ValueError("cutoff frequencies must be positive")
        if beta < 0:
            raise ValueError("beta must be non-negative")
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self._x = _LowPass()
        self._dx = _LowPass()
        self._last_t: float | None = None

    def __call__(self, x: float, timestamp: float | None = None) -> float:
        t = time.perf_counter() if timestamp is None else timestamp
        if self._last_t is None or t <= self._last_t:
            # First sample, or non-monotonic clock: seed without adapting.
            dt = 1.0 / 60.0
        else:
            dt = t - self._last_t
        self._last_t = t

        # Estimate and smooth the derivative (units/second).
        prev = self._x.value if self._x.initialized else x
        dx = (x - prev) / dt
        edx = self._dx.apply(dx, _smoothing_alpha(self.d_cutoff, dt))

        # Speed-adaptive cutoff: fast motion => higher cutoff => less lag.
        cutoff = self.min_cutoff + self.beta * abs(edx)
        return self._x.apply(x, _smoothing_alpha(cutoff, dt))

    def reset(self) -> None:
        """Forget all history; the next sample seeds the filter afresh."""
        self._x.reset()
        self._dx.reset()
        self._last_t = None


class OneEuroFilter2D:
    """Two independent :class:`OneEuroFilter` channels for smoothing an ``(x, y)`` point."""

    __slots__ = ("_fx", "_fy")

    def __init__(self, min_cutoff: float = 1.0, beta: float = 0.0, d_cutoff: float = 1.0) -> None:
        self._fx = OneEuroFilter(min_cutoff, beta, d_cutoff)
        self._fy = OneEuroFilter(min_cutoff, beta, d_cutoff)

    def __call__(
        self, x: float, y: float, timestamp: float | None = None
    ) -> tuple[float, float]:
        t = time.perf_counter() if timestamp is None else timestamp
        return self._fx(x, t), self._fy(y, t)

    def reset(self) -> None:
        self._fx.reset()
        self._fy.reset()


class ExponentialMovingAverage:
    """Plain fixed-alpha EMA — used for slowly-varying scalars (e.g. confidence, FPS)."""

    __slots__ = ("alpha", "_value", "_initialized")

    def __init__(self, alpha: float = 0.2) -> None:
        if not 0.0 < alpha <= 1.0:
            raise ValueError("alpha must be in (0, 1]")
        self.alpha = alpha
        self._value = 0.0
        self._initialized = False

    def __call__(self, x: float) -> float:
        self._value = x if not self._initialized else self.alpha * x + (1 - self.alpha) * self._value
        self._initialized = True
        return self._value

    @property
    def value(self) -> float:
        return self._value

    def reset(self) -> None:
        self._value = 0.0
        self._initialized = False
