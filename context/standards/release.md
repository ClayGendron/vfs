# Release process

VFS publishes to PyPI as `vfs-py`. Releases are cut from `main` after CI is green.

> **Naming note.** The package on PyPI is `vfs-py`. The module currently imports as `grover`; it will become `vfs` once the in-repo rename lands. Versions issued during the rename window are tagged from whichever name `pyproject.toml` carries at the time.

## When to release

- Patch (`X.Y.Z` → `X.Y.Z+1`): bug fixes, internal refactors, doc-only changes that ship something user-visible.
- Minor (`X.Y.Z` → `X.Y+1.0`): new public methods, new backends, new providers.
- Major (`X.Y.Z` → `X+1.Y.Z`): breaking changes. (Pre-1.0, breaking changes still bump minor — but call them out clearly in the changelog.)

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

The script updates both `pyproject.toml` and `src/grover/__init__.py` (post-rename: `src/vfs/__init__.py`). Don't hand-edit version strings.

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

**Full Changelog**: https://github.com/ClayGendron/grover/compare/vPREV...vX.Y.Z
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
