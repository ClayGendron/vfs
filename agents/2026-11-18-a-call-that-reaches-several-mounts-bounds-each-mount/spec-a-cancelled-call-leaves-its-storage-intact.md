# A cancelled call leaves its storage intact

This is the second draft, and it is not built. A fresh reader read it on 2026-11-18, reran its evidence, and found it fit to build, with five sentences to add, which are added. The first was reviewed by a fresh reader on 2026-11-18, in the second of the two reviews of this work that day, and found not yet fit to build. Two things stopped it. With the first draft's fix, a cancelled write on the in-memory storage always landed, which no other engine does, and the draft did not say so. And one decision could not be built where the draft put the code. Three things changed. The narrower fix the review pointed to, a second connection that keeps the database alive, was built as a spike and cut at every driver round trip: it never lost a row, and it left the storage refusing calls after some cuts, so it is not taken, and decision 6 says exactly where it failed. The fix that is kept now marks a cancelled unit of work, and a marked unit does not commit, so a cancelled write means on the in-memory storage what it means on a file database. That was also run at every round trip. And a unit that is marked before its turn sends nothing, by a check inside the unit. This draft is written against commit `a64dd18c`. It is not built and has not been reviewed again.

It is the first landing of the work in `spec.md` in this directory, and it stands alone: the defect is in the kernel as it is, with or without that design. The experiments are in `research.md`, sections 3.4 and 3.5.

## What was built, and where it differs

Built on 2026-11-20, on the branch `a-cancelled-call-leaves-its-storage-intact`, corrected the same day after a code review of the build, widened on 2026-11-21 by decisions 9 and 10, which were taken after that review, and simplified the same day by decision 11, which was taken after a second review. Decisions 1 to 8 below are the spec as it was read. Decisions 9 and 10 are written for the storages that decision 11 leaves. "Left as it is", "Cost", "Tests", "Not checked" and "One line" say what is built. The build differs from decisions 1 to 8 in ten ways.

- **Every storage builds its engine.** By decision 11 a storage always builds its engine and owns it. `session_factory=` is gone from `DatabaseStorage` and from `EngineHost`, and with it every rule that asked whether the engine was the storage's own.
- **Decision 7 is changed.** A database in a file is covered too. The build cancelled a write on a database in a file at each of its 81 driver round trips. No row was lost at any. At 3 of the 81, each a `SELECT` inside the write's transaction, the next write was refused with `conflict` after its four attempts, and it succeeded once `gc.collect()` had run. The experiment this spec rests on had checked the rows after each cut and had not tried the next write. Every server engine is still left as it is.
- **Decision 3 is widened by decision 10.** A marked unit is refused its next statement and the first use of a session, and not only its commit. The `before_commit` listener of decision 8 is on a `Session` subclass, as decision 8 said, and that class is the class of every session a SQLite storage makes.
- **Decision 4 falls out of decision 10.** An attempt that was marked while it waited for its turn is refused at the first use of its session, before a connection is checked out, by the check every SQLite session makes. The serialized session only gives the lock back.
- **First touch is covered from its first run** on every SQLite storage, because the host builds its engine at construction and reads its dialect there, with no IO. "Left as it is" said otherwise for the first first touch.
- **Where an attempt runs is declared by the dialect's profile.** Decision 8 asked `in_memory`. The build asks `DialectProfile.attempts_out_of_reach`, which SQLite alone sets, at the two places an attempt is started and at the one place the refusals are put in.
- **The caller is raised the cancellation it was cancelled with.** Decision 5 says that one cancellation is raised when the unit has ended. It is the first one the caller caught, the same exception and not a new one. A canceller that knows its own cancellation by the message on it, as an anyio cancel scope does, does not know a new one, and the error then escapes the scope. A caller whose attempt was itself cancelled, as at loop shutdown, is raised its own cancellation too.
- **`install_extensions` runs out of reach too.** Decision 8 hands each attempt of `with_retry` to the function that runs it out of reach. `install_extensions` is the one method of the host that opens a session outside `with_retry`, and a cancellation inside its probe closed an in-memory database. Its install and its probe now run as one attempt.
- **A cancelled call that waits on a worker thread waits for the thread.** A `grep` hands its verify batch to a worker thread inside its attempt. Before the build, a cancelled `grep` left the worker behind and its caller was back at once. Now its caller is back when the attempt has ended, which is when the worker has. The mark stops statements and not the thread. The test `test_a_cancelled_grep_leaves_the_next_call_whole` in `tests/test_offload.py` held the old order and failed on this branch; it now cancels the call, calls again while the worker is held, lets the worker go and awaits the cancelled call last.
- **"Unit of work" is "attempt" in the code, and the module of decision 8 is two.** `attempts.py` holds the task, the mark and the refusals, which every SQLite storage needs. `oneconnection.py` holds the serialized sessions and the re-arm.

