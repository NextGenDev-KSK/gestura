"""Tests for configuration models and the resilient settings store."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from gestura.config import AppSettings, GestureThresholds, Profile, SettingsStore


def test_defaults_are_valid_and_have_bindings() -> None:
    settings = AppSettings()
    assert settings.schema_version >= 1
    profile = settings.profile()
    assert profile.name == "Default"
    assert len(profile.bindings) > 0
    # A pinch should map to a left click out of the box.
    assert any(b.gesture == "pinch" and b.action == "left_click" for b in profile.bindings)


def test_threshold_validation_rejects_out_of_range() -> None:
    with pytest.raises(ValidationError):
        GestureThresholds(min_confidence=1.5)
    with pytest.raises(ValidationError):
        GestureThresholds(pinch_on=0.0)  # must be > 0


def test_profile_self_heals_dangling_active_pointer() -> None:
    settings = AppSettings(active_profile="Ghost", profiles={"Real": Profile(name="Real")})
    resolved = settings.profile()
    assert resolved.name == "Real"
    assert settings.active_profile == "Real"


def test_store_roundtrip(tmp_path) -> None:
    store = SettingsStore(path=tmp_path / "settings.json")
    settings = store.load()  # creates defaults
    settings.paused = True
    settings.profile().cursor.smoothing_beta = 0.5
    store.save(settings)

    reloaded = SettingsStore(path=tmp_path / "settings.json").load()
    assert reloaded.paused is True
    assert reloaded.profile().cursor.smoothing_beta == pytest.approx(0.5)


def test_store_creates_file_on_first_load(tmp_path) -> None:
    path = tmp_path / "settings.json"
    assert not path.exists()
    SettingsStore(path=path).load()
    assert path.exists()
    # Valid JSON with a schema version.
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "schema_version" in data


def test_store_recovers_from_corrupt_file(tmp_path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{ this is not valid json ", encoding="utf-8")
    settings = SettingsStore(path=path).load()
    # Falls back to defaults instead of raising...
    assert isinstance(settings, AppSettings)
    # ...and preserves the bad file for debugging.
    assert path.with_suffix(".json.corrupt").exists()


def test_store_recovers_from_schema_violation(tmp_path) -> None:
    path = tmp_path / "settings.json"
    # Valid JSON, invalid schema (confidence out of range).
    bad = {"schema_version": 1, "profiles": {"Default": {"tracking": {"use_gpu": "not-a-bool"}}}}
    path.write_text(json.dumps(bad), encoding="utf-8")
    settings = SettingsStore(path=path).load()
    assert isinstance(settings, AppSettings)
    assert path.with_suffix(".json.corrupt").exists()


def test_save_is_atomic_no_temp_left_behind(tmp_path) -> None:
    store = SettingsStore(path=tmp_path / "settings.json")
    store.save(AppSettings())
    leftovers = list(tmp_path.glob(".settings-*.tmp"))
    assert leftovers == []


def _v1_settings(**tracking) -> dict:
    """A settings file as v1 builds wrote it: old default bindings, one tracked hand."""
    return {
        "schema_version": 1,
        "active_profile": "Default",
        "profiles": {"Default": {
            "tracking": {"max_hands": 1, **tracking},
            "cursor": {"smoothing_min_cutoff": 4.4},
            "bindings": [
                {"gesture": "pinch", "action": "left_click"},
                {"gesture": "fist", "action": "drag"},
                # The user had re-bound thumb-up; that choice must survive the migration.
                {"gesture": "thumb_up", "action": "brightness_up"},
                {"gesture": "open_palm_hold", "action": "pause_toggle"},  # retired gesture
            ],
        }},
    }


def test_v1_settings_migrate_to_the_current_gesture_set(tmp_path) -> None:
    from gestura.config.models import DEFAULT_BINDINGS, SCHEMA_VERSION

    path = tmp_path / "settings.json"
    path.write_text(json.dumps(_v1_settings()), encoding="utf-8")
    profile = SettingsStore(path=path).load().profile()

    by_gesture = {b.gesture: b.action for b in profile.bindings}
    assert "open_palm_hold" not in by_gesture                 # retired binding dropped
    assert by_gesture["thumb_up"] == "brightness_up"          # user's edit kept
    assert by_gesture["zoom"] == "zoom"                       # new defaults added
    assert by_gesture["pinky_pinch"] == "middle_click"
    assert set(by_gesture) == {b.gesture for b in DEFAULT_BINDINGS}
    assert len(profile.bindings) == len(by_gesture)           # no duplicates
    assert profile.tracking.max_hands == 2                    # two-hand zoom needs it
    assert profile.cursor.smoothing_min_cutoff == pytest.approx(4.4)  # tuning untouched

    # The upgrade is persisted, so it runs once.
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == SCHEMA_VERSION


def test_migration_is_not_reapplied_to_current_files(tmp_path) -> None:
    store = SettingsStore(path=tmp_path / "settings.json")
    settings = store.load()
    settings.profile().tracking.max_hands = 1  # a deliberate choice in a v2 file
    settings.profile().bindings = [b for b in settings.profile().bindings if b.gesture != "rock"]
    store.save(settings)

    reloaded = SettingsStore(path=tmp_path / "settings.json").load().profile()
    assert reloaded.tracking.max_hands == 1
    assert all(b.gesture != "rock" for b in reloaded.bindings)


def test_default_bindings_are_independent_copies() -> None:
    from gestura.config.models import DEFAULT_BINDINGS

    a, b = Profile(), Profile()
    a.bindings[0].action = "screenshot"
    assert b.bindings[0].action != "screenshot"
    assert DEFAULT_BINDINGS[0].action != "screenshot"
