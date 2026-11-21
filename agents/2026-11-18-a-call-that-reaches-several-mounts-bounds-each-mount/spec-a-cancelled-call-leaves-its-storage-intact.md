# A cancelled call leaves its storage intact

This is the second draft, and it is not built. A fresh reader read it on 2026-11-18, reran its evidence, and found it fit to build, with five sentences to add, which are added. The first was reviewed by a fresh reader on 2026-11-18, in the second of the two reviews of this work that day, and found not yet fit to build. Two things stopped it. With the first draft's fix, a cancelled write on the in-memory storage always landed, which no other engine does, and the draft did not say so. And one decision could not be built where the draft put the code. Three things changed. The narrower fix the review pointed to, a second connection that keeps the database alive, was built as a spike and cut at every driver round trip: it never lost a row, and it left the storage refusing calls after some cuts, so it is not taken, and decision 6 says exactly where it failed. The fix that is kept now marks a cancelled unit of work, and a marked unit does not commit, so a cancelled write means on the in-memory storage what it means on a file database. That was also run at every round trip. And a unit that is marked before its turn sends nothing, by a check inside the unit. This draft is written against commit `a64dd18c`. It is not built and has not been reviewed again.

It is the first landing of the work in `spec.md` in this directory, and it stands alone: the defect is in the kernel as it is, with or without that design. The experiments are in `research.md`, sections 3.4 and 3.5.

## What was built, and where it differs

Built on 2026-11-20, on the branch `a-cancelled-call-leaves-its-storage-intact`, corrected the same day after a code review of the build, and widened on 2026-11-21 by decisions 9 and 10, which were taken after that review. Decisions 1 to 8 below are the spec as it was read. "Left as it is" and "Not checked" are corrected where decisions 9 and 10 changed them, and each correction says so. The build differs from decisions 1 to 8 in nine ways.

- **Decision 7 is changed twice.** First, a database in a file is covered too. The build cancelled a write on a database in a file at each of its 81 driver round trips. No row was lost at any. At 3 of the 81, each a `SELECT` inside the write's transaction, the next write was refused with `conflict` after its four attempts, and it succeeded once `gc.collect()` had run. The experiment this spec rests on had checked the rows after each cut and had not tried the next write. Second, decision 9 covers a storage that was handed its session factory. Every server engine is still left as it is.
- **A storage that is handed a session factory is covered as one that built its engine is.** Decisions 9 and 10 replace what this spec left: such a storage over an in-memory database was run out of reach only after its first touch and its cancelled write always landed, and over a file it was not run out of reach at all.
- **Decision 3 is widened by decision 10.** A marked unit is refused its next statement and its entry into a session, and not only its commit. The listener of decision 8, registered on a `Session` subclass, is gone: no session class is made, and the refusals are put on each session the host takes.
- **Decision 4 falls out of decision 10.** An attempt that was marked while it waited for its turn is refused as it enters its session, by the same check every SQLite session makes. The serialized session only gives the lock back.
- **First touch is covered from its first run** on every SQLite storage, because the dialect is read from the session's bind before the first attempt, with no IO. "Left as it is" said otherwise for the first first touch.
- **The caller is raised the cancellation it was cancelled with.** Decision 5 says that one cancellation is raised when the unit has ended. It is the first one the caller caught, the same exception and not a new one. A canceller that knows its own cancellation by the message on it, as an anyio cancel scope does, does not know a new one, and the error then escapes the scope.
- **`install_extensions` runs out of reach too.** Decision 8 hands each attempt of `with_retry` to the function that runs it out of reach. `install_extensions` is the one method of the host that opens a session outside `with_retry`, and a cancellation inside its probe closed an in-memory database. Its install and its probe now run as one attempt.
- **A cancelled call that waits on a worker thread waits for the thread.** A `grep` hands its verify batch to a worker thread inside its attempt. Before the build, a cancelled `grep` left the worker behind and its caller was back at once. Now its caller is back when the attempt has ended, which is when the worker has. The mark stops statements and not the thread. The test `test_a_cancelled_grep_leaves_the_next_call_whole` in `tests/test_offload.py` held the old order and failed on this branch; it now cancels the call, calls again while the worker is held, lets the worker go and awaits the cancelled call last.
- **"Unit of work" is "attempt" in the code, and the module of decision 8 is two.** `attempts.py` holds the task, the mark and the refusals, which every SQLite storage needs. `oneconnection.py` holds the serialized sessions and the re-arm.

The rule of decision 3 for a task started inside a unit is stated in the module docstring of `attempts.py`. No code depends on it today: the one task that outlives a write, the statistics pass, is started after the write's attempt has ended, and SQLAlchemy's own task that closes a session only rolls back.

