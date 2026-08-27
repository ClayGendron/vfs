# Insert shapes through SQLAlchemy — what the lexical build pays, and what it could pay

- **Date:** 2026-08-26. **Question (Clay):** can the lexical and gram
  index builds do their bulk inserts through SQLAlchemy the way the
  write pipeline does, and would it close the 108 s build wall?
- **Method:** `prototype/insert_shapes.py` — 300 k block-shaped rows
  into the real `vfs_lex_postings` table (sqlite via aiosqlite, one
  transaction), five shapes, one wall each; numbers in
  `results/insert_shapes.json`. sqlite only; the other engines are
  the spec's landing measurement.

| shape | who uses it today | µs/row |
|---|---|---|
| `session.execute(insert(t), rows)` — SQLAlchemy executemany (insertmanyvalues pages) | lexical build, gram postings, content, chunks, segments | 5.2 |
| `session.execute(insert(t).values(rows))` — one multirow `VALUES` statement | `writes.py` entry insert, the multirow branch | **40.0** |
| `conn.execute(insert(t), rows)` — same as the first, no session | — | 5.2 |
| `conn.exec_driver_sql(rendered INSERT, tuples)` — the driver's own executemany, on SQLAlchemy's connection and transaction | — | **2.2** |
| raw `sqlite3.executemany` | (reference) | 2.0 |

## What this says

1. **The lexical build already uses SQLAlchemy's bulk path.** Its
   `session.execute(insert(t), rows)` is the same shape as the content,
   chunk and segment inserts. There is no missed executemany.
2. **The write pipeline's multirow `VALUES` shape is the slow one** —
   7–8× slower per row than executemany, at every page size (100 → 4,671
   rows: 37.7 → 41.0 µs). SQLAlchemy compiles a fresh N-row statement
   on every call; multirow `.values()` statements are not cached. The
   entry insert is a small table (one row per file), so the write
   verb hides it: ~3 s of the linux gate's 48 s write at 78 k entries,
   ~0.4 s per 10 k-file batch. Cheap to take back: the executemany
   branch under the same savepoint has the same conflict semantics.
3. **Driver executemany through `exec_driver_sql` is 2.3× faster than
   today** and within 10 % of the raw driver. It keeps the engine, the
   connection, the transaction and the offload seam; it skips Core's
   per-row parameter processing. Applied to the lexical build's 10 M
   rows: ~45 s → ~20 s of the 108 s. Applied to the gram postings
   (245 k rows) it is noise.

## What it costs

- **Rendering per dialect.** `exec_driver_sql` takes the driver's
  paramstyle (`?` sqlite/aioodbc, `%s` aiomysql, `$n` asyncpg, `:1`
  oracledb). Render once from `insert(t).compile(dialect=…)` and hand
  positional tuples — one helper in `dialects.py`, not five.
- **Not every driver's executemany is fast.** SQLAlchemy's
  insertmanyvalues exists because psycopg2's and pyodbc's executemany
  are per-row round trips; asyncpg's is a prepared batch, aiomysql's
  is client-side multirow. So this is a per-dialect decision SQLAlchemy
  already takes a position on (`use_insertmanyvalues`,
  `supports_multivalues_insert`, pyodbc's `fast_executemany`) — read it
  off the live dialect, measure on every engine leg before pinning.
- **Bind processing.** `exec_driver_sql` bypasses type bind processors;
  the lexical rows are ints, bytes and a `BytewiseString` term (a
  DDL-side collation, no bind processing), so nothing is lost there —
  a table with processed types (JSON, datetimes) would need care.

## Recommendation

A small spec: (a) a `bulk_insert(conn, table, rows)` helper in
`dialects.py` that renders once per dialect and issues driver
executemany where the live dialect says it is a batch, falling back to
today's executemany elsewhere; (b) the lexical build and the gram
postings on it; (c) `writes.py`'s multirow branch replaced by the
executemany branch (measured, same savepoint). Landing measurement on
all four engine legs. Together with folding single-block terms into
their summary row (`landing-comparison.md`), the lexical build's insert
half drops from ~45 s toward ~10 s.
