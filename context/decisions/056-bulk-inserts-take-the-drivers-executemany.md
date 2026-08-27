# 056. Bulk Inserts Take the Driver's executemany on SQLAlchemy's Connection — One Owner, Pinned per Dialect by Measurement

- **Status:** accepted 2026-08-26 — decided by Clay on the insert-shapes
  memo ("lets build that ADR and spec. write a benchmark to test our
  code performance before and after. we should update write, grep,
  and lexical (and any other places it would benefit)"). Companions:
  ADR 049 (the offload seam the index builds drain through), ADR 055
  (the lexical index whose 10 M-row build wall is the trigger), spec
  128 (the `chunked()` / `ByteBatcher` owners this helper sits beside).
- **Date:** 2026-08-26
- **Deciders:** Clay Gendron
- **Decided by:** human
- **Context source:**
  `context/research/studies/2026-08-26-bm25-storage/insert-shapes.md`
  (the shapes measured on sqlite) and
  `context/research/studies/2026-08-26-bulk-inserts/` (the before/after
  benchmark on sqlite and the four Docker engines that this record's
  per-dialect pins are read from).

---

## Context

Every bulk insert in the database backend is one of three SQLAlchemy
shapes, and the spec 130 landing put a number on each (300 k
block-shaped rows into the real `lex_postings` table, sqlite via
aiosqlite, one transaction):

| shape | who uses it | µs/row |
|---|---|---|
| `session.execute(insert(t), rows)` — SQLAlchemy's executemany, rendered as insertmanyvalues pages | lexical build, gram postings, chunk rows, content rows, segment rows, the copy path | 5.2 |
| `session.execute(insert(t).values(rows))` — one multirow `VALUES` statement per parameter budget | `writes.py`'s entry insert, the multirow branch | 40.0 |
| `conn.exec_driver_sql(rendered INSERT, tuples)` — the driver's own executemany on SQLAlchemy's connection | nobody | 2.2 |
| raw `sqlite3.executemany` | (reference) | 2.0 |

Three facts follow. The lexical build's 108 s wall on the full linux
checkout (spec 130's missed criterion) is 10 M rows at the first
shape's ~5 µs — ~45 s of insert for ~42 s of engine. The write
pipeline's multirow shape is the slowest of the three at every page
size (100 → 4,671 rows: 37.7 → 41.0 µs), because SQLAlchemy compiles
a fresh N-row statement on every call and cannot cache it; the entry
table is one row per file, so the verb hides it (~3 s of the 48 s
linux write, ~0.4 s per 10 k-file batch). And the driver's own
executemany, reached through `exec_driver_sql` on the same connection
and transaction, is within 10 % of the raw driver. On sqlite and MySQL
Core's path is *already* `cursor.executemany` (neither dialect pages a
non-RETURNING insert), so the whole gap there is Core's per-row
parameter processing — the driver path skips that and nothing else
(the online verification, `studies/2026-08-26-bulk-inserts/review-verify.md`).

The catch is that "the driver's executemany" is five different
things. aiosqlite's is a thread-hopped `sqlite3.executemany`;
asyncpg's is a prepared-statement batch; aiomysql's is a client-side
multirow render; oracledb's is array DML; pyodbc's is one round trip
per row unless `fast_executemany` is on, which is exactly why
SQLAlchemy grew insertmanyvalues. So whether the driver path wins is
a per-dialect fact SQLAlchemy takes no position on (its
`use_insertmanyvalues` flag is about RETURNING, and is `True` on four
of our five dialects), and under the profile rule it is a measured
`DialectProfile` field, not a constant.

## Options considered

- **Leave the shapes as they are** — the lexical wall stays at ~108 s
  and the write path keeps its 8× shape. Rejected: the win is
  measured and the change is mechanical.
- **Bypass SQLAlchemy for the index builds** (raw driver connections,
  Postgres `COPY`, sqlite's C API) — fastest per engine, and five
  code paths with their own transaction, retry and offload story.
  Rejected: the connection, the transaction, the savepoint and the
  retry ladder are SQLAlchemy's and stay so; `COPY` is a Postgres-only
  fork noted below.
- **Widen the multirow `VALUES` shape to the index builds** — the
  write pipeline's shape; measured the slowest. Rejected, and the
  write pipeline's use of it goes too.
- **Driver executemany through `exec_driver_sql`, one owner, pinned
  per dialect by measurement** — chosen, with Postgres's `COPY` as a
  third mode behind the same owner once the before-table showed
  asyncpg's executemany losing to Core (one execute per row) while
  `COPY` halves Core.

## Decision

1. **One owner: `bulk_insert(session, table, rows)` in `dialects.py`**,
   beside `chunked()`, `statement_budget()` and the other
   statement-shaping helpers. Every bulk insert that learns nothing
   back — no `RETURNING`, no rowcount verification — goes through it:
   the lexical build (docs, summaries, blocks), the gram postings, the
   chunk rows, the content rows, the segment rows, the copy path's
   entry and content rows, and the write pipeline's entry insert.
   Single-row inserts and inserts that read something back stay on
   Core. Updates stay on Core: their verifier is the rowcount, and
   drivers disagree on what an executemany rowcount means.
2. **The statement is compiled once, per dialect, table and key set,
   and cached.** `insert(table).values({key: bindparam(key)})` compiled
   against the live dialect gives the driver's paramstyle for free;
   positional dialects take tuples in `positiontup` order, named
   dialects take dicts. Every row of a call carries the same keys
   (the first row's — a row with a different key set is a programming
   error and refused). Bind processors come from
   `type.dialect_impl(dialect).bind_processor(dialect)` per column and
   are applied to every row, so a `DateTime`, a `Boolean` or a
   `LargeBinary` reaches the driver exactly as Core would send it.
   Python-side **scalar** column defaults are filled for keys the rows
   omit; a callable, SQL-expression or `Sequence` default is refused
   (Core would evaluate or render those per row; no bulk table has one,
   and a pin keeps it so) — server defaults are the server's.
3. **The mode is a measured profile field.** `DialectProfile.bulk_insert:
   Literal["driver", "copy", "core"]` — `"driver"` issues
   `exec_driver_sql` on the session's connection; `"copy"` streams the
   same processed rows as asyncpg's binary `COPY`
   (`copy_records_to_table` on the session's raw connection, inside
   its transaction — the shape neither executemany has, and the only
   one that moves Postgres: 4.25 µs/row against Core's 9.1); `"core"`
   issues today's `session.execute(insert(table), rows)`. The value per
   dialect is read from the before/after benchmark on that engine
   **and the engine legs**, recorded in the study, and `GENERIC` is
   `"core"` (an unknown driver's executemany is not assumed fast).
   **Copy mode's two hazards are the helper's to close** (both reviews
   raised them): the asyncpg adapter opens its driver transaction
   lazily on the first *statement*, so a raw COPY issued first would
   autocommit — the helper issues a statement on the connection before
   the COPY, and a Postgres-leg test rolls back a first-statement
   `bulk_insert` and finds nothing; and a raw driver call bypasses
   SQLAlchemy's error wrapping — the helper re-raises by SQLSTATE class
   (23 → `IntegrityError`, the savepoint re-drive's key; anything else
   `DBAPIError` with the origin the retry ladder classifies). Oracle
   pins `"core"`: without Core's `setinputsizes`, python-oracledb binds
   a `datetime` as DATE and drops microseconds (179 engine-leg failures
   under `"driver"`); Core there is already array DML. **SQL Server
   pins `"core"`, and the faster shape is refused on evidence:**
   pyodbc round-trips per row (560 µs); its parameter-array
   `fast_executemany` — reachable through aioodbc from SQLAlchemy 2.0.49,
   the tree moved to 2.0.52 to measure it — read 31 µs against Core's
   86, but engine-wide it rewrote UPDATE executemany's rowcount (nine
   leg failures), a second cursor broke the one-active-statement rule
   (twelve, "invalid cursor state"), and armed on the bulk statement's
   own cursor it silently landed 203 of 300 NULL-free entry rows while
   landing 1,000 of 1,000 block rows. **That loss is explained**
   (`mssql-row-loss.md` in the study): the helper compiled a *one-row*
   insert, and SQL Server's dialect adds an implicit `OUTPUT inserted.id`
   to a one-row insert into an identity-keyed table — Core never sends
   that clause to executemany (`for_executemany=True` drops it). Under a
   parameter array the driver runs one `sp_execute` per row and each
   returns its own result set; pyodbc's fast path reads the first and
   returns, cursor close discards the rest with a TDS attention, and the
   server cancels the queued executions (3621) — a cancel is not an
   error. Block rows never lost because `lex_postings` has no identity
   column. The helper now compiles `.inline()`, and a no-server pin
   holds the text free of `OUTPUT`/`RETURNING` on all five dialects
   (Postgres and Oracle inherited `RETURNING` the same way). The
   `"core"` pin still stands, on performance: fixed, the array mode is
   still one RPC per row — 126–137 µs/row against Core's 88–99 on
   4,000 entry rows at the tree's page size — so the machinery stays
   out of the tree.
4. **The parameter guard is the dialect's, in both modes.** Core mode
   pages by SQLAlchemy's own `insertmanyvalues_max_parameters` (and
   SQL Server's 1,000-row `VALUES` cap by its page size). Driver and
   copy modes bind each row separately, so no per-statement parameter
   cap applies to them; aiomysql, which renders executemany as one
   client-side multirow statement, chunks it at 1,024,000 bytes itself,
   under any `max_allowed_packet` default. The helper still pages
   driver calls by `rows_per_statement(parameter_budget, rows)` — as a
   residency bound on what one call materialises, never a correctness
   guard — and callers keep their outer row and byte budgets
   (`_LEXICAL_INSERT_ROWS`, `_POSTING_BATCH_BYTES` and the like).
   Nothing grows with the batch. One exposure predates this record and
   stays recorded: a single row larger than `max_allowed_packet` fails
   on MySQL under every mode.
5. **Conflict semantics are unchanged.** The write pipeline's entry
   insert keeps its savepoint per chunk; an `IntegrityError` from the
   driver's executemany rolls that chunk back exactly as the multirow
   statement did, and the chunk re-drives row-wise. The copy path's
   `StaleSnapshot` on conflict is the same.
6. **The benchmark is the referee.** `bulk_insert_bench.py` runs the
   three statement shapes on the real table (micro) and the `write`
   and `reindex` verbs on a seeded linux sample (verbs), on sqlite and
   on every Docker engine, before and after. A dialect is pinned
   `"driver"` only where the micro shape wins on that engine, and the
   landing note carries both tables.

## Consequences

- Spec 139 lands it: the helper and its referees, the sites, the
  benchmark on five engines, the profile pins.
- The lexical build's insert half (~45 s of 108 s on the full linux
  checkout) drops toward ~20 s where the driver mode ships; with
  ADR 055's single-block-terms-inline fork it drops further. The
  entry insert's 8× shape leaves the write pipeline.
- `_engine_kwargs` is untouched; SQLAlchemy moved to 2.0.52 (the
  lock) — the upgrade was taken to measure `fast_executemany` through
  aioodbc, and stays because it is current.
- Both online reviews (`review-verify.md`, `review-refute.md`) are in
  the study; every objection they ranked is either closed by a pin
  above or recorded as a fork below.
- A `DialectProfile` field is added under the profile rule: the mode
  is a decision SQLAlchemy takes no position on, and its value is a
  measurement, not a guess. Unknown dialects stay on Core.
- **Forks (recorded, not taken):** MySQL `LOAD DATA LOCAL INFILE`
  (MySQL's own bulk path, security-gated, no bind processors); Oracle
  driver mode with the helper calling `setinputsizes` itself; SQL
  Server's `fast_executemany` on the inline statement — the loss is
  explained and the safe form proven at 300/1,000/5,000 entry rows,
  but it only beats Core on narrow, identity-free rows such as the
  lexical tables (31 vs 86 µs) and loses on entry-wide rows, so it
  waits for a measured workload that wants it, with a per-table
  landing test and a mid-batch failure test — or table-valued
  parameters;
  bulk *updates* through the driver
  (needs a rowcount contract per driver); the cached compile keyed on a live
  `Dialect` — if borrowed session factories (ADR on mounts) ever hand
  in a dialect the cache has not seen, the cache simply grows by one.
