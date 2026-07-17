# Reading ORM Rows Without Creating Dirty State (Snapshot / Mode-Split Pattern)

> Date: 2026-06-02
> Scope: `DatabaseFileSystem` read+index path (`src/vfs/backends/database.py`),
> inherited by the Postgres and MSSQL backends. Async (`AsyncSession`), SQLModel
> `table=True` models.
> Trigger: the chunk/encode/compile pipeline reads rows, does CPU work
> (offloaded to threads), and writes back in batches. Loading those rows as
> tracked ORM entities created dirty unit-of-work state, per-row `UPDATE`s, and
> a thread-safety hazard when domain methods (`.chunk()`) ran off the event loop.

This is the **read-side companion** to
[`2026-05-26-bulk-insert-vs-orm-per-row.md`](./2026-05-26-bulk-insert-vs-orm-per-row.md).
That memo covers *how to write* many rows cheaply (Core/ORM bulk DML instead of
per-object `session.add`). This one covers *how to read* rows you intend to
bulk-write or feed to CPU work — **without** the session accumulating dirty
objects that trigger per-row flushes or unsafe cross-thread mutation.

## Executive Summary

Keep SQLModel. The fix is **not** "make all DB work explicit Core." It is to
stop treating "a SQLModel instance" as one lifecycle and split the backend into
two modes:

```
ORM mode          select(self._model) → mutate ORM rows → flush/commit
                  Good for normal CRUD, small write flows, object-graph edits.

Bulk/planning     read trusted snapshots → pure/domain logic (threadable)
mode              → explicit batched DML (insert/update by dicts, set-based UPDATE)
                  Good for the index pipeline: chunk / encode / compile, large updates.
```

The unifying idea — **three objects, three lifecycles**:

| Object | Role | Session-attached? | Mutated how |
| --- | --- | --- | --- |
| attached SQLModel row | persistence object | yes | ORM unit-of-work (`UPDATE` at flush) |
| detached/constructed `VFSEntry` | domain / planning object | **no** | freely, in Python / threads |
| `dict` of params | bulk-DML object | n/a | fed to `insert()/update()` |

The root cause of the pain is materializing **tracked entities** for work that
only needs **data**. If you never create the tracked entity, there is nothing to
go dirty, nothing to flush per-row, and nothing unsafe to hand a worker thread.

## The Core Rule

**Don't load tracked entities when you only need data.** Read columns (or
reconstruct an *unvalidated, detached* `VFSEntry`), do the work, write back with
batched DML.

`expunge()` is a valid *bridge* out of ORM mode, but it should not be the main
read strategy — by the time you expunge you have already paid the identity-map +
instrumentation cost, and (critically) if you expunge *after* offloading work to
a thread, it does nothing for the thread-safety hazard.

## Read Strategies, Ranked

### 1. Column / mappings select — best when you only need data

```python
rows = (await session.execute(
    select(self._model.id, self._model.parent_file,
           self._model.content_hash, self._model.path)
    .where(self._model.kind == "chunk")
)).all()                       # list[Row] — plain tuples, never tracked
```

