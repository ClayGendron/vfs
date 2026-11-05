# vfs: guide for contributors and coding agents

This file is the working agreement for anyone changing this repository, a person or a coding agent. It holds the rules that apply to every change. Each rule gives its reason, so it can be applied to a case it does not name. The [README](README.md) says what vfs is; this file says how work is done here.

vfs is governed data access for AI agents: one namespace of everything an agent can see, search, and change, with permissions enforced before anything is dispatched. It is a Python package (`src/vfs`) with a required Rust extension (`crates/vfs-core`).

In this file, **the developer** means the person directing the work: the person an agent is working for, or you.

Where the rest lives:

- [context/README.md](context/README.md): the pipeline every change follows, and the shape of every document.
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
```

The rule behind each command is under [Tooling](#tooling).

## Project stage: pre-release, green tree

The design in this repository has not been released. Until it is, there are no users to migrate and no legacy to protect. Three rules follow.

- **The tree stays green.** The `tests/` suite passes, and `ruff` and `ty` are at zero across `src/` and `tests/`. A broken import, a failing test, or a new lint or type error in the live tree is a regression to fix, not expected refactor noise.
- **Green is an invariant, not a limit on ambition.** Do not discount an idea because it would require a big refactor, churn a lot of files, or take significant resources. Evaluate ideas on where the fundamentals should end up, propose the right design, and treat the cost of getting there as a planning detail, not a reason to shrink the idea. Green means each landing leaves the tree working; it does not mean changes must be small.
- **`src/` and `tests/` are the whole live tree.** New and updated code and tests go there. Earlier generations of the code exist only in git history.

When the first release of this design ships, compatibility becomes a constraint and this section is rewritten.

## Production posture: real databases, real scale, two audiences

vfs is built to run in production, not just to pass a demo. Two audiences share the same storage backend and both are first-class:

- **Agents** doing read → edit → write and search loops (small batches, latency-sensitive, high concurrency).
- **ETL devs and data pipelines** doing bulk ingest and transform. **Batches of 10,000+ files in a single call are a supported contract, not an edge case.** Every write/read builder must stay correct and bounded at that size.

Consequences that bind design work:

- **Never assume SQLite.** Production runs on Postgres, SQL Server, Oracle, and other SQLAlchemy-compatible engines; SQLite is the dev/test default, not the target. A design that only works within SQLite's generous limits is a bug. The tightest known engine caps are the floor to design against (e.g. Oracle's 1,000-element `IN`-list limit, ORA-01795; SQL Server's ~2,100 bind parameters).
- **No statement may grow unboundedly with batch size.** Any `IN (...)` list, bulk insert, or bulk update must chunk by a declared budget and merge results. Bind-parameter budgets come from SQLAlchemy where it models them (`dialect.insertmanyvalues_max_parameters`); the `IN`-list element cap, which SQLAlchemy does **not** model, is a declared per-dialect `DialectProfile` field (`in_list_budget`). The chunk size is `membership_budget(profile, parameter_budget)`, the tighter of the two caps, and the shared `chunked()` helper does the slicing. See `storage/backends/database/dialects.py`.
- **Lean on SQLAlchemy; keep profiles lightweight.** Read facts off the live `Dialect` object rather than hardcoding them. A `DialectProfile` field is justified only for a decision SQLAlchemy takes no position on (arbitration mode, key-byte budget, `IN`-list cap, isolation pins). Before adding a profile constant, check whether SQLAlchemy already exposes it.
- **Unknown dialects are served the core verbs, never ranked search.** They resolve to the conservative `GENERIC` floor stamped with their own name and serve read, write, the topology verbs, glob and grep exactly as a tuned engine does. `glean` is withheld from their declared capabilities, because ranked search needs an engine fact the floor cannot declare: a cosine distance function. **Every supported dialect has one**: native on Postgres/pgvector, MariaDB, SQL Server 2025 and Oracle 23ai; sqlite-vec on SQLite, a core dependency vfs loads on every connection. MySQL community has no distance function and no extension vfs can install, so it is not a supported dialect: a `mysql://` URL is served as an unknown one. There is no client-side vector floor; the Rust cosine kernel is the vector leg's referee.
- **Never design toward a hard scale cap.** Do not intentionally limit vfs's scale capacity (no designed corpus ceilings, row maximums, or "supported size" limits) unless an external system imposes one: a SQL engine's own caps, a protocol constant. Where the current implementation is suboptimal at scale (e.g. a whole-corpus in-memory build), acknowledge the profile honestly in the docstring and name the future direction; never convert the suboptimality into a declared limit.

