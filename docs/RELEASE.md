# Release checklist

A repeatable process for cutting a Gestura release.

## 1. Pre-flight

- [ ] `git switch -c release/vX.Y.Z` from an up-to-date `main`.
- [ ] Bump the version in `pyproject.toml` **and** `src/gestura/__init__.py` (`__version__`).
- [ ] Update `CHANGELOG.md` (or the GitHub release notes draft).
- [ ] `pip install -e ".[dev,packaging]"` in a clean virtualenv.

## 2. Quality gates (all must pass)

- [ ] `ruff check src tests scripts` — lint clean.
- [ ] `pytest --cov=gestura` — all tests pass, coverage not regressed.
- [ ] `python -m gestura --self-test 2` — UI loads with no QML warnings.
- [ ] `python scripts/diagnose.py` — camera + tracker healthy on the build machine.
- [ ] Manual smoke: launch `gestura`, verify cursor move / pinch click / drag / scroll /
      volume / pause on real hardware.

## 3. Build artifacts

- [ ] `python scripts/fetch_models.py` — model present.
- [ ] `python scripts/build_exe.py` — produces `dist/Gestura/Gestura.exe`.
- [ ] Launch `dist/Gestura/Gestura.exe` on a clean Windows VM (no Python installed) and confirm it
      runs, finds its model, and controls the cursor.
- [ ] `iscc packaging/gestura_installer.iss` — produces `packaging/dist/GesturaSetup.exe`.
- [ ] Install via the setup EXE on the clean VM; verify Start-menu/desktop shortcuts and uninstall.

## 4. Publish

- [ ] `git tag -a vX.Y.Z -m "Gestura vX.Y.Z"` and push the tag.
- [ ] Create the GitHub Release; attach `GesturaSetup.exe` and the zipped `dist/Gestura` folder.
- [ ] Verify the CI run on the tag is green.
- [ ] Announce / update the README download link.

## 5. Post-release

- [ ] Merge `release/vX.Y.Z` back to `main`.
- [ ] Open a `vX.Y.(Z+1)-dev` milestone.
