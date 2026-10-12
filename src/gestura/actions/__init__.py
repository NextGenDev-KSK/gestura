"""Action layer: the gesture->action catalogue and the dispatcher that runs it."""

from __future__ import annotations

from .dispatcher import ActionDispatcher
from .registry import (
    ACTIONS,
    ActionContext,
    ActionSpec,
    EngineControl,
    actions_for,
    all_actions,
    get_action,
)

__all__ = [
    "ACTIONS",
    "ActionContext",
    "ActionDispatcher",
    "ActionSpec",
    "EngineControl",
    "actions_for",
    "all_actions",
    "get_action",
]