The tests are `tests/storage/test_cancelled_call.py` for a whole storage on each of the four SQLite hosts, `tests/storage/database/test_attempts.py` for the task, the mark and the refusals, `tests/storage/database/test_oneconnection.py` for the serialized sessions and the re-arm, and `TestWhereAnAttemptRuns` in `tests/storage/database/test_engine.py` for the choice by dialect. The mutants they kill are rows T1 to T35 of `context/standards/mutant-ledger.md`, of which T18 and T19 are retired. No server engine was run.

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

### 9. Every SQLite storage runs each attempt out of reach

Decided on 2026-11-20, after the code review of the build. On SQLite each attempt runs in a task of its own, whether the storage built its engine from a URL or was handed a session factory, and whether the database is in memory or in a file. First touch is included, and so is `install_extensions`. The dialect is read from the bind of a session that is never entered, in `EngineHost._policy`, before the first attempt. Whether the database is in memory decides nothing about where an attempt runs.

On every other engine an attempt runs in its caller's task, as before. `TestWhereAnAttemptRuns` pins both halves.

Executed on 2026-11-21, on the build before this decision. Each of seven calls was cancelled inside the first statement of its transaction, on a storage that was handed a session factory over a file. Each of the seven cost one connection, thrown away by SQLAlchemy. After the cancelled `delete` of a directory the next write was refused, which is the locked writer of the changed decision 7. With the decision built, no connection is lost and the next write works after each of the seven.

Reason: the defect of this spec is a cancellation that reaches a SQLite connection, and it does not depend on who made the engine. Two rules, one for a built engine and one learned at first touch for a handed one over memory, left the handed file with neither.

### 10. A marked attempt sends no statement after the one in flight

Decided on 2026-11-20, with decision 9. Once an attempt is marked, the statement in flight ends and no other is sent. The attempt is refused at four places, each with `InvalidRequestError`, and its transaction is then rolled back.

- **At the entry of a session.** A marked attempt checks no connection out. This is decision 4, for every SQLite session.
- **Before each statement.** The statement that opens a transaction, `BEGIN` or `BEGIN IMMEDIATE`, is one of them, and so are the statements of a savepoint.
- **At the commit.** A commit is a call of the driver and not a statement, so it keeps its own refusal, which is the refusal of decision 3.
- **Not at a rollback.** A rollback to a savepoint is let through, and the rollback that ends the transaction is the driver's own call. They are what unwinds the attempt.

What this gives, on each of the four SQLite hosts alike. A read stops at its next statement, where it ran to its end. A delete of a directory, which releases no savepoint, stops at its next statement, where it sent every one and was stopped by its commit alone. A write that is cancelled before its commit has begun changes nothing, on a handed session factory too, where it always landed. A write that is cancelled at its commit or after has landed whole.

One thing is still sent. A connection that the pool is checking out has its settings stamped by the pool's own checkout listener: a probe for the vector function and six `PRAGMA` statements, and on a file engine that VFS built a read of the planner statistics. A refusal raised in that listener makes SQLAlchemy throw the connection away, which is the defect of this spec. The listener belongs to the pool, so it cannot tell a session VFS took from one the application made. A checkout that has begun therefore sends all its statements, and the attempt is refused at its `BEGIN`.

How it is built.

- The host wraps the session factory it built or was handed, once, when its dialect is known. Each session it takes is an `AttemptSession`. Entering one refuses a marked attempt, puts a `before_commit` listener on that session, and binds that session to a view of its engine, made by `Engine.execution_options`, that shares the engine's pool and carries the option `vfs_attempt`.
- The listener that VFS already puts on the `begin` event of every SQLite engine it serves, to send the `BEGIN`, calls `attempt_begins` first. For a connection that carries the option, inside an attempt, `attempt_begins` puts a `before_cursor_execute` listener on that connection. The connection is the session's own and ends with its transaction.
- Nothing is put on the engine, on its pool, on a DBAPI connection or on a session class. A session the application makes on the same engine carries no option and no listener, and is refused nothing, even inside a marked attempt.

Executed on 2026-11-21 as a spike, on SQLAlchemy 2.0.52 with aiosqlite, before the build. Each candidate was asked which statements it sees.

| Candidate | Sees | Does not see |
|---|---|---|
| `do_orm_execute` on the session | a statement passed to `session.execute` | a statement sent through `session.connection()`, which is how first touch, the statistics step and the savepoints send theirs; the `BEGIN`; a flush |
| `before_commit` on the session | `session.commit()` | a commit made on the connection; no code of VFS makes one |
| `before_cursor_execute` on the session's connection, put there at the session's `after_begin` | every statement through the connection: Core, driver SQL, a flush, `SAVEPOINT`, `RELEASE` and `ROLLBACK TO` | the `BEGIN`, which is sent before `after_begin` fires; the settings a checkout stamps, which use the DBAPI connection directly |
| the same listener, put there by the engine's `begin` listener for a connection that carries the option | all of the above and the `BEGIN` | the settings a checkout stamps |
| `commit` on the session's connection | both kinds of commit | nothing, but it cannot be used: see below |

