"""One-command Windows build: fetch the model, then run PyInstaller.

    python scripts/build_exe.py

Produces ``dist/Gestura/Gestura.exe``. Requires the ``packaging`` extra::

    pip install -e ".[dev,packaging]"
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    print("[1/2] Ensuring the hand-landmark model is present…")
    rc = subprocess.call([sys.executable, str(ROOT / "scripts" / "fetch_models.py")])
    if rc != 0:
        return rc

    print("[2/2] Running PyInstaller…")
    rc = subprocess.call(
        [sys.executable, "-m", "PyInstaller", "packaging/gestura.spec", "--noconfirm"],
        cwd=ROOT,
    )
    if rc != 0:
        print("PyInstaller failed. Is the [packaging] extra installed? "
              '(pip install -e ".[packaging]")')
        return rc

    out = ROOT / "dist" / "Gestura" / "Gestura.exe"
    print(f"\nBuild complete: {out}" if out.exists() else "\nBuild finished (check dist/).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
