"""Tests for the QML bridge's pure helpers (no event loop / display needed)."""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("PySide6")

from gestura.app.controller import AppController


def test_to_qimage_preserves_size_and_converts_bgr_to_rgb() -> None:
    bgr = np.zeros((48, 64, 3), dtype=np.uint8)
    bgr[:, :, 2] = 200  # red channel in BGR
    img = AppController._to_qimage(bgr)
    assert (img.width(), img.height()) == (64, 48)
    px = img.pixelColor(10, 10)
    assert px.red() == 200 and px.green() == 0 and px.blue() == 0


def test_landmark_points_returns_21_for_a_hand(hand_factory, frame_factory) -> None:
    frame = frame_factory(hand_factory("open"), timestamp=0.0)
    pts = AppController._landmark_points(frame)
    assert len(pts) == 21
    # Points are normalized [0, 1].
    assert all(0.0 <= p.x() <= 1.0 and 0.0 <= p.y() <= 1.0 for p in pts)


def test_landmark_points_empty_without_hand(frame_factory) -> None:
    assert AppController._landmark_points(frame_factory(None, timestamp=0.0)) == []


def test_controller_settings_roundtrip_and_validation(tmp_path) -> None:
    from gestura.config.store import SettingsStore

    store = SettingsStore(path=tmp_path / "settings.json")
    settings = store.load()
    ctrl = AppController(settings, store, dry_run=True)
    try:
        # Numeric round-trip through the dotted-path bridge.
        ctrl.setNumber("profile.cursor.smoothing_beta", 0.25)
        assert ctrl.getSetting("profile.cursor.smoothing_beta") == pytest.approx(0.25)

        # Change is persisted to disk.
        reloaded = SettingsStore(path=tmp_path / "settings.json").load()
        assert reloaded.profile().cursor.smoothing_beta == pytest.approx(0.25)

        # Boolean round-trip.
        ctrl.setBool("ui.show_overlay", False)
        assert ctrl.getSetting("ui.show_overlay") is False

        # Out-of-range write is rejected, leaving the value valid.
        before = ctrl.getSetting("profile.thresholds.min_confidence")
        ctrl.setNumber("profile.thresholds.min_confidence", 5.0)  # invalid (> 1)
        assert ctrl.getSetting("profile.thresholds.min_confidence") == before
    finally:
        ctrl.stop()


def test_landmark_points_cover_every_tracked_hand(hand_factory, multi_frame_factory, shift):
    frame = multi_frame_factory([hand_factory("pinch"), shift(hand_factory("pinch"), dx=0.3)],
                                timestamp=0.0)
    assert len(AppController._landmark_points(frame)) == 42  # both hands drawn for zoom


# --- Gesture editor / trainer bridge ------------------------------------------------------------
@pytest.fixture
def editor(tmp_path, monkeypatch):
    """A dry-run controller with throwaway settings and custom-gesture storage."""
    from gestura.config.store import SettingsStore

    monkeypatch.setattr("gestura.engine.pipeline.data_dir", lambda: tmp_path)
    store = SettingsStore(path=tmp_path / "settings.json")
    ctrl = AppController(store.load(), store, dry_run=True)
    yield ctrl, store
    ctrl.stop()


def _row(ctrl, gesture):
    return next(r for r in ctrl.gestureRows if r["id"] == gesture)


def test_gesture_rows_list_every_builtin_with_compatible_choices(editor) -> None:
    from gestura.engine.catalog import BUILTIN_GESTURES

    ctrl, _ = editor
    rows = ctrl.gestureRows
    assert [r["id"] for r in rows] == [g.id for g in BUILTIN_GESTURES]
    pinch = _row(ctrl, "pinch")
    assert pinch["action"] == "left_click" and pinch["enabled"]
    assert pinch["choices"][pinch["choiceIndex"]]["id"] == "left_click"
    assert pinch["choices"][0]["id"] == ""  # "Not bound"
    thumb = {c["id"] for c in _row(ctrl, "thumb_up")["choices"]}
    assert "screenshot" not in thumb and "volume_up" in thumb


def test_rebinding_persists_and_reaches_the_dispatcher(editor) -> None:
    from gestura.config.store import SettingsStore
    from gestura.core.types import GestureEvent, GesturePhase
    from gestura.engine.interpreter import InterpretationResult

    ctrl, store = editor
    assert ctrl.setGestureAction("rock", "screenshot")
    assert _row(ctrl, "rock")["action"] == "screenshot"
    saved = SettingsStore(path=store.path).load().profile().bindings
    assert {b.gesture: b.action for b in saved}["rock"] == "screenshot"  # persisted...

    # ...and applied live: the engine's dispatcher now screenshots on rock.
    adapter = ctrl._adapter
    ctrl._pipeline._dispatcher.dispatch(InterpretationResult(
        events=[GestureEvent("rock", GesturePhase.BEGAN, 0.9)]))
    assert adapter.names()[-1] == "screenshot"


