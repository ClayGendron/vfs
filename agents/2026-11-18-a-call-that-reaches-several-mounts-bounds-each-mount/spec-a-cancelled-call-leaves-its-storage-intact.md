# A cancelled call leaves its storage intact

This is the second draft, and it is not built. A fresh reader read it on 2026-11-18, reran its evidence, and found it fit to build, with five sentences to add, which are added. The first was reviewed by a fresh reader on 2026-11-18, in the second of the two reviews of this work that day, and found not yet fit to build. Two things stopped it. With the first draft's fix, a cancelled write on the in-memory storage always landed, which no other engine does, and the draft did not say so. And one decision could not be built where the draft put the code. Three things changed. The narrower fix the review pointed to, a second connection that keeps the database alive, was built as a spike and cut at every driver round trip: it never lost a row, and it left the storage refusing calls after some cuts, so it is not taken, and decision 6 says exactly where it failed. The fix that is kept now marks a cancelled unit of work, and a marked unit does not commit, so a cancelled write means on the in-memory storage what it means on a file database. That was also run at every round trip. And a unit that is marked before its turn sends nothing, by a check inside the unit. This draft is written against commit `a64dd18c`. It is not built and has not been reviewed again.

It is the first landing of the work in `spec.md` in this directory, and it stands alone: the defect is in the kernel as it is, with or without that design. The experiments are in `research.md`, sections 3.4 and 3.5.

## The outcome wanted

A caller may cancel any call at any moment. Afterwards the storage holds every row it held, the call's own change is there whole or not at all, and the next call works. A cancelled write means the same thing on the in-memory storage as on a database in a file.

## Builds on

The branch `a-mount-is-listed-as-a-directory-is` at `a64dd18c`. This spec touches no file under `src/vfs` outside `storage/backends/database/`, and that directory did not change between `0d05c606` and `a64dd18c`.

`src/vfs/storage/backends/database/engine.py` is held at 1160 lines and `backend.py` at 1506 by `MODULE_LINE_BASELINE` in `tests/lint/allowlist.py`, and neither may grow. Decision 8 says how `engine.py` is paid for. `backend.py` is not changed.

`spec.md` in this directory depends on this one. Its decision 6 cancels a late call, and that is safe only once this is built.

## Terms

- **A database that lives in one connection.** An in-memory SQLite database. It exists only while its connection is open. `InMemoryStorage` is one, and so is any storage whose host reads `in_memory` as true at first touch.
- **Unit of work.** One attempt of one verb's transaction: the session is opened, the statements run, the transaction commits or rolls back, and the session is closed. Both runners of the database storage make one unit for each attempt and pass it to `EngineHost.with_retry`: `_rows` for reads, `backend.py:1377-1383`, and `_mutate` for writes, `backend.py:1483-1493`.
- **Host lock.** The lock that lets one unit at a time use the one connection. `_SerializedSession` takes it as the session is entered, `engine.py:1112-1118`, so it is taken inside the unit.
- **Mark.** What a unit of work carries once its caller has been cancelled.
- **Driver round trip.** One function queued to the worker thread that aiosqlite keeps for a connection. A `stat` is 34 of them and a `write` is 81.
- **Invalidate.** What SQLAlchemy does to a connection it no longer trusts: it closes it, and the pool opens another.

## The problem

One cancelled call destroys an in-memory storage.

Executed on 2026-11-18. A kernel over `InMemoryStorage` holds one file, `/a.txt`, with the content `old`. One driver round trip was made slow on the worker thread, and the caller gave up while it ran, with `asyncio.wait_for`.

| After `asyncio.wait_for(fs.stat("/"), ...)` was cut inside its `SELECT` | Result |
|---|---|
| The caller | `TimeoutError`, after the statement ended and not before |
| `read("/a.txt")` | `unavailable`: `no such table: vfs_entries` |
| `write` of another file | Success, on a new empty database |
| `read("/a.txt")` again | `not_found` |
| `ls("/")` | The new file only |

How often, executed at every driver round trip.

| Call | Cuts that lost the database |
|---|---|
| `stat("/")` | 32 of 34 |
| `read("/a.txt")` | 32 of 34 |
| `write` of `/a.txt` | 81 of 81, the commit included |

Who is exposed: any host that puts `asyncio.wait_for` or `asyncio.timeout` around a call, and any server that cancels a request when its client goes away. `InMemoryStorage` is the storage a kernel makes when it is given none.

A database in a file is not exposed. The same cuts at each of the 17 statements of a write cost one connection each and no row. A cut at any of the 15 statements before the commit left the old content, and a cut at the commit or after it left the new.

