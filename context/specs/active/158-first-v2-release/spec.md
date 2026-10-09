# 158 — First v2 release: a version a host can pin, and wheels for every platform it runs on

- **Status:** draft — cut 2026-10-08 from the SmartOwl integration memo
- **Date:** 2026-10-08
- **Owner:** Clay Gendron
- **Kind:** release (version bump, changelog, GitHub release); no
  code behaviour
- **Depends on:** `context/standards/release.md`,
  `scripts/bump_version.py`, `.github/workflows/publish.yml` (already
  builds manylinux 2_28 and musllinux wheels for x86_64 and aarch64,
  macOS arm64 and x86_64, Windows x64 on a published release), 153
  (the README it ships).
- **Research it stands on:**
  `../../../research/2026-10-08-smartowl-workspace-integration-issues.md`
  items 6 and 18.

## Intent

v2 still calls itself `vfs-py 0.0.22`, the same name and number as the
obsolete previous-generation release on PyPI. A host cannot pin v2; it
has to check imports. And the only wheel anywhere is a local macOS
arm64 build, so a Linux container has to carry a Rust toolchain and
compile fifty-seven tree-sitter grammars. The publish workflow that
fixes the second problem already exists and has never run for v2.

One line: bump to a number the old release never used, cut a GitHub
release, and let the workflow ship the wheels.

## Decided semantics

1. **The version is `0.1.0`.** Pre-1.0, a breaking rebuild bumps minor
   (`release.md`). The changelog's `[Unreleased]` section becomes
   `[0.1.0]` with one line per public surface that changed since
   0.0.22, grouped Breaking / Added / Changed / Fixed.
   `[NEEDS CLARIFICATION: 0.1.0, or jump to 1.0.0a1 so the
   prerelease marker says "alpha" in the pin itself? Leaning 0.1.0;
   the README banner already says alpha.]`
2. **The release runs the existing workflow.** A GitHub release tagged
   `v0.1.0` triggers `publish.yml`; the wheels it produces are the
   platform set above plus the sdist as the maturin-bootstrap
   fallback. No new build tooling.
3. **A host verifies the pin.** `vfs.__version__ == "0.1.0"` and
   `vfs.native` imports on a manylinux container with no Rust
   toolchain; the db_test skill's Postgres leg runs from the published
   wheel once.

## Scope

- `uv run python scripts/bump_version.py --minor`; the changelog
  section; the tag and release.
- A one-time check that the `publish.yml` matrix still builds (it has
  not run since the Rust extension became required, ADR 057).
- Out of scope: PyPI trusted-publisher setup if it is already in
  place; a release cadence.

## Acceptance criteria

- `pip install vfs-py==0.1.0` on `python:3.13-slim` (x86_64 and
  aarch64) imports `vfs` and `vfs.native` without a compiler.
- PyPI lists the seven wheels and the sdist.
- `CHANGELOG.md` has a `[0.1.0]` section dated the release day.