The rule of decision 3 for a task started inside a unit is stated in the module docstring of `attempts.py`. No code depends on it today: the one task that outlives a write, the statistics pass, is started after the write's attempt has ended, and SQLAlchemy's own task that closes a session only rolls back.

The tests are `tests/storage/test_cancelled_call.py` for a whole storage on each of the two SQLite hosts, in memory and in a file, `tests/storage/database/test_attempts.py` for the task, the mark and the refusals, `tests/storage/database/test_oneconnection.py` for the serialized sessions and the re-arm, `TestWhereAnAttemptRuns` and `TestConstruction` in `tests/storage/database/test_engine.py` for the choice by dialect and for the engine a storage builds, and `TestTheEngineArguments` in `tests/storage/database/test_drivers.py` for the engine arguments. The mutants they kill are rows T1 to T44 of `context/standards/mutant-ledger.md`, of which T18, T19, T20, T25, T26, T27, T30, T32 and T34 are retired: each named a part that decision 10 or decision 11 removed. No server engine was run.

## The outcome wanted

A caller may cancel any call at any moment. Afterwards the storage holds every row it held, the call's own change is there whole or not at all, and the next call works. A cancelled write means the same thing on the in-memory storage as on a database in a file.

## Builds on

The branch `a-mount-is-listed-as-a-directory-is` at `a64dd18c`. This spec touches no file under `src/vfs` outside `storage/backends/database/`, and that directory did not change between `0d05c606` and `a64dd18c`.

`src/vfs/storage/backends/database/engine.py` is held at 1160 lines and `backend.py` at 1506 by `MODULE_LINE_BASELINE` in `tests/lint/allowlist.py`, and neither may grow. Decision 8 says how `engine.py` is paid for. `backend.py` was to be left unchanged. Corrected on 2026-11-21: it is changed. Its constructor takes `engine_arguments=` where it took `session_factory=`, it gains the `engine` property, and its docstrings state what a cancelled call does. It ends at 1,505 lines and `engine.py` at 1,042, and each entry of the baseline is lowered to its count.

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

Decided on 2026-11-20, after the code review of the build, and written again on 2026-11-21 for the storages that decision 11 leaves. On SQLite each attempt runs in a task of its own, whether the database is in memory or in a file. First touch is included, and so is `install_extensions`. Whether the database is in memory decides nothing about where an attempt runs.

The choice is a declared field of the dialect's profile, `DialectProfile.attempts_out_of_reach`. It is true for SQLite and false for every other profile, the floor that serves an unknown dialect among them. The host reads its profile from the dialect of the engine it builds, at construction, with no IO, so the first attempt of a storage is covered as every later one is. `with_retry` and `install_extensions` read the field where they start an attempt, and the constructor reads it where it puts the refusals of decision 10 in place. The test that puts SQLite's explicit `BEGIN` and its settings in place still asks for the dialect by name, because that is a fact about SQLite's transaction control and not about attempts.

On every other engine an attempt runs in its caller's task, on plain sessions, as before. `TestWhereAnAttemptRuns` pins both halves, and `test_sqlite_alone_declares_that_its_attempts_run_out_of_reach` pins the declaration.

Reason: the defect of this spec is a cancellation that reaches a SQLite connection. In memory it costs the database, and in a file it can cost the next writer its lock. One rule for the dialect covers both, and a rule that asked where the database is held left the file with none. The field follows the pattern of the profile: a decision SQLAlchemy takes no position on is declared once, by name, and not tested by the dialect's name where it is used.

### 10. A marked attempt sends no statement after the one in flight

Decided on 2026-11-20, with decision 9, and written again on 2026-11-21 with the mechanism as it is built after decision 11. Once an attempt is marked, the statement in flight ends and no other is sent. The attempt is refused at three places, each with `InvalidRequestError`, and its transaction is then rolled back.

