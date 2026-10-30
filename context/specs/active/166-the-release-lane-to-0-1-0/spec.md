# 166 — The release lane to 0.1.0: yank the old numbers, ship alphas, then betas, then the first real version

- **Status:** draft — cut 2026-10-15 from Clay's decision the same day ("yank the old code, it didn't work anyway, and then start alpha then beta releases for 0.1.0"). One `[NEEDS CLARIFICATION]` marker, the exit criteria for 0.1.0 final, pointered in `../../open-questions.md`.
- **Amended 2026-10-15** (Clay): `0.1.0a1` carries spec 167, the shell's pipeline core, beside the tree as it stands; the changelog's first section names the shell. Guest runtime artifacts ship inside the wheel for a runtime that fits, with the wheel budget in `scripts/ci.sh` raised to match (PyPI's own limit is 100 MB per file; the runtime decision is spec 172's, pending study `11-python-in-vfs.md`).
- **Amended 2026-10-16** (ADR 086, spike 173): the Python runtime does not ship in the wheel. It is a yearly-built, hashed WebAssembly artifact (8–20 MB xz; 40–95 MB raw) fetched by an install command, so the wheel budget in `scripts/ci.sh` stays where it is and PyPI's 100 MB file limit is not in play.
- **Date:** 2026-10-15
- **Owner:** Clay Gendron
- **Kind:** release engineering — the version scheme, the publish workflow, the bump script, the changelog, the README's install section and the release standard. One `src/` change: `__version__` stops being a second copy of the number. No verb changes semantics.
- **Depends on:** nothing lands first. Spec 153 (the README) landed 2026-10-10, so the README the wheel ships is already true.
- **Supersedes:** the dropped spec 158 (first v2 release as a bare `0.1.0`, dropped 2026-10-08). Its verified release facts live in `../../standards/release.md` under *Before the first v2 release* and are folded into this spec's scope.
- **Research it stands on:** the release facts in `../../standards/release.md` (verified 2026-10-08 against `0760fe9` and PyPI), re-verified 2026-10-15 against `ac5c515`; the pre-release resolution rules of `packaging`, executed 2026-10-15 (see *The resolver facts*). No memo: this is release mechanics, not a design with precedent to study.

## Intent

vfs has not shipped since `0.0.22` on 2026-04-22. 497 commits later the live tree is a ground-up rebuild that shares nothing with that release but its name. Three things are wrong at once:

1. **PyPI serves a dead API.** `pip install vfs-py` installs 0.0.22, whose every public name is gone. The README has to carry a banner explaining that the package on PyPI is not the package in the repo.
2. **A host cannot pin the rebuild.** There is no number that means "the new vfs". A host that wants it has to build from a checkout with a Rust toolchain and a C compiler.
3. **The publish pipeline has never run for the rebuild.** The seven-platform wheel matrix was written 2026-08-16 and has built nothing. Its first run should not also be the first release anyone depends on.

The fix is a lane, not a release. Yank the three dead numbers so no pin lands on them by accident. Ship the rebuild as alphas of `0.1.0`: `0.1.0a1`, `0.1.0a2`, and so on, one per batch of landed specs. Alphas may break anything between each other. When the public surface stops moving, switch to betas, which may only fix. When a beta has held, drop the suffix and `0.1.0` is the first version anyone is asked to depend on. After that the `0.x` lane applies: a breaking change bumps the minor, a fix bumps the patch, exactly as `release.md` already says.

Why alphas and not a straight `0.1.0` (what spec 158 proposed): the alpha lane gives a release cadence without a stability promise. pip and uv hide pre-releases from anyone who has not asked for them, so an alpha cannot surprise a host that pinned nothing. The pipeline gets exercised on seven platforms before a number that matters rides on it. And the step from the last beta to `0.1.0` is a suffix, not a build.

One line: yank 0.0.20 to 0.0.22, ship `0.1.0a1` now and keep shipping alphas, let `0.1.0b1` mean "the surface is frozen", and let `0.1.0` mean "depend on this".

## Decisions this spec takes

Taken by Clay on 2026-10-15 in the conversation that cut the spec. They are listed here so they can be overturned in one place; the durable home is `../../standards/release.md`, which item 8 rewrites.

