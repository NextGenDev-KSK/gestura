"""Download the ML model files Gestura needs into the local ``models/`` directory.

Run once after cloning::

    python scripts/fetch_models.py

Models are intentionally *not* committed (see .gitignore); they are fetched from Google's public
MediaPipe model registry. Everything still runs fully offline afterwards.
"""

from __future__ import annotations

import hashlib
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

MODELS_DIR = Path(__file__).resolve().parents[1] / "models"


@dataclass(frozen=True)
class ModelSpec:
    filename: str
    url: str
    description: str


MODELS: tuple[ModelSpec, ...] = (
    ModelSpec(
        filename="hand_landmarker.task",
        url=(
            "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
            "hand_landmarker/float16/1/hand_landmarker.task"
        ),
        description="MediaPipe HandLandmarker (21 landmarks, float16)",
    ),
)


def _download(spec: ModelSpec, dest: Path) -> None:
    print(f"[fetch] {spec.description}\n  {spec.url}")
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(spec.url) as resp:  # noqa: S310 - trusted Google host
        total = int(resp.headers.get("Content-Length", 0))
        read = 0
        digest = hashlib.sha256()
        with tmp.open("wb") as fh:
            while chunk := resp.read(64 * 1024):
                fh.write(chunk)
                digest.update(chunk)
                read += len(chunk)
                if total:
                    pct = read / total * 100
                    print(f"\r  {read // 1024:>6} KiB / {total // 1024} KiB ({pct:4.1f}%)", end="")
    print()
    tmp.replace(dest)
    print(f"  saved {dest.name}  sha256={digest.hexdigest()[:16]}  ({dest.stat().st_size} bytes)")


def main() -> int:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    for spec in MODELS:
        dest = MODELS_DIR / spec.filename
        if dest.exists() and dest.stat().st_size > 0:
            print(f"[ok] {spec.filename} already present ({dest.stat().st_size} bytes) - skipping")
            continue
        try:
            _download(spec, dest)
        except Exception as exc:  # noqa: BLE001 - report and fail clearly
            print(f"[error] Failed to download {spec.filename}: {exc}", file=sys.stderr)
            return 1
    print("\nAll models ready in", MODELS_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