- **At the first use of a session.** A marked attempt checks no connection out. This is decision 4, for every SQLite session.
- **Before each statement.** The statement that opens a transaction, `BEGIN` or `BEGIN IMMEDIATE`, is one of them, and so are the statements of a savepoint.
- **At the commit.** A commit is a call of the driver and not a statement, so it keeps its own refusal, which is the refusal of decision 3. The release of a savepoint is refused by the same check.
- **Not at a rollback.** A rollback to a savepoint is let through, and the rollback that ends the transaction is the driver's own call. They are what unwinds the attempt.

What this gives, on the two SQLite hosts alike. A read stops at its next statement, where it ran to its end. A delete of a directory, which releases no savepoint, stops at its next statement, where it sent every one and was stopped by its commit alone. A write that is cancelled before its commit has begun changes nothing. A write that is cancelled at its commit or after has landed whole.

One thing is still sent. A connection that the pool is checking out has its settings stamped by the engine's checkout listener: a probe for the vector function and six `PRAGMA` statements, and on a database in a file a read of the planner statistics. They are sent on the DBAPI connection and do not pass the statement refusal, and a refusal raised in a checkout listener makes SQLAlchemy throw the connection away, which is the defect of this spec. A checkout that has begun therefore sends all its statements, and the attempt is refused at its `BEGIN`.

How it is built. There are two refusals, and each is put in place once.

- **One listener on the storage's engine.** At construction the host puts a `before_cursor_execute` listener on the engine it built. It reads the mark before each statement and lets a statement that begins with `ROLLBACK` through.
- **Two listeners on the class of the storage's sessions.** A SQLite host makes its sessions from `AttemptSession`, a `Session` subclass that it gives to `async_sessionmaker` as `sync_session_class`. The class carries two listeners, registered when `attempts.py` is imported. `after_transaction_create` refuses the first use of a session, before a connection is checked out, and the start of each savepoint. `before_commit` refuses the commit and each savepoint release.
- **Nothing is made for a session, a transaction or a connection.** No factory wraps the sessions, no view of the engine is made, no execution option is carried, and no listener is put on at a `BEGIN`. They were needed while an engine could be an application's, to tell the storage's sessions from the application's. By decision 11 every connection of the engine is the storage's.
- **A task outside any attempt is refused nothing.** The mark is a context variable, and it is `None` outside an attempt. The statistics pass runs in a task of the host that is started outside any attempt, so the listeners read no mark there. Another engine in the same process, and a plain `Session`, carry neither listener, and are refused nothing even inside a marked attempt.

Executed on 2026-11-21 as a spike, on SQLAlchemy 2.0.52 with aiosqlite, first before the build of this decision and again before the build of decision 11. Each candidate was asked which statements it sees.

| Candidate | Sees | Does not see |
|---|---|---|
| `do_orm_execute` on the session | a statement passed to `session.execute` | a statement sent through `session.connection()`, which is how first touch, the statistics step and the savepoints send theirs; the `BEGIN`; a flush |
| `after_transaction_create` on the session class | the first use of a session, before any connection is checked out, and each `begin_nested` | a statement |
| `before_commit` on the session class | `session.commit()` and each savepoint release of a session | a commit made on the connection; no code of VFS makes one |
| `before_cursor_execute` on the session's connection, put there at the session's `after_begin` | every statement through the connection: Core, driver SQL, a flush, `SAVEPOINT`, `RELEASE` and `ROLLBACK TO` | the `BEGIN`, which is sent before `after_begin` fires; the settings a checkout stamps, which use the DBAPI connection directly |
| `before_cursor_execute` on the engine | all of the above on every connection of the engine, with `BEGIN` and `BEGIN IMMEDIATE`, and the statements of a session that sends no `BEGIN` | the settings a checkout stamps, and the statement the dialect sends as it makes a connection |
| `commit` on the session's connection | both kinds of commit | nothing, but it cannot be used: see below |

The listener on the engine is the one built. At the `BEGIN` the connection reports that it is in no transaction, so the listener makes no test of that. A refusal at each place was run to its end: at the first use of a session no connection was checked out and the session was left clean, and after a refusal at a statement, at the `BEGIN`, at a savepoint release, at the commit, and in a session that sends no `BEGIN`, the transaction was rolled back and the connection went back to its pool with no invalidation.