1. **0.0.20, 0.0.21 and 0.0.22 are yanked on PyPI.** Yanking keeps the files and stops default resolution from choosing them; only an exact `==0.0.22` pin still gets one. The yank reason is the same sentence on all three: *Previous-generation API, superseded by the 0.1.0 rebuild; nothing from 0.0.x carries over.* Yanking is reversible, deletion is not; vfs yanks.
2. **The next version is `0.1.0a1`**, a PEP 440 alpha pre-release of `0.1.0`. Not `0.0.23` (the number says "another patch of the old thing"), not `0.1.0` final (a stability claim the surface cannot yet back), not CalVer (`release.md` adheres to SemVer, and a `2026.x` number can never sort below itself again).
3. **The lane has three stages, named by the suffix.**

   | Stage | Numbers | What may change between releases | Who it is for |
   |---|---|---|---|
   | alpha | `0.1.0a1`, `a2`, … | anything: verbs, models, result shapes, the schema | the repo's own hosts and anyone who asked for `--pre` |
   | beta | `0.1.0b1`, `b2`, … | bugs only; a breaking fix is allowed if a bug forces it and the changelog says so | hosts preparing to depend on 0.1.0 |
   | final | `0.1.0` | nothing; the next change is `0.1.1` or `0.2.0` | everyone |

   An `rc` stage is not planned; a beta that holds becomes the final. Entry to beta and to final is by criteria, not by date (item 4 and the marker in item 5).
4. **Beta begins when the public surface is frozen.** The public surface is the set of verbs and their signatures, the `Result` shapes they return, the storage protocols a backend implements, the row schema (`SCHEMA_FORMAT_VERSION`), and the MCP surface if it exists by then. "Frozen" means: no active spec would change it, and any spec that would is deferred to `0.2.0`. Clay calls the freeze explicitly; a release note records the call.
5. **Final `0.1.0` ships when a beta has held.** Proposed meaning: the current beta has been the current release for at least two weeks, no breaking fix was needed in that time, and the four real-engine legs (Postgres, MariaDB, SQL Server, Oracle) pass from the *published wheel*, not a checkout. `[NEEDS CLARIFICATION: is this the bar, or does 0.1.0 also wait for a feature — the MCP surface, a shipped SupportsRun storage, the version-row read side (spec 161)? Leaning: the bar above and no feature gate; 0.x minors exist precisely so features can keep arriving after 0.1.0.]`
6. **Cadence: an alpha per landed batch, cut by hand.** When one or more specs land that change the public surface or fix something a host hit, the next alpha ships. There is no fixed clock and no automation that publishes from `main`; a nightly `0.1.0.devN` lane is out of scope (see *Out of scope*).
7. **The classifier follows the stage.** `Development Status :: 3 - Alpha` through the alphas, `4 - Beta` from `0.1.0b1`, and it stays at Beta through the whole `0.x` lane until `1.0.0` says Production.

## The resolver facts

These decide what a host sees after the yank, and they are the reason the yank is safe to do before `0.1.0` final. Executed 2026-10-15 with the `packaging` library the project already depends on; pip's finder calls `SpecifierSet.filter` with `prereleases=None` and inherits every line below.

| Request | Candidates on the index | Result |
|---|---|---|
| `pip install vfs-py` | only alphas (finals yanked) | installs the newest alpha — the empty specifier falls back to pre-releases when no final exists |
| `pip install vfs-py` | a final exists beside alphas | installs the final; alphas hidden |
| `pip install "vfs-py<0.2"` | only alphas | **fails, no matching distribution** — a non-empty specifier without a pre-release marker never falls back |
| `pip install "vfs-py>=0.1.0a1,<0.2"` | only alphas | installs the newest alpha — the `a1` in the specifier is the opt-in |
| `pip install --pre vfs-py` | anything | installs the newest version of any kind |
| `pip install vfs-py==0.0.22` | 0.0.22 yanked | installs it, with a yank warning — the exact pin is the one escape hatch |

uv's default pre-release strategy is `if-necessary-or-explicit`, which reaches the same answers for the first two rows and the fourth, and resolves the third row too (uv judges "all versions are pre-release" per package, not per specifier). uv skips yanked versions unless the pin is `==`, like pip.

Consequences the spec acts on:

- After the yank and before `0.1.0`, a **bare** `pip install vfs-py` gives the newest alpha. That is the behaviour wanted: the README's one-line install keeps working and installs the rebuild.
- The README's **pin guidance must carry the pre-release marker**: `vfs-py>=0.1.0a1,<0.2`. A host that writes `vfs-py<0.2` from habit gets a resolution failure under pip, and the README says why.
- The README's install section is verified against the real index after `0.1.0a1` publishes (acceptance item 7), because the table above is `packaging`'s rule and the index can differ from the rule in exactly one way: if a yank is missed, the first row installs 0.0.22 instead.

## What is wrong today (verified 2026-10-15 at `ac5c515`)

Every item is a finding from the dropped spec 158's review, re-checked against the live tree, plus the two the alpha lane adds (items 1, 2).

