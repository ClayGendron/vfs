# Release process

VFS publishes to PyPI as `vfs-py`. A release is cut from `main` after the local gate and the CI legs are green, and after the full security audit the release gets. The landings a release gathers are described in [landing.md](landing.md); each landed spec's landing notes end with the one `Changelog:` line the release assembles.

> **Naming note.** The package on PyPI is `vfs-py`; the module imports as `vfs`.

## When to release

vfs is on the lane to `0.1.0`: alphas now, betas when the public surface stops moving, the final when a beta has held. The stage is the suffix of the version, and each stage says what may change between its releases.

| Stage | Numbers | What may change between releases | Who it is for |
|---|---|---|---|
| alpha | `0.1.0a1`, `a2`, … | anything: verbs, models, result shapes, the schema | the repo's own hosts and anyone who asked for `--pre` |
| beta | `0.1.0b1`, `b2`, … | bugs only; names may be added and are listed under *Added*; no rename, removal or change of meaning | hosts preparing to depend on 0.1.0 |
| final | `0.1.0` | nothing; the next change is `0.1.1` or `0.2.0` | everyone |

- **An alpha ships per landed batch, cut by hand.** When one or more specs land that change the public surface or fix something a host hit, the next alpha ships. There is no clock and nothing publishes from `main` on its own.
- **Beta begins when the public surface is frozen, and Clay calls the freeze.** The public surface is the verbs and their signatures, the `Result` shapes, the storage protocols, the row schema (`SCHEMA_FORMAT_VERSION`), the two faces and the session, and the MCP surface if it exists by then. Frozen means no active spec would rename, remove or change the meaning of a public name; a spec that would is tagged `0.2.0`. The call is a dated line here and in the `v0.1.0b1` release notes. An `rc` stage is not planned; a beta that holds becomes the final.
- **The final ships when a beta has held.** The current beta has been the current release for at least fourteen days; no breaking fix was needed in that time; the four real-engine legs pass from the published wheel, not a checkout; and every story the [roadmap](roadmap.md) tags `f` has landed.
- **The classifier follows the version by threshold.** Below `0.1.0b1` `Development Status :: 3 - Alpha`; from `0.1.0b1` and below `1.0.0` `4 - Beta`; from `1.0.0` `5 - Production/Stable`. A pre-release sorts below its final, so `1.0.0a1` is still Beta. The classifier line is a hand edit in the release commit that crosses a threshold; `tests/scripts/test_bump_version.py` refuses a tree where it lags.

After `0.1.0`, the `0.x` rules:

- Patch (`X.Y.Z` → `X.Y.Z+1`): bug fixes, internal refactors, doc-only changes that ship something user-visible.
- Minor (`X.Y.Z` → `X.Y+1.0`): new public methods, new backends, new providers. Pre-1.0, breaking changes also bump minor, and the release notes' *Breaking* group says what broke.
- Major (`X.Y.Z` → `X+1.Y.Z`): breaking changes, from `1.0.0` on.

## What a bare install gives

These are the resolution rules of `packaging`, the library pip's finder uses (`SpecifierSet.filter` with `prereleases=None`), executed 2026-10-15 and re-executed 2026-11-06. They are why the `0.0.x` finals were yanked before the first alpha, and why the README's pin carries a pre-release marker.

| Request | Candidates on the index | Result |
|---|---|---|
| `pip install vfs-py` | only alphas (finals yanked) | installs the newest alpha: the empty specifier falls back to pre-releases when no final exists |
| `pip install vfs-py` | a final exists beside alphas | installs the final; alphas hidden |
| `pip install "vfs-py<0.2"` | only alphas | **fails, no matching distribution**: a non-empty specifier without a pre-release marker never falls back |
| `pip install "vfs-py>=0.1.0a1,<0.2"` | only alphas | installs the newest alpha: the `a1` in the specifier is the opt-in |
| `pip install --pre vfs-py` | anything | installs the newest version of any kind |
| `pip install vfs-py==0.0.22` | 0.0.22 yanked | installs it, with a yank warning: the exact pin is the one escape hatch |

uv's default pre-release strategy is `if-necessary-or-explicit`, which reaches the same answers for the first two rows and the fourth, and resolves the third row too (uv judges "all versions are pre-release" per package, not per specifier). uv skips yanked versions unless the pin is `==`, like pip.

## Permanent facts of the lane