Two refusals were found unsafe and are not built.

- A refusal raised in the connection's `commit` event leaves the transaction open. SQLAlchemy marks the transaction inactive, sends no rollback, and returns the connection to the pool without a reset. The row of the refused write was then read by the next caller of that connection, whose own commit made it permanent. So the commit is refused at the session's `before_commit`, where a failed commit is followed by a rollback.
- A refusal of `ROLLBACK TO SAVEPOINT` breaks the close of a session that holds a savepoint. The close raises half way, the transaction is not rolled back and the connection never returns to its pool. That was seen in the build's own tests, at a write cut at its first change. So a rollback is let through.

Executed on 2026-11-21, on the build before this decision and on the build as it stands. Each call was cancelled inside the first statement of its transaction. The figure is the number of statements sent after it. A rollback is not counted.

| Call | In memory | In a file |
|---|---|---|
| `stat`, `read` | 0, then 0 | 0, then 0 |
| `grep` | 3, then 0 | 3, then 0 |
| `write` of two files | 4, then 0 | 4, then 0 |
| `edit` | 2, then 0 | 2, then 0 |
| `delete` of a directory | 8, then 0 | 7, then 0 |
| `move` | 10, then 0 | 10, then 0 |
| `grant`, `revoke` | not run, then 0 | not run, then 0 |

A `stat` and a `read` send one statement in their transaction, so the cut at the first is the cut at the last. A read that sends several is the `grep`. After each of the eighteen cuts on the build as it stands, the storage held what it held before, no connection was thrown away, and the next write worked.

What it costs a call that nobody cancels, counted on 2026-11-21 on the build as it stands. No object is made and no listener is registered for a session, a transaction or a connection. Each statement calls the one listener of the engine, which reads one context variable. Each transaction of a session, its savepoints among them, calls the first-use listener, and each commit and savepoint release calls the commit listener; each reads the same variable. A `stat` calls the statement listener twice and the first-use listener once. The first `write` of a file calls the statement listener 16 times in memory and 15 in a file, the first-use listener 3 times and the commit listener twice. No statement is added and no lock is taken: a `stat` is 34 driver round trips in memory and 38 in a file, and a `write` is 81 on both, as before.

Reason: a caller that has given up should not go on loading the database, and a write it has given up on should not land later. Before this decision a marked read ran every statement it had left, and a marked write ran every statement up to its next savepoint release or its commit.

### 11. A storage always builds and owns its engine, and takes engine arguments

Decided on 2026-11-21, after the second code review of the build. `DatabaseStorage` takes `url=` and builds its engine at construction. It owns that engine, and `close()` disposes it. `session_factory=` is removed from `DatabaseStorage` and from `EngineHost`. The project is before its first release, so nothing stands in for the removed form.

What takes its place is three things.

- **`engine_arguments=`.** A mapping that is passed to `create_async_engine` beside the URL: a pool class and its size, `max_overflow`, `pool_timeout`, `pool_pre_ping`, `pool_recycle`, `connect_args`, `async_creator`, and whatever else SQLAlchemy takes. An argument VFS has no stake in passes through as it was given.
- **What VFS requires always holds.** On SQL Server the engine is made with `use_setinputsizes=False`, without which text outside Latin-1 is stored as `?`. On SQLite `connect_args["factory"]` is `ClosingConnection`, which closes the cursor of a failed statement. The application's `connect_args` are merged with it key by key, and the application's mapping is not changed. Where the application gives another value for one of these keys, the constructor raises a `ValueError` that names the key, as `engine_arguments['connect_args']['factory']`, and says why VFS sets it. The same value is accepted. No other dialect requires an argument.
- **The `engine` property.** `storage.engine` is the storage's `AsyncEngine`. It is there from construction, before first touch, so an application can put a `do_connect` hook on it for a token that expires, or a tracing listener. Its docstring says that the storage disposes it.

`schema=` is not changed. `InMemoryStorage` takes no engine arguments: its engine is one connection to a database in memory, and nothing about it is the application's to size. A test that needs a schema on SQLite attaches a database in a `connect` listener on `storage.engine`.

