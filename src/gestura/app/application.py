"""Qt/QML application bootstrap.

Creates the application, wires the :class:`AppController` into the QML context, and loads
``Main.qml``. Importing :mod:`gestura.app.camera_view` here registers the ``CameraView`` QML type.

Gestura is a background utility, so the app also:

* lives in the **system tray**: closing the window keeps gesture control running; the tray icon
  shows whether control is on or paused, and its menu can show the window, pause, or quit;
* is **single-instance**: launching it again just brings the running window forward instead of
  starting a second engine fighting over the camera;
* can **start minimized** (``--minimized``, or the setting), which is how "Start with Windows"
  launches it.

``--self-test`` loads the full UI, confirms it parses and the controller binds, then quits without
opening the camera — used by CI and packaging smoke tests where no webcam/display interaction is
wanted.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path
from typing import cast

from PySide6.QtCore import QObject, QTimer, QUrl
from PySide6.QtGui import QIcon, QWindow
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from ..config.store import SettingsStore
from ..util.logging import configure, get_logger
from ..util.paths import project_root
from . import camera_view  # noqa: F401 - registers the CameraView QML type on import
from .controller import AppController

_log = get_logger("gestura.app")

_QML_DIR = Path(__file__).resolve().parent / "qml"
_INSTANCE_KEY = f"gestura-{getpass.getuser()}"


def icon_path(name: str) -> Path:
    return project_root() / "assets" / "icons" / name


# --- single instance ------------------------------------------------------------------------------
def claim_single_instance(key: str = _INSTANCE_KEY) -> QLocalServer | None:
    """Become the one running instance, or wake the existing one.

    Returns a listening server if we're the first instance, or ``None`` after asking the instance
    that's already running to show its window (the caller should then exit).
    """
    probe = QLocalSocket()
    probe.connectToServer(key)
    if probe.waitForConnected(300):
        probe.write(b"show")
        probe.flush()
        probe.waitForBytesWritten(300)
        probe.disconnectFromServer()
        return None
    QLocalServer.removeServer(key)  # clear a stale socket left by a crash
    server = QLocalServer()
    if not server.listen(key):
        _log.warning("Single-instance server unavailable: %s", server.errorString())
    return server


# --- system tray --------------------------------------------------------------------------------
class TrayController(QObject):
    """Owns the tray icon and decides what closing the window means."""

    def __init__(self, app: QApplication, window: QQuickWindow,
                 controller: AppController) -> None:
        super().__init__(app)
        self._app = app
        self._window = window
        self._controller = controller
        self._hide_hint_shown = False
        self._icon_on = QIcon(str(icon_path("gestura.png")))
        self._icon_paused = QIcon(str(icon_path("gestura_paused.png")))

        self.available = QSystemTrayIcon.isSystemTrayAvailable()
        self._tray = QSystemTrayIcon(self._icon_on, self)
        menu = QMenu()
        self._show_action = menu.addAction("Show Gestura", self.show_window)
        self._pause_action = menu.addAction("Pause gesture control", controller.togglePause)
        menu.addSeparator()
        menu.addAction("Quit Gestura", app.quit)
        self._menu = menu  # keep a reference; the tray doesn't own it
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_activated)
        controller.pausedChanged.connect(self._refresh)
        controller.settingsChanged.connect(self._refresh)
        controller.closeRequested.connect(self._on_close_requested)
        controller.notify.connect(self._on_notify)
        controller.settingsChanged.connect(self._sync_quit_policy)
        window.visibleChanged.connect(self._on_visible_changed)
        self._refresh()
        self._sync_quit_policy()
        if self.available:
            self._tray.show()

    def _sync_quit_policy(self) -> None:
        # The window always accepts closing (so Quit and Windows shutdown are never blocked).
        # Whether closing it ends the app is decided here: with the tray in use it doesn't, so
        # Alt+F4, the taskbar's "Close window" and the title-bar X all just hide to the tray.
        self._app.setQuitOnLastWindowClosed(not self._keeps_running())

    def _keeps_running(self) -> bool:
        return self.available and bool(self._controller.closeToTray)

    def _on_visible_changed(self, visible: bool) -> None:
        _log.info("Window %s (keeps running in tray: %s, quit on last window closed: %s)",
                  "shown" if visible else "hidden", self._keeps_running(),
                  self._app.quitOnLastWindowClosed())
        if not visible and self._keeps_running() and not self._hide_hint_shown:
            self._hide_hint_shown = True
            self._tray.showMessage(
                "Gestura is still running",
                f"Gesture control stays on in the background. Press "
                f"{self._controller.pauseHotkeyLabel} to pause, or right-click the tray "
                f"icon to quit.", self._icon_on, 6000)

    def _refresh(self) -> None:
        paused = self._controller.paused
        hotkey = self._controller.pauseHotkeyLabel
        self._tray.setIcon(self._icon_paused if paused else self._icon_on)
        self._tray.setToolTip(f"Gestura: {'paused' if paused else 'gesture control on'}"
                              f"\n{hotkey} to {'resume' if paused else 'pause'}")
        self._pause_action.setText("Resume gesture control" if paused else "Pause gesture control")

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_window()

    def _on_close_requested(self) -> None:
        if self._keeps_running():
            self._window.hide()          # the hint is shown by _on_visible_changed
        else:
            self._app.quit()

    def _on_notify(self, title: str, body: str) -> None:
        # Only needed when the window can't show it (hidden in the tray).
        if self.available and not self._window.isVisible():
            self._tray.showMessage(title, body, self._icon_paused if self._controller.paused
                                   else self._icon_on, 2500)

    def show_window(self) -> None:
        self._window.show()
        if self._window.visibility() == QWindow.Visibility.Minimized:
            self._window.showNormal()
        self._window.raise_()
        self._window.requestActivate()

    def hide_icon(self) -> None:
        self._tray.hide()


# --- entry point --------------------------------------------------------------------------------
def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gestura desktop app")
    parser.add_argument("--self-test", type=float, nargs="?", const=1.5, default=None,
                        metavar="SECONDS",
                        help="Load the UI, verify it, then exit (no camera). Optional duration.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run the engine without injecting real input (safe demo mode)")
    parser.add_argument("--minimized", action="store_true",
                        help="Start in the system tray without showing the window")
    args = parser.parse_args(argv)

    configure()
    self_test = args.self_test is not None

    app = QApplication(sys.argv[:1])
    app.setApplicationName("Gestura")
    app.setOrganizationName("Gestura")
    app.setWindowIcon(QIcon(str(icon_path("gestura.ico"))))

    server = None
    if not self_test:
        server = claim_single_instance()
        if server is None:
            _log.info("Gestura is already running; asked it to show its window")
            return 0

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
    window = cast(QQuickWindow, engine.rootObjects()[0])

    if self_test:
        window.show()
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

    tray = TrayController(app, window, controller)
    if server is not None:
        server.newConnection.connect(lambda: _on_wake(server, tray))

    controller.sync_autostart()
    start_hidden = (args.minimized or settings.ui.start_minimized)
    if start_hidden and tray.available:
        _log.info("Started minimized to the system tray")
    elif start_hidden:
        window.showMinimized()
    else:
        window.show()

    controller.start()
    app.aboutToQuit.connect(lambda: _log.info("Gestura is quitting"))
    app.aboutToQuit.connect(controller.stop)
    app.aboutToQuit.connect(tray.hide_icon)
    return app.exec()


def _on_wake(server: QLocalServer, tray: TrayController) -> None:
    """Another launch asked us to show ourselves."""
    _log.info("Another launch asked us to show the window")
    while server.hasPendingConnections():
        conn = server.nextPendingConnection()
        conn.readyRead.connect(conn.readAll)     # drain the "show" message
        conn.disconnected.connect(conn.deleteLater)
    tray.show_window()
