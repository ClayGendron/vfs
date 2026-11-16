# vfs: guide for contributors and coding agents

This file is the working agreement for anyone changing this repository, a person or a coding agent. It holds the rules that apply to every change. Each rule gives its reason, so it can be applied to a case it does not name. The [README](README.md) says what vfs is; this file says how work is done here.

vfs is governed data access for AI agents: one namespace of everything an agent can see, search, and change, with permissions enforced before anything is dispatched. It is a Python package (`src/vfs`) with a required Rust extension (`crates/vfs-core`).

In this file, **the developer** means the person directing the work: the person an agent is working for, or you.

Where the rest lives:

- [documentation/maintainers/how-we-work.md](documentation/maintainers/how-we-work.md): the two modes of work, guided and autonomous, the branches, and where prose lives. Read it before starting work.
- [context/README.md](context/README.md): the earlier pipeline and the shape of every document under `context/`, which holds until that tree is migrated.
- [context/standards/how-we-code.md](context/standards/how-we-code.md): the coding patterns a review checks line by line.
- [context/standards/testing.md](context/standards/testing.md) and [context/standards/tooling.md](context/standards/tooling.md): the test tiers and the commands in full.
- [context/standards/landing.md](context/standards/landing.md): how a change becomes one commit.
- [context/research/README.md](context/research/README.md): how research is done, and the catalog of reference repos.

Section titles in this file are cited by name from `context/standards/` and the review skills. Rename one only together with its citations.

## Commands

```bash
uv sync --all-extras --group dev          # install; the extras carry the database drivers
uv run pytest                             # the whole suite, in parallel, about a minute
uv run pytest -m "not slow"               # leave out the heavy tests while iterating
uv run ruff check src/ tests/             # lint
uv run ruff format --check src/ tests/    # the format gate; CI runs it
uv run ty check src/ tests/               # types
cargo test -p vfs-core                    # the Rust engine
uv sync --all-extras --group dev --reinstall-package vfs-py   # after any Rust edit
scripts/ci.sh                             # the gate before a commit
scripts/docs.sh dev                       # preview the docs site locally; needs bun
scripts/docs.sh build                     # the static docs site, in docs-app/build
scripts/docs.sh check                     # the gate before a commit that touches the docs or a docstring
scripts/docs.sh export                    # the API export the docs app reads, from the docstrings
```