Reasons, from `agents/2026-11-21-a-storage-always-owns-its-sessions/research.md`.

- **A handed storage shared a pool and never a transaction.** Every verb opens a session of its own for each attempt. A write made through a handed storage stayed after the application rolled its own transaction back, and a write made while the application's session held SQLite's write lock failed after 20 seconds. Sections 1.1 and 1.2 of the memo. So the removal takes away nothing that was promised.
- **On SQLite the handed form changed the application's engine.** After first touch the application's own sessions saw `LIKE` become case-sensitive, the file's journal become a write-ahead log, an explicit `BEGIN`, and sqlite-vec loaded into their connections. Section 1.3.
- **The handed form cost fifteen sites of code, 61 collected tests and nine written caveats**, two of them failures on a server engine that are silent or late: wrong text on SQL Server, and a crash at the first bulk insert on Postgres with a driver the profile does not expect. Sections 1.8 and 1.9.
- **No peer takes a session factory, and every peer that owns its connections to a server takes engine or pool arguments beside the URL.** A URL alone cannot size a pool or turn it off, cannot run asyncpg behind a pooler in transaction mode, and cannot supply a token that expires. Sections 3, 4.2 and 4.3, and findings 2 and 3.
- **An engine form can be added after a release, and a handed form cannot be removed after one.** Finding 7.

The second code review of the build found three defects, and each exists only for a handed storage. A factory that returns the same session for every call, as a request-scoped `async_scoped_session` does, had its session bound again on every call, and call 954 raised `RecursionError` out of the verb. With `async_scoped_session(scopefunc=asyncio.current_task)` each attempt was a new task, so the application's registry gained a session for each attempt that it could not remove, 1,100 after 1,000 `stat` calls. And on a handed in-memory storage, whose one connection took no turns, a rebuild cancelled in its gram phase left that phase's rows committed and every later rebuild refused. A fourth case, a factory bound to a `Connection`, was refused its first write before this work and after it. None of the four can be built any more.

What went with the handed form, in `src/vfs/storage/backends/database/`.

- In `engine.py`: the test that exactly one of `url=` and `session_factory=` is given, the engine that could be `None` and the property that refused to return it, the dialect policy that waited for the bind of a first session, the marker that kept two hosts from putting SQLite's listeners on one engine twice, and the conditions that asked whether the engine was one VFS built before replacing a stale connection, taking turns on one connection, or disposing at `close()`.
- In `attempts.py`: the factory that wrapped every session, the view of the engine made for each engine, the execution option that told the storage's connections from the application's, and the listener put on each connection at its `BEGIN`.
- In `drivers.py`, `dialects.py`, `oneconnection.py`, `backend.py` and `memory.py`: each sentence about a handed, borrowed or injected factory.

`src/` is 43,927 lines where it was 43,993, with the engine arguments and the property added. `engine.py` is 1,042 lines where it was 1,095, `attempts.py` 177 where it was 209, and `backend.py` 1,505 where it was 1,506.

Two things the memo asks for are not built here, and "Left as it is" names them: one engine for several storages on one database, and the settings of a SQLite connection sent once when it is made.

## Left as it is