def test_incompatible_bindings_are_rejected(editor) -> None:
    ctrl, _ = editor
    assert not ctrl.setGestureAction("thumb_up", "screenshot")  # thumb_up never BEGINs
    assert not ctrl.setGestureAction("pinch", "drag")           # a tap can't hold a drag
    assert not ctrl.setGestureAction("pinch", "nonexistent")
    assert _row(ctrl, "thumb_up")["action"] == "volume_up"


def test_changing_action_resets_action_specific_params(editor) -> None:
    ctrl, _ = editor
    ctrl.setGestureAction("thumb_up", "brightness_up")
    binding = ctrl._binding_for("thumb_up")
    assert binding.params == {}  # volume's "amount: 2" must not leak into brightness


def test_unbind_disable_and_reset(editor) -> None:
    ctrl, _ = editor
    assert ctrl.setGestureAction("pinky", "")
    assert _row(ctrl, "pinky")["action"] == ""
    assert sum(1 for b in ctrl._settings.profile().bindings if b.gesture == "pinky") == 0

    ctrl.setGestureEnabled("pinch", False)
    assert _row(ctrl, "pinch")["enabled"] is False
    assert "pinch" not in ctrl._pipeline._dispatcher._by_gesture

    ctrl.resetGestures()
    assert _row(ctrl, "pinky")["action"] == "media_play_pause"
    assert _row(ctrl, "pinch")["enabled"] is True


def test_shortcut_binding_validates_keys(editor) -> None:
    ctrl, _ = editor
    assert ctrl.setGestureShortcut("rock", "ctrl+c") == ""  # binding exists (switch_window)
    assert ctrl.setGestureAction("rock", "run_shortcut")
    assert _row(ctrl, "rock")["shortcut"] == "ctrl+c"      # kept across the action change
    assert ctrl.setGestureShortcut("rock", "ctrl+banana") == "Unknown key 'banana'"
    assert _row(ctrl, "rock")["shortcut"] == "ctrl+c"      # bad input leaves it unchanged
    assert ctrl.setGestureShortcut("rock", "Alt + F4") == ""
    assert _row(ctrl, "rock")["shortcut"] == "alt+f4"
    ctrl.setGestureAction("pinky", "")
    assert ctrl.setGestureShortcut("pinky", "ctrl+c") != ""  # unbound gesture


def test_custom_gestures_appear_and_delete_with_their_binding(editor, hand_factory,
                                                              frame_factory) -> None:
    ctrl, _ = editor
    pipe = ctrl._pipeline
    pipe.start_recording("peace_sign", samples=2)
    for i in range(2):
        pipe._feed_recording(frame_factory(hand_factory("victory"), timestamp=i * 0.03), now=0.0)

    row = _row(ctrl, "peace_sign")
    assert row["custom"] and row["recorded"] and row["action"] == ""
    assert ctrl.setGestureAction("peace_sign", "screenshot")
    assert not ctrl.setGestureAction("peace_sign", "volume_up")  # custom gestures are taps

    ctrl.deleteCustomGesture("peace_sign")
    assert all(r["id"] != "peace_sign" for r in ctrl.gestureRows)
    assert all(b.gesture != "peace_sign" for b in ctrl._settings.profile().bindings)


def test_orphan_bindings_are_listed_so_they_can_be_removed(editor) -> None:
    from gestura.config.models import GestureBinding

    ctrl, _ = editor
    ctrl._settings.profile().bindings.append(GestureBinding(gesture="ghost", action="screenshot"))
    row = _row(ctrl, "ghost")
    assert row["custom"] and not row["recorded"]
    ctrl.setGestureAction("ghost", "")
    assert all(r["id"] != "ghost" for r in ctrl.gestureRows)


@pytest.mark.parametrize(("text", "expected"), [
    ("Peace Sign", "peace_sign"), ("  wave  ", "wave"), ("ok-2", "ok-2"),
])
def test_gesture_names_are_normalized(text, expected) -> None:
    from gestura.app.controller import normalize_gesture_name

    assert normalize_gesture_name(text) == expected


@pytest.mark.parametrize("text", ["", "   ", "pinch", "Thumb Up", "a/b", "x" * 40])
def test_bad_gesture_names_are_rejected(text) -> None:
    from gestura.app.controller import normalize_gesture_name

    with pytest.raises(ValueError):
        normalize_gesture_name(text)


def test_recording_needs_a_streaming_camera(editor) -> None:
    ctrl, _ = editor
    assert ctrl.checkRecording("") == "Give the gesture a name first"
    assert ctrl.startRecording("wave") == "The camera isn't streaming yet"
    assert not ctrl._pipeline.recording_status.active
    ctrl._camera_status = "streaming"
    assert ctrl.startRecording("wave") == ""
    assert ctrl._pipeline.recording_status.active
