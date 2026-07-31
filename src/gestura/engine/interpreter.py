"""Temporal gesture interpreter — the reliability core of Gestura.

A single-frame classifier is never trustworthy on its own: it flickers, and small hand wobbles
produce phantom triggers. This state machine turns the noisy per-frame pose/feature stream into a
small set of dependable :class:`GestureEvent`\\s using four techniques the requirements call out:

* **Hysteresis** on pinch distances (close at one threshold, release at a looser one) so a hand
  hovering near the boundary can't chatter clicks.
* **Stability gating** — a shape (fist, victory, open palm) must persist for a short time before
  it's accepted, killing momentary false positives.
* **Cooldowns** so a sustained gesture can't machine-gun an action.
* **Exclusive modes** — while dragging or scrolling, unrelated triggers are suppressed, and the
  "pinch to click" detector is gated to poses where a pinch is unambiguous (never during a fist).

On tracking loss any held mode is cleanly released (mouse button up, etc.) and cursor smoothing is
reset so the pointer doesn't leap when the hand is re-acquired.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

from ..config.models import Profile
from ..core.timing import Cooldown, StabilityGate
from ..core.types import FrameResult, GestureEvent, GesturePhase, HandObservation
from .cursor import CursorController
from .custom import CustomGestureClassifier
from .features import FeatureSet, extract
from .recognizers import Pose, classify_static_pose

# --- Tunables not (yet) surfaced in the settings UI -------------------------------------------
_SCROLL_GAIN = 22.0          # scroll "notches" per unit of normalized vertical hand travel
_SCROLL_EPSILON = 0.12       # ignore scroll deltas smaller than this (jitter floor)
_VOLUME_REPEAT = 0.10        # seconds between repeated volume nudges while a thumb pose is held
_PAUSE_HOLD = 0.8            # open palm must be held this long to toggle pause (avoid accidents)
_CLICK_COOLDOWN = 0.25       # min seconds between clicks (still allows a deliberate double-click)


class Mode(Enum):
    """Mutually-exclusive continuous interaction modes."""

    IDLE = auto()
    DRAG = auto()
    SCROLL = auto()


@dataclass
class InterpretationResult:
    """Everything the interpreter produced for one frame."""

    cursor: tuple[float, float] | None = None
    events: list[GestureEvent] = field(default_factory=list)
    pose: str = Pose.NONE
    features: FeatureSet | None = None
    tracking: bool = False


class GestureInterpreter:
    """Converts a stream of :class:`FrameResult`\\s into gesture events + a cursor target."""

    def __init__(self, profile: Profile,
                 custom: CustomGestureClassifier | None = None) -> None:
        self._profile = profile
        self._thr = profile.thresholds
        self.cursor = CursorController(profile.cursor)
        self._custom = custom

        self._mode = Mode.IDLE
        self._pinch_closed = False
        self._middle_closed = False
        self._scroll_ref_y = 0.0

        # Stability gates for shape-based gestures.
        self._fist_gate = StabilityGate(self._thr.stability_time)
        self._victory_gate = StabilityGate(self._thr.stability_time)
        self._pause_gate = StabilityGate(_PAUSE_HOLD)
        self._pause_latched = False

        # Custom-gesture state.
        self._custom_gate = StabilityGate(self._thr.stability_time * 2)
        self._custom_cd = Cooldown(self._thr.default_cooldown)
        self._custom_candidate: str | None = None
        self._custom_active: str | None = None

        # Cooldowns for discrete/repeating actions.
        self._click_cd = Cooldown(_CLICK_COOLDOWN)
        self._rclick_cd = Cooldown(_CLICK_COOLDOWN)
        self._volume_cd = Cooldown(_VOLUME_REPEAT)

    @property
    def mode(self) -> Mode:
        return self._mode

    # -- main entry point ----------------------------------------------------------------------
    def update(self, frame: FrameResult) -> InterpretationResult:
        """Process one tracked frame and return the resulting events + cursor target."""
        result = InterpretationResult()
        hand = frame.primary
        if hand is None or hand.score < self._thr.min_confidence:
            self._release_all(frame.timestamp, result)
            return result

        result.tracking = True
        f = extract(hand)
        result.features = f
        now = frame.timestamp

        # Cursor tracks every frame regardless of mode (so you can drag while moving).
        result.cursor = self.cursor.update(f.anchor, now)

        pose, conf = classify_static_pose(f)
        result.pose = pose
        ok = conf >= self._thr.min_confidence

        # 1) DRAG mode (fist) — highest priority, fully exclusive.
        if self._handle_drag(pose, ok, conf, result, now):
            return result

        # 2) SCROLL mode (victory) — exclusive while active.
        if self._handle_scroll(pose, ok, conf, f, result, now):
            return result

        # 3) Discrete/idle gestures.
        self._handle_pinch(f, conf, result, now)
        self._handle_middle_pinch(f, conf, result, now)
        self._handle_volume(pose, ok, conf, result, now)
        self._handle_pause(pose, ok, conf, result, now)
        self._handle_custom(hand, result, now)
        return result

    # -- drag ----------------------------------------------------------------------------------
    def _handle_drag(self, pose, ok, conf, result, now) -> bool:
        fist_stable = self._fist_gate.update(pose == Pose.FIST and ok, now)
        if fist_stable and self._mode is not Mode.DRAG:
            self._mode = Mode.DRAG
            result.events.append(
                GestureEvent("fist", GesturePhase.BEGAN, conf, position=result.cursor, timestamp=now)
            )
        elif not fist_stable and self._mode is Mode.DRAG:
            self._mode = Mode.IDLE
            result.events.append(
                GestureEvent("fist", GesturePhase.ENDED, conf, position=result.cursor, timestamp=now)
            )
        return self._mode is Mode.DRAG

    # -- scroll --------------------------------------------------------------------------------
    def _handle_scroll(self, pose, ok, conf, f, result, now) -> bool:
        scroll_active = self._victory_gate.update(pose == Pose.VICTORY and ok, now)
        if scroll_active:
            if self._mode is not Mode.SCROLL:
                self._mode = Mode.SCROLL
                self._scroll_ref_y = f.anchor[1]
                result.events.append(
                    GestureEvent("two_finger_scroll", GesturePhase.BEGAN, conf, timestamp=now)
                )
            else:
                # Upward hand movement (decreasing y) scrolls up (positive dy).
                dy = (self._scroll_ref_y - f.anchor[1]) * _SCROLL_GAIN
                self._scroll_ref_y = f.anchor[1]
                if abs(dy) >= _SCROLL_EPSILON:
                    result.events.append(
                        GestureEvent(
                            "two_finger_scroll", GesturePhase.UPDATED, conf,
                            payload={"dy": dy}, timestamp=now,
                        )
                    )
            return True
        if self._mode is Mode.SCROLL:
            self._mode = Mode.IDLE
            result.events.append(
                GestureEvent("two_finger_scroll", GesturePhase.ENDED, conf, timestamp=now)
            )
        return False

    # -- pinch / left click --------------------------------------------------------------------
    def _handle_pinch(self, f: FeatureSet, conf, result, now) -> None:
        # A genuine pinch keeps at least one of the other fingers out (never a fist).
        allowed = f.extended["middle"] or f.extended["ring"] or f.extended["pinky"]
        closed = self._hysteresis(
            self._pinch_closed, f.pinch_index_norm if allowed else 1.0
        )
        if closed and not self._pinch_closed and self._click_cd.try_fire(now):
            result.events.append(
                GestureEvent("pinch", GesturePhase.BEGAN, conf, position=result.cursor, timestamp=now)
            )
            result.events.append(
                GestureEvent("pinch", GesturePhase.ENDED, conf, position=result.cursor, timestamp=now)
            )
        self._pinch_closed = closed

    # -- middle pinch / right click ------------------------------------------------------------
    def _handle_middle_pinch(self, f: FeatureSet, conf, result, now) -> None:
        # Right-click pinch requires the index extended, distinguishing it from a fist/left pinch.
        allowed = f.extended["index"]
        closed = self._hysteresis(
            self._middle_closed, f.pinch_middle_norm if allowed else 1.0
        )
        if closed and not self._middle_closed and self._rclick_cd.try_fire(now):
            result.events.append(
                GestureEvent(
                    "middle_pinch", GesturePhase.BEGAN, conf, position=result.cursor, timestamp=now
                )
            )
            result.events.append(
                GestureEvent(
                    "middle_pinch", GesturePhase.ENDED, conf, position=result.cursor, timestamp=now
                )
            )
        self._middle_closed = closed

    # -- volume (thumb up/down) ----------------------------------------------------------------
    def _handle_volume(self, pose, ok, conf, result, now) -> None:
        if pose in (Pose.THUMB_UP, Pose.THUMB_DOWN) and ok:
            if self._volume_cd.try_fire(now):
                result.events.append(
                    GestureEvent(pose, GesturePhase.UPDATED, conf, timestamp=now)
                )

    # -- pause toggle (open palm hold) ---------------------------------------------------------
    def _handle_pause(self, pose, ok, conf, result, now) -> None:
        held = self._pause_gate.update(pose == Pose.OPEN_PALM and ok, now)
        if held and not self._pause_latched:
            self._pause_latched = True
            result.events.append(
                GestureEvent("open_palm_hold", GesturePhase.BEGAN, conf, timestamp=now)
            )
        elif not held:
            self._pause_latched = False

    # -- custom (user-trained) gestures --------------------------------------------------------
    def _handle_custom(self, hand: HandObservation, result: InterpretationResult,
                       now: float) -> None:
        if self._custom is None:
            return
        match = self._custom.classify(hand)
        name = match[0] if match else None

        if name is None:
            self._custom_gate.reset()
            self._custom_candidate = None
            self._custom_active = None
            return
        if name != self._custom_candidate:
            self._custom_candidate = name
            self._custom_gate.reset()

        stable = self._custom_gate.update(True, now)
        if stable and name != self._custom_active and self._custom_cd.try_fire(now):
            confidence = match[1] if match else 0.0
            result.events.append(GestureEvent(name, GesturePhase.BEGAN, confidence, timestamp=now))
            result.events.append(GestureEvent(name, GesturePhase.ENDED, confidence, timestamp=now))
            self._custom_active = name

    # -- helpers -------------------------------------------------------------------------------
    def _hysteresis(self, currently_closed: bool, distance: float) -> bool:
        """Inverted Schmitt trigger: closes below ``pinch_on``, opens above ``pinch_off``."""
        if currently_closed:
            return not (distance > self._thr.pinch_off)
        return distance < self._thr.pinch_on

    def _release_all(self, now: float, result: InterpretationResult) -> None:
        """Tracking lost: end any held mode, reset smoothing and all latches."""
        if self._mode is Mode.DRAG:
            result.events.append(GestureEvent("fist", GesturePhase.ENDED, 0.0, timestamp=now))
        elif self._mode is Mode.SCROLL:
            result.events.append(
                GestureEvent("two_finger_scroll", GesturePhase.ENDED, 0.0, timestamp=now)
            )
        self._mode = Mode.IDLE
        self._pinch_closed = False
        self._middle_closed = False
        self._pause_latched = False
        self._custom_candidate = None
        self._custom_active = None
        self._fist_gate.reset()
        self._victory_gate.reset()
        self._pause_gate.reset()
        self._custom_gate.reset()
        self.cursor.reset()

    def apply_profile(self, profile: Profile) -> None:
        """Hot-reload thresholds/cursor tuning from an edited profile."""
        self._profile = profile
        self._thr = profile.thresholds
        self.cursor.apply_config(profile.cursor)
