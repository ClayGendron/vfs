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

## The clock

Every time a record stores, and every expiry it is compared with, comes from `store.now()`, which calls `store.clock`. The default reads the system's time, and a test replaces it with a clock it steps, from `tests/support/kernel_store.py`. No statement names the engine's own clock. A lint allows one line of the package to read the system clock, and none to read the monotonic clock: the budget of `close` is a `Deadline`.

## Close

`AsyncVirtualFileSystem.close()` closes the store as one more target of the gather it runs for its storages, within the same `close_timeout`.

1. The store stops taking transactions. A `query` or a `commit` after this raises `vfs.unavailable.backend`, "the filesystem is closed", and a `record_after` returns its warning.
2. A transaction that began before ends the try it has in hand and starts no other.
3. The store waits for its transactions in flight, for a budget of `close_timeout` less one second, and never less than half of it.
4. The engine is disposed, in a `finally`.

A transaction still running when the budget is spent closes its own connection when it ends and returns it to no pool, as an analysis pass a close left running does. A cancelled close keeps the store, as it keeps a storage, and a second `close()` waits for what is still in hand and disposes again. A store that was never used has no engine, and its close does nothing.

## Rules for code that keeps a record

1. Its table is added to `build_kernel_tables`, its name begins with one of `KERNEL_TABLE_PREFIXES`, and the change adds one to `KERNEL_FORMAT_VERSION`.
2. Its statements are in a module of `vfs.kernel_store`, never in `vfs.base` or `vfs.session`. A lint holds that the kernel and its faces import no SQLAlchemy.
3. Every stored time and every expiry compared comes from `store.now()`, and every read of a table that expires filters on the expiry.
4. Many rows are written with the members above, or by a statement of its own whose binds are fixed or whose rows are cut by `row_chunks`.
5. A record written beside a change names its form, record after or claim before.

## Not built yet

The store writes synchronously alone. Writing a record behind a read, in a buffer the store's own task empties, and removing expired records in the public `sweep` are designed and land next. The sessions and jobs that will keep records here are designed in their own specs and are not built either.
