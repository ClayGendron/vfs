# Contributing to vfs

This repo still lives at `ClayGendron/grover`, but the library and docs are now branded as `vfs`.

## Setup

```bash
git clone https://github.com/ClayGendron/grover.git
cd grover
uv venv
uv pip install -e ".[all]"
uv pip install --group dev --group docs
```

Requires Python 3.12+.

## Day-to-Day Checks

```bash
uvx ruff check src/ tests/
uvx ruff format --check src/ tests/
uvx --refresh ty check src/
uv run pytest
uv run mkdocs build --clean
```

Use `uvx ruff check --fix src/ tests/` and `uvx ruff format src/ tests/` when you want ruff to rewrite code.

## Repo Layout

```text
src/vfs/
├── __init__.py
├── base.py
├── client.py
├── results.py
├── paths.py
├── permissions.py
├── models.py
├── backends/
│   ├── database.py
│   ├── postgres.py
│   └── mssql.py
├── graph/
│   └── rustworkx.py
└── query/
    ├── parser.py
    ├── executor.py
    └── render.py
```

Tests mirror the shipped modules. Examples:

- `src/vfs/query/parser.py` -> `tests/test_query_parser.py`
- `src/vfs/backends/database.py` -> `tests/test_database.py`
- `src/vfs/results.py` -> `tests/test_results.py`

## Docs

MkDocs configuration lives in `mkdocs.yml`, and the published pages in the nav come from `docs/`.

The GitHub Pages deployment workflow lives at `.github/workflows/deploy-docs.yml`. The intended public URL for this repo's docs is `https://claygendron.github.io/vfs/`.

## Pull Requests

Keep changes scoped, run the checks above, and describe the behavior change rather than only the file list. If you are touching the public API or the query language, update the docs in the same change.
