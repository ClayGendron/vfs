# Project guidance for Claude Code

## Current state: greenfield rebuild, green tree

The repo is being rebuilt around solid fundamentals — **paths, models, base,
results, and storage** — built around an MCP design. The live tree is fully
green: the `tests/` suite passes, and `ruff` and `ty` are at zero across
`src/` and `tests/`. **Keep it that way** — a broken import, a failing test,
or a new lint/type error in the live tree is a regression to fix, not
expected refactor noise.

A green tree is an invariant, not a constraint on ambition. **This is still
greenfield work: do not discount ideas because they would require a big
refactor, churn a lot of files, or take significant resources.** There is no
legacy to protect and no users to migrate — evaluate ideas on where the
fundamentals should end up, propose the right design, and treat the cost of
getting there as a planning detail, not a reason to shrink the idea. Green
means each landing leaves the tree working; it does not mean changes must be
small.

### Production posture: real databases, real scale, two audiences

vfs is built to run in production, not just to pass a demo. Two audiences
share the same storage backend and both are first-class:

- **Agents** doing read → edit → write and search loops (small batches,
  latency-sensitive, high concurrency).
- **ETL devs and data pipelines** doing bulk ingest and transform —
  **batches of 10,000+ files in a single call are a supported contract,
  not an edge case.** Every write/read builder must stay correct and
  bounded at that size.

Consequences that bind design work:

