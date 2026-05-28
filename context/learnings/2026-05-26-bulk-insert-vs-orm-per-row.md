# Core Bulk Insert vs ORM Per-Row `session.add` on the Write Path

> Date: 2026-05-26
> Scope: `DatabaseFileSystem` write/index path (`src/vfs/backends/database.py`),
> inherited by the Postgres and MSSQL backends.
> Trigger: writing one 3,679-line file (`src/vfs/backends/database.py` itself)
> through `VFSClient.write` took ~7s.

## Executive Summary

Writing a single large file is dominated almost entirely by **how the code-gram
delta-log rows are inserted**, not by how many there are. The current path stages
each gram delta as an individual ORM object via `session.add(...)` in a loop, then
flushes. For one 3,679-line file that's **69,234 gram rows**, and the ORM
unit-of-work pays a heavy per-object cost: building the SQLModel/Pydantic instance,
tracking it in the identity map, and — because the staging table's primary key
`seq` is a server-assigned autoincrement — fetching that key back for every row.

Replacing the per-object `session.add` loop with a single Core
`session.execute(insert(table), list_of_dicts)` is a measured **~50× speedup on
SQLite** and **~3.9× on Postgres**, with *identical* `seq` semantics. The change
belongs in the shared base path, so all three backends benefit from one edit.

The general lesson: **when staging many rows whose generated PK you never read
back in Python, use a Core bulk `insert()` of plain dicts, not ORM `session.add`
per object.**

## Measurements

Same workload throughout: insert 69,234 gram rows (`gram_key`, `entry_id`,
`doc_id`, `action`) into the real minted gram table.

### End-to-end `db.write` of `database.py` (SQLite, aiosqlite)

| Path | Time |
| --- | --- |
| Full write (chunk + gram index) | **7.38s** |
| Chunking only (`auto_index=False`) | 0.065s |
| No chunk, no index | 0.018s |
| Gram extraction CPU (whole file) | 0.025s |
| Building the 69K SQLModel gram objects | ~0.9s |

→ Essentially **100% of the cost is the gram-index insert.** Chunking, extraction,
and the entry write are all sub-100ms.

### Isolated 69,234-row insert

| Method | SQLite / aiosqlite | Postgres 18 / asyncpg |
| --- | --- | --- |
| (a) ORM `session.add()` per row (current) | 9.8s | 3.1s |
| (b) Core bulk `insert()` of dicts | 0.18s | 0.80s |
| **Speedup** | **~50×** | **~3.9×** |

### `seq` integrity under the bulk path

Inserting dicts that omit `seq` across two separate flushes, then ordering by
`seq`:

```
seq, gram_key, action
 (1, 10, 1)
 (2, 20, 1)
 (3, 30, 1)   ← batch 1
 (4, 40, 0)
 (5, 50, 0)   ← batch 2 (later flush)
```

- SQLite: non-null, strictly increasing, insertion-order preserved across batches.
- Postgres: dense `1..69234`, `max(seq) == count(*)`, monotonic.

The fold's "latest-action-wins per `(gram_key, entry_id)` by monotonic `seq`"
invariant holds unchanged — `seq` is an `INTEGER PRIMARY KEY` (rowid alias on
SQLite / identity on Postgres), assigned by the DB in insertion order whether or
not the ORM reads it back.

## Root Cause

Two independent costs stack up, and only the first is dialect-specific:

1. **Backend-independent ORM overhead.** Constructing 69K SQLModel instances runs
   Pydantic validation per object (~0.9s here), each gets registered in the
   session identity map, and the unit-of-work does per-object bookkeeping at
   flush. None of this depends on the database. Core `insert()` of dicts skips all
   of it.

2. **Dialect-dependent statement/round-trip behavior.** The staging PK `seq` is a
   server-assigned autoincrement (`models.py` `VFSGram.seq`), so the ORM wants the
   generated key back for every pending object:
   - **SQLite + aiosqlite:** degrades toward *one INSERT per row* to recover each
     key, and aiosqlite pays a greenlet→thread crossing per statement. Worst case
     → 9.8s.
   - **Postgres (asyncpg) / MSSQL:** SQLAlchemy 2.0 already batches the ORM insert
     via `insertmanyvalues` + `RETURNING`/`OUTPUT` (chunked ~1000 rows), so it
     never hits the per-row catastrophe. The ORM number (3.1s) is far healthier,
     which is why the *ratio* is smaller (3.9×) — the remaining win is object
     construction + identity map + the `RETURNING` clause we don't need.

