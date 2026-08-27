# Bulk inserts, before and after, on five engines

- **Date:** 2026-08-26. **Spec:** 139. **ADR:** 056.
- **Question (Clay):** can every bulk insert take the driver's own
  batch through SQLAlchemy, does it help on each database, and are we
  guarded against every dialect's parameter limit?
- **Method:** `prototype/bulk_insert_bench.py` on sqlite and the four
  Docker engines (`docker/compose.test.yml`). *Micro*: 100 k
  block-shaped rows into the real `lex_postings` table, median of
  three, one wall per statement shape. *Verbs*: the live tree writing
  4,000 seeded linux files in batches of 1,000, then `reindex` with the
  lexical build no-op'd (gram epoch + chunks), then with it. Results in
  `prototype/results/{before,after,shapes}_<dialect>.json`.
- **Docker's honesty:** the *relative* numbers (shape A vs shape B on
  one engine) are trustworthy; the *absolute* seconds are not — the
  engines run in a Linux VM on a virtual disk with an extra network
  hop, and SQL Server runs under Rosetta. Round trips cost about what
  a same-datacenter network costs, so "fewer round trips wins" carries
  to production; "how many seconds" does not.

## Before (HEAD `f008417`, every site on SQLAlchemy's executemany)

Micro, µs per row (lower is better):

| engine | Core executemany (today) | driver executemany | multirow `VALUES` (the write path's entry shape) | other |
|---|---|---|---|---|
| sqlite / aiosqlite | 6.7 | **1.9** | 52.9 | — |
| Postgres / asyncpg | 8.9 (9.1) | 23.9 (11.4) | 70.7 | **`COPY` 4.25** |
| MySQL / aiomysql | 50.6 | 44.2 | 85.4 | — |
| SQL Server / aioodbc | 85.6 | 560 | 109.9 | with `fast_executemany=True` (SQLAlchemy 2.0.52): Core 41.1, **driver 31.1**, multirow 127 |
| Oracle / oracledb | 29.4 | 23.2 | (no multirow insert) | — |

(Postgres in parentheses: the same shapes re-run twenty minutes later
— the VM is noisy at the ±2× level for the per-row-round-trip shape,
which is why the pins take the *consistent* winner, not one run.)

Verbs, seconds (4,000 files, 57 MB):

| engine | write | reindex, no lexical | lexical delta |
|---|---|---|---|
| sqlite | 1.6 | 2.9 | 5.0 |
| Postgres | 3.4 | 4.8 | **57.9** |
| MySQL | 4.5 | 7.1 | 18.0 |
| SQL Server | 22.0 | 49.2 | **266.6** |
| Oracle | 4.0 | 15.4 | 13.2 |

## What the before-table decides

- **No single statement shape wins everywhere.** The driver's
  executemany wins where there are no round trips to lose (sqlite:
  3.5×) and loses where every row becomes one (asyncpg pipelines one
  execute per row; pyodbc round-trips per row at 560 µs). Postgres has
  a shape neither of the other two has — binary `COPY` on the same
  connection — and it is the only thing that moves Postgres's 58 s.
- **The multirow `VALUES` shape is the slowest on every engine that
  has it** (8× on sqlite, 8× on Postgres, 1.7× on MySQL, 1.3× on SQL
  Server). It leaves the write pipeline.
- **The pin is per dialect, from this table and the engine legs:**
  sqlite `"driver"`, Postgres `"copy"`, MySQL `"driver"` (the same
  client-side multirow render either way; the driver path drops Core's
  per-row work and chunks by bytes itself), SQL Server `"core"` — pyodbc's
  `fast_executemany`, reachable through aioodbc from SQLAlchemy 2.0.49
  (the tree moved to 2.0.52 to measure it), read 31 µs against 86, but
  engine-wide it rewrote UPDATE executemany's rowcount (nine leg
  failures), a second cursor hit "invalid cursor state" (twelve), and
  armed on the bulk statement's own cursor it silently landed 203 of
  300 NULL-free entry rows (block rows: 1,000 of 1,000) — refused — Oracle `"core"` (the Oracle leg failed 179 tests
  under `"driver"`: without Core's `setinputsizes` python-oracledb binds
  datetimes as DATE and drops microseconds), `GENERIC` `"core"`.
