# Release process

VFS publishes to PyPI as `vfs-py`. A release is cut from `main` after the local gate and the CI legs are green, and after the full security audit the release gets. The landings a release gathers are described in [landing.md](landing.md); each landed spec's landing notes end with the one `Changelog:` line the release assembles.

> **Naming note.** The package on PyPI is `vfs-py`; the module imports as `vfs`.

## When to release

- Patch (`X.Y.Z` → `X.Y.Z+1`): bug fixes, internal refactors, doc-only changes that ship something user-visible.
- Minor (`X.Y.Z` → `X.Y+1.0`): new public methods, new backends, new providers.
- Major (`X.Y.Z` → `X+1.Y.Z`): breaking changes. (Pre-1.0, breaking changes still bump minor — but call them out clearly in the changelog.)

## Before the first v2 release (verified 2026-10-08, from the dropped spec 158)

No release is planned yet (Clay, 2026-10-08). When one is, these are the facts a reviewer established against `0760fe9` and PyPI, so the first run does not rediscover them:

- **The seven-platform matrix in `publish.yml` has never run.** The v0.0.22 publish used a two-job workflow; the matrix (manylinux and musllinux on x86_64 and aarch64, macOS arm64 and x86_64, Windows x64, one wheel per platform on `abi3-py311`, plus an sdist) was added 2026-08-16 and `uv publish --trusted-publishing` on 2026-08-25. Add a `workflow_dispatch` trigger and dry-run every leg from `main` before cutting a release.
- **The macOS x86_64 runner is retired.** `publish.yml` pins `macos-13`, which GitHub retired in December 2025; use `macos-15-intel`.
- **The workflow runs no tests and never checks the tag.** It trusts `main` is green (step 2). Add a step that fails unless `github.event.release.tag_name` equals `v` + the project version, so a release cut before the bump commit cannot rebuild the old number.
- **musllinux wheels publish but do not install.** `sqlite-vec`, a core dependency, ships no musl wheel and no sdist, so `pip install vfs-py` on Alpine fails resolution whatever vfs publishes. Say so in the README's install section.
- **The sdist is not a slim-image path.** `pyproject.toml` admits `maturin>=1.8,<2.0`; 1.8.0–1.8.3 do not bootstrap Rust, so raise the floor to `maturin>=1.8.4`. The tree-sitter crates need a C compiler regardless.
- **`bump_version.py` touches two files and cannot emit a prerelease.** It rewrites `pyproject.toml` and `src/vfs/__init__.py` with a `\d+\.\d+\.\d+` pattern; `uv.lock` carries the version too, so run `uv lock` and commit it. `crates/vfs-core/Cargo.toml` is independent (maturin reads the project version) and its comment still says `vfs._accel`.
- **The changelog's `[Unreleased]` section is previous-generation residue** (`VFSObject`, `DatabaseFileSystem`, story links). The first v2 section is written fresh, not renamed.
- **PyPI state.** `vfs-py` has 0.0.20, 0.0.21 and 0.0.22 only; 0.1.0 is unused. Pre-1.0, the v2 rebuild bumps minor to `0.1.0`.
- **The README ships in the wheel**, so the docs fix (spec 153) lands first.

## Step-by-step

### 1. `scripts/ci.sh` is green on `main`

Run the local gate on the `main` checkout that will be released: lint, format, types, the suite at 100 % coverage, the docs fences, the wheel budget. A release starts from a green tree; a red step is a fix landed first, not a retry.

```bash
scripts/ci.sh
```

### 2. The four CI legs are green on the last push

Every landing since the last tag has been pushed, and the Tests workflow's four legs (3.11, 3.12, 3.13, 3.14) and the Lint workflow are green on the last push to `main`.

```bash
gh run list --branch main --limit 5
gh run watch <run_id>
```

Only proceed when the runs succeed. A failed run is a fix landed on `main`, not a retry.

### 3. The full security audit

A release runs Cloudflare's security-audit skill in full-audit mode, not the guidance mode a per-spec code review uses; the skill, its licence and its pins are recorded in [landing.md](landing.md). `npx skills check` confirms the installed skill still matches its lock. The audit writes one review file, `context/reviews/YYYY-MM-DD-<version>-security-audit.md`, and beside it a folder of the same name holding the skill's run folder with every path rewritten relative to the repository and both validators passing. A confirmed finding at critical or high is fixed and landed before the bump.

### 4. Bump the version

```bash
uv run python scripts/bump_version.py --patch   # 0.0.20 → 0.0.21
uv run python scripts/bump_version.py --minor   # 0.0.20 → 0.1.0
uv run python scripts/bump_version.py --major   # 0.1.0  → 1.0.0
uv lock
```

The script updates `pyproject.toml` and `src/vfs/__init__.py`; `uv lock` carries the new version into `uv.lock`. Don't hand-edit version strings.

### 5. Assemble the `CHANGELOG.md` section

The changelog is written at release, from the landing notes of every spec archived since the last tag. The `Spec:` trailer of each landing commit is the index:

```bash
git log <last-tag>..HEAD --format='%(trailers:key=Spec,valueonly)' | sed '/^$/d'
```

Open each spec listed and copy the one `**Changelog:**` line that ends its landing notes under the matching heading of a new section at the top of `CHANGELOG.md`, in [Keep a Changelog](https://keepachangelog.com/) shape; a line that says `None — internal` is left out. Write the section by hand from those lines: a user reads it, so it says what changed for them, not which commits ran.

```
## [X.Y.Z] — YYYY-MM-DD

### Added
- ...

### Changed
- ...

### Fixed
- ...

### Security
- ...
```

No `[Unreleased]` section is kept between releases; the landing notes are the unreleased changelog. The first v2 section replaces the stale `[Unreleased]` residue named above.

### 6. One commit: `build: release X.Y.Z`

The commit carries the version bump, `uv.lock` and the changelog section, and nothing else. Read `git diff --cached --stat` before committing. Run `uv run ruff format --check src/ tests/` if the bump touched anything beyond version strings.

```
build: release X.Y.Z
```

Push when Clay asks, as for every commit.

### 7. Create the GitHub release

This creates the `vX.Y.Z` tag on `main` and triggers the PyPI publish workflow. The release body mirrors the changelog section: a `## What's Changed` header, the same sections, and a `**Full Changelog**` link at the bottom. Look at the last releases for tone (`gh release list --limit 3`, `gh release view vX.Y.Z-1`).

```bash
gh release create vX.Y.Z --title "vX.Y.Z" --notes "$(cat <<'NOTES'
## What's Changed

### Added
- ...

**Full Changelog**: https://github.com/ClayGendron/vfs/compare/vPREV...vX.Y.Z
NOTES
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
- No releases without a CHANGELOG section. The CHANGELOG is the user-facing record; the GitHub release notes are derived from it, not the other way round.
- No release from a tree `scripts/ci.sh` has not passed, and none while a CI leg on `main` is red.
