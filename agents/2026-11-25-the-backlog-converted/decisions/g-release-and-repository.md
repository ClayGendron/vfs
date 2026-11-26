# Decisions verified: what makes 0.1.0 final, the sync facade, repository hygiene

Scope: rows D2, D26, D27, D28, D29, D30, D31, D32 and D39 of `context/standards/roadmap.md` section 16 (READ, context/standards/roadmap.md:1067-1111). The checkout read is at HEAD `09dad59` (EXECUTED, `git rev-parse --short HEAD`), not the `0ed462f` the brief names; the history is shallow, so commit `966e7441`, which the roadmap cites for D29, D31, D32 and D39, is not present (EXECUTED, `git cat-file -t 966e7441` fails). Each claim about those four rows is therefore checked against the tree as it stands, not against the commit.

Summary: eight of the nine rows are settled by landed work; D2 is settled in substance by the landed release standard, and only the stale wording of its roadmap row remains. No backlog spec has to carry any of the nine as an open decision.

## D2. 0.1.0 final is the held-beta bar plus the roadmap's `f` gate, and the beta freeze forbids rename, removal and change of meaning while allowing listed additions

Lean: the roadmap row says option (iii), the structural cut, is refused, and that the choice between (i) the bar alone and (ii) the bar plus the `f` gate is not ruled; it keeps the additive freeze rule as the lean (READ, context/standards/roadmap.md:1074).

Verification: settled-by-landed-work.

Decision text: "Final `0.1.0` ships when the current beta has been the current release for at least fourteen days with no breaking fix, the four real-engine legs pass from the published wheel, and every story the roadmap tags `f` has landed; a beta may fix bugs and add names listed under *Added*, and may not rename, remove or change the meaning of a public name."

Reason: option (ii) and the additive freeze are already the landed standard, not a lean. The archived release-lane spec took option (ii) as its decision 5 (READ, context/specifications/archive/166-the-release-lane-to-0-1-0/spec.md:84-86). It took the freeze rule as its stage table and decision 4 (READ, same file:75 and :80-82). Both are written into the release standard (READ, context/standards/release.md:14, :18, :19). Decided 2026-11-15: "MCP ships with 0.1.0", which refuses option (iii) (READ, context/standards/roadmap.md:1074, :1034). So the only part still open is wording: the roadmap row and section 2 say "Decision D2 confirms", when the archived spec and `release.md` already state the rule (READ, context/standards/roadmap.md:69). Option (i) would contradict the landed `release.md:19` (INFERRED).

Precedent: the landed release standard and spec 166, cited above. A beta rule that is looser than a feature freeze, allowing listed additions, matches the Keep-a-Changelog *Added* group the lane already uses (READ, context/standards/release.md:108). A public-standard check of CPython's beta rule failed because the host could not be reached (EXECUTED, WebFetch of devguide.python.org failed DNS resolution). No external source is cited.

Note for conversion: the roadmap row's "not ruled" text is stale against `release.md:18-19`. Correcting it is a roadmap edit, not a spec decision. `context/standards/versioning.md`, which story R5 asks for, still does not exist (READ, context/standards/roadmap.md:894, :938); that is R5's work, not an open question.

