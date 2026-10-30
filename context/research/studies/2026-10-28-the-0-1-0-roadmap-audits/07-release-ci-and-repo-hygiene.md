# Audit — release engineering, CI, quality gates, packaging, repository hygiene, context-pipeline health

Audited 2026-10-28 at `90f5883` (main). Read-only. Labels: READ / EXECUTED / INFERRED. Caveat: the checkout is a **shallow clone of 50 commits** (EXECUTED: `.git/shallow` exists, `git rev-list --count HEAD` = 50; `git tag` is empty). The oldest visible commit is `3e5e9cf` (2026-09-06). Every "last touched" below is therefore an upper bound: a file whose only visible commit is `3e5e9cf` was last changed **on or before** 2026-09-06. GitHub Actions history was read through `gh run list` (REST), which is not shallow.

---

## 1. Built today, with evidence

### 1.1 CI workflows (`.github/workflows/`) — READ

| Workflow | Trigger | What it runs | Last run on `main` (EXECUTED, `gh run list`) |
|---|---|---|---|
| `test.yml` "Tests" | push to `main` + PR, path-filtered to `src/**`, `tests/**`, `crates/**`, `Cargo.*`, `pyproject.toml`, `.github/workflows/**` | matrix py 3.11/3.12/3.13/3.14; `uv sync --all-extras --group dev --group docs`; `ruff check`, `ruff format --check` on every leg; `ty check` + `pytest --cov --cov-fail-under=100` + Sybil docs fences (`pytest docs README.md -n 0`) + codecov upload on 3.13 only | success, 2026-10-28 (6 m 15 s) |
| `test-dialects.yml` "Dialect tests" | push to `main` + PR, path-filtered to storage/models/tests/compose/pyproject; `workflow_dispatch`; **no schedule** (dropped 2026-10-13 `242ca9f`) | four legs (postgres, mariadb, mssql, oracle) from `docker/compose.test.yml`, `uv sync --extra <dialect> --extra documents --group dev`, SQL readiness probe, `pytest -m <dialect> -n 0` | **failure, 2026-10-28** — mssql leg died at *Install ODBC driver* (37 s); postgres, mariadb, oracle green. The job's cache key names `ubuntu-26.04` while the workflow hardcodes `packages.microsoft.com/config/ubuntu/24.04/prod.list` (INFERRED cause: `ubuntu-latest` rolled to 26.04 and the apt list is pinned to 24.04). The previous 4 pushes were all green. |
| `publish.yml` "Publish to PyPI" | `release: [published]` **only** — no `workflow_dispatch` | 7 wheel jobs (`PyO3/maturin-action@v1`, abi3-py311): linux x86_64 + aarch64 manylinux_2_28, musllinux_1_2 x86_64 + aarch64, macos-15 arm64, **`macos-13` x86_64 (retired runner)**, windows-latest x64; sdist job; publish job gated by a 50 MB wheel-size loop then `uv publish --trusted-publishing always` under the `pypi` environment | last run **v0.0.22, 2026-04-23, 12 s** (EXECUTED). A 12-second run cannot be the seven-platform matrix; `release.md` says v0.0.22 used a two-job workflow and the matrix was added 2026-08-16. **The matrix has never run.** |
| `deploy-docs.yml` | push to `main` on `docs/**`/`mkdocs.yml`; `workflow_dispatch` | `uv pip install mkdocs-material`, `mkdocs build --clean`, `actions/deploy-pages@v4` | success 2026-10-15 (EXECUTED). Docs are live at `https://claygendron.github.io/vfs/` (INFERRED from `site_url` + green deploy; the Pages API is blocked through the proxy). |
| `vfs-app.yml` | push/PR on `vfs-app/**` | bun install/lint/typecheck/test/build | not queried |

Other facts (READ): no `.pre-commit-config.yaml` exists although `pre-commit>=4.0` sits in the dev group; no `dependabot.yml`, no `CODEOWNERS`, no `codecov.yml` (codecov runs with a `CODECOV_TOKEN` secret and default settings).