The rule behind each command is under [Tooling](#tooling).

## Project stage: pre-release, green tree

The design in this repository has not been released. Until it is, there are no users to migrate and no legacy to protect. Three rules follow.

- **The tree stays green.** The `tests/` suite passes, and `ruff` and `ty` are at zero across `src/` and `tests/`. A broken import, a failing test, or a new lint or type error in the live tree is a regression to fix, not expected refactor noise. Green is held on `dev` and `main`; a work branch may be red between a guided commit and the autonomous pass that follows it.
- **Green is an invariant, not a limit on ambition.** Do not discount an idea because it would require a big refactor, churn a lot of files, or take significant resources. Evaluate ideas on where the fundamentals should end up, propose the right design, and treat the cost of getting there as a planning detail, not a reason to shrink the idea. Green means each landing leaves the tree working; it does not mean changes must be small.
- **`src/` and `tests/` are the whole live tree.** New and updated code and tests go there. Earlier generations of the code exist only in git history. `docs-app/` is the one other tree: the docs site, a Svelte app with its own toolchain and its own tests, and no part of the Python package.

When the first release of this design ships, compatibility becomes a constraint and this section is rewritten.

## Production posture: real databases, real scale, two audiences

vfs is built to run in production, not just to pass a demo. Two audiences share the same storage backend and both are first-class:

- **Agents** doing read → edit → write and search loops (small batches, latency-sensitive, high concurrency).
- **ETL devs and data pipelines** doing bulk ingest and transform. **Batches of 10,000+ files in a single call are a supported contract, not an edge case.** Every write/read builder must stay correct and bounded at that size.

Consequences that bind design work:

- **Never assume SQLite.** Production runs on Postgres, SQL Server, Oracle, and other SQLAlchemy-compatible engines; SQLite is the dev/test default, not the target. A design that only works within SQLite's generous limits is a bug. The tightest known engine caps are the floor to design against (e.g. Oracle's 1,000-element `IN`-list limit, ORA-01795; SQL Server's ~2,100 bind parameters).
- **No statement may grow unboundedly with batch size.** Any `IN (...)` list, bulk insert, or bulk update must chunk by a declared budget and merge results. Bind-parameter budgets come from SQLAlchemy where it models them (`dialect.insertmanyvalues_max_parameters`); the `IN`-list element cap, which SQLAlchemy does **not** model, is a declared per-dialect `DialectProfile` field (`in_list_budget`). The chunk size is `membership_budget(profile, parameter_budget)`, the tighter of the two caps, and the shared `chunked()` helper does the slicing. See `storage/backends/database/dialects.py`.
- **Lean on SQLAlchemy; keep profiles lightweight.** Read facts off the live `Dialect` object rather than hardcoding them. A `DialectProfile` field is justified only for a decision SQLAlchemy takes no position on (arbitration mode, key-byte budget, `IN`-list cap, isolation pins). Before adding a profile constant, check whether SQLAlchemy already exposes it.
- **Unknown dialects are served the core verbs, never ranked search.** They resolve to the conservative `GENERIC` floor stamped with their own name and serve read, write, the topology verbs, glob and grep exactly as a tuned engine does. `search` is withheld from their declared capabilities, because ranked search needs an engine fact the floor cannot declare: a cosine distance function. **Every supported dialect has one**: native on Postgres/pgvector, MariaDB, SQL Server 2025 and Oracle 23ai; sqlite-vec on SQLite, a core dependency vfs loads on every connection. MySQL community has no distance function and no extension vfs can install, so it is not a supported dialect: a `mysql://` URL is served as an unknown one. There is no client-side vector floor; the Rust cosine kernel is the vector leg's referee.
- **Never design toward a hard scale cap.** Do not intentionally limit vfs's scale capacity (no designed corpus ceilings, row maximums, or "supported size" limits) unless an external system imposes one: a SQL engine's own caps, a protocol constant. Where the current implementation is suboptimal at scale (e.g. a whole-corpus in-memory build), acknowledge the profile honestly in the docstring and name the future direction; never convert the suboptimality into a declared limit.

## The reference deployment: the scale every idea is filtered through

Every design idea is costed against one concrete enterprise deployment before it is proposed. It is a filter, not a target and not a cap: an idea that is cheap in a demo and ruinous here is rejected here, and an idea that looks heavy in the abstract but is a rounding error here is not rejected for looking heavy. Every figure is sourced in [the 2026-11-09 research memo](context/research/2026-11-09-what-an-enterprise-scale-deployment-looks-like.md), which names the study, the population and the year behind each one; a row marked *assumption* is one no public measurement exists for. When a real deployment is measured and diverges, the table is updated and the ideas it filtered are revisited.

| Dimension | Figure | Source in words |
|---|---|---|
| Files | 10,000,000 | the share estate of about 2,400 accounts at the measured 4,225 files per account (785 organizations, 2019), or a 1,000-person company once code, wiki versions and cloud drives are counted |
| Directories | about 1,000,000; median directory 2 files, a quarter empty of files, a tail into thousands of children | 6 to 12 files per directory in every study from 1998 to 2019; the largest directory in the Linux tree holds 1,533 entries |
| Depth | mean 6; 15% of directories at depth 8 or more; tail to 12 to 15 | the Microsoft desktop series, 2000 to 2009 |
| File size | median 4 KB; mean 0.3 to 0.7 MB; 3 to 7 TB of bodies, about 40 GB of text at the median | the 4 KB median is unchanged since 1981; the text share by count is high and by bytes low, and is an *assumption* |
| Growth | about 25% a year, doubling in three years | 20 to 32% a year on desktops over eleven years; about 5% in a mature code tree |
| Derived rows | about 100,000,000 chunks with their postings and embeddings | the ten-chunks-per-file ratio vfs's own embed docstring states |
| Callers | 1,000 people and the agents acting for them | the user count is the owner's choice; the rows below separate the two populations |
| Human ranked searches | about 0.2 a person a day, 200 a day in all | two intranet query logs, 60,000 and 75,000 employees, 2002 and 2018 |
| Agent verb calls | 100 to 200 a user a day, 150 as the figure; 150,000 a day; about 5 a second over an eight-hour day, about 20 a second at peak; about three reads, lists, globs and greps per write or edit, `search` under a tenth; the top 1% of identities issue 10 to 20% of calls | about 10 actions a prompt and 4 prompts a session measured on 400,000 agent sessions, at 2 to 5 sessions a day; a 4× peak hour from the NetApp traces |
| Concurrency | many callers on one database at once: at peak about 20 verb calls a second arrive beside the day's single-file writes, with a partial index pass every 15 minutes; overnight a 10,000-file batch is almost always running beside the rebuild; a verb call lasts tens of milliseconds, a batch tens of seconds to minutes, a rights change (grant, revoke, posture, membership) is a person's act a few times a day | the arrival rates are the rows above and below; the durations and the rate of rights changes are an *assumption*; which calls wait behind a posture change on each engine is measured in [the 2026-11-14 label memo](context/research/2026-11-14-a-mint-must-prove-its-label-against-a-posture-change-committed-inside-its-window.md) |
| Organic change | 0.5% of files a working day, 50,000 single-file writes; 1% as the design ceiling, 100,000 | at most 0.95% a day from the desktop studies, 0.1% of bytes on shared servers; human saves are 1,000 to 5,000 of these and the rest are machine writes |
| Nightly batch | 10% of files, 1,000,000, in 10,000-file batches, 100 batches inside six hours, about 50 files a second sustained | the ingest contract vfs chooses; no organic corpus measures anything near it, and automation issuing most writes has precedent |
| Partial index pass | every 15 minutes, floor 1 minute, over what changed since the last pass: about 1,250 to 2,500 files in working hours, the nightly million overnight; each pass writes its own posting table | SharePoint's continuous-crawl default and Microsoft's connector floor; Glean's connectors run at 10 minutes to 1 hour |
| Full rebuild | once a day, required by the design, folding the delta posting tables into one; 10,000,000 file visits, about ten times the day's organic writes | prior art rebuilds weekly to monthly or never; the only sub-daily full builds are zoekt's, per repository, for compaction |
| Directory aggregates | direct-children file count, subdirectory count and byte total per directory, maintained with the write and coalesced per batch; recursive totals only for marked directories; labelled approximate, with a strict read and a repair verb; a 1 to 5 second lag budget where asynchronous | the consensus of CephFS, HDFS, btrfs, ZFS, Lustre, GPFS, FSRM and JuiceFS at ten million files and beyond; the shape vfs's own aggregation experiment tests |
| Rights | every verb call judged against row-level grants | the number of groups and the share of files under grants is an *assumption* |
| Engines | Postgres as the common case; SQL Server and Oracle at customer sites | the floors above, 1,000-element `IN` lists and about 2,100 bind parameters, are live constraints |

How to use it: name the multiplier an idea rides on, then multiply.

- **Per verb call** is about 150,000 a day. A read must cost in proportion to what it returns, never to the corpus: one scan of 10,000,000 rows per call is 1.5 trillion row visits a day, and an agent is waiting on the latency.
- **Per file write** is about 1,050,000 a day at the centre and 1,100,000 at the ceiling. One bounded statement per write is about a million statements a day, affordable if it is bounded and uncontended; the same statement landing on one hot row is about 30 updates a second on that row at the daytime peak and about 50 a second through the nightly batch, a serialization point.
- **Per index visit** is about 11,000,000 a day: the partial passes' million plus the daily rebuild's ten million. Anything added to the rebuild path is paid ten times more often than anything on the write path and seventy times more often than anything on a verb call. This is the multiplier that most often turns a small idea into an unaffordable one.
- **Per batch** is 100 a night inside six hours. 10,000 rows through chunked builders at the engine floor is already about ten statements per table touched; a round trip per row adds 10,000.
- **Per corpus** is once a day, the rebuild. A whole-table operation is affordable only there, only bounded in memory and interruptible, and never per call or per write.
- **Per lock** is everyone who waits behind it, times how long it is held. Every caller shares one database, so a lock is never costed alone: about 20 calls a second arrive at peak, so a lock every call needs, held for one second, stalls about 20 calls, and the same lock held through a 10,000-file batch's body stalls every caller for the length of the batch. Four rules follow.
  - *A read never waits on a writer or on a rights change.* Reads, lists, globs, greps and searches are about three calls in four, and an agent is waiting on each. A design that makes them queue behind a write, a batch or a posture change is rejected here however rare the write is.
  - *A lock other callers need is held for the length of a commit.* Never for a batch's body, a relabel's region, an index pass or a person's pause. A lock taken as a transaction's last statement is held for a commit; a lock taken as its first is held for everything after it.
  - *A table lock is the last resort and is named in full.* It is taken only in a mode that leaves plain reads running, only on a table no read verb writes to, and the design lists every call that queues behind it. A counted test then shows, on every server engine, that each other kind of call returns while the lock is held: a read, a search, an edit of an existing file, by the system actor, a named caller and anonymous.
  - *The engine's own reader locks count.* Where an engine makes a plain read wait on an uncommitted write (SQL Server with `READ_COMMITTED_SNAPSHOT` off), every open write transaction is a lock on its readers: measured there, one open posture change held every call on the mount, reads included. A design is costed on the engine setting vfs requires, and a setting that makes readers wait is refused at first touch or flagged, never designed around.

## Tooling

- **This is a uv project.** Run Python and tooling through `uv`, e.g. `uv run python ...`, `uv run pytest ...`. Do not invoke the interpreter or `pip` directly, and do not manually `source .venv`.
- **Every shell command gets a timeout, set from an estimate of how long it should take.** Before running a command, estimate its time to complete, state the estimate, and set the timeout to about twice it; a background command gets one too. A script that waits on something else (a test run, a container, a lock) carries its own deadline and stops what it started when the deadline passes, whether or not the thing it waited on reported anything. A command with no deadline blocks the session silently: an experiment run on the SQL Server leg hung with every thread blocked on a lock, its wrapper stopped a run only when the run recorded its own hang, which a run with no free thread cannot do, and a job expected to take four minutes held the session for fifty-four. A timeout that fires is a finding to diagnose, not a number to raise and run again.
- **`ruff check`, `ruff format --check`, and `ty` must stay at zero across `src/` and `tests/`.** Leave them that way after every change. The format gate is not optional: CI runs `ruff format --check`, and format drift has reached `main` twice from sessions that ran only `ruff check`.
- **`uv run pytest` is the inner loop, it is parallel, and it runs the whole suite** (`-n auto --dist worksteal` in `addopts`, pytest-xdist; about a minute on a ten-core machine). `tests/conftest.py` deselects the real-engine legs whose `VFS_TEST_<ENGINE>_URL` is unset. A test that is deliberately heavy (a BEIR corpus, a 10k batch, a second backend for a contract already proven on one) is marked `slow` so `-m "not slow"` can leave it out while iterating. Nothing deselects it by default, because the whole heavy tier costs about eleven seconds and the suite's budget is one minute. Never assert on elapsed time, and never skip a test by hand where a marker and this hook can deselect it.
- **Before a work branch's pull request to `dev`, when the branch touches `src/`, `tests/`, `crates/`, or `pyproject.toml`, run `scripts/ci.sh`**, the Python 3.13 gate; a guided commit that only saves work does not run it. It covers lint, format, types, tests under 100% coverage, the docs fences and the wheel budget, about a minute warm. It mirrors the CI Tests job's 3.13 leg exactly; green here means green there. The other matrix legs (3.11, 3.12, 3.14) are CI's job on every push, not a local gate, because they rerun the same tests and add about three minutes. `scripts/ci.sh 3.14` reproduces one when CI goes red.
- **Before a work branch's pull request to `dev`, when the branch touches `documentation/`, `docs-app/`, `scripts/docs_export.py`, `scripts/docs.sh` or a docstring under `src/vfs/`, run `scripts/docs.sh check`.** It exports the public API from the docstrings, builds the docs site, type-checks the app and runs its tests, and it needs `bun` beside `uv`. A docstring is a page's content: the Python gate does not build the docs, so a dead link, a glossary term nobody defined, an exported name on no page, or a docstring the renderer cannot draw goes red only here and in the `Docs site` workflow.
- **The Rust engine** lives in `crates/vfs-core` (pyo3 binding behind its `python` cargo feature; maturin builds it into the wheel as `vfs._native`, fronted by the `vfs/native.py` seam). **The extension is required**: vfs has one engine, the seam fails loudly when it is missing, and there is no pure-Python runtime fallback. The readable reference implementations live in `tests/support/oracles/` and pin the engine through parity tests. Keep `cargo test -p vfs-core` green. **After editing Rust, run `uv sync --all-extras --group dev --reinstall-package vfs-py`**: uv caches the built wheel and does not rebuild on Rust-only edits. A bare `uv sync` is exact: without the extras it strips the database drivers, and the engine legs then fail.
- **Performance work goes in our own Rust crate; pure Python is a test oracle, not a fallback.**
  - *The engine*: when a hot path needs vectorized or compiled speed, build a kernel in `crates/vfs-core`. Do not reach for a numeric acceleration library (numpy, scipy, numba) as a middle tier: it is a compiled wheel with all of the portability cost of our own Rust and none of the control, and it is slower than what we own. numpy is not a dependency and does not come back.
  - *Why no pure-Python fallback*: "runs on any interpreter" was never true. `pydantic-core` is compiled Rust with no pure edition, so vfs is a compiled-extension package already, like pydantic-core, orjson, and polars. A second shipped engine bought no reach and cost a double implementation plus a class of interpreter-drift bugs (the pure tokenizer took its Unicode classes from the running Python; the Rust tables are frozen).
  - *Oracles*: a readable pure-Python reference implementation lives in `tests/support/`, only where it pins a parity test. It ships in no wheel, carries no coverage obligation, and may skip on interpreters other than the one that generated the Rust tables.
  - *Scope*: this governs vfs's own engine code (index build, posting decode and intersection, scoring, matching, chunking). Framework dependencies (pydantic, SQLAlchemy) are a separate decision, made on their own merits. Small sets and lists stay stdlib Python.

## Development process and project knowledge

- **The developer directs all work, guided and autonomous.** A session of either kind starts on the developer's decision. An agent may ask to start one, and never starts one by itself: a finished guided session does not begin an autonomous pass, and a finished pass does not begin the next piece of work.
- **Understand the goal before starting in-depth work.** Ask the developer what the goal is, then question it the way an analyst would: is it specified, is it the right thing to build, what is left out. Work starts when the developer and the agent agree on the goal. A goal the agent guessed is how a day goes to the wrong change.
- **Work is guided or autonomous; ask which when the developer has not said.** Guided work is live with the developer for one to four hours: act toward the goal, explain as you go, do most of the work yourself, start a subagent only for work better done in parallel and say so first, and do not run the full suite or the engine legs. Autonomous work is the agent alone, before a guided session to prepare it or after one to finish it: research, reviews, end-to-end tests and the full gate. [How we work](documentation/maintainers/how-we-work.md) has both in full.
- **More than one question goes through the question dialog.** In Claude Code that is the `AskUserQuestion` tool. A list of questions in chat prose costs the developer more time to answer than a dialog with a recommended option.
- **All project knowledge lives in this repo, never outside it.** Do not keep project knowledge in a tool's private memory or any other out-of-repo location (for example, Claude Code's memory files under `~/.claude/projects/*/memory/`); if any exist, move what matters into the repo and delete them. Working material goes in a work directory, `agents/YYYY-MM-DD-short-descriptive-title/`, which is written for agents, never published, and may be deleted once the work has been released. Everything under `agents/` is in an objective, impersonal voice: no person's name, no mention of a human, a developer or an agent, no "I", "we" or "you"; it states what was found, decided and done, never who did it. Anything that must outlive the work is promoted to `documentation/`, which is published, or it is lost.
- **`context/` is the earlier layout and takes no new work.** Its intentions, research, specs, reviews and standards are read and cited until they are migrated to `agents/` and `documentation/`. The pieces in flight on 2026-11-15 finish under its pipeline. Every document there is dated, headerless and one line per paragraph, and holds no open question; `tests/lint/` holds those shapes in `scripts/ci.sh`, and `scripts/unwrap_context.py --fix` joins wrapped prose.
- **A guided session writes no document for the developer.** It is chat, code and documentation. It ends with a handoff note in the work directory, the goal, the decisions with their reasons and what is unfinished, written for the autonomous pass. A spec is written only when the autonomous pass needs one for its reviewers.
- **The autonomous pass fixes what keeps behaviour and reports what would change it.** It may fix anything that leaves the behaviour of the feature and the project as it was. A big finding, a fix that would change behaviour significantly, or a case that the feature should not be built comes back to the developer as a report and is not acted on.
- **Nothing reaches `dev` unreviewed.** Before a work branch's pull request, the autonomous pass reviews the code with a fresh agent that did not write it, given the diff and the handoff note and never the author's summary. The `code_review` and `spec_review` skills hold the procedures, under `.claude/skills/<name>/SKILL.md`; the security lens is the installed `security-audit` skill in guidance mode.
- **Tests first, then code.** A new behaviour's test is written and seen failing before the code that passes it; a bug's reproducing test before its fix; at the layer the behaviour lives. This holds in guided work as well as autonomous. See `context/standards/how-we-code.md`.
- **The research stage means new investigation, not transcription.** A research memo is produced by actually gathering new findings (subagents studying the reference repos, executed experiments, benchmarks) that inform a pending decision or spec. Never write a memo that merely records in-session reasoning or restates a spec; that is bookkeeping, and it belongs in the spec itself.

