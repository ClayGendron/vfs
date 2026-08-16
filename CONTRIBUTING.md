# Contributing to vfs

Thanks for your interest in contributing to vfs! This guide covers how to set up your development environment, run the test suite, and submit changes.

## Getting started

### Prerequisites

- **Python 3.11+** (3.13 recommended)
- **[uv](https://docs.astral.sh/uv/)** for package management

### Setup

Clone the repo and install in editable mode with dev dependencies:

```bash
git clone https://github.com/ClayGendron/vfs.git
cd vfs
uv venv
uv pip install -e ".[all]"
uv pip install --group dev
```

This installs vfs with all optional extras plus the development tools (pytest, ruff, ty, etc.).

### Verify your setup

```bash
uv run ruff check src/ tests/
uv run ty check src/ tests/
uv run pytest
```

All three should pass cleanly.

## Development workflow

### Making changes

1. Create a branch from `main`.
2. Make your changes.
3. Run the quality checks (see below).
4. Open a pull request against `main`.

Issues are encouraged for larger changes or design discussions, but not required for straightforward fixes or additions. If you're unsure whether something warrants an issue, go ahead and open a PR — we can discuss there.

### Quality checks

Every PR should pass all three checks:

**Linting** (ruff):

```bash
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
```

To auto-fix lint issues and formatting:

```bash
uv run ruff check --fix src/ tests/
uv run ruff format src/ tests/
```

**Type checking** (ty):

```bash
uv run ty check src/ tests/
```

**Tests** (pytest):

```bash
uv run pytest
```

The full CI-parity matrix (lint, format, types, and coverage across every supported Python) runs via `scripts/ci.sh`.

### Writing tests

Tests live in `tests/` and use pytest with `pytest-asyncio` (async mode is set to `auto`). A few conventions:

- Test files mirror the source structure: `src/vfs/storage/backends/database/reads.py` is tested in `tests/storage/database/test_reads.py`.
- Shared fixtures are in `tests/conftest.py`.
- Prefer in-memory SQLite (`DatabaseStorage` over `:memory:`) for unit tests; the real-engine legs (Postgres, MySQL, MSSQL, Oracle) run in Docker via the conformance suite.
- Assert on `Result` fields directly; see `context/standards/testing.md` for the house conventions.

### Commit messages

Keep commit messages concise and descriptive. Focus on the *why*, not the *what*:

```
Fix version reconstruction when snapshot is at boundary

The snapshot interval check was off-by-one, causing reconstruction
to miss the boundary snapshot and fall back to a stale one.
```

## Project structure

```
src/vfs/
├── base.py               # VirtualFileSystem — the router: mounts, dispatch, fan-out
├── paths.py              # Path type, normalization, extension law
├── params.py             # Per-verb parameter gates
├── permissions.py        # Permission maps and write authorization
├── exceptions.py         # Error hierarchy
├── ops.py                # Op vocabulary and shared type aliases
├── pattern_matching/     # Pure pattern authorities
│   ├── glob.py           # Glob language: defect gate, compile chokepoint, residuation
│   └── grep.py           # Grep match authority: verifier, per-file verification
├── models/               # Row and value models (entries, chunks, grams, postings)
├── results/              # Result envelope, error kinds, rendering
└── storage/
    ├── protocol.py       # StorageBackend capability protocols
    └── backends/
        └── database/     # The portable SQL backend (SQLAlchemy)
```

`src2/` and `tests2/` are archived pre-refactor code kept as a reference quarry — never edit, run, or lint them.

For the design record — decisions, specs, research — see `context/README.md`.

## Tooling reference

| Tool | Purpose | Command |
|------|---------|---------|
| **ruff** | Linting and formatting | `uv run ruff check src/ tests/` |
| **ty** | Type checking | `uv run ty check src/ tests/` |
| **pytest** | Test runner | `uv run pytest` |
| **uv** | Package management | `uv pip install ...` |

Run everything through `uv` so the correct virtualenv is used.

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](https://www.contributor-covenant.org/version/2/1/code_of_conduct/). By participating, you agree to uphold a welcoming, inclusive, and respectful environment for everyone.

In short: be kind, be constructive, and assume good intent. If you experience or witness unacceptable behavior, please reach out to the maintainers.

## Questions?

If you're not sure about something, open an issue or start a discussion. We're happy to help.