## The cause

Established by reading and by experiment.

1. **The cancellation lands on a wait for the driver.** A call spends its database time waiting on a future that aiosqlite's worker thread will fill. Cancelling the call cancels that wait. The thread runs the function to its end regardless. aiosqlite `core.py:48-76`, `150-160`.
2. **SQLAlchemy invalidates the connection.** It does so by three paths. A listener on the pool's `invalidate` event saw each one, with `CancelledError` as the reason.

   | Where the cancellation lands | Path | Read at |
   |---|---|---|
   | Inside a statement or a commit | `_handle_dbapi_exception`, then `invalidate` | sqlalchemy `engine/base.py:2246-2259`, `2369-2378` |
   | While the connection is checked out, in a listener | `_checkout`, `_checkin_failed`, `invalidate` | sqlalchemy `pool/base.py:743-749`, `1369-1376` |
   | While a returned connection is reset | `_finalize_fairy`, `invalidate` | sqlalchemy `pool/base.py:1007-1012` |

   The second path is wide in VFS. The session settings are stamped in a `checkout` listener on every checkout, `engine.py:1021-1031`, and they are 26 of the 34 round trips of a `stat`.
3. **The connection is the database.** Invalidating closes it. The pool opens another, and that is a new empty database.
4. **The next call runs on the empty database.** The new connection drops the host's ready latch as it connects, `engine.py:1145-1160`, but the call in hand has passed the latch already. It fails with `no such table`. The call after it provisions an empty schema.

SQLAlchemy is not at fault. A connection that was cancelled in mid-use is in an unknown state, and replacing a pooled connection to a server is sound. The fault is that VFS lets a caller's cancellation reach a connection that cannot be replaced.

The engine already knows this for its own work. It does not replace a stale connection of an in-memory database, because "replacing the last connection to any in-memory database drops it", `engine.py:747-752`. No verb has that protection.

## Decisions

### 1. After a cancelled call, the storage is whole, and a cancelled write means one thing on every engine

On every storage, after a call is cancelled:

- every row the call's transaction did not touch is as it was;
- the call's own transaction is committed whole or rolled back whole;
- the next call to the storage works;
- the caller's cancellation is raised to the caller, once.

What a cancelled write has done:

| Storage | Cancelled before its commit began | Cancelled at its commit or after |
|---|---|---|
| In-memory SQLite, under this spec | Rolled back. Executed in the spike, 79 of 79 cuts. | Landed. Executed, 2 of 2. |
| SQLite in a file, today | Rolled back. Executed, 15 of 15 statements. | Landed. Executed, 2 of 2. |
| Postgres, MariaDB, SQL Server, Oracle, today | Rolled back, when the connection is closed and replaced. Read in driver source, not executed. | It may have landed. Not executed. |

A caller cannot know which of the two a cancelled write did. That is so on every engine.

Reason: `memory.py:1-10` states the in-memory storage's purpose: one semantics, on the code path the production engines run. The first draft's fix made every cancelled write land there, and the review showed that tests on the default storage would then pin a behaviour production never shows.

### 2. On a database that lives in one connection, a unit of work runs out of reach of the caller's cancellation

When the host's `in_memory` is true, each unit of work runs in a task of its own. The caller waits for that task behind a shield. A cancellation of the caller does not enter the task, so it never lands on a statement, a checkout or a reset.

The test is the database and not the pool. A queue pool can hold an in-memory database too, as `engine.py:747-752` says.

Reason: all three paths of the cause start with a cancellation that arrives while the connection is in use. Keeping the cancellation out of the unit closes all three at once.

### 3. A cancelled unit is marked, and a marked unit does not commit

When the caller is cancelled, the unit is marked. The context variable is set inside the unit's own task, and it holds a mark object. The caller keeps the same object and flips it when it is cancelled, because a task cannot set a variable in another task's context. A task started inside a unit would inherit that object. No such task exists today, and one that is added sets the variable to `None` first.

- A listener on the session's `before_commit` event raises when the unit is marked. Nothing is sent to the driver: the refusal is raised before the commit statement. The session then rolls back and closes as it does after any failed write.
- The refusal at the commit, and the refusal at the lock of decision 4, raise `InvalidRequestError`. `with_retry` does not restart on it, so a refused unit is not run again. The caller drops it and raises its cancellation.
- SQLAlchemy raises the same event at the release of a savepoint. A marked unit therefore stops at its next savepoint release or at its commit, whichever comes first.
- A unit that is marked after its commit has begun is not stopped. The commit ends, and the write has landed.
- A read has nothing to commit. A marked read runs its statements to their end, and its answer is dropped.
- The unit's own result is dropped in every case. The caller gets its cancellation.