## Git workflow

- **Work happens on a branch off `dev`.** Each piece of work gets its own branch, created once the goal is agreed. The branch reaches `dev` through a pull request that runs the gate and is squashed to one commit whose subject names the change in words. A person presses merge, always; an agent never merges a pull request. A release moves `dev` to `main`. Nothing is committed to `dev` or `main` directly.
- **A guided commit saves work and has no gate.** Commit on the work branch as often as the work needs saving. The checks run in the autonomous pass and on the pull request.
- **Ask before every push to a remote.** A push publishes, and a pull request starts with one. Approval for one push does not carry to the next.
- **Never use git worktrees.** Work in place in this checkout: no `git worktree add`, and none of a tool's worktree features (in Claude Code, `EnterWorktree` and `isolation: "worktree"` on a subagent). Edits left in a worktree do not show in this checkout's `git status`. Uncommitted agent work has sat in forgotten worktrees for weeks, reviewed by nobody, before it was found.
- **Never run `git checkout -- <file>`, `git restore`, or `git stash` on a file that carries uncommitted work without backing that file up first.** These commands silently replace the working copy with the committed version. On a file mid-implementation, that destroys the work with no undo: a `git checkout` used to undo a temporary test mutation once erased a day of uncommitted changes to one file, which had to be re-applied edit by edit. The safe pattern:
  1. `cp <file> <scratch>/<file>.bak` **before** any restore-shaped command touches it. The scratch directory is outside the repo (the session scratchpad, where the tool provides one), not `/tmp`.
  2. For temporary mutations (mutation testing, quick experiments), prefer never touching git at all: apply the mutation, run the check, then restore **from the backup copy** (`cp <backup> <file>`), and verify with `ruff` or a targeted test that the restored file is intact.
  3. Reach for `git checkout` or `git restore` only on files that are clean in `git status`, when the working copy genuinely holds nothing beyond HEAD.

