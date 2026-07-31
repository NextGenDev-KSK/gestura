"""Cursor mapping and smoothing.

Converts a hand anchor (normalized frame coordinates) into a smoothed, normalized *screen*
position in ``[0, 1]²`` that the OS adapter turns into pixels. Three stages, each tackling a
specific "no cursor jump / no jitter" requirement:

1. **Active region** — only the central rectangle of the frame maps to the full screen, so you
   never have to stretch your arm to the physical edge of the camera's view to reach a corner.
2. **Dead zone** — sub-pixel hand tremor below a threshold is suppressed so a resting hand yields
   a perfectly still cursor.
3. **One-Euro smoothing** — adaptive low-pass that stays steady when slow and lags minimally when
   fast (ADR-0006).
"""

from __future__ import annotations

import math

from ..config.models import CursorConfig
from ..core.filters import OneEuroFilter2D
from ..core.geometry import clamp, remap


class CursorController:
    """Stateful mapper from hand anchor -> smoothed normalized screen position."""

    def __init__(self, config: CursorConfig) -> None:
        self._cfg = config
        self._filter = OneEuroFilter2D(
            min_cutoff=config.smoothing_min_cutoff, beta=config.smoothing_beta
        )
        self._last_raw: tuple[float, float] | None = None
        self._last_out: tuple[float, float] | None = None

    def update(
        self, anchor: tuple[float, float], timestamp: float | None = None
    ) -> tuple[float, float] | None:
        """Map and smooth one anchor sample. Returns ``(x, y)`` in ``[0, 1]²`` or ``None``.

        ``None`` means cursor control is disabled; the caller should leave the pointer alone.
        """
        if not self._cfg.enabled:
            return None

        mx = self._cfg.region_margin_x
        my = self._cfg.region_margin_y
        x = remap(anchor[0], mx, 1.0 - mx, 0.0, 1.0)
        y = remap(anchor[1], my, 1.0 - my, 0.0, 1.0)

        # Dead zone: if the hand barely moved, hold the previous raw target so the cursor rests.
        if self._last_raw is not None:
            dx = x - self._last_raw[0]
            dy = y - self._last_raw[1]
            if math.hypot(dx, dy) < self._cfg.dead_zone:
                x, y = self._last_raw
        self._last_raw = (x, y)

        sx, sy = self._filter(x, y, timestamp)
        self._last_out = (clamp(sx), clamp(sy))
        return self._last_out

    @property
    def last_position(self) -> tuple[float, float] | None:
        """The most recent smoothed output (for the UI overlay), or ``None``."""
        return self._last_out

    def reset(self) -> None:
        """Clear smoothing state — call on tracking loss so the cursor doesn't leap on re-acquire."""
        self._filter.reset()
        self._last_raw = None
        self._last_out = None

    def apply_config(self, config: CursorConfig) -> None:
        """Hot-swap tuning (e.g. from the settings UI) without dropping the current position."""
        self._cfg = config
        self._filter = OneEuroFilter2D(
            min_cutoff=config.smoothing_min_cutoff, beta=config.smoothing_beta
        )
        self._last_raw = None
