"""Shared utilities: filesystem locations and logging setup."""

from __future__ import annotations

from .logging import configure, get_logger
from .paths import config_dir, data_dir, log_dir, models_dir

__all__ = [
    "config_dir",
    "configure",
    "data_dir",
    "get_logger",
    "log_dir",
    "models_dir",
]