### 1.2 The local gate `scripts/ci.sh` — READ
Mirrors the 3.13 leg exactly: `uv sync --all-extras --group dev --group docs`, `ruff check`, `ruff format --check`, `ty check`, `pytest --cov --cov-fail-under=100`, docs fences, then **`check_wheel_size`** (`uv build --wheel` into `target/wheels-ci`, budget `WHEEL_BUDGET_MB=50`). Last changed 2026-10-10 (`d791d18`, sys.monitoring coverage core). It is the only place the wheel is built before a tag.

### 1.3 Packaging — READ
- `pyproject.toml`: `name = "vfs-py"`, **`version = "0.0.22"`**, `requires-python >= 3.11`, classifiers 3.11–3.14 + `Development Status :: 3 - Alpha`, `[build-system] maturin>=1.8,<2.0` (floor not yet 1.8.4), `[tool.maturin]` module `vfs._native`, manifest `crates/vfs-core/Cargo.toml`. Extras: openai, langchain, embed-local, postgres, mssql, mariadb, oracle, pdf/docx/pptx/xlsx, `documents`, `all`. Core deps include `sqlite-vec>=0.1.6` (the musl blocker).
- `src/vfs/__init__.py` line 1: `__version__ = "0.0.22"` — a hand-kept literal.
- `uv.lock` line 3657: `version = "0.0.22"`.
- `crates/vfs-core/Cargo.toml`: `version = "0.1.0"` (inert; maturin reads the project version) and the feature comment still says `vfs._accel`.
- `Cargo.toml` workspace: edition 2024, release profile `lto = "thin"`, `codegen-units = 1`.
- `scripts/bump_version.py`: regex `\d+\.\d+\.\d+` on `pyproject.toml` and `__init__.py`; `--major/--minor/--patch` only; does not run `uv lock`. Cannot emit `0.1.0a1`.
- PyPI (EXECUTED, `https://pypi.org/pypi/vfs-py/json`): latest `0.0.22`; releases 0.0.20/0.0.21/0.0.22 present, **none yanked**. GitHub releases (EXECUTED, REST): v0.0.22 2026-04-23, v0.0.21, v0.0.20, v0.0.18 — all `prerelease: false`.
- Trusted publishing: the workflow asks for it (`--trusted-publishing always`, `environment: pypi`, `id-token: write`) and **it has never been exercised** (the v0.0.22 run predates the switch to `uv publish` on 2026-08-25 per `release.md`). INFERRED: whether the PyPI side has a trusted publisher configured for `publish.yml` is unknown until the first run.

### 1.4 Quality gates in `tests/` and the standards — READ
- Suite: 2,992 `def test_` functions across 127 files (EXECUTED `grep`); `addopts = -n auto --dist worksteal`; markers `slow`, `postgres/mariadb/mssql/oracle` deselected by `tests/conftest.py` when the env URL is unset; `fail_under = 100` with `sysmon` core.
- `tests/test_dependencies.py`: one test — importing every `vfs.*` module in a fresh interpreter never loads numpy.
- `context/standards/testing.md` (114 lines): stance, layout, "pins land with their mutant", engine legs reentrant, docs examples are tests. **Stale**: the *Running* section names `tests/test_database_fs.py` (does not exist) and a `--mssql` flag (no `addoption` anywhere; the engine legs select by env URL). `tests/conftest.py`'s own docstring also still says "see `--mssql`".
- `context/standards/tooling.md`: says build backend **hatchling** (it is maturin), ruff/ty via `uvx` (both are locked dev-group deps), and `uv pip install -e ".[all]"` (CLAUDE.md says `uv sync --all-extras --group dev`). `CONTRIBUTING.md` repeats the `uv pip install` recipe; `docs/contributing.md` is a diverged copy (EXECUTED `cmp`: differ).
- `context/standards/quality-rubric.md`: 8 dimensions; §8 *Repo hygiene & delivery* (weight 5) requires "no generated artifacts, scratch notes, or one-off documents at the root" and "archived trees shrinking". `grades/` holds one entry, `2026-07-16-quality-baseline-review.md` — no grade since the rebuild.
- `context/standards/release.md`: three-rung SemVer *When to release*, a *Before the first v2 release* fact list (verified 2026-10-08), the 8-step cut procedure that still says the bump script "updates both pyproject.toml and `__init__.py`". No pre-release stage exists in it yet. The constitution still defers API versioning/deprecation to a **pending `versioning.md`** that does not exist.
- `.claude/skills/` (10 skills, READ descriptions): `adversarial_review`, `code_review` (five-agent suite), `contract_review`, `db_test` (Docker engine legs end to end), `ownership_review`, `scale_review`, `teach`, `test_review`, `test_suite` (inner loop + `scripts/ci.sh` + engine legs), `verify_findings`. These are the team's review and gate process; none covers "cut a release".

