"""The catalogue of built-in gestures the interpreter can emit.

This is the single source of truth for *which* gesture names exist, how they're shown to the user,
and what :class:`~gestura.core.types.GestureKind` of events each one produces. The gesture editor
renders its list from here (so the UI can never drift from the engine), and the kind decides which
actions a gesture can be bound to — e.g. a thumb-up only ever emits repeated ``UPDATED`` events,
so binding "screenshot" (which fires on ``BEGAN``) to it would silently never trigger.

User-recorded gestures aren't listed here; they are always :attr:`GestureKind.TAP` (see
:mod:`gestura.engine.custom`).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core.types import GestureKind


@dataclass(frozen=True)
class GestureInfo:
    """Display metadata for one built-in gesture."""

    id: str
    label: str
    icon: str
    hint: str
    kind: GestureKind


BUILTIN_GESTURES: tuple[GestureInfo, ...] = (
    GestureInfo("pinch", "Pinch (index)", "👌", "Index fingertip meets the thumb",
                GestureKind.TAP),
    GestureInfo("middle_pinch", "Middle pinch", "🤏", "Middle finger meets the thumb, index out",
                GestureKind.TAP),
    GestureInfo("pinky_pinch", "Pinky pinch", "🤞", "Pinky meets the thumb, index out",
                GestureKind.TAP),
    GestureInfo("fist", "Fist (hold)", "✊", "Close to grab, open to release", GestureKind.HOLD),
    GestureInfo("two_finger_scroll", "Two fingers", "✌️", "Index + middle up, move up/down",
                GestureKind.SCROLL),
    GestureInfo("zoom", "Two-hand pinch", "🙌", "Pinch with both hands, move them apart/together",
                GestureKind.ZOOM),
    GestureInfo("rock", "Rock", "🤘", "Index + pinky up", GestureKind.TAP),
    GestureInfo("three_fingers", "Three fingers", "3️⃣", "Index + middle + ring up",
                GestureKind.TAP),
    GestureInfo("pinky", "Pinky", "🤙", "Only the pinky up", GestureKind.TAP),
    GestureInfo("thumb_up", "Thumb up", "👍", "Fist with the thumb pointing up",
                GestureKind.REPEAT),
    GestureInfo("thumb_down", "Thumb down", "👎", "Fist with the thumb pointing down",
                GestureKind.REPEAT),
    GestureInfo("thumb_left", "Thumb left", "👈", "Fist with the thumb pointing left",
                GestureKind.TAP),
    GestureInfo("thumb_right", "Thumb right", "👉", "Fist with the thumb pointing right",
                GestureKind.TAP),
)

_BY_ID: dict[str, GestureInfo] = {g.id: g for g in BUILTIN_GESTURES}


def builtin_gesture(gesture_id: str) -> GestureInfo | None:
    """Look up a built-in gesture by id, or ``None`` if it isn't one (e.g. a custom gesture)."""
    return _BY_ID.get(gesture_id)


def gesture_kind(gesture_id: str) -> GestureKind:
    """The event kind a gesture produces. Anything not built in is a custom (``TAP``) gesture."""
    info = _BY_ID.get(gesture_id)
    return info.kind if info is not None else GestureKind.TAP