Core insert wins on every backend because cost (1) is always eliminated, and on a
networked DB it additionally collapses N statements into a handful of multi-row
INSERTs, removing per-statement round-trip latency.

## The Pattern

Replace:

```python
for gram_key in grams:
    session.add(gram_model(gram_key=gram_key, entry_id=..., doc_id=None, action=ADD))
```

with accumulate-then-bulk-insert:

```python
rows.append({"gram_key": gram_key, "entry_id": ..., "doc_id": None, "action": ADD})
# once, at flush time:
await session.execute(insert(gram_model.__table__), rows)
```

**Preconditions for using it (all true for the gram delta-log):**
- The generated PK is never read off the in-memory object afterward (verified: no
  code reads `.seq` off a staged gram; the fold re-queries via SQL).
- No ORM-relationship cascade or event hook needs to fire on the inserted objects.
- Insertion-order PK assignment is acceptable (it is, and the DB guarantees it).

When those hold, the ORM identity map and PK fetch-back are pure waste.

## Session & Transaction State Management (the foundation this rests on)

The bulk-insert optimization is safe only because of how state is scoped in a
session. Getting this model right is what lets the write pipeline emit whatever
mix of statements is fastest without weakening the atomicity contract.

### The core rule: atomicity comes from the transaction, not from `flush()`

- **One session == one transaction** (until commit). Every statement you emit —
  ORM `session.add` flushes, Core `session.execute(insert(...))`, `update(...)`,
  `delete(...)` — accumulates in that one transaction.
- **`commit()`** is the only thing that makes the work durable.
- **`rollback()`** undoes *everything* since the last commit, regardless of how
  many statements or flushes happened in between.
- **`flush()`** only controls *when* pending ORM changes become SQL on the wire.
  It does **not** commit and does **not** create a durability/atomicity boundary.
  You can flush many times in a transaction and a single `rollback()` still erases
  all of it.

Consequence for the write pipeline: you do **not** need to funnel every change
through one final `session.flush()` for safety. Emit inserts/updates as you go; on
error `rollback()`; on success the single `commit()` in `_with_session`
(`base.py:1084`) makes it all durable together. "Single flush" and "single
transaction" are different guarantees — only the latter matters for all-or-nothing.

### What `flush()` is actually for

Two reasons, neither about atomicity:
1. **Read-back of server-generated values** — pulling autoincrement PKs / defaults
   back onto ORM objects. (This is precisely the cost the bulk-insert pattern
   skips: we never read `seq` back, so we never need the flush-driven fetch-back.)
2. **Visibility within the transaction** — making pending changes visible to a
   later `SELECT` in the same transaction.

SQLAlchemy's **autoflush** does #2 automatically: pending ORM changes flush right
before the next query, so explicit `flush()` is rarely needed. Note this means a
Core `insert()` issued while ORM objects are pending will trigger an autoflush of
those objects first — still inside the same transaction, no correctness impact.
Use `with session.no_autoflush:` only when you deliberately need to control
ordering.

### The one real gotcha: a DB error poisons the transaction