- **The publish matrix builds five wheels and an sdist**: manylinux 2_28 on x86_64 and aarch64, macOS arm64 and x86_64, Windows x64, one wheel per platform on `abi3-py311`. No musl wheel: `sqlite-vec`, a core dependency, ships no musl wheel and no sdist, so `pip install vfs-py` on Alpine fails resolution whatever vfs publishes, and the README's install section says so. The two musllinux jobs return when `sqlite-vec` publishes a musl wheel.
- **No release after a change to `publish.yml` without a `workflow_dispatch` run of it from `main` first.** The dispatch builds every wheel and the sdist and uploads nothing, so the matrix is proven before a tag exists. The first such run, `42326517501` on 2026-11-06, found a grammar crate that could not build under MSVC and a cache step that failed four green builds; the fixes landed before any tag.
- **The workflow runs no tests.** It trusts `main` is green (step 2). It does check the tag: every job runs `scripts/check_release_tag.py` right after checkout and `setup-uv`, which fails the release unless the tag equals `v` + the project version, so a release cut before the bump commit cannot rebuild the old number.
- **The sdist is not a slim-image path.** `pyproject.toml` requires `maturin>=1.8.4`, the first version whose sdist build bootstraps Rust, but the tree-sitter crates need a C compiler regardless.
- **There is no `CHANGELOG.md`.** The [GitHub releases](https://github.com/ClayGendron/vfs/releases) are the user-facing record of what changed.
- **The README ships in the wheel.** A README fix a release needs lands before the bump.
- **The `0.0.x` releases are yanked, not deleted.** `0.0.20`, `0.0.21` and `0.0.22` carry the reason *Previous-generation API, superseded by the 0.1.0 rebuild; nothing from 0.0.x carries over.* An exact pin still resolves to one, with a warning.

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

A release runs Cloudflare's security-audit skill in full-audit mode, not the guidance mode a per-spec code review uses; the skill, its licence and its pins are recorded in [landing.md](landing.md). `npx skills check` confirms the installed skill still matches its lock. The audit writes one review file, `context/reviews/YYYY-MM-DD-<version>-security-audit.md`, and beside it a folder of the same name holding the skill's run folder with every path rewritten relative to the repository and both validators passing. A confirmed finding at critical or high is fixed and landed before the bump. The rule holds for pre-releases: every alpha and beta gets the full audit, exactly as a final does (Clay, 2026-11-06).

### 4. Bump the version

```bash
uv run python scripts/bump_version.py --patch           # 0.0.22  → 0.0.23
uv run python scripts/bump_version.py --minor           # 0.0.22  → 0.1.0
uv run python scripts/bump_version.py --major           # 0.1.0   → 1.0.0
uv run python scripts/bump_version.py --minor --pre a   # 0.0.22  → 0.1.0a1, opening a pre-release lane
uv run python scripts/bump_version.py --pre a           # 0.1.0a1 → 0.1.0a2
uv run python scripts/bump_version.py --pre b           # 0.1.0a4 → 0.1.0b1
uv run python scripts/bump_version.py --final           # 0.1.0b3 → 0.1.0
uv run python scripts/bump_version.py --set 0.2.0.dev1  # anything the rules do not cover
```

`pyproject.toml` is the only file that states the version; `vfs.__version__` reads it from the installed metadata. The script rewrites that one line and runs `uv lock` itself, so `uv.lock` follows. A move the lane does not allow (a stage letter going backwards, `--final` on a final, a part flag on a pre-release) is refused with exit status 2 and nothing is written. Don't hand-edit version strings.

### 5. Draft the release notes

The release notes are written at release, from the landing notes of every spec archived since the last tag. The `Spec:` trailer of each landing commit is the index:

```bash
git log <last-tag>..HEAD --format='%(trailers:key=Spec,valueonly)' | sed '/^$/d'
```

Open each spec listed and copy the one `**Changelog:**` line that ends its landing notes under the matching heading of the draft, in [Keep a Changelog](https://keepachangelog.com/) shape; a line that says `None — internal` is left out. The draft is a scratch file, not a file in the tree: it becomes the body of the GitHub release in step 7. Write it by hand from those lines: a user reads it, so it says what changed for them, not which commits ran.

```
## What's Changed

### Added
- ...

### Changed
- ...

### Fixed
- ...

### Security
- ...
```

No unreleased list is kept between releases; the landing notes are the unreleased changelog.

### 6. One commit: `build: release X.Y.Z`

The commit carries the version bump and `uv.lock`, and nothing else. Read `git diff --cached --stat` before committing. Run `uv run ruff format --check src/ tests/` if the bump touched anything beyond version strings.

```
build: release X.Y.Z
```

Push when Clay asks, as for every commit.

### 7. Create the GitHub release

This creates the `vX.Y.Z` tag on `main` and triggers the PyPI publish workflow. The release body is the draft from step 5: a `## What's Changed` header, its sections, and a `**Full Changelog**` link at the bottom. Look at the last releases for tone (`gh release list --limit 3`, `gh release view vX.Y.Z-1`). **`--prerelease` is mandatory for any suffixed version** (`0.1.0a1`, `0.1.0b2`): it is what tells GitHub not to mark the release *Latest* and what keeps the release list honest about the stage. In an alpha, the *Breaking* group is allowed and expected, and every alpha's notes carry the line that until `0.1.0b1` an alpha may change the row schema, in which case a mount made by an earlier alpha is re-provisioned.

```bash
gh release create vX.Y.ZaN --prerelease --title "vX.Y.ZaN" --notes "$(cat <<'NOTES'
## What's Changed

### Added
- ...

### Breaking
- ...

**Full Changelog**: https://github.com/ClayGendron/vfs/compare/vPREV...vX.Y.ZaN
NOTES
)"
```

A final drops `--prerelease` and the *Breaking* group's alpha line; nothing else in the command changes.

### 8. Watch the publish workflow

```bash
gh run watch <run_id>
```

If the publish step fails, fix the underlying issue and cut the next patch release. **Do not** delete and re-create a release — the tag is then ambiguous to consumers.

## Don'ts

- No `--no-verify` on commits or pushes during a release. Hooks exist for a reason; if a hook fails, fix the cause.
- No force-pushes to `main`.
- No release without release notes. The GitHub release is the user-facing record; the tree holds no `CHANGELOG.md`.
- No release from a tree `scripts/ci.sh` has not passed, and none while a CI leg on `main` is red.
- No alpha or beta without `--prerelease` on `gh release create`.
- No musl wheel while `sqlite-vec` ships none; a wheel that publishes but cannot install is a platform claim vfs cannot keep.
- No release after a change to `publish.yml` without a `workflow_dispatch` dry run of it first.
