"""Persistence for :class:`AppSettings`: atomic writes, schema migration, corruption recovery.

Design goals:
* **Never crash the app** because of a bad config file. A corrupt or incompatible file is backed
  up and replaced with defaults instead of raising.
* **Atomic saves** — write to a temp file and ``os.replace`` so a crash mid-write can't truncate
  the real config.
* **Forward migration** — old on-disk schemas are upgraded through registered steps.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ..util.logging import get_logger
from ..util.paths import config_dir
from .models import DEFAULT_BINDINGS, SCHEMA_VERSION, AppSettings

_log = get_logger("gestura.config")

CONFIG_FILENAME = "settings.json"

#: Gesture ids that v1 builds emitted but the engine no longer produces; a binding to one of these
#: can never fire again, so the v1 -> v2 migration drops it.
_RETIRED_V1_GESTURES = frozenset({"open_palm_hold"})


def _migrate_v1_to_v2(raw: dict[str, Any]) -> dict[str, Any]:
    """v1 -> v2: adopt the new gesture vocabulary and two-hand tracking without losing edits.

    v1 installs saved the *old* default bindings and ``max_hands = 1``, so new gestures (pinky
    pinch, the thumb directions, the one-shot signs, two-hand zoom) never reached them. For every
    profile this:

    * drops bindings to retired gestures (``open_palm_hold``);
    * adds each current default binding whose gesture isn't bound yet — existing bindings,
      including ones the user changed, are kept exactly as they are;
    * raises ``tracking.max_hands`` from the old default of 1 to 2 (it wasn't user-editable in
      v1), which the two-hand zoom gesture needs.
    """
    for profile in (raw.get("profiles") or {}).values():
        if not isinstance(profile, dict):
            continue
        bindings = [
            b for b in profile.get("bindings", [])
            if not (isinstance(b, dict) and b.get("gesture") in _RETIRED_V1_GESTURES)
        ]
        bound = {b.get("gesture") for b in bindings if isinstance(b, dict)}
        bindings += [
            d.model_dump(mode="json") for d in DEFAULT_BINDINGS if d.gesture not in bound
        ]
        profile["bindings"] = bindings

        tracking = profile.get("tracking")
        if isinstance(tracking, dict) and tracking.get("max_hands", 1) == 1:
            tracking["max_hands"] = 2
    return raw


# Ordered migrations: {from_version: fn(raw_dict) -> raw_dict at from_version+1}.
# Add an entry here whenever SCHEMA_VERSION is bumped.
_MIGRATIONS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {1: _migrate_v1_to_v2}


def _migrate(raw: dict[str, Any]) -> dict[str, Any]:
    """Upgrade a raw settings dict to the current schema, applying steps in order."""
    version = int(raw.get("schema_version", SCHEMA_VERSION))
    while version < SCHEMA_VERSION:
        step = _MIGRATIONS.get(version)
        if step is None:
            _log.warning("No migration from schema v%s; using defaults for missing fields", version)
            break
        _log.info("Migrating settings schema v%s -> v%s", version, version + 1)
        raw = step(raw)
        version += 1
        raw["schema_version"] = version
    return raw


class SettingsStore:
    """Loads and saves the settings tree at a fixed path (defaults to the user config dir)."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (config_dir() / CONFIG_FILENAME)

    # -- load ----------------------------------------------------------------------------------
    def load(self) -> AppSettings:
        """Return settings from disk, or freshly-defaulted settings if absent/corrupt.

        On a parse/validation error the offending file is preserved as ``<name>.corrupt`` for
        debugging and defaults are returned, so the app always starts.
        """
        if not self.path.exists():
            _log.info("No settings file at %s; creating defaults", self.path)
            settings = AppSettings()
            self.save(settings)
            return settings

        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            self._quarantine(reason=f"unreadable/invalid JSON: {exc}")
            return AppSettings()

        try:
            on_disk_version = int(raw.get("schema_version", SCHEMA_VERSION))
            raw = _migrate(raw)
            settings = AppSettings.model_validate(raw)
        except (ValidationError, TypeError, ValueError) as exc:
            count = exc.error_count() if isinstance(exc, ValidationError) else 1
            self._quarantine(reason=f"schema validation failed: {count} error(s)")
            return AppSettings()

        if on_disk_version < SCHEMA_VERSION:
            # Persist the upgrade so it runs exactly once (and the file matches what's in memory).
            try:
                self.save(settings)
            except OSError:  # pragma: no cover - read-only config dir; keep running in memory
                _log.exception("Could not persist migrated settings")
        return settings

    # -- save ----------------------------------------------------------------------------------
    def save(self, settings: AppSettings) -> None:
        """Atomically persist settings as pretty-printed JSON."""
        settings.schema_version = SCHEMA_VERSION
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = settings.model_dump(mode="json")
        text = json.dumps(payload, indent=2, ensure_ascii=False)

        # Write to a temp file in the same directory, then atomically replace.
        fd, tmp_name = tempfile.mkstemp(dir=self.path.parent, prefix=".settings-", suffix=".tmp")
        tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(text)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)
        except OSError:
            tmp.unlink(missing_ok=True)
            raise
        _log.debug("Saved settings to %s", self.path)

    # -- helpers -------------------------------------------------------------------------------
    def _quarantine(self, *, reason: str) -> None:
        backup = self.path.with_suffix(self.path.suffix + ".corrupt")
        _log.error("Settings file rejected (%s); backing up to %s and using defaults",
                   reason, backup)
        try:
            shutil.copy2(self.path, backup)
        except OSError:  # pragma: no cover - best-effort backup
            _log.exception("Failed to back up corrupt settings file")
