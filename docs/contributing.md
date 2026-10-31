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
`tests/storage/database/test_reads.py`.

## Docs

MkDocs configuration lives in `mkdocs.yml`, and the published pages in the nav come from `docs/`.

The GitHub Pages deployment workflow lives at `.github/workflows/deploy-docs.yml`. The intended public URL for this repo's docs is `https://claygendron.github.io/vfs/`.

## How a change lands

Every change has a specification, one file under `context/specs/active/`, that states the problem, draws the components it touches, decides every choice with its reason, and names the test that will pin each acceptance criterion. Larger work starts earlier, with an intention under `context/intentions/` that says what experience the work enables and why, and with research memos under `context/research/` when there is something to learn.

A specification is reviewed before it is built, and the code is reviewed again before it lands. Both reviews are written by someone who did not write the change and are kept as files under `context/reviews/`; the specification's landing notes link them. The code is written tests first: the test is seen failing before the code that passes it.

A change lands as one commit to `main` whose subject names it in words and whose trailers link the specification and both reviews. The gate is `scripts/ci.sh`: lint, format, types, the tests under full coverage, the docs examples, the wheel budget, and the lint tests that hold the documents to their shape. The whole process is described in `context/README.md`, and the standards it rests on are `context/standards/how-we-code.md` and `context/standards/landing.md`.

Keep changes scoped, run the checks above, and describe the behavior change rather than only the file list. If you are touching the public API, update the docs in the same change.