## Imports

- **All imports go at the top of the file. No mid-file or function-local imports, ever**: not in functions, not in methods, and not to dodge a cycle. If an import is only needed for typing, still place it at the top, under a top-level `if TYPE_CHECKING:` block. A real import cycle is a structural problem to fix, not to paper over with a deferred import.

## File organization

Lay every module out top-to-bottom in this order:

1. **Module docstring**: what the module is for, with a short example when the shape isn't obvious.
2. **`from __future__ import annotations`**, then **imports**: stdlib, then third-party, then a trailing `if TYPE_CHECKING:` block (see *Imports* above).
3. **Module constants and shared types**: type aliases (`ObjectKind`), small `NamedTuple` types used across the module (`EdgeParts`), and hard-coded values (`METADATA_ROOT`, frozensets). A derived or private constant (`_EXTENSIONLESS_FILES_LOWER`) sits directly under the public name it comes from, not down in the helpers.
4. **Public API, grouped by concern.** Introduce each group with a three-line banner comment:

   ```python
   # ---------------------------------------------------------------------------
   # Normalization and validation
   # ---------------------------------------------------------------------------
   ```

   Order groups by the flow a caller follows (gate → normalize/validate → construct → decompose → query). A private type bound to a single group (`_EdgePathParts`) lives in that group, beside its user.