## Tooling

- **This is a uv project.** Run Python and tooling through `uv`, e.g. `uv run python ...`, `uv run pytest ...`. Do not invoke the interpreter or `pip` directly, and do not manually `source .venv`.
- **`ruff check`, `ruff format --check`, and `ty` must stay at zero across `src/` and `tests/`.** Leave them that way after every change. The format gate is not optional: CI runs `ruff format --check`, and format drift has reached `main` twice from sessions that ran only `ruff check`.
- **`uv run pytest` is the inner loop, it is parallel, and it runs the whole suite** (`-n auto --dist worksteal` in `addopts`, pytest-xdist; about a minute on a ten-core machine). `tests/conftest.py` deselects the real-engine legs whose `VFS_TEST_<ENGINE>_URL` is unset. A test that is deliberately heavy (a BEIR corpus, a 10k batch, a second backend for a contract already proven on one) is marked `slow` so `-m "not slow"` can leave it out while iterating. Nothing deselects it by default, because the whole heavy tier costs about eleven seconds and the suite's budget is one minute. Never assert on elapsed time, and never skip a test by hand where a marker and this hook can deselect it.
- **Before any commit touching `src/`, `tests/`, `crates/`, or `pyproject.toml`, run `scripts/ci.sh`**, the Python 3.13 gate: lint, format, types, tests under 100% coverage, the docs fences and the wheel budget, about a minute warm. It mirrors the CI Tests job's 3.13 leg exactly; green here means green there. The other matrix legs (3.11, 3.12, 3.14) are CI's job on every push, not a local gate, because they rerun the same tests and add about three minutes. `scripts/ci.sh 3.14` reproduces one when CI goes red.
- **The Rust engine** lives in `crates/vfs-core` (pyo3 binding behind its `python` cargo feature; maturin builds it into the wheel as `vfs._native`, fronted by the `vfs/native.py` seam). **The extension is required**: vfs has one engine, the seam fails loudly when it is missing, and there is no pure-Python runtime fallback. The readable reference implementations live in `tests/support/oracles/` and pin the engine through parity tests. Keep `cargo test -p vfs-core` green. **After editing Rust, run `uv sync --all-extras --group dev --reinstall-package vfs-py`**: uv caches the built wheel and does not rebuild on Rust-only edits. A bare `uv sync` is exact: without the extras it strips the database drivers, and the engine legs then fail.
- **Performance work goes in our own Rust crate; pure Python is a test oracle, not a fallback.**
  - *The engine*: when a hot path needs vectorized or compiled speed, build a kernel in `crates/vfs-core`. Do not reach for a numeric acceleration library (numpy, scipy, numba) as a middle tier: it is a compiled wheel with all of the portability cost of our own Rust and none of the control, and it is slower than what we own. numpy is not a dependency and does not come back.
  - *Why no pure-Python fallback*: "runs on any interpreter" was never true. `pydantic-core` is compiled Rust with no pure edition, so vfs is a compiled-extension package already, like pydantic-core, orjson, and polars. A second shipped engine bought no reach and cost a double implementation plus a class of interpreter-drift bugs (the pure tokenizer took its Unicode classes from the running Python; the Rust tables are frozen).
  - *Oracles*: a readable pure-Python reference implementation lives in `tests/support/`, only where it pins a parity test. It ships in no wheel, carries no coverage obligation, and may skip on interpreters other than the one that generated the Rust tables.
  - *Scope*: this governs vfs's own engine code (index build, posting decode and intersection, scoring, matching, chunking). Framework dependencies (pydantic, SQLAlchemy) are a separate decision, made on their own merits. Small sets and lists stay stdlib Python.

## Development process and project knowledge

