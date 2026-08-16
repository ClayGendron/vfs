# Contributing to vfs

The repo lives at [`ClayGendron/vfs`](https://github.com/ClayGendron/vfs).

## Setup

```bash
git clone https://github.com/ClayGendron/vfs.git
cd vfs
uv venv
uv pip install -e ".[all]"
uv pip install --group dev --group docs
```

Requires Python 3.11+.

## Day-to-Day Checks

```bash
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run ty check src/ tests/
uv run pytest
uv run mkdocs build --clean
```

Use `uv run ruff check --fix src/ tests/` and `uv run ruff format src/ tests/` when you want ruff to rewrite code.

## Repo Layout

```text
src/vfs/
├── base.py               # VirtualFileSystem — mounts, dispatch, fan-out
├── paths.py              # Path type, normalization, extension law
├── params.py             # Per-verb parameter gates
├── permissions.py        # Permission maps and write authorization
├── exceptions.py         # Error hierarchy
├── pattern_matching/     # Glob and grep pattern authorities
├── models/               # Row and value models
├── results/              # Result envelope, error kinds, rendering
└── storage/
    ├── protocol.py       # StorageBackend capability protocols
    └── backends/
        └── database/     # The portable SQL backend
```

Tests mirror the shipped modules under `tests/` — for example
`src/vfs/storage/backends/database/reads.py` is tested in
`tests/storage/database/test_reads.py`. `src2/` and `tests2/` are an
archived reference quarry; never edit, run, or lint them.

## Docs

MkDocs configuration lives in `mkdocs.yml`, and the published pages in the nav come from `docs/`.

The GitHub Pages deployment workflow lives at `.github/workflows/deploy-docs.yml`. The intended public URL for this repo's docs is `https://claygendron.github.io/vfs/`.

## Pull Requests

Keep changes scoped, run the checks above, and describe the behavior change rather than only the file list. If you are touching the public API, update the docs in the same change.
