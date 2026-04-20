# Tooling

How we install, lint, type-check, and run tests in this repo. These commands are exact — substitutes (e.g. `uv sync` for `uv pip`, `pytest` for `uv run pytest`) have caused real problems and should not be used.

## Stack

- **Python:** 3.12 minimum, 3.13 target (`.python-version`).
- **Package manager:** `uv` (the venv is already a `uv` environment).
- **Build backend:** `hatchling`.
- **Linter / formatter:** `ruff` — invoked via `uvx`, never installed as a pip package.
- **Type checker:** `ty` — invoked via `uvx`.
- **Test runner:** `pytest` with `pytest-asyncio` (auto mode) and `pytest-cov`.

## Install

```bash
uv venv
uv pip install -e ".[all]"
uv pip install --group dev
```

Use `uv pip`, **not** `uv sync`. Dev dependencies live in `[dependency-groups]` (modern); user-facing extras live in `[project.optional-dependencies]`.

## Lint and format

```bash
uvx ruff check src/ tests/
uvx ruff format --check src/ tests/
uvx ruff check --fix src/ tests/
uvx ruff format src/ tests/
```

`ruff format` is the format authority. CI runs `ruff format --check` and fails the entire Tests workflow on any unformatted file. **Run `uvx ruff format` before every `git push`** — this has been forgotten enough times to deserve top billing here.

## Type check

```bash
uvx --refresh ty check src/
```

`ty` runs on `src/` only (tests are excluded by config in `pyproject.toml`).

## Test

```bash
uv run pytest                       # full suite
uv run pytest tests/test_thing.py   # single file
uv run pytest --cov                 # with coverage
```

No flags beyond what's shown. **No piping** (`| head`, `2>&1`, `| tail`). Failures hide behind pipes; the full output must be visible.

Coverage gate is `fail_under = 99` (see `[tool.coverage.report]`). The MSSQL backend is excluded — it's tested under `--mssql` against a real SQL Server instance from `docker/mssql/`.

## Pre-push checklist

In order, every push:

1. `uvx ruff format src/ tests/`
2. `uvx ruff check src/ tests/`
3. `uvx --refresh ty check src/`
4. `uv run pytest`
5. `git push`

The release process layers on top of this — see `standards/release.md`.