- **All project knowledge lives in this repo, never outside it.** Do not keep project knowledge in a tool's private memory or any other out-of-repo location (for example, Claude Code's memory files under `~/.claude/projects/*/memory/`); if any exist, move what matters into the repo and delete them. Durable context belongs in `context/` (intentions, research, specs, reviews, standards) or this file, where it is versioned and visible to everyone. The pipeline is intent → research → spec → review → code → review → commit, all under standards; see `context/README.md`. Every change needs a spec; not every change needs an intention or research.
- **Decisions live in the spec that carries them.** There are no decision records. A choice is a numbered entry in the spec's Decisions section with its reason; a choice that cannot be made yet becomes a placeholder research memo and the spec waits. No document holds an open question: no clarification marker, neither of the two marker words, no heading that opens a list of questions; `tests/lint/` refuses them.
- **Every document under `context/` is dated, headerless and one line per paragraph.** Names are `YYYY-MM-DD-descriptive-slug.md`, never numbered; the title is line one and prose follows with no bullet header; cross-references are Markdown links with relative paths; a paragraph is one line of any length (`scripts/unwrap_context.py --fix` joins wrapped prose). The lint package `tests/lint/` holds these shapes in `scripts/ci.sh`.
- **Nothing lands unreviewed.** A spec is reviewed before it is built and the code again before it lands, each by a fresh agent or a person who did not write the change, given the spec and the diff and never the author's summary. Each review is a file under `context/reviews/`, and the landing notes link both. The spec review ends "Fit to build" or "Not yet"; the code review ends "Lands" or "Does not land yet". The `spec_review` and `code_review` skills write them; the security lens is the installed `security-audit` skill in guidance mode. The procedures are files under `.claude/skills/<name>/SKILL.md`; an agent without skill support reads the file and follows it.
- **Tests first, then code.** A new behaviour's test is written and seen failing before the code that passes it; a bug's reproducing test before its fix; at the layer the behaviour lives. This is an instruction of how to code, not a record to keep: the tests land in the same commit as the code they pin. See `context/standards/how-we-code.md`.
- **A change lands as one commit** whose subject names it in words and whose trailers link the spec and both reviews; see `context/standards/landing.md`. Commit and push only when the developer asks.
- **The research stage means new investigation, not transcription.** A research memo is produced by actually gathering new findings (subagents studying the reference repos, executed experiments, benchmarks) that inform a pending decision or spec. Never write a memo that merely records in-session reasoning or restates a spec; that is bookkeeping, and it belongs in the spec itself.

## Git workflow

- **The developer chooses the branch.** Do not create a branch before committing. Commit to the current branch as it is, `main` included, unless the developer asks for a new branch.
- **Commit or push only when the developer asks.** A finished change waits in the working tree until then.
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

- **Read-only, and never copied.** Read, search, and cite a reference repo freely. Never modify it, and never copy code from it, whatever its license. Prior-art study is design input only: we study how others solved a problem to inform the design of our own original implementation. Research memos cite and describe, and every line of vfs code is written here.
- **Check the license immediately after cloning a new reference repo, and record it in the memo.** Copyleft licenses (AGPL, GPL, dual AGPL/Elastic) are fine to *study*: the no-copy rule is what protects the project, and it applies to every clone regardless of license. Delete a clone only when it carries no license or the terms are unclear, and study that project through its public docs and design writing instead.
- **Refresh every clone in a study set to its upstream default branch before anyone studies it.** Reference repos drift. One moved orgs, relicensed, and switched its default branch between two studies, and a memo built on a stale checkout cites code that no longer exists. Per repo: `git fetch origin`, then check out `origin/<default>` (the branch `origin/HEAD` points at, not assumed `main`); skip a clone `git status` reports dirty and say so in the memo. Re-check the license after refreshing, because it can change. Record the refreshed commit and date in the memo's sources line.

## Explaining work to people

- **Explain simply, and say the key idea more than once.** Dense, packed prose costs the reader real decoding time. When explaining a result, a design, or a trade-off: short sentences, one idea per sentence, say the key idea more than once in different words, define every term of art the first time it appears, and end with a one-line version. Tables and code are fine; compressed jargon-laden paragraphs are not.
