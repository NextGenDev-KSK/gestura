"""Centralised logging setup: pretty console output plus a rotating file log.

Rich renders readable, colourised console logs during development; a rotating file handler in the
per-user log directory captures diagnostics for bug reports without unbounded disk growth. Call
:func:`configure` once at startup.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from rich.logging import RichHandler

from .paths import log_dir

_CONFIGURED = False


def configure(level: int | str = logging.INFO, *, to_file: bool = True) -> None:
    """Initialise root logging. Safe to call more than once (subsequent calls are no-ops)."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)  # handlers filter; keep the root permissive

    console = RichHandler(rich_tracebacks=True, show_path=False, markup=False)
    console.setLevel(level)
    console.setFormatter(logging.Formatter("%(name)s — %(message)s", datefmt="%H:%M:%S"))
    root.addHandler(console)

    # Quiet chatty third-party libraries pulled in transitively (matplotlib via mediapipe, etc.).
    for noisy in ("matplotlib", "PIL", "comtypes", "fontTools", "h5py"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    if to_file:
        logfile = log_dir() / "gestura.log"
        file_handler = RotatingFileHandler(
            logfile, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)-7s %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
            )
        )
        root.addHandler(file_handler)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a module logger; namespaced under ``gestura`` for easy filtering."""
    return logging.getLogger(name)
