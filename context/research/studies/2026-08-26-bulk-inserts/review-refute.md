# Adversarial review of the per-dialect bulk-insert pins

- **Date:** 2026-08-26. Produced by a research subagent told to refute
  each pin from official docs, driver source and issue trackers — no
  local code read, no code run. Companion: `review-verify.md`.

## Verdicts

1. **sqlite → "driver" — HOLDS.** CPython prepares once and rebinds per
   row; SQLite contributors recommend exactly that over multirow
   `VALUES` (forum post baf9c444d9: prepared-and-rebound ~2.8–3.7×
   faster than unprepared, marginal further gain from batching);
   aiosqlite's known pathologies (#34, #97) come from per-row hops,
   which one `executemany` call avoids. Transaction boundaries dominate
   (SQLite FAQ 19) and the helper runs inside the open transaction.
2. **PostgreSQL → "copy" — WEAKENED (one serious hole).** The adapter's
   lazy `BEGIN` means a raw COPY as the first statement autocommits
   (sqlalchemy discussions #8448, #12460). Raw asyncpg exceptions
   bypass SQLAlchemy's translation. COPY: triggers yes, rules no, no
   ON CONFLICT/RETURNING (asyncpg #454, #749); binary format is
   type-exact; jsonb works only because SQLAlchemy registers binary
   codecs expecting pre-serialised strings; a naive datetime into
   `timestamptz` is read as local time; `Decimal`, `bytes`, `bool`
   must be exact. asyncpg `executemany` is one Bind/Execute per row
   packed into 32 KB buffers with a single Sync — server-side per-portal
   cost, not network — and the ordering COPY < insertmanyvalues <
   executemany matches independent benchmarks.
3. **MySQL → "driver" — WEAKENED.** The rewrite silently falls back to
   per-row execution on unmatched shapes (expressions inside VALUES, a
   leading comment, the 8.0.19 `AS alias` form on aiomysql). The
   rewrite chunks by 1,024,000 bytes; **Core mode has no byte budget**
   (pages by row and parameter count only) — 1,000 × 100 KB blobs is a
   100 MB statement and `ER_NET_PACKET_TOO_LARGE`. `LOAD DATA LOCAL
   INFILE` is MySQL's real bulk path (~20× per its docs; security-gated).
4. **SQL Server → "core" — premise REFUTED, mode WEAKENED.** SQLAlchemy
   2.0.49 exposes `fast_executemany` on aioodbc (#13152). Discussion
   #9436: 5,000 × 28 columns, insertmanyvalues 62.7 s vs
   fast_executemany 4.0 s. With it on, a plain executemany (including
   `exec_driver_sql` with a parameter list) takes the fast path;
   `use_setinputsizes=False` is compatible (`do_set_input_sizes` returns
   early under fast_executemany). Hazards: `(max)` truncation on some
   platforms (pyodbc #867), memory growth (#802, sqlalchemy #5334). The
   1,000-row `VALUES` cap (error 10738) is real and covered by the
   default page size. TVPs need stored procedures; `BULK INSERT`/`bcp`
   need server-visible files.
5. **Oracle — HOLDS for large binds, parity hazard flagged (7).** Thin
   mode grows `max_size` across rows and defers LONG binds; no
   raise/truncate path found; `batch_size` exists; the only thin-async
   unknown was settled by the engine leg.
6. **Parameter guard — WEAKENED (wrong datum).** A driver executemany
   binds per row, so total-parameter budgets are irrelevant to it;
   paging adds calls, harmlessly. What it misses: MySQL bytes in core
   mode; fast_executemany / array DML are memory-bounded.
7. **Bind parity — WEAKENED on Oracle.** `setinputsizes` runs only in
   `_init_compiled`; on Oracle, `datetime` without it binds as DATE and
   drops fractional seconds (python-oracledb #563), `str` binds as
   VARCHAR in the DB charset rather than NVARCHAR. SQL Server already
   runs `use_setinputsizes=False`, so both modes bind identically there.
   SQL-expression and `Sequence` defaults are rendered inline by Core
   and would be silently dropped by a pre-rendered INSERT.

## Ranked objections and how each was settled

1. COPY outside the transaction → prologue statement in `bulk_insert`;
   a Postgres-leg test rolls back a first-statement `bulk_insert` and
   finds zero rows.
2. SQL Server's fast path exists → SQLAlchemy upgraded to 2.0.52 and
   `fast_executemany` benchmarked (`bulk-inserts.md`).
3. Oracle driver mode truncates TIMESTAMPs → Oracle pinned `"core"`.
4. MySQL core mode has no byte budget → MySQL pinned `"driver"` (the
   driver chunks by bytes); the rendered INSERT is pure placeholders
   ending in `VALUES (…)`, pinned by the rendering test; `GENERIC`
   stays `"core"` with the pre-existing exposure noted.
5. Raw-driver exceptions bypass translation → SQLSTATE-class wrapping
   in copy mode, pinned by tests.
6. SQL-expression / Sequence defaults → refused with callables.
7. Guard datum → reworded as a residency bound in driver mode.
