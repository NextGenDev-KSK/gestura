"""Reach calibration: fit the cursor's active area to how *you* actually move.

Everyone sits at a different distance and angle from the webcam, and a hand rarely reaches
evenly towards every edge of the frame. During calibration the user sweeps their hand around the
area that feels comfortable; we take the spread of the cursor anchor over that sweep and make that
rectangle the part of the frame that maps onto the whole screen.

Robust by construction:

* **Percentiles, not min/max**: a single wild sample (a tracking glitch, a hand leaving the frame)
  can't stretch the region.
* **Padding**: the region is grown slightly so the screen edges are reachable without straining to
  the very limit of the sweep.
* **Minimum size**: a lazy sweep can't produce a region so small that the cursor turns twitchy.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from ..config.models import MIN_REGION_SPAN

#: Fewest samples a sweep needs (~1 s of tracked hand at 30 FPS).
MIN_SAMPLES = 30
#: Percentile trimmed from each end of the sweep.
TRIM_PERCENT = 5.0
#: Extra margin added around the trimmed spread, as a fraction of its size.
PADDING = 0.06


class CalibrationError(ValueError):
    """The sweep can't produce a usable region; the message is shown to the user."""


def region_from_anchors(xs: Sequence[float], ys: Sequence[float]) -> list[float]:
    """Return ``[x0, y0, x1, y1]`` covering the user's comfortable reach.

    Raises:
        CalibrationError: if there are too few samples or the hand barely moved.
    """
    if len(xs) != len(ys):
        raise ValueError("xs and ys must be the same length")
    if len(xs) < MIN_SAMPLES:
        raise CalibrationError("Not enough of your hand was seen. Keep it in view and try again.")

    ax, ay = np.asarray(xs, dtype=float), np.asarray(ys, dtype=float)
    x0, x1 = np.percentile(ax, [TRIM_PERCENT, 100 - TRIM_PERCENT])
    y0, y1 = np.percentile(ay, [TRIM_PERCENT, 100 - TRIM_PERCENT])

    # Tiny spreads mean the hand stayed put, so there's nothing to calibrate from.
    if (x1 - x0) < MIN_REGION_SPAN / 2 or (y1 - y0) < MIN_REGION_SPAN / 2:
        raise CalibrationError(
            "Your hand barely moved. Sweep it to the left, right, top and bottom of where "
            "it feels comfortable.")

    region = []
    for lo, hi in ((x0, x1), (y0, y1)):
        pad = (hi - lo) * PADDING
        lo, hi = lo - pad, hi + pad
        # Enforce the minimum span symmetrically, then keep the box inside the frame.
        if hi - lo < MIN_REGION_SPAN:
            grow = (MIN_REGION_SPAN - (hi - lo)) / 2
            lo, hi = lo - grow, hi + grow
        if lo < 0.0:
            lo, hi = 0.0, hi - lo
        if hi > 1.0:
            lo, hi = lo - (hi - 1.0), 1.0
        region.append((max(0.0, lo), min(1.0, hi)))
    (rx0, rx1), (ry0, ry1) = region
    return [round(float(rx0), 4), round(float(ry0), 4), round(float(rx1), 4), round(float(ry1), 4)]