- **First touch.** Corrected on 2026-11-21. First touch runs through `with_retry` and is run out of reach from its first run on every SQLite storage, by decision 9. A marked first touch is refused its next statement, is rolled back whole, tables and all, and runs again on the next call.
- **The rebuild's lease.** The fix also covers the rebuild on a SQLite storage, whose lease heartbeat is cancelled inside a statement today. This is read from the code and was not run.
- **How soon a cancelled caller is back.** Corrected on 2026-11-21. It waits for its attempt to end, which by decision 10 is when the statement in flight has ended and the transaction is rolled back. An attempt that waits on a worker thread, as a `grep` does, ends when the thread has.
- **A wait for a connection, or for a turn.** A mark does not end a wait. An attempt that is waiting for a connection from its pool, or for its turn on a database that lives in one connection, is refused when it gets one, and its caller is back then and not before. Executed by the second review on a storage in a file with the default pool of fifteen connections: with fifteen reads held in flight, a sixteenth call that was cancelled was not back half a second later, and was raised its own cancellation only after the reads ahead were let go. The test `TestACallerCancelledWhileItsAttemptWaitsForAConnection` holds the same on a pool of one connection, by counting: the checkout then sends its settings, and no `BEGIN` follows. On a pool the wait is the pool's timeout at the latest, 30 seconds by default, and an application that wants it shorter sets `pool_timeout` in `engine_arguments`. Ending the wait at the mark would mean cancelling a checkout, and a cancelled checkout is the defect of this spec. The docstrings of `DatabaseStorage`, `InMemoryStorage`, `with_retry` and `attempts.py` say so.
- **Interrupting a statement.** Not built. It lost the database when it landed outside the transaction's own statements.
- **Loop shutdown.** When the event loop shuts down, every task is cancelled, the attempt's own included, and an in-memory database goes with its loop, as today.
- **`close()`.** It does not wait for an attempt. Closing the connection queues behind the statement in flight on the worker thread, and the kernel's `close_timeout` bounds that, as today.
- **The analysis pass.** It keeps its own shield and its interrupt. An earlier draft of this line said it never runs on an in-memory database, and that was wrong: the build, on 2026-11-20, saw its `BEGIN IMMEDIATE /* vfs_statistics */` and its `ANALYZE` statements on an `InMemoryStorage` after the first write. What `engine.py` stops for an in-memory database is the replacement of a stale connection, in `_replace_stale`, and not the pass. The pass is a task of the host, started outside any attempt, so it carries no mark, no caller's cancellation reaches it, and the refusals of decision 10 read no mark in it. Its interrupt at `close()` was not run against this fix.
- **Whether the database is in memory is still read at first touch.** A mount's schema may be a database attached to the connection, so the URL and the pool do not say where the mount's tables are held, and SQLite's own list of databases does. It decides only whether a stale connection is replaced.
- **The settings of a SQLite connection are still stamped at each checkout.** Seven of the statements of a `stat` are the checkout's. On an engine that only the storage uses they could be sent once, when a connection is made. That is a change of its own and is not made here.
- **One engine for each storage.** Many storages on one database are as many pools. The memo's condition that several storages can share one engine that VFS made is not built here.
- **An in-memory URL with a pool class of the application's choosing.** `engine_arguments` passes `poolclass` through. A pool that opens a second connection to an in-memory database opens a second, empty database. It is not refused.

## Cost

An attempt on a SQLite storage gains one task and one context variable. No statement is added and no lock is taken: a `stat` is 34 driver round trips in memory and a `write` is 81, as before.

The refusals are three listeners, each registered once: one on the engine of each SQLite storage and two on the class of its sessions. None is on a session class or an engine that another dialect uses, so a call on a server engine runs none of them. On SQLite each statement, each transaction of a session and each commit or savepoint release reads one context variable and returns. A `stat` makes three such reads and the first `write` of a file about twenty. At the reference deployment that would be a few million reads of a variable a day, if the deployment ran on SQLite, which it does not.

A cancelled call on a SQLite storage waits for its attempt, where before it waited for its statement or not at all. By decision 10 that is the statement in flight and a rollback. An attempt that is waiting for a connection or for its turn is the exception, and "Left as it is" gives its bound.

A storage builds one engine, at construction, with no IO. A storage that is never used holds an engine with an empty pool.

## Tests

In `tests/storage/test_cancelled_call.py`, written and seen failing before the code. No test reads a clock. A hook on aiosqlite's queue holds one chosen driver round trip on the worker thread until the test releases it, and tells the test when it is reached. The test cancels the call while the round trip is held, and then releases it. Each test of a whole storage runs on the two SQLite hosts, a database in memory behind one connection and a database in a file behind a pool, unless it says otherwise.

The sweep traces each call once and cuts at each round trip it traced. It holds no count of its own, so it does not go stale when a call gains a statement. It is marked `slow`. In memory it cuts at every round trip of a `stat`, a `read` and a `write`. In a file it cuts at the first round trip of each kind. The slow tier of the file costs about 6 seconds of processor time.

