"""Start Gestura when you sign in to Windows.

Uses the per-user ``Run`` registry key (no admin rights, nothing outside your profile). The app is
launched with ``--minimized`` so it starts quietly in the system tray. The registry access is a
small injectable backend so tests never touch the real registry.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Protocol

from ..util.logging import get_logger

_log = get_logger("gestura.platform.autostart")

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "Gestura"


class RunKey(Protocol):
    def get(self, name: str) -> str | None: ...
    def set(self, name: str, command: str) -> None: ...
    def delete(self, name: str) -> None: ...


class WindowsRunKey:
    """``HKEY_CURRENT_USER\\...\\CurrentVersion\\Run`` via :mod:`winreg`."""

    def get(self, name: str) -> str | None:
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                value, _ = winreg.QueryValueEx(key, name)
                return str(value)
        except FileNotFoundError:
            return None

    def set(self, name: str, command: str) -> None:
        import winreg

        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, command)

    def delete(self, name: str) -> None:
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, name)
        except FileNotFoundError:
            pass


def launch_command() -> str:
    """The command that starts this installation of Gestura, minimized to the tray."""
    if getattr(sys, "frozen", False):                       # installed / PyInstaller build
        return subprocess.list2cmdline([sys.executable, "--minimized"])
    # From source: prefer pythonw.exe so no console window appears at sign-in.
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    return subprocess.list2cmdline(
        [str(pythonw if pythonw.exists() else exe), "-m", "gestura", "--minimized"])


class AutoStart:
    """Turns "start with Windows" on or off."""

    def __init__(self, run_key: RunKey | None = None) -> None:
        if run_key is None and sys.platform == "win32":
            run_key = WindowsRunKey()
        self._key = run_key

    @property
    def supported(self) -> bool:
        return self._key is not None

    def is_enabled(self) -> bool:
        return self._key is not None and self._key.get(VALUE_NAME) is not None

    def apply(self, enabled: bool) -> bool:
        """Make the registry match ``enabled``. Returns ``False`` if that wasn't possible."""
        if self._key is None:
            return False
        try:
            if enabled:
                command = launch_command()
                if self._key.get(VALUE_NAME) != command:
                    self._key.set(VALUE_NAME, command)
                    _log.info("Start with Windows enabled: %s", command)
            elif self._key.get(VALUE_NAME) is not None:
                self._key.delete(VALUE_NAME)
                _log.info("Start with Windows disabled")
        except OSError:
            _log.exception("Couldn't update the Windows startup entry")
            return False
        return True
