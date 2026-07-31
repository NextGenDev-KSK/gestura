"""The catalogue of actions a gesture can trigger.

Each :class:`ActionSpec` pairs a stable ``id`` (referenced by config bindings) with a human label,
a category (for grouping in the settings UI), and a handler that performs the effect. Keeping this
as data — rather than scattering ``if action == ...`` across the code — means the settings UI can
render the full list of bindable actions automatically, and adding an action is a one-liner.

Handlers are **phase-aware**: a momentary action fires on ``BEGAN``; a continuous one (drag)
maps ``BEGAN``/``ENDED`` to button down/up; a repeating one (scroll, volume) acts on ``UPDATED``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ..core.types import GestureEvent, GesturePhase
from ..platform.base import MediaAction, MouseButton, OSAdapter, WindowAction


class EngineControl(Protocol):
    """App-level controls an action may need (implemented by the pipeline/app)."""

    def toggle_pause(self) -> None: ...


@dataclass(frozen=True)
class ActionContext:
    """Everything a handler needs to perform its effect."""

    adapter: OSAdapter
    event: GestureEvent
    params: dict[str, float]
    control: EngineControl | None


Handler = Callable[[ActionContext], None]


@dataclass(frozen=True)
class ActionSpec:
    id: str
    label: str
    category: str
    description: str
    handler: Handler


# --- Handlers ---------------------------------------------------------------------------------
def _on_began(ctx: ActionContext) -> bool:
    return ctx.event.phase is GesturePhase.BEGAN


def _left_click(ctx: ActionContext) -> None:
    if _on_began(ctx):
        ctx.adapter.click(MouseButton.LEFT)


def _right_click(ctx: ActionContext) -> None:
    if _on_began(ctx):
        ctx.adapter.click(MouseButton.RIGHT)


def _middle_click(ctx: ActionContext) -> None:
    if _on_began(ctx):
        ctx.adapter.click(MouseButton.MIDDLE)


def _double_click(ctx: ActionContext) -> None:
    if _on_began(ctx):
        ctx.adapter.double_click(MouseButton.LEFT)


def _drag(ctx: ActionContext) -> None:
    # Fist BEGAN -> press and hold; ENDED (release or tracking loss) -> drop.
    if ctx.event.phase is GesturePhase.BEGAN:
        ctx.adapter.mouse_down(MouseButton.LEFT)
    elif ctx.event.phase is GesturePhase.ENDED:
        ctx.adapter.mouse_up(MouseButton.LEFT)


def _scroll(ctx: ActionContext) -> None:
    if ctx.event.phase is GesturePhase.UPDATED:
        dy = ctx.event.payload.get("dy", 0.0) * ctx.params.get("speed", 1.0)
        dx = ctx.event.payload.get("dx", 0.0) * ctx.params.get("speed", 1.0)
        ctx.adapter.scroll(dy, dx)


def _volume_up(ctx: ActionContext) -> None:
    if ctx.event.phase is GesturePhase.UPDATED:
        ctx.adapter.adjust_volume(+ctx.params.get("amount", 2.0))


def _volume_down(ctx: ActionContext) -> None:
    if ctx.event.phase is GesturePhase.UPDATED:
        ctx.adapter.adjust_volume(-ctx.params.get("amount", 2.0))


def _brightness_up(ctx: ActionContext) -> None:
    if ctx.event.phase is GesturePhase.UPDATED:
        ctx.adapter.adjust_brightness(+ctx.params.get("amount", 5.0))


def _brightness_down(ctx: ActionContext) -> None:
    if ctx.event.phase is GesturePhase.UPDATED:
        ctx.adapter.adjust_brightness(-ctx.params.get("amount", 5.0))


def _screenshot(ctx: ActionContext) -> None:
    if _on_began(ctx):
        ctx.adapter.screenshot()


def _pause_toggle(ctx: ActionContext) -> None:
    if _on_began(ctx) and ctx.control is not None:
        ctx.control.toggle_pause()


def _media(action: MediaAction) -> Handler:
    def handler(ctx: ActionContext) -> None:
        if _on_began(ctx):
            ctx.adapter.media(action)
    return handler


def _window(action: WindowAction) -> Handler:
    def handler(ctx: ActionContext) -> None:
        if _on_began(ctx):
            ctx.adapter.window(action)
    return handler


# --- Catalogue --------------------------------------------------------------------------------
_SPECS: tuple[ActionSpec, ...] = (
    ActionSpec("left_click", "Left click", "Mouse", "Primary click", _left_click),
    ActionSpec("right_click", "Right click", "Mouse", "Context-menu click", _right_click),
    ActionSpec("middle_click", "Middle click", "Mouse", "Middle-button click", _middle_click),
    ActionSpec("double_click", "Double click", "Mouse", "Double primary click", _double_click),
    ActionSpec("drag", "Drag", "Mouse", "Hold to drag, release to drop", _drag),
    ActionSpec("scroll", "Scroll", "Mouse", "Scroll vertically/horizontally", _scroll),
    ActionSpec("volume_up", "Volume up", "System", "Raise master volume", _volume_up),
    ActionSpec("volume_down", "Volume down", "System", "Lower master volume", _volume_down),
    ActionSpec("brightness_up", "Brightness up", "System", "Raise display brightness", _brightness_up),
    ActionSpec("brightness_down", "Brightness down", "System", "Lower display brightness",
               _brightness_down),
    ActionSpec("screenshot", "Screenshot", "System", "Capture the screen to a file", _screenshot),
    ActionSpec("pause_toggle", "Pause / resume", "App", "Toggle gesture control", _pause_toggle),
    ActionSpec("media_play_pause", "Play / pause", "Media", "Toggle media playback",
               _media(MediaAction.PLAY_PAUSE)),
    ActionSpec("media_next", "Next track", "Media", "Skip to next track", _media(MediaAction.NEXT)),
    ActionSpec("media_prev", "Previous track", "Media", "Back to previous track",
               _media(MediaAction.PREVIOUS)),
    ActionSpec("window_minimize", "Minimize window", "Window", "Minimize the active window",
               _window(WindowAction.MINIMIZE)),
    ActionSpec("window_maximize", "Maximize window", "Window", "Maximize the active window",
               _window(WindowAction.MAXIMIZE)),
    ActionSpec("window_snap_left", "Snap left", "Window", "Snap window to the left half",
               _window(WindowAction.SNAP_LEFT)),
    ActionSpec("window_snap_right", "Snap right", "Window", "Snap window to the right half",
               _window(WindowAction.SNAP_RIGHT)),
    ActionSpec("window_close", "Close window", "Window", "Close the active window",
               _window(WindowAction.CLOSE)),
    ActionSpec("switch_window", "Switch window", "Window", "Alt-Tab to another window",
               _window(WindowAction.SWITCH)),
    ActionSpec("show_desktop", "Show desktop", "Window", "Minimize everything",
               _window(WindowAction.SHOW_DESKTOP)),
)

ACTIONS: dict[str, ActionSpec] = {spec.id: spec for spec in _SPECS}


def get_action(action_id: str) -> ActionSpec | None:
    """Look up an action by id, or ``None`` if unknown."""
    return ACTIONS.get(action_id)


def all_actions() -> tuple[ActionSpec, ...]:
    """Every registered action (for the settings UI)."""
    return _SPECS