- **Never assume SQLite.** Production runs on Postgres, SQL Server,
  Oracle, and other SQLAlchemy-compatible engines; SQLite is the dev/test
  default, not the target. A design that only works within SQLite's
  generous limits is a bug. The tightest known engine caps are the floor
  to design against (e.g. Oracle's 1,000-element `IN`-list limit,
  ORA-01795; SQL Server's ~2,100 bind parameters).
- **No statement may grow unboundedly with batch size.** Any `IN (...)`
  list, bulk insert, or bulk update must chunk by a declared budget and
  merge results. Bind-parameter budgets come from SQLAlchemy where it
  models them (`dialect.insertmanyvalues_max_parameters`); the `IN`-list
  element cap, which SQLAlchemy does **not** model, is a declared
  per-dialect `DialectProfile` field (`in_list_budget`). The chunk size
  is `membership_budget(profile, parameter_budget)` — the tighter of the
  two caps — and the shared `chunked()` helper does the slicing. See
  `storage/backends/database/dialects.py`.
- **Lean on SQLAlchemy; keep profiles lightweight.** Read facts off the
  live `Dialect` object rather than hardcoding them. A `DialectProfile`
  field is justified only for a decision SQLAlchemy takes no position on
  (arbitration mode, key-byte budget, `IN`-list cap, isolation pins).
  Before adding a profile constant, check whether SQLAlchemy already
  exposes it.
- **Unknown dialects are served, not refused** — they resolve to the
  conservative `GENERIC` floor stamped with their own name.
- **Never design toward a hard scale cap** (Clay, 2026-08-13). Do not
  intentionally limit vfs's scale capacity — no designed corpus
  ceilings, row maximums, or "supported size" limits — unless an
  external system (a SQL engine's own caps, a protocol constant)
  imposes one. Where the current implementation is suboptimal at scale
  (e.g. a whole-corpus in-memory build), acknowledge the profile
  honestly in the docstring and name the future direction; never
  convert the suboptimality into a declared limit.

### Live code vs archived reference: `src/`+`tests/` vs `src2/`+`tests2/`

- **`src/` and `tests/` are live.** New and updated code and tests go here;
  `tests/` is the only suite worth running.
- **`src2/` and `tests2/` are archived pre-refactor code, kept as a quarry**
  to mine while building out the live tree. Do **not** run, lint, fix, or
  port-fix them — they reference names that no longer exist by design, and
  tooling config already excludes them. When a file has been fully ported or
  superseded, it can go.

## Tooling

- This is a **uv** project. Run Python and tooling through `uv` — e.g.
  `uv run python ...`, `uv run pytest ...`. Do not invoke the interpreter or
  `pip` directly, and do not manually `source .venv`.
- **`ruff check`, `ruff format --check`, and `ty` must stay at zero across
  `src/` and `tests/`.** They currently pass clean; leave them that way
  after every change. The format gate is not optional: CI runs
  `ruff format --check`, and format drift has reached `main` twice by
  sessions running only `ruff check`. `src2/` and `tests2/` are excluded
  in `pyproject.toml` — never chase errors there.
- **Before any commit touching `src/`, `tests/`, `crates/`, or
  `pyproject.toml`, run `scripts/ci.sh 3.13`** (the coverage leg — lint,
  format, types, tests, 100% coverage, pure-Python engine), or the full
  matrix `scripts/ci.sh` before a push. It mirrors the CI Tests job
  exactly; green here means green there.
- **The Rust engine** lives in `crates/vfs-core` (pyo3 binding behind its
  `python` cargo feature; maturin builds it into the wheel as
  `vfs._native`, fronted by the `vfs/native.py` seam with a pure-Python
  fallback — `VFS_PURE_PYTHON=1` forces the fallback). Keep
  `cargo test -p vfs-core` green, and keep the two engines byte-identical
  (pinned by `tests/test_native.py`). **After editing Rust, run
  `uv sync --reinstall-package vfs-py`** — uv caches the built wheel and
  does not rebuild on Rust-only edits.

## Git workflow

- Do **not** auto-create a branch before committing. Commit to the current
  branch as-is — including `main` — unless I explicitly ask for a new branch.
- Commit or push only when I ask.
- **Never run `git checkout -- <file>`, `git restore`, or `git stash` on a
  file that carries uncommitted work without backing that file up first.**
  These commands silently replace the working copy with the committed
  version — on a file mid-implementation, that destroys the session's work
  with no undo (this happened: a `git checkout` used to undo a temporary
  test mutation wiped a day of uncommitted changes to `grep.py`, which had
  to be re-applied edit by edit). The safe pattern:
  1. `cp <file> <scratchpad>/<file>.bak` **before** any restore-shaped
     command touches it — the session scratchpad, not `/tmp`.
  2. For temporary mutations (mutation testing, quick experiments), prefer
     never touching git at all: apply the mutation, run the check, then
     restore **from the backup copy** (`cp <backup> <file>`), and verify
     with `ruff`/a targeted test that the restored file is intact.
  3. Reach for `git checkout`/`git restore` only on files that are clean in
     `git status` — when the working copy genuinely holds nothing beyond
     HEAD.

## Project memory

- **All project knowledge lives in this repo — never outside it.** Do not
  write memory files to `~/.claude/projects/*/memory/` or any other
  out-of-repo location; if any exist, delete them. Durable context belongs
  in `context/` (research, decisions, specs, standards) or this file, where
  it is versioned and visible to everyone. The pipeline is research →
  decide → specify → code, all under standards — see `context/README.md`.
- **The research stage means new investigation, not transcription** (Clay,
  2026-08-04): a research memo is produced by actually gathering new
  findings — subagents studying the reference repos, executed experiments,
  benchmarks — that inform a pending decision or spec. Never write a memo
  that merely records in-session reasoning or restates an ADR; that is
  bookkeeping, and it belongs in the ADR or spec itself.

## Reference repos for research

Sibling checkouts under `~/Git/Repos/` are available **read-only** for
research — study prior art there freely (read, grep, cite), but never modify
them and **never copy code from them**. Prior-art study is design input
only: we study how others solved a problem to inform the design of our own
original implementation — research memos cite and describe, and every line
of vfs code is written by us. Run `ls ~/Git/Repos` for the full list; the
most relevant to this project:

- **Always check the license immediately after cloning a new reference
  repo.** Keep only clones under clearly permissive open-source licenses
  (MIT, BSD, Apache-2.0, and similar); if the license is copyleft, missing,
  or unclear, delete the clone and study that project through its public
  docs and design writing instead.
- **Refresh every clone in a study set to its upstream default branch
  before any subagent studies it** (Clay, 2026-08-26). Reference repos
  drift — graphify moved orgs, relicensed, and switched its default
  branch between two studies — so a memo built on a stale checkout cites
  code that no longer exists. Per repo: `git fetch origin`, then check
  out `origin/<default>` (the branch `origin/HEAD` points at, not
  assumed `main`); skip a clone `git status` reports dirty and say so in
  the memo. Re-check the license after refreshing — it can change. Record
  the refreshed commit and date in the memo's sources line.

- **Filesystem heritage & semantics**: `plan9`, `plan9port`,
  `unix-history-repo`, `freebsd-src`, `linux`, `libfuse`, `pjdfstest`
  (POSIX fs test suite)
- **VFS / storage layers**: `filesystem_spec` (fsspec), `pyfilesystem2`,
  `opendal`, `juicefs`, `seaweedfs`, `minio`, `libsqlfs`, `agentfs`,
  `jackrabbit-oak`
- **Databases**: `sqlite`, `postgres`, `turso`, `sqlalchemy`
- **Code search & indexing** (trigram-index stories): `zoekt`, `codesearch`,
  `scip`
- **Ranked search, fusion & embeddings** (glean stories): `pgvector`,
  `pgvector-python`, `sqlite-vec`, `bm25s`, `tantivy`, `lucene`
  (unified highlighter), `ranx` (rank fusion + IR metrics),
  `neural-search` (OpenSearch hybrid normalization), `lancedb`,
  `haystack`, `llama_index`, `pyserini`, `fastembed`, `model2vec`,
  `openai-python`
- **Graphs & relation stores** (edge/graph stories): `neo4j`, `kuzu`
  (archived upstream — kept as a frozen design record), `ladybug` (Kuzu's
  community successor), `age` (graph on Postgres), `gel` (typed links
  compiled onto Postgres), `cayley` (graph over SQL/KV backends),
  `terminusdb` (versioned KG), `helix-db`, `tinkerpop` (Gremlin traversal
  API), `networkx`, `rustworkx`, `spicedb`, `openfga`
- **Graph query standards**: `openCypher`, `opengql-grammar` (LDBC's ISO
  GQL 2024 grammar), `GraphLite` (early embedded ISO-GQL), `duckpgq`
  (SQL/PGQ on DuckDB)
- **Knowledge graphs, agent memory & ontologies**: `graphrag`, `graphiti`,
  `cognee`, `LightRAG`, `graphify`, `letta`, `mem0`, `memori`
  (bring-your-own-SQL agent memory), `MemOS`, `HippoRAG`, `KAG`,
  `youtu-graphrag`, `ontogpt`, `rdflib`, `oxigraph`, `jena`
- **MCP**: `modelcontextprotocol`, `python-sdk`, `fastmcp`
- **Sandboxed execution & wasm** (hermetic-runtime direction): `monty`
  (pydantic's sandboxed Python interpreter), `wasmtime-py` (wasm
  embedding), `browser_wasi_shim` (WASI preview1 over a virtual fs),
  `WASI` (spec — preview1 lives on branch `origin/wasi-0.1`), `nushell`
  (structured-value pipelines)

## Imports

- **All imports go at the top of the file. No mid-file or function-local
  imports, ever** — not in functions, methods, `TYPE_CHECKING` aside, or to
  dodge a cycle. If an import is only needed for typing, still place it at the
  top (under a top-level `if TYPE_CHECKING:` block). A real import cycle is a
  structural problem to fix, not to paper over with a deferred import.

## File organization

Lay every module out top-to-bottom in this order:

1. **Module docstring** — what the module is for, with a short example when the
   shape isn't obvious.
2. **`from __future__ import annotations`**, then **imports** — stdlib, then
   third-party, then a trailing `if TYPE_CHECKING:` block (see *Imports* above).
3. **Module constants and shared types** — type aliases (`ObjectKind`), small
   `NamedTuple` types used across the module (`EdgeParts`), and hard-coded
   values (`METADATA_ROOT`, frozensets). A derived or private constant
   (`_EXTENSIONLESS_FILES_LOWER`) sits directly under the public name it comes
   from, not down in the helpers.
4. **Public API, grouped by concern.** Introduce each group with a three-line
   banner comment:

   ```python
   # ---------------------------------------------------------------------------
   # Normalization and validation
   # ---------------------------------------------------------------------------
   ```

   Order groups by the flow a caller follows (gate → normalize/validate →
   construct → decompose → query). A private type bound to a single group
   (`_EdgePathParts`) lives in that group, beside its user.
5. **Internal helpers last** — one trailing `# Internal helpers` banner holding
   the private `_`-prefixed functions, ordered roughly by first use. This keeps
   the public surface up top and the plumbing out of the way.

The split is by visibility and concern, not by kind: public functions live with
the section they serve; only private *functions* are deferred to the end —
private *types and constants* stay next to what they support.

## Code comments

- Inline comments and comment blocks are **2 lines maximum** — this includes
  multi-line `#` blocks above a statement. State the what/why directly; if it
  needs more room, it belongs in a docstring.
- Do **not** reference story/spec numbers or decision records (e.g.
  "spec 030 §5.2", "Phase 4", "ADR 019") in code comments **or
  docstrings**. Traceability lives in `context/specs/` and
  `context/decisions/`, not inline.

## Code smells

- **After writing or changing code, reflect on whether it contains any "code
  smell"** — the classic hints that something may be off: duplicated code,
  long methods, long parameter lists, magic numbers, primitive obsession
  (bare strings/ints/lists where a small type belongs), positional indexing
  that decodes a hidden field of a heterogeneous structure (`parts[2]` where
  the 2 secretly means "kind" — name the structure instead), deep nesting,
  feature envy, god classes, shotgun surgery, dead code, or speculative
  generality. First/last access on a homogeneous sequence (`lines[0]`,
  `rows[-1]`) is not this smell: there the position *is* the meaning, and it
  beats a `first, *_, last` destructure that materializes the middle.
- **A smell is a hint to look closer, not a rule to obey blindly.** When you
  spot one, dig in: understand *why* the code took that shape, and decide
  whether it is justified here.
- **Don't reach for numpy where plain Python suffices** (Clay, 2026-08-17):
  heavy dependencies belong only where measured scale justifies them (grep's
  posting intersections); small sets and lists take stdlib structures.
- **`assert` narrows, never validates.** An `assert` in `src/` is a
  type-narrowing statement after an ingress gate that already refused the
  bad shape (`assert path is not None` once the XOR check has run). It must
  never be the thing that turns bad input into a refusal — that is a
  classified `Result`, and `python -O` must change no behavior.