Executed, as a patch in the experiment, at every driver round trip.

| Call | Cuts | Database kept | Connections invalidated | Content afterwards |
|---|---|---|---|---|
| `stat("/")` | 34 | 34 | 0 | `old` |
| `write`, cut before the commit | 79 | 79 | 0 | `old` in all 79 |
| `write`, cut at the commit or after | 2 | 2 | 0 | `new` in both |

After every one of the 115 cuts, a write of another file succeeded.

Reason: the first draft let a marked unit run to its commit, and 81 of 81 cancelled writes landed. Refusing the commit is the review's fix, and it gives the split a file database gives. It is safe by construction, because nothing is injected into the connection: the refusal is raised in Python, where a failed write is raised today. The other way to stop a unit, SQLite's interrupt, was run in the first draft's experiments and lost the database in 8 of 81 cuts.

### 4. A unit that is marked before its turn sends nothing

A unit takes the host lock as its session is entered. A unit that is already marked when it gets the lock gives the lock back and ends there. No connection is checked out and no statement is sent.

Executed. A `stat` was made slow, and a `write` was started behind it and cancelled while it waited. The write's caller got its cancellation. The `stat` ahead ended with success. The only statement sent after the cancel was the `stat`'s own. The content was `old`, and no connection was invalidated.

The first draft put this decision outside the unit, and the review showed it could not sit there: the lock is taken inside the unit, at `engine.py:1112-1118`, so a shield around the unit covers the wait for the lock as well. The review offered a fix that takes the lock in the caller's task and tells `_SerializedSession` through a context variable that it is held. This draft does not take that fix. The mark of decision 3 already reaches the place where the lock is taken, so one check there is enough, and the lock keeps one owner and one path.

Reason: a write that its caller gave up on before it began should not land later, and should not make the calls behind it wait for work nobody wants.

### 5. The caller waits on the unit itself, and raises one cancellation when it has ended

The caller waits on the unit's task, never by polling. Each further cancellation that arrives while it waits is caught, and the wait goes on. When the unit has ended, one cancellation is raised.

Executed. A caller was cancelled twice, 10 ms apart, inside a slow statement of a `stat` and of a `write`. It was still waiting after each. It raised one `CancelledError` when the unit ended. The content was `old`, and no connection was invalidated.

Reason: the first draft's spike waited by sleeping a millisecond at a time. The review showed that a second cancellation would break that wait and raise before the unit had ended, which breaks decision 1.

### 6. A second connection that keeps the database alive was tried, and is not taken

The review pointed to a narrower fix: keep the database alive with a second connection, so that a cancelled call costs one connection, as it does on a file. Its premise holds, and the review executed it with plain `sqlite3`. It was then built as a spike on `InMemoryStorage` and cut at every driver round trip.

How it was built. The storage was made as VFS makes it, except that the engine's URL named a shared in-memory database, and one plain `sqlite3` connection to the same name was opened beside it and never used. The pool stayed the `StaticPool`, so the session factory was `_SerializedSessions` and the host read `in_memory` as true, as today. Two ways of naming the database were run: SQLite's shared cache, `file:NAME?mode=memory&cache=shared`, and SQLite's `memdb` file system, `file:/NAME?vfs=memdb`.

| | Shared cache | `memdb` |
|---|---|---|
| `stat`, 34 cuts | 34 kept every row. 32 cost one connection. | The same. |
| `write`, 81 cuts | 81 kept every row. 73 left `old` and 2 left `new`, and the next calls worked. After 6 cuts before the commit, the next read and the next write were refused: `database table is locked: vfs_entries`. | The sweep stopped at its first cut inside the transaction, round trip 29. The next read gave no answer in 20 s. |
| The refused cuts, run again | 4 of 53 cuts between `BEGIN` and the commit were refused. Each answered again, with `old`, after `gc.collect()`. | Not run. |
| A `stat` cancelled and not awaited, then a write | The write was refused: `database table is locked`. | The write was refused: `first touch kept losing to concurrent changes`. Four more connections were invalidated at checkout, and `ls` returned no rows. |

Where it failed. No row was ever lost. But after a cancelled call, the storage can refuse every call for a while, and nothing in VFS ends that while.

