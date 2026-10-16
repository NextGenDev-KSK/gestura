"""Tests for the app shell: single instance and the system-tray close behaviour."""

from __future__ import annotations

import uuid

import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QWindow
from PySide6.QtWidgets import QSystemTrayIcon

from gestura.app.application import TrayController, claim_single_instance
from gestura.app.controller import AppController
from gestura.config.store import SettingsStore
from gestura.platform.autostart import AutoStart


class _NoRegistry:
    def get(self, name):
        return None

    def set(self, name, command):
        pass

    def delete(self, name):
        pass


def test_second_launch_wakes_the_first(qapp, qtbot) -> None:
    key = f"gestura-test-{uuid.uuid4().hex}"
    server = claim_single_instance(key)
    assert server is not None and server.isListening()
    woken = []
    server.newConnection.connect(lambda: woken.append(True))
    try:
        assert claim_single_instance(key) is None        # the second launch defers...
        qtbot.waitUntil(lambda: bool(woken), timeout=2000)  # ...and the first one hears it
    finally:
        server.close()


@pytest.fixture
def shell(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: True))
    monkeypatch.setattr("gestura.engine.pipeline.data_dir", lambda: tmp_path)
    store = SettingsStore(path=tmp_path / "settings.json")
    ctrl = AppController(store.load(), store, dry_run=True, autostart=AutoStart(_NoRegistry()))
    window = QWindow()
    window.show()
    tray = TrayController(qapp, window, ctrl)
    yield qapp, window, ctrl, tray
    tray.hide_icon()
    window.destroy()
    qapp.setQuitOnLastWindowClosed(True)


def test_closing_hides_to_the_tray_by_default(shell) -> None:
    app, window, ctrl, _ = shell
    assert app.quitOnLastWindowClosed() is False       # closing the window must not end the app
    ctrl.requestClose()
    assert not window.isVisible()


def test_turning_off_close_to_tray_restores_normal_quitting(shell) -> None:
    app, _, ctrl, _ = shell
    ctrl.setBool("ui.close_to_tray", False)
    assert app.quitOnLastWindowClosed() is True


def test_tray_menu_follows_the_pause_state(shell) -> None:
    _, _, ctrl, tray = shell
    assert tray._pause_action.text() == "Pause gesture control"
    ctrl._on_hotkey()
    ctrl._tick()
    assert tray._pause_action.text() == "Resume gesture control"
    assert "paused" in tray._tray.toolTip()
