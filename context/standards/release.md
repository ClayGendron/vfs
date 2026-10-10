# Release process

VFS publishes to PyPI as `vfs-py`. Releases are cut from `main` after CI is green.

> **Naming note.** The package on PyPI is `vfs-py`; the module imports as `vfs`.

## When to release

- Patch (`X.Y.Z` → `X.Y.Z+1`): bug fixes, internal refactors, doc-only changes that ship something user-visible.
- Minor (`X.Y.Z` → `X.Y+1.0`): new public methods, new backends, new providers.
- Major (`X.Y.Z` → `X+1.Y.Z`): breaking changes. (Pre-1.0, breaking changes still bump minor — but call them out clearly in the changelog.)

## Before the first v2 release (verified 2026-10-08, from the dropped spec 158)

No release is planned yet (Clay, 2026-10-08). When one is, these are
the facts a reviewer established against `0760fe9` and PyPI, so the
first run does not rediscover them:

- **The seven-platform matrix in `publish.yml` has never run.** The
  v0.0.22 publish used a two-job workflow; the matrix (manylinux and
  musllinux on x86_64 and aarch64, macOS arm64 and x86_64, Windows
  x64, one wheel per platform on `abi3-py311`, plus an sdist) was
  added 2026-08-16 and `uv publish --trusted-publishing` on
  2026-08-25. Add a `workflow_dispatch` trigger and dry-run every
  leg from `main` before cutting a release.
- **The macOS x86_64 runner is retired.** `publish.yml` pins
  `macos-13`, which GitHub retired in December 2025; use
  `macos-15-intel`.
- **The workflow runs no tests and never checks the tag.** It trusts
  `main` is green (step 2). Add a step that fails unless
  `github.event.release.tag_name` equals `v` + the project version,
  so a release cut before the bump commit cannot rebuild the old
  number.
- **musllinux wheels publish but do not install.** `sqlite-vec`, a
  core dependency, ships no musl wheel and no sdist, so `pip install
  vfs-py` on Alpine fails resolution whatever vfs publishes. Say so
  in the README's install section.
- **The sdist is not a slim-image path.** `pyproject.toml` admits
  `maturin>=1.8,<2.0`; 1.8.0–1.8.3 do not bootstrap Rust, so raise
  the floor to `maturin>=1.8.4`. The tree-sitter crates need a C
  compiler regardless.
- **`bump_version.py` touches two files and cannot emit a
  prerelease.** It rewrites `pyproject.toml` and `src/vfs/__init__.py`
  with a `\d+\.\d+\.\d+` pattern; `uv.lock` carries the version
  too, so run `uv lock` and commit it. `crates/vfs-core/Cargo.toml`
  is independent (maturin reads the project version) and its comment
  still says `vfs._accel`.
- **The changelog's `[Unreleased]` section is previous-generation
  residue** (`VFSObject`, `DatabaseFileSystem`, story links). The
  first v2 section is written fresh, not renamed.
- **PyPI state.** `vfs-py` has 0.0.20, 0.0.21 and 0.0.22 only; 0.1.0
  is unused. Pre-1.0, the v2 rebuild bumps minor to `0.1.0`.
- **The README ships in the wheel**, so the docs fix (spec 153)
  lands first.

## Step-by-step

### 0. Format before pushing — every time

```bash
uvx ruff format src/ tests/
```

CI's `ruff format --check` gate fails the entire Tests workflow on any unformatted file. Skipping this step has cost a CI run more than once.

### 1. Push the code changes

All production code, tests, and docs land on `main` via PR. No release-only branches.

### 2. Wait for CI to pass

```bash
gh run list --limit 1
gh run watch <run_id>
```

Only proceed if the run succeeds. A failed run is a fix, not a retry.

### 3. Bump the version

```bash
uv run python scripts/bump_version.py --patch   # 0.0.20 → 0.0.21
uv run python scripts/bump_version.py --minor   # 0.0.20 → 0.1.0
uv run python scripts/bump_version.py --major   # 0.1.0  → 1.0.0
```

The script updates both `pyproject.toml` and `src/vfs/__init__.py`. Don't hand-edit version strings.

### 4. Update `CHANGELOG.md`

Add a section at the top following [Keep a Changelog](https://keepachangelog.com/) format:

```
## [X.Y.Z] — YYYY-MM-DD

### Added
- ...

### Changed
- ...

### Fixed
- ...
```

### 5. Commit and push

```
Bump version to X.Y.Z, update changelog
```

Run `uvx ruff format` again before pushing if the bump touched anything beyond version strings.

### 6. Draft the release notes

Look at the last three releases for tone and structure:

```bash
gh release list --limit 3
gh release view vX.Y.Z-1
```

The release body mirrors the CHANGELOG entry: a `## What's Changed` header, the same sections, and a `**Full Changelog**` link at the bottom.

### 7. Create the GitHub release

This auto-creates the `vX.Y.Z` tag on `main` and triggers the PyPI publish workflow.

```bash
gh release create vX.Y.Z --title "vX.Y.Z" --notes "$(cat <<'EOF'
## What's Changed

### Added
- ...

**Full Changelog**: https://github.com/ClayGendron/vfs/compare/vPREV...vX.Y.Z
EOF
)"
```

### 8. Watch the publish workflow

```bash
gh run watch <run_id>
```

If the publish step fails, fix the underlying issue and cut the next patch release. **Do not** delete and re-create a release — the tag is then ambiguous to consumers.

## Don'ts

- No `--no-verify` on commits or pushes during a release. Hooks exist for a reason; if a hook fails, fix the cause.
- No force-pushes to `main`.
- No releases without a CHANGELOG entry. The CHANGELOG is the user-facing record; the GitHub release notes are derived from it, not the other way round.
