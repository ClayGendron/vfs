# The Kernel's Store

This page says where the kernel keeps its own records, how the code reaches them, and why. It is for people who change VFS, and above all for a change that adds a record.

## What it is

A record is a row the kernel keeps about calls: a session, a turn, a job, what a session saw. A record is not an [entry](../reference/glossary.md#entry). It has no path, it adds no kind, and no verb reads, lists, greps or searches it. The `/.vfs` view does not show it.

The kernel's store is the one object, for each file system, through which every record is read and written. In code it is `KernelStore`, in `src/vfs/kernel_store/store.py`. The kernel builds it in its constructor, with no I/O, and keeps it at `fs._kernel_store`.

**There is one store for each file system, because the store belongs to the kernel and not to a storage.** A storage only names where the records go. It writes no record and no statement for them. A third-party storage need provide nothing, and a mount that is not the root carries no machinery nothing calls.

**The store is private.** No public method returns it, and a session, a policy or a tool holds nothing that reaches it. It judges no rights and is handed no authority, because every call on it is the kernel's own. Which caller may see a record is decided by the code that owns the record. A test keeps a session from reaching the store, as one keeps it from reaching a mount.

## Where the records live

The root storage names a place through `record_place`, a `RecordPlace` of a URL, a label, the engine arguments, a schema and whether it is durable. The kernel asks once, in its constructor. A storage with no such attribute, or one that returns `None`, gets a place in memory.

| The root storage | Where the records are |
|---|---|
| A SQLite file | The mount's own file, in tables of their own, on an engine of the store's own |
| Postgres | The mount's own database and schema, on a pool of the store's own of the mount's size |
| In memory | A second database in memory, with its own connection and its own turn lock |
| No `record_place`, or `None` | A second database in memory |

The tables' names begin `vfs_kernel_`, `vfs_session` or `vfs_job`, and no mount table's name does. A lint holds both halves. The store never reads or writes a mount's table, and a storage never reads or writes a kernel table.

**A store transaction is never a mount's transaction and never rides a mount's connection.** The store builds its engine on the same `EngineCore` a mount's engine host is built on, in `storage/backends/database/core.py`, with the vector extension left out. So on SQLite its attempts run out of a cancelled caller's reach, its failed cursors close, its database in memory takes turns, and its close leaves no side file, by the code that already does each for a mount.

**On SQLite the store shares the file's one writer with the mount.** A store write waits behind a mount's write, and a mount's write behind a store write, each for a commit's length. Behind a batch on the mount, a store write waits its four tries of five seconds and then fails as unavailable. A read of the mount never waits on the store, because WAL serves a reader beside the writer. This price was ruled acceptable because SQLite serves demos and local applications, and a load that holds its writer for longer than about 20 seconds belongs on Postgres.

**On Postgres every store transaction runs at READ COMMITTED,** whatever the role, the database or the server defaults to. A counter must read what a rival committed while it waited for the rival's row lock. Without the pin, and with a default of REPEATABLE READ, two stores taking numbers were refused `40001`.

A file system whose records are in memory, and which holds a mount whose storage names a durable place, logs one `WARNING` under `vfs.kernel_store` at the first record it writes while such a mount is held. That is the one shape where the files outlive the process and the records do not.

## First touch

The tables are made at the store's first use, not when it is built, so a file system that keeps no record makes no table and opens no connection. `KernelStore.ensure_ready` runs it, and `query` and `commit` run it when it is needed.

First touch sends the file settings, then opens one writer transaction at a serialization point: `BEGIN IMMEDIATE` on SQLite, and on Postgres an advisory lock on a key made from the meta table's qualified name, which is not the mount's key. It makes the tables when the meta table is missing, reads the meta row, and writes one under a savepoint when there is none, so a rival's is harmless. A first touch that fails is not remembered, and the next call tries again.

The meta table `vfs_kernel_meta` holds one row, with `KERNEL_FORMAT_VERSION`. A change that adds or changes a kernel table adds one to that constant, in `src/vfs/models/kernel_rows.py`. Nothing migrates a table and nothing drops one. A store of another format is refused with `vfs.unavailable.schema`, and the file verbs go on. The refusal names the tables to drop, in the order they are to be dropped, and never a prefix: an application's own table can take a prefix, and a person told to drop by prefix would drop it too.

On Postgres, first touch needs `CREATE` on the schema once. A refusal for want of a privilege, SQLSTATE `42501`, is `vfs.unavailable` and not retryable, and never the `vfs.internal` the core's classifier would give it. It names the grant and each table.

## The two transactions

```python
await store.query(fn)
await store.commit(fn)
```

`fn` takes a `Transaction`, which is SQLAlchemy's `AsyncSession` under the one name the store gives it. In VFS a session is something else, so the store's code never calls this object a session.

- `query` reads. On SQLite it begins with a plain `BEGIN`, so it is no writer. Its `fn` writes nothing: a SQLite transaction that reads and then writes is refused whenever another connection committed in between.
- `commit` opens a writer transaction, `BEGIN IMMEDIATE` on SQLite, and commits when `fn` returns. An exception from `fn` rolls back and is raised as it is.
- Each runs `fn` under the core's retry, so `fn` runs again from its first statement when the engine asks. It waits as a mount's write does: four tries, and on SQLite five seconds a try.
- A store failure is one exception, `KernelStoreUnavailable`, whose `error` is a classified `ResultError`. Retries that run out are `vfs.unavailable` and retryable, not the `vfs.conflict` a mount's write answers, because no precondition of a caller's is stale.

Several functions can share one `commit`: `fn` hands its transaction to each. `transaction.info` is a dictionary that begins empty and ends with the transaction, and a retry starts with an empty one.

## A record that goes with a change

A record that goes with a change is written in a transaction of the store's own, never inside the mount's. The change may be on a mount that is not the root, and a storage commits inside its own method, so a promise of one transaction could not hold for every mount. There are two forms, and code that writes a record beside a change says which it uses.

**Record after.** The storage commits the change. Then `record_after(fn)` commits the record.

| The process dies, or the call is cancelled | What is left |
|---|---|
| before the change commits | nothing |
| after the change commits and before the record commits | the change, and no record |
| after the record commits | both |

A record exists only if its change landed. A landed change may lack its record. `record_after` never raises for a store failure: it returns a warning of kind `vfs.unavailable`, severity `warning`, which the caller adds to the change's result. Its tries run to their end out of the caller's reach, as [Cancellation](cancellation.md) says, so the second row of the table is a crash's width and not a cancellation's.

**Claim before.** `commit(claim)` writes a row that says what is about to be done. Then the change runs. Then `record_after(completion)` marks the claim done, or not done when the change was refused.

| The process dies, or the call is cancelled | What is left |
|---|---|
| before the claim commits | nothing |
| after the claim commits and before the change commits | the claim, and no change |
| after the change commits and before the completion commits | the claim and the change, and no completion |
| after the completion commits | all three |

A change exists only if its claim was committed first. A claim with no completion is in doubt, and the code that owns the claim settles it by reading the entry against what the claim recorded. This form is for a step that must not be carried out twice or by two callers. Both forms are pinned by child processes that leave through `os._exit` between two commits.

## Statements for many rows

A batch of 10,000 records is a supported call, so the store owns the chunking.

| Member | What it sends |
|---|---|
| `next_number` | One `UPDATE … SET counter = counter + :count … RETURNING`; the last number of the block, or `LookupError` when no row matches |
| `insert_rows` | The adapter's `bulk_insert`: `COPY` on Postgres, the driver's `executemany` on SQLite, paged under the live parameter budget |
| `upsert_rows` | Rows sorted by key, cut by `rows_per_statement`, one `INSERT … ON CONFLICT` a chunk; the rows written, and `ValueError` for a key given twice |
| `key_chunks` | Slices of keys for an `IN` list under the membership budget, at `width` binds a key |
| `row_chunks` | Slices of rows for a statement of a caller's own, under the parameter budget |
| `delete_where` | `DELETE … WHERE key IN (SELECT key … LIMIT :limit)`, whose binds do not change with the rows it removes |
| `delete_expired` | `delete_where` with the expiry as its filter and its order; a null expiry never expires |

The check for a key given twice is what keeps the engines alike: Postgres refuses a statement that updates one row twice, and SQLite stores the later row. Sorted keys make two processes lock rows in one order.

## Written behind

A record that may be dropped is written behind. `put_behind` adds rows to a buffer in memory, wakes the store's task, and returns. **It sends nothing and awaits nothing**, so a read verb whose whole dealing with the store is `put_behind` adds no statement and never waits for one. The writer is `src/vfs/kernel_store/behind.py`.

```python
store.register_behind(kind)
store.put_behind(kind, rows, scope=session)
await store.drain(session)
```

- **A kind** is a `BehindKind`: a name, the `write` function that writes a batch of its rows in the flush's transaction, and an optional `key`. The kernel registers each kind once, when it is built, and the kinds are flushed in that order, so a kind that needs another kind's rows is registered after it. A row of a keyed kind replaces a waiting row of that kind with the same key, in that row's place, and a keyed kind is handed its rows sorted by key. The store sorts them inside the flush, so keys that cannot be ordered fail as the kind's own `write` would, and only that kind is dropped. A deferred task is a kind too: its row names the task, and its key is what the task is for, so many requests become one run.
- **The task** is one background task for each store, named `vfs-kernel-store`. It starts at the first put, on the running loop, in a context of its own, so it carries no call's context variables and no attempt's mark. A put on another loop moves it there.
- **A flush** takes up to `FLUSH_ROWS`, 1,024 rows, from the head of the buffer and writes every kind's rows in one `commit`. The task flushes while the buffer holds anything, and then waits for the next put, `drain`, sweep chunk or `close`. There is no row count to reach and no timer, so rows put in one turn of the loop ride one flush, and batches grow with load.
- **What waits** can be read and withdrawn. `waiting_behind` returns the rows of a kind, by scope or by key, that are buffered or in the flush in flight. `discard_behind` takes rows out of the buffer, and a row of the flush in flight is stored all the same. `drain(scope)` waits until the rows of that scope put before the call are written or dropped, and raises when the flush that carried one of them failed, or when a flush ahead of them was held for a retry, since no row moves past the head of the buffer. A drain that is cancelled loses no row.

**Every record written behind may be dropped, and a record that may not be dropped is never written behind.** The buffer holds at most `BEHIND_CAPACITY`, 16,384 rows, and drops its oldest rows past it, counted in `store.dropped`. A process that dies loses its buffer and the flush in flight.

| A flush meets | What happens to its rows |
|---|---|
| a failure a retry can clear: the store cannot be reached, the writer is held past the retries, a connection is lost, or a privilege the role lacks | They go back to the head of the buffer, and the next put, drain, sweep chunk or close tries again. One `WARNING` at the first failure after a good flush, and one `INFO` at the first good flush after it |
| a failure no retry can clear: a broken constraint, a statement defect, a value over the engine's cap, or a kind's own code that raises | The flush is tried once more in one transaction, a kind at a time, each under a savepoint. The kinds that fail again are dropped, with one `ERROR` each, and the others are written |
| a store of another format | The whole flush is dropped, with no second try, under first touch's one `WARNING` |

A row that can never land would otherwise block the head of the buffer until every row behind it was dropped. A flush carries the rows of every kind and every session, so the second try keeps one broken row from costing the rows of kinds that have nothing wrong with them.

## The sweep

**Expired records are removed only when the public `sweep` is called.** `AsyncVirtualFileSystem.sweep()` on the root's trash, its default path, runs the trash's retention and, when that succeeded, awaits one pass of the store. Nothing else starts a pass: no count of writes, no timer and no close, and the task writes and never removes. A root that masks `sweep`, a storage that declares none, and a caller who may not write the root's trash run no pass. A pass that fails adds one error of severity `warning` to the sweep's result.

Expiry does not wait for the sweep. Every read of a table that expires filters on its expiry against `store.now()`, so a record past its expiry reads as absent before it is swept, and a null expiry never expires. The sweep only gives the space back. The sweep is `src/vfs/kernel_store/sweep.py`.

- **A sweeper** is registered by the code that owns a table with an expiry, with `register_sweeper`, in the order its parents and dependents need. It is handed the store, a transaction, the pass's one reading of the clock and a limit, and removes at most that many rows. `expiry_sweeper(table, key=..., expires=..., dependents=...)` is the common case ready-made: it removes the rows of each dependent table that name an expired parent, then the expired parents that have none left.
- **A pass** calls each sweeper in a `commit` of its own with `SWEEP_CHUNK`, 5,000, until a call removes no row. Each chunk is a transaction of its own, so a lock is held for a commit's length, and a pass that is cancelled or fails has removed whole chunks and nothing else.
- **The task's flush goes first.** Between two chunks the pass wakes the task when rows wait, waits for that one flush, landed or failed, and goes on. So rows written behind wait a chunk and not a pass.
- **Two passes at once** remove each row once: on SQLite they take turns on the one writer, and on Postgres the second waits for the first one's row locks and then finds the rows gone.
- **A place that holds no kernel table** is swept of nothing, and no table is made in it.

## The clock

Every time a record stores, and every expiry it is compared with, comes from `store.now()`, which calls `store.clock`. The default reads the system's time, and a test replaces it with a clock it steps, from `tests/support/kernel_store.py`. No statement names the engine's own clock. A lint allows one line of the package to read the system clock, and none to read the monotonic clock: the budget of `close` is a `Deadline`.

## Close

`AsyncVirtualFileSystem.close()` closes the store as one more target of the gather it runs for its storages, within the same `close_timeout`.

1. The store stops taking rows and transactions. A put after this is dropped and counted. A `query` or a `commit` raises `vfs.unavailable.backend`, "the filesystem is closed", and a `record_after` returns its warning.
2. A transaction or a flush that began before ends the try it has in hand and starts no other.
3. The task flushes what the buffer holds, **one try for each flush and not four**. On SQLite that try waits for the file's writer at most the smaller of the connection's `busy_timeout`, 5 seconds by the profile, and half of what is left of the budget. The store carries that wait in an execution option, and the engine core lowers `busy_timeout` to it before it sends the `BEGIN IMMEDIATE`. A flush that fails ends the flushing, and the rows left are dropped and counted with one `WARNING`. Nothing is raised for them, since every such row may be dropped.
4. The task ends, and is awaited and never interrupted. At the same time the store waits for its transactions in flight.
5. The engine is disposed, in a `finally`.

The budget is `close_timeout` less one second, which is kept for the dispose, and never less than half of it. It is a `Deadline` made once when `close` is entered, so the store reads no clock of its own, and a test passes `within=0` for a budget that is spent at once. The task is told the budget with the signal that tells it to close, before the close awaits anything, so no flush of its own starts after the close. Four tries behind a writer held by another process would take about 21 seconds against a timeout of 10; one try ends in about 5.

**A close that is cut short leaves nothing open.** When the budget is spent, when the kernel's timeout fires first, or when the close is cancelled, the task starts no further flush, the rows left are dropped and counted, and the engine is disposed. A flush or a transaction still running closes its own connection when it ends and returns it to no pool, as an analysis pass a close left running does, so SQLite's side files go when it does. A cancelled close keeps the store, as it keeps a storage, and a second `close()` waits for what is still in hand and disposes again. A store that was never used has no engine and no task, and its close does nothing.

## Rules for code that keeps a record

1. Its table is added to `build_kernel_tables`, its name begins with one of `KERNEL_TABLE_PREFIXES`, and the change adds one to `KERNEL_FORMAT_VERSION`.
2. Its statements are in a module of `vfs.kernel_store`, never in `vfs.base` or `vfs.session`. A lint holds that the kernel and its faces import no SQLAlchemy.
3. A read verb calls `put_behind` and nothing else of the store, unless a policy stops it: a read that is interrupted has read nothing, and its job is stored with `commit`.
4. Every stored time and every expiry compared comes from `store.now()`, and every read of a table that expires filters on the expiry.
5. Many rows are written with the members above, or by a statement of its own whose binds are fixed or whose rows are cut by `row_chunks`.
6. A record written beside a change names its form, record after or claim before.
7. A kind's `key` is its statement's conflict key or coarser. A kind that is also written synchronously makes its upsert keep the newest with `newest`, or, where its rows have no counter, reads `waiting_behind` before its synchronous write, calls `discard_behind` for the keys it writes, and states what a row of the flush in flight can then do.
8. A table that expires has a sweeper.

## Not built yet

The sessions, turns, stamps, changes and jobs that will keep records here are designed in their own specs and are not built. This store registers no kind and no sweeper of its own.