"Emit statements, on error rollback" is correct — but once a *database* statement
actually errors (e.g. `IntegrityError`), the transaction enters a failed state and
the connection **rejects all further statements** until the transaction ends
(Postgres: *"current transaction is aborted, commands ignored until end of
transaction block"*; SQLAlchemy enforces the same). Your only valid moves then:

- `session.rollback()` — abandon the whole transaction, or
- roll back to a **savepoint** opened with `session.begin_nested()` — undo just the
  failed sub-operation and continue.

So the pattern is **not** "catch the error and keep issuing statements on the same
session." It is "catch → rollback (full or to a savepoint) → then continue." The
codebase already uses the savepoint form at `database.py:1179`
(`async with session.begin_nested():` around the metadata-root insert, tolerating
the `IntegrityError`).

### How this maps onto the write pipeline today

- A single transaction wraps the whole write: `_with_session` (`base.py:1077-1087`)
  yields the session, commits once after `_write_impl` returns, and rolls back on
  any exception. `_write_impl` never commits — it catches `_WriteAbort` and calls
  `session.rollback()` (`database.py:1538-1540`).
- The "partial-persist, append-to-`errors`-and-continue" loop in
  `_write_phase_persist` (`database.py:2159-2162`) only works because those
  per-entry failures are **Python-level** (plan building, etc.) caught *before* a
  DB error aborts the transaction; the real `session.flush()` is deferred to the
  end of the phase.
- **Implication for the bulk-insert change:** emit the gram `insert()` inside this
  one transaction. If it fails at the DB level it poisons the transaction, so it
  must be treated as a whole-batch abort (raise `_WriteAbort` → existing
  `rollback()` cleanly undoes everything) — *not* swallowed and continued like the
  Python-level per-entry errors. If you ever need a gram-insert failure to be
  survivable mid-write, wrap it in `session.begin_nested()` and roll back to the
  savepoint.

### Practical guidance for keeping the write path fast

- Prefer the fewest, largest statements per transaction: collect rows, emit one
  Core bulk `insert()`, let it ride the existing transaction.
- Don't add defensive `flush()` calls "to be safe" — they cost round-trips and buy
  no atomicity. Flush only when you must read back a generated value or query
  pending state.
- Treat DB-level failures as transaction-fatal by default (abort + rollback). Reach
  for `begin_nested()` savepoints only where genuine partial-failure tolerance is
  required — they are not free (each is a `SAVEPOINT`/`RELEASE` round-trip).

## Where This Pattern Applies in the Repo

Ranked by expected payoff. All live in `src/vfs/backends/database.py` and are
inherited by `postgres.py` / `mssql.py`.

### 1. Gram delta-log staging — **primary, do this first**
- `_apply_trigram_maintenance` (the add/delete delta loops) — per-object
  `session.add` for every folded trigram.
- `_stage_chunk_delete_deltas` — same, for chunks leaving the index.

This is the 69K-row hotspot measured above. Highest volume, biggest win, and the
preconditions are cleanly satisfied. These two helpers stage onto the session and
are flushed once in `_write_phase_persist`; switching them to collect dicts and
emit one bulk `insert()` per table is the core change.

### 2. Entry / chunk / version persist — **secondary, scales with fan-out**
- `_write_phase_persist` — `session.add(incoming)` per changed object in a loop.
- `_insert_new` — `session.add(version_obj)` + `session.add(incoming)` per new file.
- Parent-dir revival loop — `session.add(d)` per directory.

Per single-file write this is only ~150 rows (one per chunk + a version), so it's
not today's bottleneck. But `write()` accepts a `Sequence[VFSEntry]`, so a **bulk
repo load** (thousands of files at once) multiplies this loop and inherits the same
autoincrement-`id` fetch-back penalty. Worth converting once #1 lands, especially
for ingestion workloads. Caveat: files create version snapshots and need their
`id`/relationships consistent — confirm the PK-not-read precondition per row type
before converting (chunks are the safe, high-volume subset).

### 3. Posting-block compaction — **forward-looking, build it bulk-first**
- The durable-store models exist (`_posting_block_model`, `_gram_batch_model`,
  `_gram_stat_model`) and `index(..., compile_post_list=...)` references the
  deferred flush that folds deltas into posting blocks (story 030 Phase 4 / 013).
- When that compaction path is implemented it will insert one posting-block row
  per `gram_key` per batch — another high-volume write. **Write it as a Core bulk
  insert from the start** rather than per-object `session.add`.

### Not applicable
- Embeddings and BM25 lexical tokens ride along on the entry row
  (`entry.embedding = vector`), so there is no separate per-row insert to batch.
- Postgres/MSSQL backends add no `session.add` loops of their own — they inherit
  the base write path, which is exactly why fixing the base class is sufficient.

## Recommendation / Next Steps

1. Convert #1 (gram delta-log staging) to Core bulk insert. Land with a
   before/after timing assertion so the ~50× SQLite / ~4× Postgres gain is pinned
   and protected from regression.
2. Re-measure the end-to-end `db.write(database.py)` — expect ~7.4s → well under
   1s.
3. Evaluate #2 against a real bulk repo-ingest workload before converting.
4. Keep the bulk pattern in mind when implementing #3.

## Reproduction Notes

- SQLite numbers: file-backed `sqlite+aiosqlite:///...db` (an in-memory `://` DB
  with `NullPool` gives each connection a *separate* empty database — a separate
  footgun, not relevant to this finding).
- Postgres numbers: local Postgres 18, throwaway `vfs_bench_tmp` database created
  and dropped by the bench; `asyncpg` driver pulled in via `uv run --with asyncpg`.
- SQLAlchemy 2.0.46, SQLite 3.50.4.

## Table Modeling: SQLModel vs Core (does every table need SQLModel?)

No. SQLModel (Pydantic + an ORM mapped class) earns its keep on some tables and is
pure overhead on others. A clean criterion splits them:

**Use SQLModel when *either* is true:**
1. The table is a **validated boundary/domain object** — constructed from input that
   needs normalization, validation, or derived defaults.
2. The table is **mutated in place through the ORM unit of work** — load a row,
   change attributes, rely on an auto-generated `UPDATE` at flush.

**Use a plain Core `Table` when *both* are true:**
1. **Internal, machine-generated** — never crosses a validation boundary.
2. **Append-only / bulk-written / compacted** — never load-mutate-flush via the ORM.

### How the VFS tables fall out

- **`VFSEntry` → keep SQLModel.** Hits both SQLModel criteria. `_row()`
  (`database.py:347-365`) routes construction through `VFSEntry` for path
  normalization, kind inference, content hashing, and lexical tokenization — real
  validation. And the write path mutates loaded rows in place (`_update_existing`,
  `_apply_incoming_embedding`, the carry-rename loop) and lets the unit-of-work emit
  the `UPDATE`. That is exactly what an ORM mapped class is for.

- **Gram family (`VFSGram`, `VFSPostingBlock`, `VFSGramBatch`, `VFSGramStat`) →
  strong candidates for Core `Table`.** Hits both Core criteria: internal index
  machinery (nothing about a trigram delta is "validated"), and append-only or
  compacted rather than ORM-mutated. Even the one mutation — the posting-block
  `is_active` flip on compaction (`models.py:932-943`, "never edited in place") — is
  better expressed as a bulk `update(table).where(block_id.in_(...)).values(...)`
  than per-row ORM mutation.

### Why this is more than aesthetics

1. **Structurally prevents the regression this memo is about.** With no mapped class
   for `VFSGram`, `session.add(gram(...))` is not expressible — the only write path
   is `insert(table)`. The 50× foot-gun cannot be reintroduced by a future edit.
2. **Removes the Pydantic construction cost** (~0.9s / 69K rows) on any path that
   still handles these rows as objects, not only the one being bulk-inserted.
3. **Likely simplifies the minting.** The per-instance table classes are minted via
   `SQLModelMetaclass` in `models.py` (`_build_gram_table_class` et al.). A Core
   `Table(name, self._model.metadata, Column(...), *indexes, schema=...)` is just an
   object constructed directly — bound to the same `MetaData`, so the single
   `create_all` and `schema_translate_map` behavior are unchanged. The
   `ACTION_ADD/DELETE` class vars become module-level constants.

### Caveat / sequencing

The **runtime win is already captured by the bulk-insert fix** — it bypasses
SQLModel on the hot path regardless of whether the class stays. So demoting the gram
family to Core is about *intent clarity, regression-proofing, and minting
simplicity*, not a second speedup. It is also a non-trivial refactor: it touches the
`_build_*_table_class` helpers and every query that references `gram_model.attr`
(which becomes `table.c.attr`). Sequence it **after** the bulk-insert fix lands, as a
deliberate cleanup — not bundled in. Worth promoting to a `context/decisions/` entry
once committed to.
