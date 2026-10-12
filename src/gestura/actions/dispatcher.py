"""Action dispatcher: turns interpreter output into OS effects via the active bindings.

The dispatcher is the only place that knows how gesture *names* map to *actions* — it resolves
each :class:`GestureEvent` through the profile's :class:`GestureBinding`\\s and invokes the
registered handler. It also moves the cursor and owns the global pause switch (so the "open palm
hold" gesture, or the UI, can freeze all input while the engine keeps running).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from ..config.models import GestureBinding, Profile
from ..core.types import GestureEvent
from ..platform.base import OSAdapter
from ..util.logging import get_logger
from .registry import ActionContext, EngineControl, get_action

if TYPE_CHECKING:
    # Annotation-only: importing the engine at runtime would form a cycle
    # (engine.pipeline -> actions.dispatcher -> engine), making import order matter.
    from ..engine.interpreter import InterpretationResult

_log = get_logger("gestura.actions")


class ActionDispatcher(EngineControl):
    """Executes gesture events against an :class:`OSAdapter` using the active bindings."""

    def __init__(
        self,
        adapter: OSAdapter,
        profile: Profile,
        *,
        paused: bool = False,
        on_pause_changed: Callable[[bool], None] | None = None,
    ) -> None:
        self._adapter = adapter
        self._paused = paused
        self._on_pause_changed = on_pause_changed
        self._unknown_warned: set[str] = set()
        self._by_gesture: dict[str, GestureBinding] = {}
        self.set_profile(profile)

    # -- configuration -------------------------------------------------------------------------
    def set_profile(self, profile: Profile) -> None:
        """Rebuild the gesture->binding lookup (call after the user edits mappings)."""
        self._by_gesture = {b.gesture: b for b in profile.bindings if b.enabled}

    # -- pause control (EngineControl) ---------------------------------------------------------
    @property
    def paused(self) -> bool:
        return self._paused

    def set_paused(self, value: bool) -> None:
        if value != self._paused:
            self._paused = value
            _log.info("Gesture control %s", "paused" if value else "resumed")
            if self._on_pause_changed is not None:
                self._on_pause_changed(value)

    def toggle_pause(self) -> None:
        self.set_paused(not self._paused)

    # -- dispatch ------------------------------------------------------------------------------
    def dispatch(self, result: InterpretationResult) -> None:
        """Apply one interpreter result: move the cursor and run any triggered actions."""
        if not self._paused and result.cursor is not None:
            x, y = result.cursor
            self._adapter.move_cursor(x, y)

        for event in result.events:
            self._dispatch_event(event)

    def _dispatch_event(self, event: GestureEvent) -> None:
        binding = self._by_gesture.get(event.name)
        if binding is None:
            return  # gesture recognised but not bound to anything

        # While paused, swallow everything except the gesture that resumes us.
        if self._paused and binding.action != "pause_toggle":
            return

        spec = get_action(binding.action)
        if spec is None:
            if binding.action not in self._unknown_warned:
                self._unknown_warned.add(binding.action)
                _log.warning("Binding '%s' -> unknown action '%s'", event.name, binding.action)
            return

        ctx = ActionContext(self._adapter, event, binding.params, control=self,
                            shortcut=binding.shortcut)
        try:
            spec.handler(ctx)
        except Exception:
            _log.exception("Action '%s' failed", binding.action)
