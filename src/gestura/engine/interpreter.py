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

import math
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
_ZOOM_GAIN = 12.0            # zoom "notches" per unit change in the two-hand separation
_ZOOM_EPSILON = 0.15         # ignore zoom deltas smaller than this (jitter floor)
_VOLUME_REPEAT = 0.10        # seconds between repeated volume nudges while a thumb pose is held
_CLICK_COOLDOWN = 0.25       # min seconds between clicks (still allows a deliberate double-click)

#: One-shot shape poses: each fires a single action when first held stably, and won't repeat until
#: the hand leaves the pose. Kept distinct from the continuous (drag/scroll) and repeating (volume)
#: gestures so nothing double-acts.
_ONESHOT_POSES = frozenset({
    Pose.THREE_FINGERS, Pose.PINKY, Pose.ROCK, Pose.THUMB_LEFT, Pose.THUMB_RIGHT,
})


class Mode(Enum):
    """Mutually-exclusive continuous interaction modes."""

    IDLE = auto()
    DRAG = auto()
    SCROLL = auto()
    ZOOM = auto()  # two hands, both pinched, moved together/apart


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
        self._pinky_closed = False
        self._scroll_ref_y = 0.0
        self._zoom_ref = 0.0

        # Stability gates for shape-based gestures.
        self._fist_gate = StabilityGate(self._thr.stability_time)
        self._victory_gate = StabilityGate(self._thr.stability_time)

        # One-shot discrete-pose state (three-fingers, rock, pinky, thumb left/right).
        self._discrete_gate = StabilityGate(self._thr.stability_time)
        self._discrete_cd = Cooldown(self._thr.default_cooldown)
        self._discrete_candidate: str | None = None
        self._discrete_active: str | None = None

        # Custom-gesture state.
        self._custom_gate = StabilityGate(self._thr.stability_time * 2)
        self._custom_cd = Cooldown(self._thr.default_cooldown)
        self._custom_candidate: str | None = None
        self._custom_active: str | None = None

        # Cooldowns for discrete/repeating actions.
        self._click_cd = Cooldown(_CLICK_COOLDOWN)
        self._rclick_cd = Cooldown(_CLICK_COOLDOWN)
        self._mclick_cd = Cooldown(_CLICK_COOLDOWN)
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
        now = frame.timestamp

        # Two-hand pinch-to-zoom pre-empts everything else. It's fully exclusive and, being a
        # *two-hand* gesture, can never be confused with any of the single-hand signs.
        if len(frame.hands) >= 2:
            if self._handle_zoom(frame, result, now):
                return result
        elif self._mode is Mode.ZOOM:
            self._end_zoom(result, now)

        f = extract(hand)
        result.features = f

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
        self._handle_pinky_pinch(f, conf, result, now)
        self._handle_volume(pose, ok, conf, result, now)
        self._handle_discrete(pose, ok, conf, result, now)
        self._handle_custom(hand, result, now)
        return result

    # -- drag ----------------------------------------------------------------------------------
    def _handle_drag(self, pose, ok, conf, result, now) -> bool:
        fist_stable = self._fist_gate.update(pose == Pose.FIST and ok, now)
        if fist_stable and self._mode is not Mode.DRAG:
            self._mode = Mode.DRAG
            result.events.append(GestureEvent(
                "fist", GesturePhase.BEGAN, conf, position=result.cursor, timestamp=now))
        elif not fist_stable and self._mode is Mode.DRAG:
            self._mode = Mode.IDLE
            result.events.append(GestureEvent(
                "fist", GesturePhase.ENDED, conf, position=result.cursor, timestamp=now))
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

    # -- zoom (two-hand pinch-spread) ----------------------------------------------------------
    def _handle_zoom(self, frame: FrameResult, result: InterpretationResult, now: float) -> bool:
        """Engage zoom when both hands are pinched; emit scale deltas as they move apart/together.

        Returns ``True`` while zoom is active (so the caller skips all single-hand handling).
        """
        h1, h2 = frame.hands[0], frame.hands[1]
        if h1.score < self._thr.min_confidence or h2.score < self._thr.min_confidence:
            if self._mode is Mode.ZOOM:
                self._end_zoom(result, now)
            return False

        f1, f2 = extract(h1), extract(h2)
        # Hysteresis: engage below pinch_on, stay engaged until clearly released above pinch_off.
        limit = self._thr.pinch_off if self._mode is Mode.ZOOM else self._thr.pinch_on
        both_pinched = f1.pinch_index_norm < limit and f2.pinch_index_norm < limit
        if not both_pinched:
            if self._mode is Mode.ZOOM:
                self._end_zoom(result, now)
            return False

        separation = math.hypot(f1.anchor[0] - f2.anchor[0], f1.anchor[1] - f2.anchor[1])
        conf = min(f1.score, f2.score)
        if self._mode is not Mode.ZOOM:
            self._mode = Mode.ZOOM
            self._zoom_ref = separation
            self.cursor.reset()  # avoid a pointer jump when we later return to one hand
            result.events.append(GestureEvent("zoom", GesturePhase.BEGAN, conf, timestamp=now))
        else:
            delta = (separation - self._zoom_ref) * _ZOOM_GAIN
            self._zoom_ref = separation
            if abs(delta) >= _ZOOM_EPSILON:
                result.events.append(GestureEvent(
                    "zoom", GesturePhase.UPDATED, conf, payload={"scale": delta}, timestamp=now))
        result.cursor = None  # don't move the pointer while zooming
        return True

    def _end_zoom(self, result: InterpretationResult, now: float) -> None:
        self._mode = Mode.IDLE
        result.events.append(GestureEvent("zoom", GesturePhase.ENDED, 0.0, timestamp=now))

    # -- pinch / left click --------------------------------------------------------------------
    def _handle_pinch(self, f: FeatureSet, conf, result, now) -> None:
        # A genuine pinch keeps at least one of the other fingers out (never a fist).
        allowed = f.extended["middle"] or f.extended["ring"] or f.extended["pinky"]
        closed = self._hysteresis(
            self._pinch_closed, f.pinch_index_norm if allowed else 1.0
        )
        if closed and not self._pinch_closed and self._click_cd.try_fire(now):
            result.events.append(GestureEvent(
                "pinch", GesturePhase.BEGAN, conf, position=result.cursor, timestamp=now))
            result.events.append(GestureEvent(
                "pinch", GesturePhase.ENDED, conf, position=result.cursor, timestamp=now))
        self._pinch_closed = closed

    # -- middle pinch / right click ------------------------------------------------------------
    def _handle_middle_pinch(self, f: FeatureSet, conf, result, now) -> None:
        # Right-click pinch needs the index extended (not a fist/left pinch) AND the middle to be
        # the finger actually touching the thumb — otherwise a pinky pinch could double-trigger.
        allowed = f.extended["index"] and f.pinch_middle_norm <= f.pinch_pinky_norm
        closed = self._hysteresis(
            self._middle_closed, f.pinch_middle_norm if allowed else 1.0
        )
        if closed and not self._middle_closed and self._rclick_cd.try_fire(now):
            result.events.append(GestureEvent(
                "middle_pinch", GesturePhase.BEGAN, conf, position=result.cursor, timestamp=now))
            result.events.append(GestureEvent(
                "middle_pinch", GesturePhase.ENDED, conf, position=result.cursor, timestamp=now))
        self._middle_closed = closed

    # -- pinky pinch / middle click ------------------------------------------------------------
    def _handle_pinky_pinch(self, f: FeatureSet, conf, result, now) -> None:
        # Mirror of the middle pinch: index extended, and the pinky must be the *closest* finger
        # to the thumb so it can never be confused with a middle pinch.
        allowed = f.extended["index"] and f.pinch_pinky_norm < f.pinch_middle_norm
        closed = self._hysteresis(
            self._pinky_closed, f.pinch_pinky_norm if allowed else 1.0
        )
        if closed and not self._pinky_closed and self._mclick_cd.try_fire(now):
            result.events.append(GestureEvent(
                "pinky_pinch", GesturePhase.BEGAN, conf, position=result.cursor, timestamp=now))
            result.events.append(GestureEvent(
                "pinky_pinch", GesturePhase.ENDED, conf, position=result.cursor, timestamp=now))
        self._pinky_closed = closed

    # -- volume (thumb up/down) ----------------------------------------------------------------
    def _handle_volume(self, pose, ok, conf, result, now) -> None:
        if pose in (Pose.THUMB_UP, Pose.THUMB_DOWN) and ok and self._volume_cd.try_fire(now):
            result.events.append(GestureEvent(pose, GesturePhase.UPDATED, conf, timestamp=now))

    # -- one-shot discrete poses (screenshot, media, window, …) --------------------------------
    def _handle_discrete(self, pose, ok, conf, result, now) -> None:
        """Fire a one-shot event when a discrete shape pose is first held stably.

        A single stability gate + "active pose" latch means each pose fires exactly once and only
        re-arms after the hand leaves it — so holding, say, the rock sign can't spam Alt-Tab.
        """
        candidate = pose if (pose in _ONESHOT_POSES and ok) else None
        if candidate is None:
            self._discrete_gate.reset()
            self._discrete_candidate = None
            self._discrete_active = None
            return
        if candidate != self._discrete_candidate:
            self._discrete_candidate = candidate
            self._discrete_gate.reset()
        stable = self._discrete_gate.update(True, now)
        if stable and candidate != self._discrete_active and self._discrete_cd.try_fire(now):
            result.events.append(GestureEvent(candidate, GesturePhase.BEGAN, conf, timestamp=now))
            result.events.append(GestureEvent(candidate, GesturePhase.ENDED, conf, timestamp=now))
            self._discrete_active = candidate

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
        elif self._mode is Mode.ZOOM:
            result.events.append(GestureEvent("zoom", GesturePhase.ENDED, 0.0, timestamp=now))
        self._mode = Mode.IDLE
        self._pinch_closed = False
        self._middle_closed = False
        self._pinky_closed = False
        self._discrete_candidate = None
        self._discrete_active = None
        self._custom_candidate = None
        self._custom_active = None
        self._fist_gate.reset()
        self._victory_gate.reset()
        self._discrete_gate.reset()
        self._custom_gate.reset()
        self.cursor.reset()

    def apply_profile(self, profile: Profile) -> None:
        """Hot-reload thresholds/cursor tuning from an edited profile."""
        self._profile = profile
        self._thr = profile.thresholds
        self.cursor.apply_config(profile.cursor)

    def set_custom(self, custom: CustomGestureClassifier | None) -> None:
        """Swap in a new custom-gesture classifier (after the user records or deletes one).

        Latches are reset so a deleted gesture can't stay "active". Not thread-safe on its own:
        call it from the thread that runs :meth:`update`, or under the same lock (the pipeline
        does the latter).
        """
        self._custom = custom
        self._custom_candidate = None
        self._custom_active = None
        self._custom_gate.reset()