Two refusals were found unsafe and are not built.

- A refusal raised in the connection's `commit` event leaves the transaction open. SQLAlchemy marks the transaction inactive, sends no rollback, and returns the connection to the pool without a reset. The row of the refused write was then read by the next caller of that connection, whose own commit made it permanent. So the commit is refused at the session's `before_commit`, where a failed commit is followed by a rollback.
- A refusal of `ROLLBACK TO SAVEPOINT` breaks the close of a session that holds a savepoint. The close raises half way, the transaction is not rolled back and the connection never returns to its pool. That was seen in the build's own tests, at a write cut at its first change. So a rollback is let through.

Executed on 2026-11-21, on the build before decisions 9 and 10 and after them. Each call was cancelled inside the first statement of its transaction. The figure is the number of statements sent after it. A rollback is not counted.

| Call | Built, in memory | Built, in a file | Handed, in memory | Handed, in a file |
|---|---|---|---|---|
| `stat`, `read` | 0, then 0 | 0, then 0 | 0, then 0 | 0 and a connection lost, then 0 |
| `grep` | 3, then 0 | 3, then 0 | 3, then 0 | 0 and a connection lost, then 0 |
| `write` of two files | 4, then 0 | 4, then 0 | 22 and the write landed, then 0 | 0 and a connection lost, then 0 |
| `edit` | 2, then 0 | 2, then 0 | 13 and the edit landed, then 0 | 0 and a connection lost, then 0 |
| `delete` of a directory | 8, then 0 | 7, then 0 | 8 and the delete landed, then 0 | 0, a connection lost and the next write refused, then 0 |
| `move` | 10, then 0 | 10, then 0 | 21 and the move landed, then 0 | 0 and a connection lost, then 0 |

A `stat` and a `read` send one statement in their transaction, so the cut at the first is the cut at the last. A read that sends several is the `grep`.

What it costs a call that nobody cancels, counted. A session the host takes is one wrapper object and one listener more than a session the application makes, and its connection is one listener more. The view of the engine is made once for each engine. Each statement calls that one listener, which reads one attribute and, while it is false, does nothing else. No statement is added and no lock is taken: a `stat` is 34 driver round trips and a `write` is 81, as before. Outside an attempt, as in the statistics pass, a connection is given no listener.

Reason: a caller that has given up should not go on loading the database, and a write it has given up on should not land later. Before this decision a marked read ran every statement it had left, and a marked write ran every statement up to its next savepoint release or its commit.

## Left as it is

- **First touch.** Corrected on 2026-11-21. First touch runs through `with_retry` and is run out of reach from its first run on every SQLite storage, by decision 9. A marked first touch is refused its next statement, is rolled back whole, tables and all, and runs again on the next call.
- **The rebuild's lease.** The fix also covers the rebuild on an in-memory storage, whose lease heartbeat is cancelled inside a statement today. This is read from the code and was not run.
- **How soon a cancelled caller is back.** Corrected on 2026-11-21. It waits for its unit to end, which by decision 10 is when the statement in flight has ended and the transaction is rolled back. A unit that waits on a worker thread, as a `grep` does, ends when the thread has. Before decision 10 a marked write ran on to its next savepoint release or its commit, and a marked read to its end.
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
- **First touch under a cancellation.** Corrected on 2026-11-21: it is now run. The first touch of a storage is cancelled at the first round trip of each kind it sends, and at each round trip that makes its connection, on each of the four SQLite hosts.
- **The sync kernel.** `VirtualFileSystem` runs its own loop. Its path to a cancellation was not read.
- **A borrowed in-memory database.** Corrected on 2026-11-21: it is now run, and decisions 9 and 10 cover it. A storage that is handed a session factory over an in-memory database runs every attempt out of reach, first touch included, and its marked attempt is refused as on any SQLite storage. It has no serialized session, so its calls take no turns: a statistics pass that is still running collides with the next call on the one connection, as it did before this spec, and the tests wait for the pass.
- **The `memdb` form of the kept-alive database beyond its first failure**, and why the collector is needed to end a refusal. The cause in decision 6 is reasoned from the result of `gc.collect()` and was not traced in SQLite.
- **A unit whose write uses no savepoint and a long plan.** The patch was run on a single-file write.
- **The line counts.** The 63 lines were counted at `a64dd18c`. The move was not made.

## Choices to confirm

1. **Marked shield, or the kept-alive connection?** Recommended: the marked shield. Alternative: the kept-alive connection. Its cost: after some cancelled calls the storage refuses every call until Python's collector runs, as executed in 6 of 81 cuts of a write.

## One line

On a database that lives in one connection, a verb's transaction runs in a task the caller's cancellation cannot enter, is marked when its caller is cancelled, refuses to commit once marked, and only then raises the cancellation, so the one connection is never thrown away and a cancelled write means what it means on a file.
