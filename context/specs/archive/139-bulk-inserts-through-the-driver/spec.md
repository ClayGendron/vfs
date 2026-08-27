# 139 — bulk inserts through the driver: one owner, every bulk site, measured on five engines

- **Status: landed 2026-08-26.** Slices A–C green: `bulk_insert` in
  `dialects.py` with three modes, every bulk site converted, the write
  pipeline's multirow shape retired, pins read from the benchmark and
  the engine legs — sqlite `"driver"`, Postgres `"copy"`, MySQL
  `"driver"`, SQL Server and Oracle `"core"`, `GENERIC` `"core"`; CI
  leg 100 % coverage, all four engine legs green (run concurrently,
  under three minutes); ledger rows B1–B7 proven; the two online
  reviews (`review-verify.md`, `review-refute.md`) folded in. Details
  in the landing note below.
- **Born from** ADR 056 (`../../../decisions/056-bulk-inserts-take-the-drivers-executemany.md`),
  itself born from the insert-shapes measurement taken while
  explaining spec 130's missed build-wall criterion
  (`../../../research/studies/2026-08-26-bm25-storage/insert-shapes.md`).
- **Date:** 2026-08-26
- **Owner:** Clay Gendron
- **Kind:** consolidation plus a measured per-dialect pin in the
  database backend. No verb changes shape or output; every bulk insert
  writes the same rows through a different statement, and the
  benchmark is the referee that it is faster, engine by engine.
- **Depends on:** spec 128 (`chunked()` / `ByteBatcher` — the helper
  slices nothing and rides the callers' budgets), spec 130 (the
  lexical build, the largest site), ADR 049 (the offload seam: row
  batches are still drained off the loop and inserted on it).
- **Relates to:** the profile rule in `CLAUDE.md` (a `DialectProfile`
  field only for a decision SQLAlchemy takes no position on — the
  mode is one), the no-designed-caps rule (batching stays the callers'
  residency bound, never a ceiling).

---

## Intent

Every bulk insert in `src/vfs/storage/backends/database/` goes
through one helper that issues the driver's own executemany on
SQLAlchemy's connection where that is measured faster, and today's
Core executemany where it is not. The write pipeline's multirow
`VALUES` shape — the slowest of the three measured — is retired. The
change is proven by a before/after benchmark on sqlite and the four
Docker engines, and the per-dialect mode is pinned from that
measurement.

## Shape

