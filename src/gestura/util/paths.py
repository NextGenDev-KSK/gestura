"""Cross-platform locations for config, data, logs, and bundled assets.

Kept tiny and dependency-free. Windows uses the standard ``%APPDATA%`` / ``%LOCALAPPDATA%``
roots; other platforms follow the XDG Base Directory spec so a future Linux port needs no changes
here. All returned directories are created on first access.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "Gestura"


def _ensure(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_dir() -> Path:
    """Per-user configuration directory (roams with the user profile on Windows)."""
    if sys.platform == "win32":
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return _ensure(root / APP_NAME)


def data_dir() -> Path:
    """Per-user data directory for profiles, recorded gestures, and trained models."""
    if sys.platform == "win32":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return _ensure(root / APP_NAME)


def log_dir() -> Path:
    """Directory for rotating diagnostic logs."""
    if sys.platform == "win32":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return _ensure(root / APP_NAME / "logs")
    return _ensure(data_dir() / "logs")


def project_root() -> Path:
    """Repository root (useful in dev for locating bundled assets/models)."""
    return Path(__file__).resolve().parents[3]


def models_dir() -> Path:
    """Where ML model files live. Prefers a user copy, falls back to the bundled repo dir."""
    user_models = data_dir() / "models"
    if user_models.exists():
        return user_models
    return project_root() / "models"
