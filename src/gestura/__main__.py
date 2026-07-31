"""Console entry point: ``gestura`` / ``python -m gestura``."""

from __future__ import annotations

import sys


def main() -> int:
    from .app.application import run

    return run(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