5. **Internal helpers last**: one trailing `# Internal helpers` banner holding the private `_`-prefixed functions, ordered roughly by first use. This keeps the public surface up top and the plumbing out of the way.

The split is by visibility and concern, not by kind: public functions live with the section they serve; only private *functions* are deferred to the end. Private *types and constants* stay next to what they support.

## Code comments

- Inline comments and comment blocks are **2 lines maximum**. This includes multi-line `#` blocks above a statement. State the what/why directly; if it needs more room, it belongs in a docstring.
- Do **not** reference story/spec numbers or decision records (e.g. "spec 030 §5.2", "Phase 4", "ADR 019") in code comments **or docstrings**. The comment gives its reason in words; the document cites the code, never the other way round. `tests/lint/` holds this for `src/`; traceability lives in `context/specifications/`, not inline.

## Code smells

- **After writing or changing code, reflect on whether it contains any "code smell"**: the classic hints that something may be off. Duplicated code, long methods, long parameter lists, magic numbers, primitive obsession (bare strings/ints/lists where a small type belongs), positional indexing that decodes a hidden field of a heterogeneous structure (`parts[2]` where the 2 secretly means "kind"; name the structure instead), deep nesting, feature envy, god classes, shotgun surgery, dead code, or speculative generality. First/last access on a homogeneous sequence (`lines[0]`, `rows[-1]`) is not this smell: there the position *is* the meaning, and it beats a `first, *_, last` destructure that materializes the middle.
- **A smell is a hint to look closer, not a rule to obey blindly.** When you spot one, dig in: understand *why* the code took that shape, and decide whether it is justified here.
- **Don't reach for numpy.** Small sets and lists take stdlib structures, and where measured scale justifies more the answer is a kernel in our own Rust crate; see *Performance work goes in our own Rust crate* under Tooling. There are no numpy call sites in `src/`; do not add one.
- **`assert` narrows, never validates.** An `assert` in `src/` is a type-narrowing statement after an ingress gate that already refused the bad shape (`assert path is not None` once the XOR check has run). It must never be the thing that turns bad input into a refusal: that is a classified `Result`, and `python -O` must change no behavior.