- **Two hazards the reviews raised on `COPY`, closed in the helper:**
  the asyncpg adapter opens its transaction on the first statement, so
  a raw COPY issued first would autocommit — the helper issues a
  statement before the COPY, and a Postgres-leg test rolls back a
  first-statement `bulk_insert` to zero rows; raw driver errors bypass
  SQLAlchemy's wrapping — the helper re-raises by SQLSTATE class.
- **The parameter guard.** Core mode is paged by SQLAlchemy itself
  (`insertmanyvalues_max_parameters`, and SQL Server's 1,000-row
  `VALUES` cap by its page size). Driver and copy modes bind each row
  separately, so no per-statement parameter cap applies to them — the
  reviews were right that the budget is not their datum — and aiomysql,
  the one driver that renders executemany as a multirow statement,
  chunks it at 1,024,000 bytes itself. `bulk_insert` still pages driver
  calls by `rows_per_statement(insertmanyvalues_max_parameters)` as a
  residency bound on one call (SQL Server's 2,099 → ~300 block rows;
  the 32,700 caps → ~4,600), and the declared-value pin in
  `test_dialects.py` counts the calls under the real budget. The one
  exposure that predates this work stays recorded: a single row larger
  than MySQL's `max_allowed_packet` fails under every mode.

## After (the landed tree: sqlite `"driver"`, Postgres `"copy"`, MySQL `"driver"`, SQL Server and Oracle `"core"`)

Micro, µs per row — the shipped mode in bold:

| engine | Core executemany | driver executemany | multirow `VALUES` | other |
|---|---|---|---|---|
| sqlite | 6.7 | **1.8** | 45.3 | — |
| Postgres | 17.6 | 10.6 | 70.4 | **`COPY` 5.7** |
| MySQL | 48.7 | **44.9** | 87.5 | — |
| SQL Server | **90.7** | 612 | 118 | — |
| Oracle | **114** | 97 | — | — |

Verbs, seconds (4,000 files, 57 MB), before → after:

| engine | write | reindex, no lexical | lexical delta |
|---|---|---|---|
| sqlite | 1.6 → 1.6 | 2.9 → 2.8 | **5.0 → 4.6** |
| Postgres | 3.4 → 3.7 | 4.8 → 4.7 | **57.9 → 43.6** |
| MySQL | 4.5 → 3.8 | 7.1 → 7.1 | **18.0 → 17.0** |
| SQL Server | 22.0 → 20.8 | 49.2 → 61.5 | 266.6 → 264.5 |
| Oracle | 4.0 → 14.4 | 15.4 → 15.0 | 13.2 → 14.9 |

Reading it honestly:

- **Postgres is the win the change was for**: the lexical delta drops a
  quarter (57.9 → 43.6 s) on `COPY`; the rest of that delta is the
  scan, the engine and `lex_df`'s btree on 487 k random keys, not the
  insert statement.
- **sqlite gains 8 % on the verb** where the micro promised 3.5× on
  the statement — at 4,000 files the insert is a small share of a
  5 s build (the engine and the keyset scan are most of it); the
  full-linux re-run below is where the insert half was 45 of 108 s.
- **MySQL's 6 %** is what "the same client-side render minus Core's
  per-row work" buys, as the reviews predicted.
- **SQL Server and Oracle are unchanged by construction** (`"core"`);
  their after numbers show the VM's noise floor instead — Oracle's
  write verb read 4.0 s before and 14.4 s after on identical code, and
  its Core micro 29 vs 114 µs, after two hours of legs on the same
  container. That noise is the reason the pins were taken from the
  *consistent* winner and the engine legs, never from one run.
- The write verb is flat everywhere within noise: the entry insert's
  8× shape was ~0.4 s of a 4,000-file write, as computed.

### Full linux checkout, sqlite (674,445 chunks; the spec 130 store, re-indexed)

Spec 130's landing store re-indexed under the new insert path
(`prototype/results/after_sqlite_full_linux.json`; gram epoch rebuilt
whole in 13.1 s first, then the lexical build):

| | before (spec 130 landing) | after |
|---|---|---|
| lexical delta, full linux, sqlite | **108.2 s** | **91.4 s** (−16 %) |
| tokenizer share | 14.4 s | 14.1 s |

The insert *statement* was one of several costs inside the ~45 s
"insert half": the driver path gives back 17 s of it; what remains is
the offload hops per drained batch, `lex_df`'s btree over 4.8 M random
keys, and the keyset scan — none of them a statement shape. Spec 130's
≤ ~50–60 s criterion is still missed; the next lever is ADR 055's
single-block-terms-inline fork (half the rows), not the insert path.
