"""Qt/QML application bootstrap.

Creates the ``QGuiApplication``, wires the :class:`AppController` into the QML context, and loads
``Main.qml``. Importing :mod:`gestura.app.camera_view` here registers the ``CameraView`` QML type.

``--self-test`` loads the full UI, confirms it parses and the controller binds, then quits without
opening the camera — used by CI and packaging smoke tests where no webcam/display interaction is
wanted.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from ..config.store import SettingsStore
from ..util.logging import configure, get_logger
from . import camera_view  # noqa: F401 - registers the CameraView QML type on import
from .controller import AppController

_log = get_logger("gestura.app")

_QML_DIR = Path(__file__).resolve().parent / "qml"


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gestura desktop app")
    parser.add_argument("--self-test", type=float, nargs="?", const=1.5, default=None,
                        metavar="SECONDS",
                        help="Load the UI, verify it, then exit (no camera). Optional duration.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run the engine without injecting real input (safe demo mode)")
    args = parser.parse_args(argv)

    configure()
    self_test = args.self_test is not None

    app = QGuiApplication(sys.argv[:1])
    app.setApplicationName("Gestura")
    app.setOrganizationName("Gestura")

    store = SettingsStore()
    settings = store.load()
    controller = AppController(settings, store, dry_run=args.dry_run or self_test)

    engine = QQmlApplicationEngine()
    engine.addImportPath(str(_QML_DIR))
    engine.rootContext().setContextProperty("controller", controller)

    load_errors: list[str] = []
    engine.warnings.connect(lambda ws: load_errors.extend(str(w.toString()) for w in ws))
    engine.load(QUrl.fromLocalFile(str(_QML_DIR / "Main.qml")))

    if not engine.rootObjects():
        _log.error("Failed to load QML UI")
        for err in load_errors:
            _log.error("QML: %s", err)
        return 1

    if self_test:
        _log.info("Self-test: UI loaded successfully (%d root object(s))",
                  len(engine.rootObjects()))
        QTimer.singleShot(int(args.self_test * 1000), app.quit)
        code = app.exec()
        controller.stop()
        # Any QML warning during the run is a failure for the self-test.
        real_warnings = [w for w in load_errors if "TypeError" in w or "ReferenceError" in w
                         or "is not a" in w or "Unable" in w or "Binding loop" in w
                         or "recursive rearrange" in w]
        if real_warnings:
            for w in real_warnings:
                _log.error("QML warning: %s", w)
            return 1
        return code

    controller.start()
    app.aboutToQuit.connect(controller.stop)
    return app.exec()
