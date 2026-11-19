# Contributing

This repository is built by directing Claude Code against `docs/spec.md`. Issues describing a spec gap, a missed leak, or a false positive are welcome. Use a synthetic file; never attach a real document.

For a change: open an issue first. Pull requests need green CI and a test tagged with the requirement id it proves.

Set up: `uv sync --locked`, then `uv run pytest -q --tb=line`.

By contributing you agree that your contribution is licensed under AGPL-3.0-or-later.