- A call cancelled inside the first statement of its transaction sends no other statement but its rollbacks. The calls are `stat`, `read`, `grep`, a `write` of two files, `edit`, `delete` of a directory, `move`, `grant` and `revoke`. The two rights verbs cost about 1.5 seconds of processor time for their four cases.
- A call cancelled while its connection is checked out sends what is left of the checkout and begins no transaction.
- After each cut of the sweep, every earlier row is readable, the pool recorded no invalidation and opened no new connection, a `write` and a `read` of another file succeed, and nothing was sent after the statement in flight but rollbacks.
- A `write` cancelled before its commit has changed nothing: the file holds its old content and no new version. It is cut at its first change, after a savepoint is released, and at the last statement before the commit.
- A `write` cancelled at its commit or after has landed whole.
- A `write` cancelled while it waits behind another call sends no statement and does not land, and the call ahead ends as it would have.
- The first touch of a fresh storage, cancelled at the first round trip of each kind and at each round trip that makes its connection, leaves the storage whole and runs again on the next call.
- On a database in a file, a write cancelled inside one of its reads leaves the next write working.
- An `install_extensions` cancelled inside its probe costs no connection and no row.
- A caller cancelled twice while its attempt runs is still waiting after the second, and raises one `CancelledError` when the attempt has ended. It is the cancellation the caller was cancelled with.
- What a dropped attempt raised is never reported by the loop as never retrieved.
- A kernel lists every file after `asyncio.wait_for` around one of its calls ran out, and a read that is cancelled and not awaited leaves the next write working.
- With a pool of one connection held by a call ahead, a cancelled caller is still waiting, is raised its own cancellation once the connection is let go, and its attempt sends the checkout's settings and no `BEGIN`.

In `tests/storage/database/test_attempts.py`, on an engine and sessions made as a host makes them: a marked attempt is refused at its next statement, at its commit, at the first use of a session with no connection checked out, and inside a savepoint, where its rollback to the savepoint is let through; a task it started carries its mark; a caller whose attempt was cancelled too is raised its own cancellation; another engine and its sessions are refused nothing inside a marked attempt; and a session and its connection are given no listener of their own.

In `tests/storage/database/test_oneconnection.py`: a session whose entry fails gives the lock back, and so does one whose exit fails; the lock is held until the wrapped session has been left; and an attempt marked while it waits for its turn checks no connection out.

In `tests/storage/database/test_engine.py` and `test_drivers.py`: a storage's engine is there before first touch and is disposed at `close()`; engine arguments reach the engine beside what VFS requires; another value for a required argument is refused at construction by name; `connect_args` are merged key by key; on SQLite an attempt runs in a task of its own on sessions that refuse, and off SQLite in its caller's task on plain sessions.

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
- **First touch under a cancellation.** Corrected on 2026-11-21: it is now run. The first touch of a storage is cancelled at the first round trip of each kind it sends, and at each round trip that makes its connection, on each of the two SQLite hosts.
- **The sync kernel.** `VirtualFileSystem` runs its own loop. Its path to a cancellation was not read.
- **A borrowed in-memory database.** Corrected on 2026-11-21: there is none. By decision 11 a storage builds its engine, and an in-memory storage takes turns on its one connection.
- **The `memdb` form of the kept-alive database beyond its first failure**, and why the collector is needed to end a refusal. The cause in decision 6 is reasoned from the result of `gc.collect()` and was not traced in SQLite.
- **A unit whose write uses no savepoint and a long plan.** The patch was run on a single-file write.
- **The line counts.** The 63 lines were counted at `a64dd18c`. Corrected on 2026-11-21: the move was made, and `engine.py` ends at 1,042 lines and `backend.py` at 1,505.
- **Engine arguments on a server engine.** That `use_setinputsizes=False` is kept and another value refused is run on the merge alone, with a SQL Server URL and no server. A pool class, `async_creator` and a `do_connect` hook on `storage.engine` were not run against Postgres, a pooler or a token service.
- **A pool class other than the default on SQLite.** `NullPool` on a file and a `poolclass` on an in-memory URL were not run.

## Choices to confirm

1. **Marked shield, or the kept-alive connection?** Recommended: the marked shield. Alternative: the kept-alive connection. Its cost: after some cancelled calls the storage refuses every call until Python's collector runs, as executed in 6 of 81 cuts of a write.

## One line

A storage builds and owns its engine, and on SQLite each attempt of a call runs in a task the caller's cancellation cannot enter, is marked when its caller is cancelled, is refused its next statement, its next session and its commit once marked, and only then raises the caller's own cancellation, so no connection is thrown away and a cancelled write changes nothing unless its commit had begun.
