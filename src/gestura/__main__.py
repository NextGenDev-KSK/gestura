"""Console entry point: ``gestura`` / ``python -m gestura``."""

from __future__ import annotations

import sys


def main() -> int:
    # Absolute imports (not relative): PyInstaller runs this file as a top-level ``__main__``
    # script with no parent package, where ``from .app...`` would raise ImportError. Absolute
    # imports work identically under ``python -m gestura``, the ``gestura`` console script, and
    # the frozen executable.
    try:
        from gestura.app.application import run

        return run(sys.argv[1:])
    except BaseException:
        # Frozen (windowed) builds have no console, so persist any fatal error for diagnosis.
        import traceback

        report = traceback.format_exc()
        try:
            from gestura.util.paths import log_dir

            (log_dir() / "crash.txt").write_text(report, encoding="utf-8")
        except Exception:
            import tempfile

            with open(f"{tempfile.gettempdir()}/gestura_crash.txt", "w", encoding="utf-8") as fh:
                fh.write(report)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