- INFERRED. The invalidated connection is asked to close, and SQLite keeps a connection open while one of its statements is still referenced. The cancelled call's cursor is referenced until Python collects it. Until then the old connection holds its transaction and its locks. The refusals ended at `gc.collect()`, which fits.
- INFERRED. An in-memory database has no write-ahead log, so a reader and a writer on two connections block each other. A database in a file runs in WAL mode, where they do not. That is why a file database survives the same cut cleanly and the kept-alive database does not.
- The last row of the table is the case `spec.md` needs: its timeout cancels a read and does not await it. The marked unit was run the same way. A `stat` and a `write` were cancelled and not awaited, and a read, a write and an `ls` followed at once. All three answered, and no connection was invalidated.

Reason: the choice is made on the two sweeps. The marked unit kept the database and answered the next call after 115 of 115 cuts, with no connection lost. The kept-alive database answered the next call after 109 of 115 cuts in one form and stopped in the other, and what ends a refusal is the garbage collector. It would also add a second connection, a database name and a second way of locking to the default storage.

### 7. Every other storage is left as it is

A database in a file, and every server engine, keeps SQLAlchemy's handling. A cancelled call costs one connection, which the pool replaces.

Reason: decision 1 already holds there. It was executed on a file database at every statement of a write. On a server engine a replaced connection also frees the statement's snapshot, which is wanted.

### 8. The code lives with the rest of what one connection needs

A new module, `src/vfs/storage/backends/database/oneconnection.py`, takes what is particular to a database that lives in one connection.

- `_SerializedSession`, `_SerializedSessions` and `_rearm_on_fresh_connection` move there from the foot of `engine.py`, with the same bodies but for the one check of decision 4 in `_SerializedSession.__aenter__`.
- The function that runs a unit of work is there: it starts the task, sets the mark's context variable inside it, waits as decision 5 says, and marks the unit on a cancellation.
- The `before_commit` listener is there. It is registered once, on a `Session` subclass that the in-memory host's session factory makes, so no other session in the process runs it. It reads the context variable and does nothing when no unit is marked.
- `EngineHost.with_retry` hands each attempt to that function when `in_memory` is true. Each attempt is one unit. A cancellation during the wait between two attempts raises at once and touches no connection.

`engine.py` loses 63 lines by the move, `engine.py:1098-1160`, and gains the hand-over. It ends shorter than it began, and its entry in `MODULE_LINE_BASELINE` is set to the new exact count. The counts are taken again when it is built.

Reason: the serialized sessions and the re-arm exist for the same fact as this fix. One module then says everything that fact costs.

## Left as it is

- **First touch.** First touch runs through `with_retry`, `engine.py:317`, but `in_memory` is not known until first touch reads it, so the first first touch is not shielded. A storage that VFS built is empty until it ends. First touch is shielded only when it runs again after a re-arm, when `in_memory` is already true. A marked first touch is refused like any unit and runs again on the next call.
- **The rebuild's lease.** The fix also covers the rebuild on an in-memory storage, whose lease heartbeat is cancelled inside a statement today. This is read from the code and was not run.
- **How soon a cancelled caller is back.** It waits for its unit to end. A marked write stops at its next savepoint release or its commit, and the statements before that still run. Today's caller already waits for the statement in flight.
- **Interrupting a statement.** Not built. It lost the database when it landed outside the transaction's own statements.
- **Loop shutdown.** When the event loop shuts down, every task is cancelled, the unit's own included, and an in-memory database goes with its loop, as today.
- **`close()`.** It does not wait for a unit. Closing the connection queues behind the statement in flight on the worker thread, and the kernel's `close_timeout` bounds that, as today.
- **The analysis pass.** It keeps its own shield and its interrupt. An earlier draft of this line said it never runs on an in-memory database, and that was wrong: the build, on 2026-11-20, saw its `BEGIN IMMEDIATE /* vfs_statistics */` and its `ANALYZE` statements on an `InMemoryStorage` after the first write. What `engine.py` stops for an in-memory database is the replacement of a stale connection, in `_replace_stale`, and not the pass. The pass is a task of the host, started outside any attempt, so it carries no mark and no caller's cancellation reaches it. Its interrupt at `close()` was not run against this fix.

## Cost

A unit of work on an in-memory storage gains one task and one context variable. No statement is added and no lock is taken.

The `before_commit` listener is on the session class, so it runs at each commit and each savepoint release on every engine. It reads one context variable and returns. At the reference deployment that is about a million reads of a variable a day, on the write path, and nothing on a verb call that only reads.

A cancelled call on an in-memory storage waits for its unit, where today it waits for its statement. The in-memory storage is the default for development and tests, and not the production target.

## Tests

In `tests/storage/test_cancelled_call.py`, written and seen failing before the code. No test reads a clock. A hook on aiosqlite's queue holds one chosen driver round trip on the worker thread until the test releases it, and tells the test when it is reached. The test cancels the call while the round trip is held, and then releases it.

