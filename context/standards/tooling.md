# Tooling

How we install, lint, type-check and test this repository. The commands here are the ones `scripts/ci.sh` runs, with the same flags; a substitute (a bare `pytest`, a bare `ruff`, a plain `uv sync` without the extras) has caused real problems and is not used.

## Stack

- **Python:** 3.11 minimum (`requires-python`), 3.13 the target (`.python-version`); CI also runs 3.12 and 3.14.
- **Package manager:** `uv`. Every Python command runs through `uv run`; nothing invokes the interpreter or `pip` directly, and nobody activates `.venv` by hand.
- **Build backend:** `maturin`, which compiles `crates/vfs-core` into the wheel as `vfs._native`.
- **Linter and formatter:** `ruff`, a dev dependency, run as `uv run ruff`.
- **Type checker:** `ty`, a dev dependency, run as `uv run ty`.
- **Test runner:** `pytest` with `pytest-asyncio` (auto mode), `pytest-cov` and `pytest-xdist`.

## Install

```bash
uv sync --all-extras --group dev
```

The extras are not optional: without them `uv sync` strips the database drivers the engine legs need (this happened, 2026-09-04). Dev dependencies live in `[dependency-groups]`; user-facing extras live in `[project.optional-dependencies]`. The `docs` group holds Griffe, which `scripts/docs_export.py` reads the public API with; `dev` includes it, so the export's tests run after the install above, and `scripts/ci.sh` still names it.

After editing anything under `crates/`, reinstall the wheel, because `uv` caches the built wheel and does not rebuild on Rust-only edits:

```bash
uv sync --all-extras --group dev --reinstall-package vfs-py
cargo test -p vfs-core
```

## Lint and format

```bash
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run ruff check --fix src/ tests/
uv run ruff format src/ tests/
```

`ruff format` is the format authority. CI runs `ruff format --check` and fails the Tests workflow on any unformatted file; format drift has reached `main` twice by sessions that ran only `ruff check`. `src2/` and `tests2/` are excluded in `pyproject.toml`; never chase errors there.

## Type check

```bash
uv run ty check src/ tests/
```

`ty` runs on `src/` and `tests/`, exactly as `scripts/ci.sh` does (`[tool.ty.src]` includes both), and must stay at zero.

## Test

```bash
uv run pytest                               # the whole suite, parallel
uv run pytest tests/storage/database/test_reads.py
uv run pytest --cov --cov-fail-under=100    # the coverage gate
```

No flags beyond what is shown. **No piping** (`| head`, `2>&1`, `| tail`): failures hide behind pipes, and the full output must be visible.

The coverage gate is `fail_under = 100` (`[tool.coverage.report]`). The real-engine legs are selected by `VFS_TEST_<ENGINE>_URL` and come from `docker/compose.test.yml`; see [testing.md](testing.md), "Engine legs are selected by a URL".

## The gate before a commit

Before any commit touching `src/`, `tests/`, `crates/` or `pyproject.toml`, run the gate:

```bash
scripts/ci.sh
```

It mirrors the CI Tests job's Python 3.13 leg exactly: install, lint, format, types, tests under 100% coverage, the docs fences and the wheel budget, about a minute warm. Green here means green there. `scripts/ci.sh 3.14` reproduces one other matrix leg when CI goes red; the other legs are CI's job on every push, not a local gate.

## The docs site

The docs site is a second tree with its own toolchain: `docs-app/`, a Svelte app run with `bun`, that draws the Markdown pages of `documentation/` and the public API with the Pluto Systems design system. Its components are design-system items installed as source at a release tag, which `docs-app/README.md` names with the install command; they are a dependency, not copied prior art, and they are not edited here.

```bash
scripts/docs.sh dev      # preview locally
scripts/docs.sh check    # the gate for a docs change
```

Before any commit touching `documentation/`, `docs-app/`, `scripts/docs_export.py`, `scripts/docs.sh` or a docstring under `src/vfs/`, run `scripts/docs.sh check`. It writes the API export from the docstrings (never stored: `docs-app/src/lib/generated/` is ignored), builds the static site, type-checks the app and runs its tests: `bun test` for what the build writes and refuses, and Playwright in Chromium for the layout. The build itself fails on a link to a page or a heading that does not exist. The `Docs site` workflow runs the same command. `scripts/ci.sh` does not need `bun` and does not build the docs; the export's own rules are pinned in `tests/scripts/test_docs_export.py`, which it does run.

How a change lands, from the review file to the one landing commit, is in [landing.md](landing.md); the release process layers on top in [release.md](release.md).
