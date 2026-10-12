"""OS adapter layer: a platform-independent control surface + concrete backends.

Use :func:`get_adapter` to obtain the right adapter for the current platform. Pass
``dry_run=True`` (or set it automatically off-Windows) to get a :class:`RecordingAdapter` that
performs no real input — used by the headless demo and tests.
"""

from __future__ import annotations

import sys

from .base import (
    SHORTCUT_KEYS,
    MediaAction,
    MouseButton,
    OSAdapter,
    RecordedAction,
    RecordingAdapter,
    WindowAction,
    parse_shortcut,
)

__all__ = [
    "SHORTCUT_KEYS",
    "MediaAction",
    "MouseButton",
    "OSAdapter",
    "RecordedAction",
    "RecordingAdapter",
    "WindowAction",
    "get_adapter",
    "parse_shortcut",
]


def get_adapter(*, dry_run: bool = False) -> OSAdapter:
    """Return an :class:`OSAdapter` for this platform.

    Args:
        dry_run: If ``True``, return a :class:`RecordingAdapter` that injects nothing. This is
            also the automatic fallback on non-Windows platforms until those backends land.
    """
    if dry_run:
        return RecordingAdapter()
    if sys.platform == "win32":
        from .windows import WindowsAdapter

        return WindowsAdapter()
    # No real backend yet for this OS — fail safe to a no-op recorder.
    return RecordingAdapter()
