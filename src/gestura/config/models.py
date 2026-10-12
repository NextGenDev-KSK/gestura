"""Typed, validated configuration models (ADR-0007).

The whole application is configured by an :class:`AppSettings` tree. Pydantic gives us
validation (e.g. confidences must be in ``[0, 1]``), sane defaults, and lossless JSON
round-tripping for the visual gesture editor. Nothing here imports from higher layers, so action
ids are kept as plain strings and validated against the action registry at dispatch time.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

#: Bumped whenever the on-disk schema changes in a way that needs migration.
#: v2: two-hand tracking by default, new default gesture vocabulary (see config/store.py).
SCHEMA_VERSION = 2


class _Model(BaseModel):
    # ``ignore`` (not ``forbid``) so a config written by a newer version still loads in an older
    # one; unknown keys are dropped rather than raising.
    model_config = ConfigDict(extra="ignore", validate_assignment=True)


class Theme(str, Enum):
    SYSTEM = "system"
    DARK = "dark"
    LIGHT = "light"


class CameraConfig(_Model):
    """Webcam capture parameters."""

    device_index: int = Field(0, ge=0, description="OpenCV camera index")
    # 640x480 is the tracking sweet spot: MediaPipe accuracy is unaffected, inference is fast,
    # and most webcams only sustain high frame-rates below 720p (see docs/PERFORMANCE.md).
    width: int = Field(640, ge=320, le=3840)
    height: int = Field(480, ge=240, le=2160)
    target_fps: int = Field(60, ge=15, le=240)
    mirror: bool = Field(True, description="Horizontally flip to a natural 'selfie' view")


class TrackingConfig(_Model):
    """MediaPipe HandLandmarker parameters."""

    # Two hands are tracked by default so the two-hand pinch-to-zoom gesture works out of the box.
    # Set to 1 for a small performance gain if you never use two-hand gestures.
    max_hands: int = Field(2, ge=1, le=2)
    min_detection_confidence: float = Field(0.5, ge=0.0, le=1.0)
    min_presence_confidence: float = Field(0.5, ge=0.0, le=1.0)
    min_tracking_confidence: float = Field(0.5, ge=0.0, le=1.0)
    use_gpu: bool = Field(False, description="Use the GPU delegate if available (ADR-0002)")


class CursorConfig(_Model):
    """Continuous pointer-control behaviour."""

    enabled: bool = True
    # 1€ filter tuning (ADR-0006).
    smoothing_min_cutoff: float = Field(1.2, gt=0.0, description="Lower = steadier when slow")
    smoothing_beta: float = Field(0.03, ge=0.0, description="Higher = less lag when fast")
    # The camera sub-rectangle mapped onto the whole screen. A margin means you never have to
    # reach the physical edge of the frame to hit a screen edge.
    region_margin_x: float = Field(0.14, ge=0.0, le=0.4)
    region_margin_y: float = Field(0.14, ge=0.0, le=0.4)
    # Movements smaller than this (in normalized frame units) are ignored to kill micro-jitter.
    dead_zone: float = Field(0.004, ge=0.0, le=0.1)


class GestureThresholds(_Model):
    """Tunable thresholds shared by the rule-based recognizers.

    Distances are in *palm-width units* (scale-invariant) unless noted; times are seconds.
    """

    pinch_on: float = Field(0.45, gt=0.0, description="Pinch closes below this tip distance")
    pinch_off: float = Field(0.65, gt=0.0, description="Pinch opens above this (hysteresis)")
    min_confidence: float = Field(0.6, ge=0.0, le=1.0, description="Reject hands below this score")
    stability_time: float = Field(0.06, ge=0.0, description="Pose must hold this long to accept")
    default_cooldown: float = Field(0.4, ge=0.0, description="Min seconds between discrete fires")


class GestureBinding(_Model):
    """Maps a recognised gesture to an action. Editable in the UI, no code required."""

    gesture: str = Field(description="Recogniser id, e.g. 'pinch', 'victory', or a custom name")
    action: str = Field(description="Action id resolved by the action registry at runtime")
    enabled: bool = True
    cooldown: float | None = Field(
        None, ge=0.0, description="Per-binding override of the default cooldown (seconds)"
    )
    params: dict[str, float] = Field(
        default_factory=dict, description="Action parameters, e.g. {'amount': 3} scroll steps"
    )
    shortcut: list[str] = Field(
        default_factory=list,
        description="Key chord for the 'run_shortcut' action, e.g. ['ctrl', 'c'] or ['alt', 'f4']",
    )


class CustomGesture(_Model):
    """A user-recorded gesture classified by the ONNX model (ADR-0003)."""

    name: str
    samples: int = Field(0, ge=0, description="Number of recorded example frames")
    model_label: int = Field(-1, description="Class index in the trained classifier, -1 if unbuilt")


class Profile(_Model):
    """A complete, named configuration the user can switch between."""

    name: str = "Default"
    camera: CameraConfig = Field(default_factory=CameraConfig)
    tracking: TrackingConfig = Field(default_factory=TrackingConfig)
    cursor: CursorConfig = Field(default_factory=CursorConfig)
    thresholds: GestureThresholds = Field(default_factory=GestureThresholds)
    # Deep copies: the gesture editor mutates bindings in place, which must never reach the shared
    # module-level DEFAULT_BINDINGS (that would also corrupt "reset to defaults").
    bindings: list[GestureBinding] = Field(default_factory=lambda: default_bindings())


class UiConfig(_Model):
    theme: Theme = Theme.SYSTEM
    show_overlay: bool = True
    show_camera_preview: bool = True
    launch_on_startup: bool = False
    start_minimized: bool = False


class AppSettings(_Model):
    """Root settings tree persisted to disk."""

    schema_version: int = SCHEMA_VERSION
    paused: bool = Field(False, description="Global kill-switch: engine runs but injects nothing")
    active_profile: str = "Default"
    profiles: dict[str, Profile] = Field(default_factory=lambda: {"Default": Profile()})
    custom_gestures: list[CustomGesture] = Field(default_factory=list)
    ui: UiConfig = Field(default_factory=UiConfig)

    def profile(self) -> Profile:
        """Return the active profile, falling back to any profile if the name is stale."""
        if self.active_profile in self.profiles:
            return self.profiles[self.active_profile]
        # Self-heal a dangling active_profile pointer rather than raising.
        if self.profiles:
            first = next(iter(self.profiles))
            self.active_profile = first
            return self.profiles[first]
        default = Profile()
        self.profiles["Default"] = default
        self.active_profile = "Default"
        return default


# --- Built-in default gesture map --------------------------------------------------------------
# The out-of-the-box gesture vocabulary. Cursor motion is continuous and handled by CursorConfig;
# these are the discrete/modal actions. Names correspond to recognizers in gestura.engine.
DEFAULT_BINDINGS: tuple[GestureBinding, ...] = (
    # Contact (pinch) gestures — distinguished by which finger meets the thumb.
    GestureBinding(gesture="pinch", action="left_click"),          # index + thumb
    GestureBinding(gesture="middle_pinch", action="right_click"),  # middle + thumb
    GestureBinding(gesture="pinky_pinch", action="middle_click"),  # pinky + thumb
    # Continuous modes.
    GestureBinding(gesture="fist", action="drag"),                 # hold to drag, release to drop
    GestureBinding(gesture="two_finger_scroll", action="scroll"),  # victory + vertical move
    GestureBinding(gesture="zoom", action="zoom"),                 # two-hand pinch, spread apart
    # Directional thumb (fist + thumb pointing) — cardinal directions only.
    GestureBinding(gesture="thumb_up", action="volume_up", params={"amount": 2.0}),
    GestureBinding(gesture="thumb_down", action="volume_down", params={"amount": 2.0}),
    GestureBinding(gesture="thumb_left", action="media_prev"),
    GestureBinding(gesture="thumb_right", action="media_next"),
    # One-shot shape poses — each a distinct extended-finger pattern.
    GestureBinding(gesture="three_fingers", action="screenshot"),      # index+middle+ring
    GestureBinding(gesture="rock", action="switch_window"),            # index+pinky ("horns")
    GestureBinding(gesture="pinky", action="media_play_pause"),        # pinky only
)


def default_bindings() -> list[GestureBinding]:
    """A fresh, independently-editable copy of the built-in gesture map."""
    return [b.model_copy(deep=True) for b in DEFAULT_BINDINGS]