## Performance tests

- **Count operations, never wall-clock time.** A performance pin in `tests/` asserts how much work ran (calls to a spied function, statements issued, rows visited, a doubling ratio of profiled calls), never how many seconds it took. A clock measures the CI runner, not the algorithm: a time budget of 50 µs a chunk, a 2–5× margin over a laptop, failed two of four CI legs on every push with the code unchanged. Every mature project we study does the same (SQLAlchemy's cProfile call counts, SQLite's `sqlite_search_count`, zoekt's exact `Stats`, neo4j's `dbHits`, lancedb's `read_iops`) and keeps the clock in a separate benchmark (cachegrind, CodSpeed, criterion, asv) that cannot fail a test run. Wall-clock belongs in a bench or a research memo, never in a test.

## Reference repos for research

Prior art is studied in local clones of other projects, kept as sibling directories of this checkout (`../sqlite`, `../postgres`, `../zoekt`). They are not part of this repository, and a fresh clone of vfs has none: clone what a study needs. The catalog by topic is in [context/research/README.md](context/research/README.md), "Reference checkouts".

- **Read-only, and never copied.** Read, search, and cite a reference repo freely. Never modify it, and never copy code from it, whatever its license. Prior-art study is design input only: we study how others solved a problem to inform the design of our own original implementation. Research memos cite and describe, and every line of vfs code is written here. A dependency installed as source by its own tool, as `docs-app/` installs design-system items, is not a reference repo; `docs-app/README.md` names the tag.
- **Check the license immediately after cloning a new reference repo, and record it in the memo.** Copyleft licenses (AGPL, GPL, dual AGPL/Elastic) are fine to *study*: the no-copy rule is what protects the project, and it applies to every clone regardless of license. Delete a clone only when it carries no license or the terms are unclear, and study that project through its public docs and design writing instead.
- **Refresh every clone in a study set to its upstream default branch before anyone studies it.** Reference repos drift. One moved orgs, relicensed, and switched its default branch between two studies, and a memo built on a stale checkout cites code that no longer exists. Per repo: `git fetch origin`, then check out `origin/<default>` (the branch `origin/HEAD` points at, not assumed `main`); skip a clone `git status` reports dirty and say so in the memo. Re-check the license after refreshing, because it can change. Record the refreshed commit and date in the memo's sources line.

## Explaining work to people

- **Explain simply, and say the key idea more than once.** Dense, packed prose costs the reader real decoding time. When explaining a result, a design, or a trade-off: short sentences, one idea per sentence, say the key idea more than once in different words, define every term of art the first time it appears, and end with a one-line version. Tables and code are fine; compressed jargon-laden paragraphs are not.