1. **The bump script cannot write a pre-release.** `scripts/bump_version.py` matches `\d+\.\d+\.\d+` only, so `0.1.0a1` is unreachable and, once written by hand, `--patch` would fail to find the version at all.
2. **The version lives in three files.** `pyproject.toml` (the source of truth maturin reads), `src/vfs/__init__.py` (`__version__ = "0.0.22"`, a hand-kept copy) and `uv.lock` (which the bump script does not touch, so the lock goes stale on every bump). The seam in `rendering/seam.py` already reads versions through `importlib.metadata`, so the pattern is in the tree.
3. **The publish matrix has never run.** `publish.yml` triggers only on a published release; there is no `workflow_dispatch`, so the only way to find out whether seven wheels build is to cut a release.
4. **One runner is retired.** The macOS x86_64 leg pins `macos-13`, retired by GitHub in December 2025.
5. **Nothing checks the tag against the version.** A release tagged `v0.1.0a2` on a `main` still at `0.1.0a1` would publish a second `0.1.0a1`, which PyPI refuses, after a seven-platform build.
6. **The maturin floor admits versions that cannot bootstrap Rust.** `maturin>=1.8,<2.0`; the sdist fallback needs `>=1.8.4`.
7. **The changelog's `[Unreleased]` is previous-generation residue**: `VFSObject → VFSEntry`, `DatabaseFileSystem`, the MSSQL `FREETEXTTABLE` rewrite. None of it exists in `src/`.
8. **The README says PyPI ships the old API** in two places (the banner at line 19 and *Released:* at line 135), which stops being true at the yank and must change in the same landing.
9. **The release standard describes a world with no pre-releases.** `release.md`'s *When to release* has three rungs, its step 3 offers three flags, and its *Before the first v2 release* section is a fact list waiting for a spec to consume it. This spec is that spec.
10. **musllinux wheels publish but do not install.** `sqlite-vec`, a core dependency, ships no musl wheel and no sdist. Not fixable here; the README says so.
11. **`crates/vfs-core/Cargo.toml` carries its own `0.1.0`** and a comment naming `vfs._accel`. maturin reads the project version, so the crate number is inert; the comment is wrong.

## Scope — what lands

Ordered as the first alpha needs them. Items 1 to 6 are code and config; 7 to 9 are the release itself; 10 is the standard.

1. **One source of truth for the version.** `src/vfs/__init__.py` reads `__version__` from `importlib.metadata.version("vfs-py")` at import (top-of-file import, per the import rule). `pyproject.toml` is the only file that states the number. The bump script runs `uv lock` so `uv.lock` follows. A test pins `vfs.__version__ == importlib.metadata.version("vfs-py")` so the seam cannot drift back to a literal.
2. **The bump script learns the lane.** `scripts/bump_version.py` parses with `packaging.version.Version` instead of a regex and gains, beside `--major/--minor/--patch`:
   - `--pre {a,b,rc}`: on a final, combine with a part flag to open the lane (`0.0.22 --minor --pre a → 0.1.0a1`); on a pre-release of the same letter, increment (`0.1.0a1 → 0.1.0a2`); on a lower letter, start the new stage at 1 (`0.1.0a4 --pre b → 0.1.0b1`). Moving backwards (`b → a`) is refused.
   - `--final`: strips the suffix (`0.1.0b3 → 0.1.0`); refused on a final.
   - `--set X`: writes an explicit PEP 440 version, for the cases the rules do not cover. It prints `old → new`, rewrites `pyproject.toml`, runs `uv lock`, and touches nothing else. Covered by a test under `tests/` that drives it against a scratch `pyproject.toml`.
3. **`publish.yml` can be dry-run and refuses the wrong tag.**
   - Add `workflow_dispatch` so the matrix runs from `main` without a release; on a dispatch the publish job is skipped and the wheels are kept as workflow artifacts.
   - Add a first step in every job that reads the project version (`uv run python -c "import tomllib..."` or `grep`) and, on a release event, fails unless `github.event.release.tag_name == "v" + version`.
   - `macos-13 → macos-15-intel`.
   - The release trigger stays `release: [published]`, which fires for pre-releases marked as such on GitHub.