`select(Model.col, ...)` returns `Row` objects, **not** entities — they never
enter the identity map and can never go dirty
([ORM SELECT guide](https://docs.sqlalchemy.org/en/20/orm/queryguide/select.html)).
Use `.mappings().all()` if you want `dict`-like rows. This is exactly what
`_chunk_pending` now does for existing chunks: the match planner receives plain
`Row` snapshots, so it is pure and safe to run via `asyncio.to_thread`.

### 2. Reconstruct a detached `VFSEntry` *without validation* — when you need domain methods

When the planning logic needs domain behavior (e.g. `file_row.chunk()`), don't
load an attached entity and expunge it. **Read columns, then rebuild a `VFSEntry`
with `model_construct`**, which skips Pydantic validation for trusted DB rows
([Pydantic: creating models without validation](https://docs.pydantic.dev/latest/concepts/models/#creating-models-without-validation)):

```python
rows = (await session.execute(
    select(self._model.id, self._model.path, self._model.content,
           self._model.ext, self._model.kind, self._model.version_number,
           self._model.owner_id)
    .where(self._model.kind == "file", self._model.chunked.is_(False))
)).mappings().all()

entries = [VFSEntry.model_construct(**dict(r), _fields_set=set(r.keys())) for r in rows]
```

Why this is elegant for hot read paths:
- The object is **never session-attached** → no dirty state, no expunge, no
  cross-thread session hazard. It is a pure domain object, safe to hand a thread.
- It **skips re-validation** of data the DB already derived. `VFSEntry`'s
  validators recompute `content_hash`, lexical tokens, and path derivations
  (`parent_dir`/`parent_file`/`name`); re-running them on trusted rows is waste
  on a hot path. (Profile — Pydantic v2 validation is not always slow — but these
  validators do real CPU.)
- **Caveat:** `model_construct` does no derivation, so you must `SELECT` every
  column the downstream logic reads — nothing is back-filled. Prefer base
  `VFSEntry` (not the `table=True` subclass) for planning work so it is obviously
  not a persistence row. Note SQLModel `table=True` models skip validation on
  normal construction anyway ([sqlmodel #453](https://github.com/fastapi/sqlmodel/issues/453),
  [#406](https://github.com/fastapi/sqlmodel/issues/406)) — `model_construct`
  makes the "trusted, unvalidated" intent explicit.

### 3. Load entities then `expunge()` — the bridge, not the default

```python
rows = (await session.execute(select(self._model).where(...))).scalars().all()
for row in rows:
    session.expunge(row)       # persistent → detached; will not flush
```

Legitimate when you genuinely needed ORM behavior during the read and now want
the instances as inert data. But you already paid object construction + identity
map, and a detached object that later touches a **deferred/expired** attribute
still faults (`DetachedInstanceError` sync; `MissingGreenlet` async). So load
narrowly and only touch loaded attributes.

**Timing is load-bearing.** If you offload work that mutates these instances
(`asyncio.to_thread(file_row.chunk)` sets `self.chunked = True`), the expunge
must happen **before** the offload — a worker thread must never touch a
session-attached instance ([AsyncSession concurrency](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)).
Expunging *after* the thread already ran is too late for safety; it only
suppresses the later flush.

### Comparison

| Approach | Prevents dirty/flush? | Frees identity map? | Breaks on… | Use when |
| --- | --- | --- | --- | --- |
| Column / mappings select | yes (no entity exists) | n/a | — | you need only data |
| `model_construct` detached `VFSEntry` | yes (never attached) | n/a | missing un-selected attrs | you need domain methods, trusted rows |
| Load entities + `expunge` | yes (detached) | yes | deferred/expired attr access | you truly needed ORM behavior first |
| `autoflush=False` / `no_autoflush` | **no** (commit still flushes) | no | — | only to control flush *ordering* |
| `make_transient` | yes, but strips PK → re-add INSERTs | yes | wrong if you meant UPDATE | niche |

## The Write Side (cross-reference)

Once the session holds no tracked entities, write with batched DML
(full detail in the sibling memo):

- **Insert children:** `await session.execute(insert(table), list_of_dicts)`
  (`insertmanyvalues`-batched).
- **Update by PK, per-row distinct values:** `await session.execute(update(self._model), dicts_with_pk)`
  (each dict carries the PK; uses `executemany`)
  ([ORM DML guide](https://docs.sqlalchemy.org/en/20/orm/queryguide/dml.html)).
- **Same value for many rows (e.g. flip `chunked=True`):** one **set-based**
  statement, not `executemany`:
  ```python
  await session.execute(update(table).where(table.c.id.in_(ids)).values(chunked=True))
  ```

## Do Not Rely On

- **`no_autoflush` / `autoflush=False`** — suppresses *automatic* flush before a
  query, but dirty rows still flush at `commit()`/explicit `flush()`. It treats
  the symptom (flush *timing*), not the cause (dirty objects exist). Reach for it
  only to control statement *ordering*
  ([Session basics](https://docs.sqlalchemy.org/en/20/orm/session_basics.html)).
- **`set_committed_value()`** — a narrow escape hatch to set an instrumented
  attribute without recording history. Fine as a tactical tool, too low-level as
  an architecture, and it does **not** fix the off-thread hazard (the method
  still runs on an attached instance).
- **`expunge()` after mutation/offload** — too late for thread safety, and easy
  to misuse.

## Async-Specific Footguns

1. **Never pass session-attached instances into `asyncio.to_thread`.**
   `AsyncSession` is an *unsynchronized, mutable, stateful* object, unsafe to use
   across concurrent tasks/threads
   ([asyncio docs](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)).
   Ship plain tuples/dicts or detached `model_construct` objects.
2. **`expire_on_commit=True` (the default) + async = `MissingGreenlet`.** Any
   attribute access on a still-attached entity after `commit()` emits a SELECT,
   which fails under asyncio. Set **`expire_on_commit=False`** on the async
   sessionmaker. (Verify how our sessions are built.)
3. **Autoflush fires only on ORM-enabled `execute()`**, not plain Core/`text()`
   ([discussion #9776](https://github.com/sqlalchemy/sqlalchemy/discussions/9776)).
   An ORM `insert()/update()` will autoflush *other* pending dirty objects first
   ([#11343](https://github.com/sqlalchemy/sqlalchemy/discussions/11343)) — one
   more reason to keep the session free of tracked entities so bulk writes run
   clean.
4. **`commit()` / `begin_nested()` always flush** pending changes regardless of
   autoflush settings.

## How This Maps onto `_chunk_pending` Today

The goal of `_chunk_pending` is narrow: find `chunked = False` files, build their
chunks, reconcile against existing chunks, write the result, flip the files to
`chunked = True`. It exercises every rule above:

- **Existing chunks → strategy 1.** Selected as column `Row` snapshots
  (`id, parent_file, content_hash, path`); `_match_chunks` is a pure planner over
  those snapshots, returning a `_ChunkReconcilePlan(new_chunks, carry_updates,
  stale_ids)` — no ORM instances cross into the `to_thread` call.
- **Pending files → strategy 2 or 3.** They need `.chunk()`. Cleanest is
  strategy 2 (`model_construct` a detached `VFSEntry` from selected columns, never
  attached). If kept as loaded entities (strategy 3), **expunge before** the
  `to_thread(f.chunk)` offload, not after — because `chunk()` mutates the instance
  in the worker thread.
- **Writes → batched DML.** `insert(table, dicts)` for new chunks; `update(table)`
  by `_id` for carry repositions; a **set-based** `update(...).where(id.in_(ids))`
  for the uniform `chunked=True` flip (not a per-row `executemany`).

## When To Stay in ORM Mode

This memo is about the *index/bulk* path. Normal CRUD and small object-graph
edits should still use the ORM unit of work — load `self._model`, mutate
attributes, let flush emit the `UPDATE`. That is expressive and correct; the
per-row cost only matters at volume. The discipline is **per-path**, not global:
reach for snapshots + batched DML in the hot index phases, keep the ORM where it
reads well.

## Sources

Documented behavior (primary):
- ORM SELECT guide (column selects return untracked `Row`): https://docs.sqlalchemy.org/en/20/orm/queryguide/select.html
- ORM-Enabled INSERT/UPDATE/DELETE (bulk DML, by-PK update, `insertmanyvalues`): https://docs.sqlalchemy.org/en/20/orm/queryguide/dml.html
- State management (`expunge`/`expire`/`make_transient`): https://docs.sqlalchemy.org/en/20/orm/session_state_management.html
- Session basics (autoflush, identity map, thread-safety FAQ): https://docs.sqlalchemy.org/en/20/orm/session_basics.html
- AsyncIO extension (implicit IO / `MissingGreenlet`, concurrency, `run_sync`): https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- `yield_per` for large reads: https://docs.sqlalchemy.org/en/20/orm/queryguide/api.html
- `insertmanyvalues` / Core connections: https://docs.sqlalchemy.org/en/20/core/connections.html
- Pydantic `model_construct` (skip validation for trusted data): https://docs.pydantic.dev/latest/concepts/models/#creating-models-without-validation
- SQLModel select (returns model instances): https://sqlmodel.tiangolo.com/tutorial/select/

Maintainer-stated (authoritative, not in the manual):
- Autoflush only on ORM-enabled `execute()`: https://github.com/sqlalchemy/sqlalchemy/discussions/9776
- ORM bulk insert/update autoflushes *other* pending objects: https://github.com/sqlalchemy/sqlalchemy/discussions/11343
- SQLModel `table=True` skips validation (intentional): https://github.com/fastapi/sqlmodel/issues/453 , https://github.com/fastapi/sqlmodel/issues/406 , https://github.com/fastapi/sqlmodel/issues/225

Verified against SQLAlchemy 2.0.46.
