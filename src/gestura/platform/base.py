"""Platform-independent OS control interface.

The action dispatcher talks only to this abstract :class:`OSAdapter`, never to Win32 directly, so
a Linux/macOS port is a matter of adding one subclass (ADR/ARCHITECTURE "OS Adapter" layer). All
cursor coordinates crossing this boundary are **normalized** ``[0, 1]`` across the virtual
desktop; each adapter maps them to physical pixels.

:class:`RecordingAdapter` is a real, side-effect-free implementation used for the headless demo,
dispatcher tests, and CI — it records intended actions instead of performing them.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum


class MouseButton(Enum):
    LEFT = "left"
    RIGHT = "right"
    MIDDLE = "middle"


class MediaAction(Enum):
    PLAY_PAUSE = "play_pause"
    NEXT = "next"
    PREVIOUS = "previous"
    STOP = "stop"


class WindowAction(Enum):
    MINIMIZE = "minimize"
    MAXIMIZE = "maximize"
    RESTORE = "restore"
    SNAP_LEFT = "snap_left"
    SNAP_RIGHT = "snap_right"
    CLOSE = "close"
    SWITCH = "switch"
    SHOW_DESKTOP = "show_desktop"


# --- Keyboard shortcuts -----------------------------------------------------------------------
#: Named keys every adapter's :meth:`OSAdapter.hotkey` must accept (lower-case). Single letters
#: ``a``-``z`` and digits ``0``-``9`` are accepted in addition to these.
SHORTCUT_KEYS: frozenset[str] = frozenset({
    "ctrl", "control", "alt", "shift", "win", "super", "meta", "cmd",
    "tab", "enter", "return", "esc", "escape", "space", "backspace", "delete", "del", "insert",
    "home", "end", "pageup", "pagedown", "left", "up", "right", "down", "printscreen", "prtscn",
    "volume_up", "volume_down", "volume_mute",
    "media_next", "media_prev", "media_stop", "media_play_pause",
    *(f"f{i}" for i in range(1, 13)),
})

_MAX_CHORD = 4  # modifiers + key; anything longer is almost certainly a typo


def parse_shortcut(text: str) -> list[str]:
    """Parse a human key chord such as ``"Ctrl + Shift + S"`` into ``["ctrl", "shift", "s"]``.

    Raises:
        ValueError: with a user-presentable message if any key is unknown, a key repeats, or the
            chord is empty/too long. Validating here (when the user types it) means a bad binding
            is rejected in the editor instead of failing silently each time the gesture fires.
    """
    keys = [part.strip().lower() for part in text.split("+")]
    if not text.strip() or any(not k for k in keys):
        raise ValueError("Type keys joined with '+', e.g. ctrl+shift+s")
    for key in keys:
        if key not in SHORTCUT_KEYS and not (len(key) == 1 and key.isascii() and key.isalnum()):
            raise ValueError(f"Unknown key '{key}'")
    if len(set(keys)) != len(keys):
        raise ValueError("A key is repeated")
    if len(keys) > _MAX_CHORD:
        raise ValueError(f"Use at most {_MAX_CHORD} keys")
    return keys


class OSAdapter(ABC):
    """Abstract OS control surface. Concrete adapters must implement every method."""

    @abstractmethod
    def screen_size(self) -> tuple[int, int]:
        """Return the virtual-desktop size in pixels ``(width, height)``."""

    @abstractmethod
    def move_cursor(self, x: float, y: float) -> None:
        """Move the pointer to a normalized ``[0, 1]`` position on the virtual desktop."""

    @abstractmethod
    def mouse_down(self, button: MouseButton = MouseButton.LEFT) -> None: ...

    @abstractmethod
    def mouse_up(self, button: MouseButton = MouseButton.LEFT) -> None: ...

    @abstractmethod
    def click(self, button: MouseButton = MouseButton.LEFT) -> None: ...

    @abstractmethod
    def double_click(self, button: MouseButton = MouseButton.LEFT) -> None: ...

    @abstractmethod
    def scroll(self, dy: float, dx: float = 0.0) -> None:
        """Scroll by wheel notches; positive ``dy`` scrolls up, positive ``dx`` scrolls right."""

    @abstractmethod
    def zoom(self, delta: float) -> None:
        """Zoom by ``delta`` steps (Ctrl + wheel); positive zooms in, negative zooms out."""

    @abstractmethod
    def adjust_volume(self, delta_percent: float) -> None:
        """Change master volume by a signed percentage of the full range."""

    @abstractmethod
    def set_mute(self, muted: bool) -> None: ...

    @abstractmethod
    def adjust_brightness(self, delta_percent: float) -> None: ...

    @abstractmethod
    def media(self, action: MediaAction) -> None: ...

    @abstractmethod
    def window(self, action: WindowAction) -> None: ...

    @abstractmethod
    def screenshot(self) -> str:
        """Capture the screen to a file and return its path."""

    @abstractmethod
    def hotkey(self, *keys: str) -> None:
        """Press a key chord, e.g. ``hotkey('ctrl', 'c')``. Modifiers first, then the main key."""

    def close(self) -> None:  # noqa: B027 - intentionally optional (not all adapters hold resources)
        """Release any held resources (COM handles, etc.). Optional override."""


@dataclass
class RecordedAction:
    name: str
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)

    def __repr__(self) -> str:  # concise, readable in test failures/logs
        parts = [repr(a) for a in self.args]
        parts += [f"{k}={v!r}" for k, v in self.kwargs.items()]
        return f"{self.name}({', '.join(parts)})"


class RecordingAdapter(OSAdapter):
    """A no-op adapter that records intended actions — for dry-run mode, tests, and CI."""

    def __init__(self, screen: tuple[int, int] = (1920, 1080)) -> None:
        self._screen = screen
        self.actions: list[RecordedAction] = []
        self.cursor: tuple[float, float] = (0.5, 0.5)
        self.buttons_down: set[MouseButton] = set()

    def _record(self, name: str, *args: object, **kwargs: object) -> None:
        self.actions.append(RecordedAction(name, args, dict(kwargs)))

    def names(self) -> list[str]:
        """Convenience for assertions: the ordered list of action names."""
        return [a.name for a in self.actions]

    # -- OSAdapter -----------------------------------------------------------------------------
    def screen_size(self) -> tuple[int, int]:
        return self._screen

    def move_cursor(self, x: float, y: float) -> None:
        self.cursor = (x, y)
        self._record("move_cursor", x, y)

    def mouse_down(self, button: MouseButton = MouseButton.LEFT) -> None:
        self.buttons_down.add(button)
        self._record("mouse_down", button)

    def mouse_up(self, button: MouseButton = MouseButton.LEFT) -> None:
        self.buttons_down.discard(button)
        self._record("mouse_up", button)

    def click(self, button: MouseButton = MouseButton.LEFT) -> None:
        self._record("click", button)

    def double_click(self, button: MouseButton = MouseButton.LEFT) -> None:
        self._record("double_click", button)

    def scroll(self, dy: float, dx: float = 0.0) -> None:
        self._record("scroll", dy, dx)

    def zoom(self, delta: float) -> None:
        self._record("zoom", delta)

    def adjust_volume(self, delta_percent: float) -> None:
        self._record("adjust_volume", delta_percent)

    def set_mute(self, muted: bool) -> None:
        self._record("set_mute", muted)

    def adjust_brightness(self, delta_percent: float) -> None:
        self._record("adjust_brightness", delta_percent)

    def media(self, action: MediaAction) -> None:
        self._record("media", action)

    def window(self, action: WindowAction) -> None:
        self._record("window", action)

    def screenshot(self) -> str:
        self._record("screenshot")
        return "<recorded>"

    def hotkey(self, *keys: str) -> None:
        self._record("hotkey", *keys)