4. **`maturin>=1.8.4,<2.0`** in `[build-system]`. Fix the Cargo.toml comment (`vfs._accel → vfs._native`); leave the crate version, it is inert and documented as such in the comment.
5. **The changelog starts over.** Delete the `[Unreleased]` residue. Write `[0.1.0a1] — <release date>` fresh with one *Rebuild* paragraph (ground-up; nothing from 0.0.x carries over; 0.0.20 to 0.0.22 yanked and why) and the Keep-a-Changelog groups listing the public surface that exists: the verbs by name, the storage backends, the dialects, the permission ladder, the graph walk. Each later alpha adds its own `[0.1.0aN]` section; `[Unreleased]` collects between releases as before. The *Breaking* group is allowed and expected in alpha sections.
6. **The README tells the truth after the yank.** The banner at line 19 drops the sentence about 0.0.22 and says instead that the package is in alpha, that `pip install vfs-py` installs the newest alpha, and how to pin (`vfs-py>=0.1.0a1,<0.2`, with the one-line reason the marker is needed). The *Released:* bullet at line 135 points at the newest alpha and the changelog. An *Install* note says Alpine (musl) cannot resolve `sqlite-vec` and names the workaround (a glibc image). The README ships in the wheel, so this lands before the tag.
7. **Dry-run the matrix.** Dispatch `publish.yml` from `main` once the above has landed and confirm seven wheels and an sdist build. Fix whatever breaks before any tag exists. This is the step spec 158 would have skipped.
8. **Yank on PyPI.** Through the project's release pages on pypi.org (there is no `uv` or `twine` command for it), yank 0.0.20, 0.0.21 and 0.0.22 with the reason in decision 1. Then edit the three GitHub releases' bodies to add the same line at the top; GitHub will keep `v0.0.22` marked *Latest* until a non-pre-release ships, because that marker ignores pre-releases, and the body line is what tells a visitor it is dead.
9. **Cut `0.1.0a1`.** `bump_version.py --minor --pre a`, commit `Bump version to 0.1.0a1, update changelog`, push, wait for Tests green, then `gh release create v0.1.0a1 --prerelease --title "v0.1.0a1"` with notes mirroring the changelog section, then watch the publish run. The `--prerelease` flag is mandatory on every alpha and beta release; the standard says so.
10. **Rewrite `../../standards/release.md`.** *When to release* gains the three-stage table from decision 3 and the entry rules from decisions 4 and 5. Step 3 lists the new flags. Step 7 adds `--prerelease` for any suffixed version. The *Before the first v2 release* section is deleted: each of its facts is either fixed by this spec or restated as a permanent rule (the musl note, the tag check). *The resolver facts* table above moves there as the permanent record of what a bare install does in each stage.

## Out of scope

- **A nightly `0.1.0.devN` lane** published from every `main` push. Useful later for hosts that track the tip; it needs a second workflow and a dev-number scheme (commit count, or date). Parked; revisit if a host asks for it.
- **Trusted-publisher setup on PyPI.** `publish.yml` already uses `uv publish --trusted-publishing always` and the `pypi` environment; if the first publish run fails on authentication, that is a one-time fix in PyPI's settings, not a spec change.
- **Fixing the musl install.** Upstream `sqlite-vec` ships no musl artifact. vfs documents it.
- **Any change to what the verbs do.** An alpha ships the tree as it is.
- **Deleting the 0.0.x releases.** Yank, do not delete; an exact pin from an old project must keep resolving with a warning.

## Acceptance criteria

The first seven are checked once at `0.1.0a1`; the rest hold for every release the lane cuts.

1. `pip install vfs-py` on `python:3.13-slim` (x86_64 and aarch64, no compiler, no Rust) with no pin and no `--pre` installs `0.1.0a1`, and `python -c "import vfs, vfs.native; print(vfs.__version__)"` prints `0.1.0a1`.
2. `pip install "vfs-py<0.2"` on the same image fails with *no matching distribution*, and the README's pin guidance explains it.
3. `pip install vfs-py==0.0.22` still installs, with pip's yank warning.
4. pypi.org shows 0.0.20, 0.0.21 and 0.0.22 as yanked with the decision-1 reason, and lists seven wheels and one sdist for `0.1.0a1`.
5. The `workflow_dispatch` dry run (scope item 7) went green on all eight jobs before the tag existed, and its run id is in the spec's landing notes.
6. `CHANGELOG.md` has no `[Unreleased]` content older than the rebuild and a `[0.1.0a1]` section dated the release day.
7. The README nowhere says PyPI ships the previous-generation API.
8. A release whose tag does not equal `v` + the project version fails `publish.yml` in its first step, on every job, before any wheel is built (pin with a deliberate mismatched dispatch, or a unit test of the check script if it is factored into `scripts/`).
9. `scripts/bump_version.py` is tested in `tests/` for every transition in scope item 2, including the two refusals, and `uv.lock` matches `pyproject.toml` after any bump.
10. `vfs.__version__` is read from distribution metadata and a test pins the equality.
11. `scripts/ci.sh` is green after items 1 to 6; `ruff`, `ruff format --check` and `ty` at zero; coverage at 100 % (the `__init__.py` read is one line and the test covers it).

## Landing notes

(Filled in on landing: the dry-run id, the publish run id, the measured wheel sizes per platform against the 50 MB budget, anything the first real run of the matrix taught, and the date of the yank.)
