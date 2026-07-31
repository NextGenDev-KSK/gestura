# Contributing to Gestura

Thanks for your interest! Gestura aims to be a polished, trustworthy, fully-offline gesture
controller. Contributions of all kinds are welcome — bug reports, gestures, docs, and code.

## Ground rules

- Be respectful and constructive.
- Keep the project **offline-first**: no feature may phone home or require an account.
- Reliability beats features. A gesture that misfires is worse than one that doesn't exist.

## Getting started

1. Read [`docs/DEVELOPER_GUIDE.md`](docs/DEVELOPER_GUIDE.md) and set up the dev environment.
2. Read [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) to understand the layering.
3. Find or open an issue describing what you want to do.

## Making a change

1. Branch off `main`: `git switch -c feat/short-description`.
2. Write code **and tests**. New logic without tests won't be merged. The engine is fully testable
   without hardware (`RecordingAdapter`, synthetic hands) — use it.
3. Before pushing, ensure all of these pass:
   ```
   ruff check src tests scripts
   pytest
   python -m gestura --self-test 2
   ```
4. Write a clear commit message (imperative subject, explain the *why* in the body).
5. Open a PR. Describe the change, how you tested it, and any trade-offs.

## Coding conventions

- Type hints + docstrings on public APIs; `mypy` in strict mode.
- Follow the existing layering — no upward imports.
- Match the surrounding code's style (Ruff enforces the rest).
- No new runtime dependency without a matching ADR in `docs/DECISIONS.md`.

## Reporting bugs

Include: OS version, how you installed, steps to reproduce, what you expected vs. saw, and the tail
of `%LOCALAPPDATA%\Gestura\logs\gestura.log`. For tracking/perf issues, attach the output of
`python scripts\diagnose.py`.

## Adding a gesture or action

See the "Extending" sections of the architecture and developer guides — most additions are a few
lines plus tests. Prefer deterministic recognisers for built-ins; use the custom-gesture trainer
for anything user-specific.

## License

By contributing you agree that your contributions are licensed under the project's Apache-2.0
license.