- **§1 The owner.** `bulk_insert(session, table, rows)` in
  `dialects.py`. Compiles `insert(table).values({k: bindparam(k)})`
  once per `(dialect, table, keys)` and caches it; positional
  dialects get tuples in `positiontup` order, named dialects get
  dicts; `"copy"` (asyncpg)
  streams the same processed rows as a binary `COPY` on the session's
  raw connection; per-column bind processors from
  `type.dialect_impl(dialect).bind_processor(dialect)` applied to
  every row; Python-side scalar defaults filled for omitted keys,
  callable defaults refused; uniform key set required. Mode from
  `profile.bulk_insert`: `"driver"` → `exec_driver_sql` on the
  session's connection; `"core"` → `session.execute(insert(table),
  rows)`. An empty `rows` is a no-op. **The parameter guard:** driver
  mode pages its calls by `rows_per_statement(parameter_budget,
  rows)` with the budget read off the live dialect
  (`insertmanyvalues_max_parameters`), so a driver that renders
  executemany client-side as one multirow statement (aiomysql) never
  builds one Core would not have; Core mode is paged by SQLAlchemy
  itself. A pin referees it: a spy under a small monkeypatched budget
  counts the driver calls, and a declared-value assert fails if the
  guard is voided.
- **§2 The sites.** Each converts; behavior-preservation referees are
  the existing suites at each site:
  - `lexical.py`: `lex_docs` pages, `lex_df` batches, `lex_postings`
    batches (the `lex_stats` single row stays on Core).
  - `indexing.py`: `posting_list` drains, `chunks` rows.
  - `writes.py`: the entry insert under its savepoint (the multirow
    branch and `supports_multivalues_insert` read die; one branch,
    same `IntegrityError` re-drive), the content rows.
  - `segments.py`: the three segment inserts.
  - `topology.py`: the copy path's entry rows (under their savepoint,
    same `StaleSnapshot`), content rows, segment rows.
  - Anything else `grep -n "session.execute(insert"` turns up that
    learns nothing back.
- **§3 The profile pin.** `DialectProfile.bulk_insert: Literal["driver",
  "copy", "core"] = "core"`; `SQLITE`, `POSTGRESQL`, `MYSQL`, `MSSQL`,
  `ORACLE` set from the benchmark; `GENERIC` stays `"core"`. The
  before-table (`../../../research/studies/2026-08-26-bulk-inserts/bulk-inserts.md`)
  decides sqlite `"driver"`, Postgres `"copy"`, MySQL `"driver"`;
  the engine legs decide Oracle `"core"` (driver mode drops
  TIMESTAMP microseconds without `setinputsizes`) and SQL Server
  `"core"` — pyodbc's `fast_executemany` measured 31 µs against 86 but
  silently landed 203 of 300 NULL-free entry rows (ADR 056 pin 3), so
  Core's multirow pages stay.
- **§4 The referees.** Unit: rendering per paramstyle (qmark,
  format, numeric_dollar, named) against a stub dialect; processors
  applied (a `DateTime` and a `Boolean` row reach the driver as Core
  sends them — pinned by comparing the tuple the helper builds to
  Core's own compiled parameters); scalar default filled; callable
  default refused; mixed key sets refused; empty rows no-op; `"core"`
  mode issues Core's statement (spy); `"driver"` mode issues
  `exec_driver_sql` (spy). Integration: every bulk table has no
  callable Python-side default (a pin over `build_vfs_tables`). The
  existing site suites and all four engine legs prove the rows are
  the same.
- **§5 The benchmark.** `research/studies/2026-08-26-bulk-inserts/prototype/bulk_insert_bench.py`
  — micro (three shapes, 100 k rows, median of three) and verbs
  (`write` 4,000 linux files in batches of 1,000; `reindex` without
  and with the lexical build) — run **before** on the pre-change tree
  and **after** on the landed tree, on sqlite, Postgres, MySQL, SQL
  Server and Oracle. Results in `results/{before,after}_<dialect>.json`;
  the memo `bulk-inserts.md` carries the two tables.
- **§6 The ledger rows.** Executed under safe-restore: the processor
  dropped (a `DateTime` row reaches the driver raw — killed by the
  Core-parity pin); the default not filled (killed by the default
  pin); mode ignored (every dialect on `"driver"` — killed by the
  spy under a `"core"` profile); the write pipeline's chunk re-drive
  lost (killed by the existing arbitration suite); the copy prologue
  dropped (killed by the statement spy and the Postgres-leg rollback
  test); the SQLSTATE wrap dropped (killed by the error-class pins).

## Slices

- **A** — §1 + §4 + §6: the owner, its referees, the ledger rows;
  every profile still `"core"` so nothing changes on the wire yet.
- **B** — §2: the sites convert (green with `"core"` everywhere —
  the conversion is proven behavior-preserving before any mode
  flips).
- **C** — §3 + §5: the after-benchmark on five engines, the profile
  pins read from it, the landing note.

Gates: `scripts/ci.sh 3.13` at 100 % coverage under both engines;
all four engine legs; the benchmark's after ≤ before on every engine
for every shape a dialect pins `"driver"`, and the lexical delta on
the 4,000-file sample improves on every such engine.

## Landing criteria

- Every `session.execute(insert(...), rows)` bulk site in the backend
  goes through `bulk_insert`; `insert(...).values(rows)` with a list
  no longer appears in `src/`.
- Per-dialect mode pinned from the benchmark, recorded in the profile
  and the memo; `GENERIC` is `"core"`.
- The 4,000-file lexical delta on sqlite improves measurably (the
  micro shape says ~2×; the verb carries the engine and the scan too,
  so the landing note reports the actual figure).
- Ledger rows proven; the arbitration suites green; four engine legs
  green.

## Landing note (2026-08-26)

- **What landed.** `bulk_insert(session, table, rows)` — compiled once
  per (dialect facts, table, keys), Core's bind processors per column,
  scalar defaults filled, anything else refused, driver calls paged by
  the live parameter budget; `"copy"` with the transaction prologue and
  SQLSTATE-class error wrapping. Sites: lexical (docs, summaries,
  blocks), gram postings, chunk rows, content rows (write and copy),
  segment rows (three), the write pipeline's entry insert (one branch,
  same savepoint re-drive), the copy path's entry rows. SQLAlchemy
  2.0.46 → 2.0.52 (taken to measure `fast_executemany`; kept).
- **What the measurement decided, in order.** The before-table
  (`../../../research/studies/2026-08-26-bulk-inserts/bulk-inserts.md`)
  pinned sqlite `"driver"` and Postgres `"copy"` and showed the
  multirow shape slowest everywhere. The engine legs then overrode two
  candidate pins: Oracle `"driver"` failed 179 tests (DATE binds drop
  microseconds without `setinputsizes`) → `"core"`; SQL Server's
  `fast_executemany` — 31 µs against 86 — failed nine tests engine-wide
  (UPDATE rowcounts), twelve on a second cursor (one active statement
  per connection), and **silently landed 203 of 300 entry rows** armed
  on the bulk cursor alone → `"core"`, machinery removed, fork recorded.
- **After, 4,000 files:** lexical delta sqlite 5.0 → 4.6 s, Postgres
  57.9 → 43.6 s, MySQL 18.0 → 17.0 s; SQL Server and Oracle unchanged
  by construction; write verb flat within noise everywhere. **Full
  linux checkout, sqlite: lexical build 108.2 → 91.4 s (−16 %)** on
  spec 130's store re-indexed — the statement was one of several costs
  in the insert half; spec 130's ≤ 50–60 s criterion stays missed and
  the next lever is ADR 055's single-block-terms fork.
- **Criteria.** Every bulk site through the owner and no
  `insert(...).values(rows)` list form left in `src/` — met. Pins
  from the benchmark and legs, `GENERIC` `"core"` — met. sqlite's
  4,000-file lexical delta "improves measurably" — 8 %, honest but
  small: at that size the insert is a minor share of the build; the
  full-linux figure is the one to read. Ledger, arbitration suites,
  four legs — met.
- **Process residue.** The four legs and the CI leg now run
  concurrently (the db_test skill records it; the gate went from ~10
  to ~3 minutes); the benchmark's server sample defaults to 1,000
  files. The Docker VM's noise floor is real (Oracle's write verb read
  4.0 s and 14.4 s on identical code) — pins come from consistent
  winners and legs, never one run.