Specs affected: none carries the rule as a decision. The specs that cite the freeze cite it as a boundary and take it as written: context/specifications/active/2026-11-15-the-kernels-public-names-and-argument-families-are-ruled.md:61 and :144, and 181-the-public-surface-regrouped-by-kernel-group (which public names are frozen is R5's list) (READ).

## D26. The sync facade is a thread-loop wrapper with no new dependency, not an `anyio` portal

Lean: thread-loop, taken as written by the landed sync facade (READ, context/standards/roadmap.md:1098).

Verification: settled-by-landed-work.

Decision text: "The synchronous face owns one asyncio loop on one daemon thread and forwards each call through `asyncio.run_coroutine_threadsafe`; vfs takes no `anyio` dependency for it."

Reason: the design is built. `src/vfs/sync.py` owns a loop on a daemon thread (READ, src/vfs/sync.py:3, :651) and forwards each call through `run_coroutine_threadsafe` (READ, src/vfs/sync.py:721). `anyio` is not a declared dependency (EXECUTED, grep for `anyio` in pyproject.toml finds nothing). The decision is recorded as the archived spec's decision 1 (READ, context/specifications/archive/2026-11-06-the-sync-facade.md:60-62).

Precedent: the developer-experience audit compared four options: thread-loop, greenlet, anyio portal and unasync. It prototyped the thread-loop in both a plain script and a running loop (READ, context/research/studies/2026-10-28-the-0-1-0-roadmap-audits/06-developer-experience-sync-jupyter-etl.md:170-177). It found that `anyio` reaches the venv only transitively (READ, same file:111). It named anyio's portal as the fallback if Ctrl-C handling needed more (READ, same file:185). The landed facade cancels the in-flight call when an exception escapes the wait (READ, context/specifications/archive/2026-11-06-the-sync-facade.md:76). The fallback is not needed (INFERRED).

Specs affected: none carries it. Later verbs built by backlog specs, such as `Session.cli` in 167-the-shell-pipeline-core, must add a sync twin to pass the landed parity test (READ, context/standards/roadmap.md:816; INFERRED that 167 inherits this). 171-the-mcp-adapter-and-the-cli-tool keeps `serve()` async-native, as acceptance criterion 8 of story X1 already says (READ, context/standards/roadmap.md:826).

## D27. The facade may wrap an already-awaited file system, documented as pinned on SQLite only

Lean: yes, documented SQLite-only until pinned; taken as written by the landed sync facade (READ, context/standards/roadmap.md:1099).

Verification: settled-by-landed-work.

Decision text: "`VirtualFileSystem.wrap(fs)` takes a kernel the caller already built and may already have awaited; it is pinned on SQLite and documented as unproven on asyncpg, whose engine binds to the loop that first touched it."

Reason: the method and its stated gap are in the tree (READ, src/vfs/sync.py:132-139). They are the archived spec's decision 4 (READ, context/specifications/archive/2026-11-06-the-sync-facade.md:72-74). Stating the gap honestly follows AGENTS.md's rule to acknowledge a limit in the docstring rather than claim a guarantee (READ, AGENTS.md, *Production posture*).

Precedent: the audit's prototype ran the facade over a SQLite storage already touched on an outer loop (READ, context/research/studies/2026-10-28-the-0-1-0-roadmap-audits/06-developer-experience-sync-jupyter-etl.md:118). The same audit stated the asyncpg loop-affinity hazard (READ, same file:172, :179).

Specs affected: none. Pinning the asyncpg case would be new work for a later story, not a decision any backlog spec owns (INFERRED).

## D28. `Entry`, `DatabaseStorage` and `InMemoryStorage` are exported from the top-level `vfs` package

Lean: yes; built by ETL ergonomics (READ, context/standards/roadmap.md:1100).

Verification: settled-by-landed-work.

Decision text: "`from vfs import Entry, DatabaseStorage, InMemoryStorage` imports, and `vfs.__all__` lists all three beside the four face names."

Reason: the imports and `__all__` entries are in the tree (READ, src/vfs/__init__.py:14, :19-20, :26-32). The archived ETL-ergonomics spec records the ruling and its landing (READ, context/specifications/archive/2026-11-06-etl-ergonomics.md:1-3, :9).

Precedent: the package already exported the four face names for the same reason, one import line for the first script (READ, context/specifications/archive/2026-11-06-etl-ergonomics.md:3, :9).

Specs affected: 181-the-public-surface-regrouped-by-kernel-group, which adds `from vfs import chain` (READ, context/specifications/active/181-the-public-surface-regrouped-by-kernel-group/spec.md:310). It must keep the three exports in place, which holds under the freeze rule of D2 (INFERRED).

## D29. Stale examples are deleted, not archived beside `src2/`

Lean: delete; recorded as done on 2026-10-30 (READ, context/standards/roadmap.md:1101).

Verification: settled-by-landed-work.

Decision text: "A stale example is deleted, and git history keeps it; nothing under `examples/` is archived in the tree."

Reason: `examples/` holds only `glob_residuation.ipynb` and `search_walkthrough.ipynb` (EXECUTED, `ls examples`). There is no `src2/` left to archive beside (EXECUTED, `ls src2` fails). Commit `966e7441` is not in this shallow checkout, so the deletion is confirmed from the tree, not the commit (EXECUTED). Story X6's remaining work, running the live notebook in CI and an import-guard test, is build work, not a decision (READ, context/standards/roadmap.md:866-868).

Precedent: AGENTS.md says "Earlier generations of the code exist only in git history" (READ, AGENTS.md:46). The audit offered the same delete-or-archive choice and noted that git history keeps a deleted file (READ, context/research/studies/2026-10-28-the-0-1-0-roadmap-audits/06-developer-experience-sync-jupyter-etl.md:263, :299).

Specs affected: none; this is repository hygiene that no backlog spec carries.

## D30. The two musllinux wheel jobs are dropped, and the drop is noted

Lean: drop; done by the release lane and noted in `release.md` (READ, context/standards/roadmap.md:1102).

Verification: settled-by-landed-work.

Decision text: "vfs publishes no musl wheel while its core dependency `sqlite-vec` ships none; the install guide says Alpine cannot install vfs, and the musllinux jobs return when `sqlite-vec` publishes a musl wheel."

Reason: the release standard states the drop and its reason, and the condition for return (READ, context/standards/release.md:45, :169). The publish workflow carries the note (READ, .github/workflows/publish.yml:6). The install guide carries the Alpine note (READ, docs/how-to/install.md:27). A lint test pins that note (READ, tests/lint/test_code_shape.py:315, :328).

Precedent: two earlier packaging memos recommended musllinux jobs (READ, context/research/2026-08-16-rust-accelerator-packaging.md:36; context/research/2026-08-12-posting-path-rust-kernel.md:56). Both predate `sqlite-vec` becoming a core dependency. The landed reason, that a wheel which publishes but cannot install is a platform claim vfs cannot keep, supersedes them (READ, context/standards/release.md:169).

Specs affected: none; this is a release-process choice that no backlog spec carries.

## D31. `business/`, `vfs-app/`, `vfs-brand/` and `logos/` live outside this repository

Lean: sibling repositories, with `business/` under `context/product/` only if it must stay; recorded as done on 2026-10-30, with all four moved to a sibling checkout (READ, context/standards/roadmap.md:1103).

Verification: settled-by-landed-work.

Decision text: "The repository holds the Python package, its Rust crate, its tests, its documentation and the docs app; business, application, brand and logo material lives in sibling repositories."

Reason: none of the four directories is present, and `context/product/` does not exist (EXECUTED, `ls`). This matches AGENTS.md: `src/` and `tests/` are the whole live tree, and `docs-app/` is the one other tree (READ, AGENTS.md:46). The rest of story R6's root allow-list still differs from the tree: `skills-lock.json` is at the root and `SECURITY.md` and `THREAT_MODEL.md` are absent, and `__pycache__/` and `target/` show in the listing (EXECUTED, `ls`). Those are R6 and R8 build items, not part of this decision (READ, context/standards/roadmap.md:951-954).

Precedent: AGENTS.md:46, cited above; no external precedent sought, because the choice is repository scope.

Specs affected: none; this is repository hygiene.

## D32. `src2/` and `tests2/` are deleted

Lean: delete what `MINING.md` marks mined and list the rest; recorded as done on 2026-10-30 with both deleted whole (READ, context/standards/roadmap.md:1104).

Verification: settled-by-landed-work.

Decision text: "The earlier code generations `src2/` and `tests2/` are gone from the tree; git history holds them."

Reason: neither directory exists (EXECUTED, `ls src2 tests2` fails). The landed form, delete whole, is stronger than the lean's "delete the mined part and list the rest". It is consistent with AGENTS.md, which keeps earlier generations only in git history (READ, AGENTS.md:46). It is also allowed by story R6's criterion 3, which reads "deleted or shrunk" (READ, context/standards/roadmap.md:956). No list of unmined parts is owed, because git history keeps every part (INFERRED).

Precedent: AGENTS.md:46; the audit's hygiene item 6 (READ, context/research/studies/2026-10-28-the-0-1-0-roadmap-audits/07-release-ci-and-repo-hygiene.md:134).

Specs affected: none; this is repository hygiene.

## D39. The roadmap lives at `context/standards/roadmap.md` and the root `ROADMAP-v0.1.0.md` is deleted

Lean: yes; recorded as done on 2026-10-30 (READ, context/standards/roadmap.md:1111).

Verification: settled-by-landed-work.

Decision text: "The 0.1.0 roadmap is `context/standards/roadmap.md`; no roadmap file sits at the repository root."

Reason: `context/standards/roadmap.md` exists and `ROADMAP-v0.1.0.md` does not (EXECUTED, `ls`). AGENTS.md marks `context/` as the earlier layout that takes no new work until it is migrated (READ, AGENTS.md, *Development process and project knowledge*). The roadmap may therefore move again when `context/` is migrated to `documentation/` and `agents/`. That later move is a migration, not a reversal of this decision (INFERRED).

Precedent: the hygiene audit's item 5 (READ, context/research/studies/2026-10-28-the-0-1-0-roadmap-audits/07-release-ci-and-repo-hygiene.md:133).

Specs affected: none; this is repository hygiene.
