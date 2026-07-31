"""Typed, persisted configuration for the whole application."""

from __future__ import annotations

from .models import (
    DEFAULT_BINDINGS,
    SCHEMA_VERSION,
    AppSettings,
    CameraConfig,
    CursorConfig,
    CustomGesture,
    GestureBinding,
    GestureThresholds,
    Profile,
    Theme,
    TrackingConfig,
    UiConfig,
)
from .store import CONFIG_FILENAME, SettingsStore

__all__ = [
    "DEFAULT_BINDINGS",
    "SCHEMA_VERSION",
    "AppSettings",
    "CameraConfig",
    "CursorConfig",
    "CustomGesture",
    "GestureBinding",
    "GestureThresholds",
    "Profile",
    "Theme",
    "TrackingConfig",
    "UiConfig",
    "CONFIG_FILENAME",
    "SettingsStore",
]