### 1.5 Docs — READ
`mkdocs.yml` (material theme, Diátaxis nav, `site_url` set) and 29 files under `docs/`. Five pages exist but are **not in the nav**: `explanation/the-namespace-is-the-interface.md`, `explanation/why-mounts-expand-agent-capability.md`, `explanation/write-pipeline.md`, `how-to/share-a-folder-with-grants.md`, `how-to/walk-the-edges-around-a-file.md`. `docs/index.md` and the tutorial carry no `pip install` line or version claim (EXECUTED grep: no hits), so the install story lives only in `README.md`.

### 1.6 Context pipeline — counts (EXECUTED `ls`/`grep`)
- 88 ADR files (87 numbered + README); 155 research memos; 40 archived open questions; **42 open-question headings** in `open-questions.md` (two are the *Format*/*Lifecycle* preamble, so ~40 live entries); exactly one touches 0.1.0: *"What makes `0.1.0` final: a held beta alone, or a feature too?"* (open, "Clay's call, due before `0.1.0b1`").
- `context/specs/STATUS.md` exists — a 1,168-line append-only snapshot log, last entry 2026-10-24, headed "this is a snapshot, not a live index".
- 31 active spec folders, 108 archived.

---

## 2. In flight

- **Spec 166 (the release lane)**: READ in full; status *draft*. **None of scope items 1–6 has landed**: `__version__` is still a literal, the bump script is still the regex, `publish.yml` has no `workflow_dispatch`, no tag check and still `macos-13`, maturin floor still `>=1.8`, the `_accel` comment is still there, `CHANGELOG.md` `[Unreleased]` is still the `VFSObject → VFSEntry` / `DatabaseFileSystem` / `FREETEXTTABLE` residue (READ lines 7–21), the README banner (line 19) and *Released:* bullet (line 135) still say PyPI ships the previous-generation API. The 2026-10-15 amendment says **`0.1.0a1` carries spec 167 (the shell pipeline core, five slices A–E)** and spec 167 is "Not started" (READ). So as the spec is written, a1 is blocked on an unstarted five-slice feature.
- **Dialect tests red on `main`** since 2026-10-28 (the mssql ODBC install step). First red push-run since the schedule was dropped.
- **Specs built but still in `active/`**: 165 (landed 2026-10-14, ADR 080 accepted), 162 (both slices built 2026-10-11; `trash.py`/`versions.py` committed as `3229889`/`0e0f7d8` 2026-10-12/13 — the "uncommitted, awaiting Clay's review" status lines in spec 162, spec 161 and STATUS.md are stale), 152 slices A/B (landed `6db7053`, `be504a3`; C/D not started), 173 (spike executed and reported 2026-10-16).
- **ADR 087 kernel program**: specs 174–181 drafted 2026-10-24, all "not started", 36 `[NEEDS CLARIFICATION]` markers between them (174:2, 175:6, 176:4, 177:3, 178:2, 179:3, 180:9, 181:7). Spec 181 regroups the **public surface** — it is the spec that decides what "frozen" means for beta entry.

---

## 3. Gaps vs the 0.1.0 goal

1. **No shippable version number exists.** PyPI still serves 0.0.22 unyanked; nothing in the tree can mint a PEP 440 pre-release.
2. **The publish matrix is untested.** Seven wheel jobs, one on a retired runner, never executed; the first run of the matrix would also be the first alpha unless a dispatch is added first.
3. **The "a1 = spec 167" coupling** means the lane cannot start until the shell lands, even though spec 166 scope items 1–6 are mechanical and independent of any feature.
4. **No definition of the frozen surface.** Spec 166 decision 4 freezes "verbs and signatures, Result shapes, storage protocols, `SCHEMA_FORMAT_VERSION`, the MCP surface if it exists". Spec 181 (not started) regroups exactly that; spec 174 proposes removing the public `overwrite=` argument; ADR 087 pins 3, 12, 16, 17 (rename `delete`/`move`, resumption key placement, namespacing, replace identity) are pending Clay. Beta cannot be called until these are decided.
5. **The engine legs do not run from a wheel.** `test-dialects.yml` runs from a checkout with `uv sync`; spec 166 decision 5 wants them "from the published wheel". No workflow does that.
6. **Standards drift**: `tooling.md` (hatchling, uvx, `uv pip`), `testing.md` *Running*, `release.md` steps 3/5, `CONTRIBUTING.md` and `docs/contributing.md` all describe a tree that no longer exists. `roadmap.md` is the Q2/Q3 "Plan 9 wave" (specs 015–024, all archived); `ROADMAP-v0.1.0.md` at the root is the 2026-05-18 YC/FastAPI/SSO plan.
7. **No versioning/deprecation policy** (`versioning.md` pending since the constitution was written) — needed by the `0.x` lane the moment `0.1.0` final ships.
8. **Repo-hygiene rubric §8 is failed mechanically** by the root (see §4 table) and by `coverage.json` being tracked.

---

## 4. Risks

| Risk | Evidence | Severity |
|---|---|---|
| First matrix run fails on a `macos-13` job that cannot be scheduled, or on trusted-publishing auth, during a real release | `publish.yml` READ; `release.md` fact list | High — the fix is cheap (dispatch first) |
| `pip install vfs-py` keeps installing 0.0.22 until the yank is done, and a missed yank makes the a1 README lie | PyPI EXECUTED: none yanked | High |
| The mssql engine leg stays red because `ubuntu-latest` moved to 26.04 and the apt list is pinned to 24.04 | run 40689014566 EXECUTED | Medium — every storage push now shows a red check |
| Beta is called with the surface still moving (specs 174, 176, 181 all change public arguments/return fields) | spec texts READ | High for the lane's credibility |
| musllinux wheels publish but cannot install (`sqlite-vec` has no musl artifact) | `release.md`, spec 166 item 10 | Low — document; consider dropping the two musl jobs from the matrix to save a third of the build minutes |
| Three stale "uncommitted" status lines (162, 161, STATUS.md) could lead a session to re-land or re-review work already on `main` | git log EXECUTED | Medium |
| `STATUS.md` at 1,168 lines is read by every planning session; its cost grows per entry and it already contradicts the specs | READ | Medium |
| The shallow-clone + no-tags environment means a release cut from a cloud session cannot see `v0.0.22` or compute `--prerelease` notes diff links | EXECUTED | Low — cut releases from a full checkout |
| Codecov upload uses a token secret with no `codecov.yml`; a flaky upload fails the 3.13 leg | `test.yml` READ | Low |

---

## 5. Proposed roadmap stories

### R1 — Release plumbing (spec 166 scope items 1–4, decoupled from spec 167)
Acceptance:
1. `vfs.__version__` is read from `importlib.metadata.version("vfs-py")`; a test pins equality.
2. `scripts/bump_version.py` parses with `packaging.version.Version`, gains `--pre {a,b,rc}`, `--final`, `--set`, refuses `b→a` and `--final` on a final, runs `uv lock`; a test under `tests/` drives every transition against a scratch `pyproject.toml`.
3. `publish.yml` has `workflow_dispatch`; on dispatch the publish job is skipped and wheels upload as artifacts; every job's first step fails on a release when `tag_name != "v" + version`.
4. `macos-13` → `macos-15-intel`; `maturin>=1.8.4,<2.0`; the Cargo feature comment says `vfs._native`.
5. `release.md` step 3 lists the new flags; its "two files" sentence is gone.
6. `scripts/ci.sh` green; ruff/format/ty zero; coverage 100.

### R2 — Dry-run the matrix and fix the engine leg
1. A `workflow_dispatch` run of `publish.yml` from `main` is green on all 8 jobs; its run id is recorded in spec 166's landing notes with each wheel's size.
2. Decide and record musllinux: either the two musl jobs are removed with a changelog/README note, or they stay and the README says the install fails on Alpine.
3. `test-dialects.yml` mssql leg installs msodbcsql18 on the current `ubuntu-latest` (pin `ubuntu-24.04` or derive the apt list from `lsb_release`); the next storage push is green on all four legs.
4. Trusted publishing is confirmed configured on PyPI for `ClayGendron/vfs` / `publish.yml` / environment `pypi` (a note in `release.md`).

### R3 — Cut `0.1.0a1` from the tree as it stands (drop the "a1 carries 167" amendment, or re-letter: a1 = the tree, a2 = the shell)
1. `CHANGELOG.md` has no pre-rebuild `[Unreleased]` content; `[0.1.0a1] — <date>` lists the verbs, backends, dialects, the permission ladder, the graph walk, trash-as-tombstone, binary bodies, with a *Breaking* group ("nothing from 0.0.x carries over").
2. README line 19 and 135 no longer say PyPI ships the previous-generation API; pin guidance reads `vfs-py>=0.1.0a1,<0.2` with the one-line reason; the Alpine note is present.
3. 0.0.20, 0.0.21, 0.0.22 show as yanked on pypi.org with the decision-1 reason; the three GitHub release bodies carry the same line.
4. `gh release create v0.1.0a1 --prerelease` triggers a green publish; pypi.org lists the wheels and one sdist for `0.1.0a1`.
5. On `python:3.13-slim` x86_64 and aarch64, `pip install vfs-py` installs `0.1.0a1` and `python -c "import vfs, vfs.native; print(vfs.__version__)"` prints it; `pip install "vfs-py<0.2"` fails with *no matching distribution*; `pip install vfs-py==0.0.22` installs with a yank warning.
6. `Development Status :: 3 - Alpha` is the classifier.

### R4 — The engine legs from the published wheel (the beta/final gate)
1. A new workflow (or a `test-dialects.yml` input) installs `vfs-py==<version>` from PyPI into a clean venv with `--no-build-isolation` disallowed (no Rust, no C compiler on the runner) and runs the four `-m <dialect>` legs against the compose services.
2. It can be dispatched with a version argument and runs automatically after a green publish.
3. Its result for each beta is recorded in the release notes; `0.1.0` final requires a green run against the last beta.

### R5 — Freeze the public surface (the beta-entry decision)
1. Spec 181 (or a slimmer successor) lands with a written list of the public names, signatures, `Result` fields, storage protocols and `SCHEMA_FORMAT_VERSION` that `0.1.0` freezes; `docs/reference/api.md` matches it (a Sybil-checked table or an import test).
2. ADR 087 pins 3, 12, 16, 17 and spec 174's `overwrite=` removal are each decided by Clay, recorded in the ADR's *Pending Clay* section as resolved.
3. Every active spec is tagged `0.1.0` or `0.2.0+`; none tagged `0.2.0+` changes a frozen name.
4. Clay's freeze call is a dated line in `release.md` and in the `[0.1.0b1]` changelog section.
5. A `versioning.md` standard exists (what a breaking change is in `0.x`, the deprecation window, what the changelog *Breaking* group must say).

### R6 — Repository hygiene (root, standards, archived trees)
1. `git ls-files` at the root shows only: `CHANGELOG.md CLAUDE.md CONTRIBUTING.md Cargo.lock Cargo.toml LICENSE README.md conftest.py mkdocs.yml pyproject.toml uv.lock .gitignore .python-version` plus directories; the disposition table in §4a below is applied.
2. `coverage.json` is untracked and in `.gitignore` next to `coverage.xml`.
3. `tooling.md`, `testing.md` *Running*, `CONTRIBUTING.md`, `docs/contributing.md` and `tests/conftest.py`'s docstring describe the maturin/uv-sync/env-URL tree; `docs/contributing.md` is either the same file via `pymdownx.snippets` or deleted.
4. The five orphan docs pages are in `mkdocs.yml` nav or deleted; `mkdocs build --strict` passes.
5. `context/standards/roadmap.md` is rewritten as the 0.1.0 lane (R1–R6 + the feature stories the other audits propose) and `ROADMAP-v0.1.0.md` is deleted (its content is historical; `business/product-plan-2026-08.md` already holds the business plan).
6. `src2/` and `tests2/` are deleted or shrunk with a dated note of what remains unmined (`specs/archive/MINING.md` exists for this); rubric §8 "shrinking, not accreting" is measurable.

### R7 — Context-pipeline true-up (so the active set equals the 0.1.0 work)
1. Specs 165, 162, 152 (slices A/B as a closed spec; C/D re-cut as a new spec or an explicit `0.2.0` tag), 173 (spike) and 164's companions move to `specs/archive/` with landing notes; their stale "uncommitted" lines are corrected first.
2. Spec 161 is dropped (superseded: its write half landed in 162, its read half — `versions(path)`, `read(version=)`, retention — is owned by spec 180). Spec 051 is dropped or merged into spec 176/177 (the resumable model and the fault model are where a budget would live); spec 102 is re-cut against the tombstone delete (its premise — a path-rewriting scattered delete holding the topology lock — no longer exists after 162) or dropped; spec 080 stays research-only and is tagged `0.2.0+`.
3. `STATUS.md` is replaced by a ≤ 60-line live table (spec, status, tag, landing commit) regenerated from the spec status lines, with the 1,168-line history moved to `research/` as a dated memo or deleted (the archived specs already hold their own notes).
4. The 10 proposed ADRs (022, 058, 069, 081–087) each get a decision: ratified, amended, or withdrawn; the count of *Pending Clay* leans (ADR 086: 4; ADR 087: 6 pins + 2 spec forks) is zero before `0.1.0b1`.
5. `open-questions.md` entries resolved by 162/165/ADR 087 move to the archive; the 0.1.0 final-bar question is answered.

#### 4a. Root-level disposition (all READ; last-touched ≤ 2026-09-06 unless noted)

| Item | Finding | Recommend |
|---|---|---|
| `ROADMAP-v0.1.0.md` | 2026-05-18 plan: FastAPI service, SSO/OIDC, RBAC, OTel, web console, `src/vfs/client.py` (does not exist), `context/stories/` (gone). Every phase contradicts ADRs 068 (open in process), 085 (MCP only), 087 (kernel). | **Delete**; replace with the rewritten `context/standards/roadmap.md`. |
| `write-pipeline.md` | A plan-then-execute note on `writes.py`; a different, older text than `docs/explanation/write-pipeline.md` (which is itself not in the nav). | **Delete** the root copy; put the docs page in the nav after checking it against today's `writes.py`. |
| `pr_description.md` | A single PR's description. | **Delete**. |
| `Validate SQLModel on all Non-Database Sourced Data.md` | An upstream SQLModel issue write-up (two copies of the same text inside); vfs no longer uses SQLModel. | **Delete** (or `context/research/` if Clay wants the record). |
| `grep_glob research/` | 2026-04-24 Postgres pushdown research; notebooks reference `DatabaseFileSystem`/`VFSResult`. | **Move** to `context/research/2026-04-24-grep-glob-pushdown/` (append-only research), then stop editing. |
| `business/` | brand, product plan 2026-08, AIE submission, October talk slides, `business/vfs-app/` design hand-off. | **Keep** but out of the code root: `context/product/` already exists — move there, or a sibling repo. |
| `vfs-app/` | A bun/vite marketing site with its own CI workflow. | **Move** to its own repo (its only coupling is `vfs-app.yml`); otherwise keep and exclude from the wheel (`sdist` includes only `src`, `crates` by maturin default — INFERRED, verify on the dry run). |
| `vfs-brand/` | bun project with README/package.json only. | **Merge** into `vfs-app/` or delete. |
| `logos/` | 1.1 MB of PNGs + favicon previews + wordmark. | **Move** into `vfs-app/public` or `docs/assets`; keep one README logo. |
| `examples/` | 9 files; 5 reference `DatabaseFileSystem`, `VFSClient` or `VFSResult` — dead names. | **Delete** the dead five; keep/port the rest as Sybil-checked docs pages. |
| `coverage.json` | Tracked; `timestamp 2026-04-23` (pre-rebuild); not in `.gitignore` (only `.coverage*` and `coverage.xml` are). | **Delete** and ignore. |
| `src2/` (23 files, 636 K) and `tests2/` (47 files, 1.1 M) | Archived quarry; rubric §8 wants them shrinking. | **Delete** what `specs/archive/MINING.md` marks mined; list the remainder. |
| `context/standards/roadmap.md` | "Plan 9 wave 2026-Q2/Q3", specs 015–024 — all archived. | **Rewrite** as the 0.1.0 lane. |
| `context/open-questions.md` | ~40 live entries; several are answered by landed work (e.g. *Trash as a tombstone*, *Write preconditions on the wire* → spec 174, *Shell pipe payload* → ADR 083, *Result content typed blocks* → ADR 085). | **Sweep** to the archive in R7. |
| `CONTRIBUTING.md` / `docs/contributing.md` | Diverged copies, both with the `uv pip install -e` recipe. | **One source**, updated. |

---

## 6. Open questions Clay must decide

1. **Does `0.1.0a1` ship the tree as it stands, or wait for spec 167?** The 2026-10-15 amendment couples a1 to an unstarted five-slice feature. Recommendation: a1 = the tree this week; the shell is a2.
2. **The 0.1.0 final bar** (open-questions.md entry, "due before b1"): a held beta alone, or the MCP surface / a shipped `SupportsRun` too? Spec 166 leans (a).
3. **What is the frozen surface?** Flat names vs kernel-group namespaces (ADR 087 pin 16), `delete`/`move` vs `remove`/`rename` (pin 3), `overwrite=` removal (spec 174), resumption key on `Result` (pin 12), replace identity (pin 17). Each changes a public name; all must be settled before `0.1.0b1`.
4. **musllinux**: keep publishing wheels that cannot install, or drop the two jobs?
5. **Where do `vfs-app/`, `vfs-brand/`, `logos/`, `business/` live** — this repo or siblings?
6. **Delete or keep shrinking `src2/`/`tests2/`?**
7. **`STATUS.md`**: replace with a short generated table, or keep the log?
8. **Ratify or withdraw the ten proposed ADRs** (022, 058, 069, 081–087) before beta; which of ADR 086's four leans are decided now?
9. **Does a `versioning.md` standard land before `0.1.0` final** (the constitution has deferred it since the rebuild began)?

---

## 7. The concrete checklist to cut `0.1.0a1` this week

In order; each line is a commit or an external action.

1. Fix the mssql apt list in `test-dialects.yml` (pin `ubuntu-24.04` or derive the Ubuntu version); push; four legs green.
2. Land R1: `__version__` from metadata + test; bump script rewrite + test; `publish.yml` dispatch + tag check + `macos-15-intel`; `maturin>=1.8.4`; Cargo comment. `scripts/ci.sh` green.
3. Dispatch `publish.yml` from `main`; all 8 jobs green; record run id and per-wheel sizes in spec 166 landing notes. Decide musl.
4. Rewrite `CHANGELOG.md` (`[0.1.0a1]` fresh, residue deleted) and the README banner/Released/pin/Alpine lines; `pytest README.md` (Sybil) green.
5. Yank 0.0.20–0.0.22 on pypi.org with the decision-1 reason; edit the three GitHub release bodies.
6. `uv run python scripts/bump_version.py --minor --pre a` → `0.1.0a1`; commit `Bump version to 0.1.0a1, update changelog`; push; Tests green.
7. `gh release create v0.1.0a1 --prerelease --title "v0.1.0a1" --notes <changelog section>`; watch the publish run (from a full, non-shallow checkout so release notes can link `v0.0.22...v0.1.0a1`).
8. Verify from `python:3.13-slim` (x86_64, aarch64): bare install → `0.1.0a1`; `<0.2` fails; `==0.0.22` warns; `import vfs.native` works.
9. Rewrite `release.md` (three-stage table, the resolver facts, `--prerelease` in step 7, delete *Before the first v2 release*); move spec 166 to `archive/` with landing notes.

Definition of done for the lane, in one line each:
- **alpha**: the matrix is green on dispatch, the yank is done, every alpha is `--prerelease`, the changelog's alpha sections may carry *Breaking*.
- **beta**: Clay's dated freeze call; spec 181's surface list matches `docs/reference/api.md`; no active spec tagged `0.1.0` changes a public name; `versioning.md` exists; classifier `4 - Beta`.
- **final**: one beta current ≥ 14 days with no breaking fix; the four engine legs green **from the published wheel** (R4); the final-bar question answered; `0.1.0` cut by `--final`.