The sweep traces each call once and cuts at each round trip it traced. It holds no count of its own, so it does not go stale when a call gains a statement. It is marked `slow`.

- For each driver round trip of `stat`, `read` and `write` on an in-memory storage, a call cancelled at that round trip leaves every earlier row readable.
- After each of those cuts, the pool recorded no invalidation and opened no new connection.
- After each of those cuts, a `write` and a `read` of another file succeed.
- A `write` cancelled at any round trip before its commit has changed nothing: the file holds its old content and no new version.
- A `write` cancelled at its commit or after has landed whole.
- The same sweep of `write` on a database in a file gives the same two answers at the same statements. This is the test that holds the two storages alike.
- A marked unit that reaches the release of a savepoint stops there: no statement of the write is sent after it but its rollbacks.
- A `write` cancelled while it waits behind another call sends no statement and does not land, and the call ahead ends as it would have.
- A caller cancelled twice while its unit runs is still waiting after the second, and raises one `CancelledError` when the unit has ended.
- The cancelled call raises `CancelledError` to its caller, and only after its unit of work has ended.
- A kernel over an in-memory storage lists every file after `asyncio.wait_for` around one of its calls ran out.
- A read that is cancelled and not awaited, as the kernel's timeout will do, leaves the next write working.
- On a database in a file, a call cancelled at each statement of a `write` loses no row and costs at most one connection. This passes today and pins decision 7.
- A commit of a session outside any marked unit is not refused.

## Scope

In: the function that runs a unit of work, the mark and the `before_commit` listener; the check in `_SerializedSession.__aenter__`; the hand-over in `EngineHost.with_retry`; the move to `oneconnection.py`; the baseline entry of `engine.py`; the tests; one paragraph in the docstring of `InMemoryStorage` and one in `with_retry`.

Out: every server engine and SQLite in a file. First touch. An interrupt. A second connection. The kernel, which is not changed. The timeout of `spec.md`.

## What the docs must say

- A call on any storage can be cancelled, and the storage is whole afterwards.
- A cancelled write may have landed. Read the file before writing it again.
- On an in-memory storage a cancelled call returns when its transaction has ended.

Pages: the docstrings of `InMemoryStorage` and `EngineHost.with_retry`, and the module docstring of `memory.py`, which says today that concurrent callers queue and says nothing of a cancelled one.

## What the review found, and the answer

| Finding | Answer |
|---|---|
| M1. Decision 4 cannot sit where the code is put. | Taken, by a different fix. The lock is not moved. The unit checks its mark when it gets the lock, and that was executed. |
| M2. A cancelled in-memory write always lands. | Taken. The kept-alive connection was built and cut at every round trip, and it is refused on that evidence, in decision 6. The shield is kept, and the review's commit listener is taken and was executed: 79 of 79 cuts before the commit rolled back. |
| L1. A wrong sentence about first touch. | Taken as written. |
| L2. A second cancellation. | Taken as written, and executed. |
| L3. Shutdown. | Taken in part. The sentence on loop shutdown is taken. `close()` does not wait for a unit at all, and "Left as it is" says what bounds it. |
| L4. The test sweep. | Taken as written. |

## Not checked

- **The server engines.** The third row of the table in decision 1 is read in driver source.
- **`close()` of a storage while a unit runs**, and loop shutdown. Both are stated from reading and were not run.
- **First touch under a cancellation.** Every cut was made on a storage that was already provisioned.
- **The sync kernel.** `VirtualFileSystem` runs its own loop. Its path to a cancellation was not read.
- **A borrowed in-memory database.** A host that hands VFS its own session factory over an in-memory database gets the shield through `in_memory`. It has no `_SerializedSession`, so decision 4's check has no place there. This was not run.
- **The `memdb` form of the kept-alive database beyond its first failure**, and why the collector is needed to end a refusal. The cause in decision 6 is reasoned from the result of `gc.collect()` and was not traced in SQLite.
- **A unit whose write uses no savepoint and a long plan.** The patch was run on a single-file write.
- **The line counts.** The 63 lines were counted at `a64dd18c`. The move was not made.

## Choices to confirm

1. **Marked shield, or the kept-alive connection?** Recommended: the marked shield. Alternative: the kept-alive connection. Its cost: after some cancelled calls the storage refuses every call until Python's collector runs, as executed in 6 of 81 cuts of a write.

## One line

On a database that lives in one connection, a verb's transaction runs in a task the caller's cancellation cannot enter, is marked when its caller is cancelled, refuses to commit once marked, and only then raises the cancellation, so the one connection is never thrown away and a cancelled write means what it means on a file.
