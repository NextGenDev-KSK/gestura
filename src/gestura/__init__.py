"""Gestura — offline, AI-powered hand-gesture control for the desktop.

The package is organised in layers (see ``docs/ARCHITECTURE.md``); import from the
public sub-packages rather than reaching into private modules::

    gestura.core      pure-logic primitives (types, geometry, filters, timing)
    gestura.config    typed, persisted configuration
    gestura.vision    camera capture + MediaPipe hand tracking
    gestura.engine    gesture recognition, smoothing, interpretation
    gestura.actions   gesture -> command mapping + dispatch
    gestura.platform  OS adapters (Windows today; Linux later)
    gestura.app       Qt6/QML presentation layer
"""

from __future__ import annotations

__all__ = ["__author__", "__version__"]

__version__ = "0.1.0"
__author__ = "Krithik S"
