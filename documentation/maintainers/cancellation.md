# Cancellation

This page says what VFS does when the caller of a call is cancelled, how that is built in the code, and why. It is for people who change VFS.

## The rule

A cancelled call leaves its [storage](../reference/glossary.md#storage) whole. Every row is there afterwards, and the next call works at once.

A cancelled write has changed nothing or has landed whole. A write that is cancelled before its commit has begun changes nothing, and one that is cancelled at its commit or after has landed. The caller cannot know which of the two happened, and that is so on every database engine.

The caller is raised the cancellation it was cancelled with. It is the same exception object, and not a new one.

On SQLite there is one rule more. A cancelled call ends the statement in flight and sends no other. Its transaction is then rolled back, and only then is the caller's cancellation raised.

## The words

An attempt is one try of one call's transaction. `EngineHost.with_retry` runs a call as one attempt, and as another when the database asks for a retry.

An attempt is marked when its caller is cancelled. The mark is the one thing the attempt is told, and the attempt is not interrupted. An attempt runs out of reach when it runs in a task of its own, which a cancellation of the caller does not enter.

A storage either built its engine or was handed its sessions. `DatabaseStorage(url=...)` builds an engine and owns it. `DatabaseStorage(session_factory=...)` is handed the application's session factory. Either way the storage opens and closes each session itself. What a handed storage does not own is the engine, the pool and the factory, and that difference decides where the code on this page may put a listener.

## Why SQLite needs it

A call spends its database time waiting for the driver's worker thread. A cancellation lands on that wait, and SQLAlchemy then throws the connection away. On SQLite that costs more than a connection.

In memory, the connection is the database. After one cancelled `stat`, the next read failed with `no such table`, and the next write started an empty database.

In a file, a connection that is thrown away with a cursor still open keeps its write lock until Python's collector frees the cursor. The next write was refused until then, in 3 of 81 cuts.

A database server has neither problem, because its database does not live inside a connection. Nothing on this page changes what VFS does on Postgres, SQL Server, Oracle or MariaDB. An attempt there runs in its caller's task, as it always did.

## How an attempt runs out of reach

`run_out_of_reach`, in `storage/backends/database/attempts.py`, is the whole of it. It starts the attempt in a task and waits for the task. Each cancellation that arrives during the wait is caught, the attempt is marked, and the wait goes on. A second cancellation does not cut the wait short.

When the attempt has ended, the function raises the first cancellation it caught, and not a new one. The reason is anyio, which knows its own cancellation by the message on the exception. An earlier build raised a new and empty `CancelledError`, and `anyio.move_on_after` and `anyio.fail_after` then let the error escape their blocks. Starlette, FastAPI, httpx and the MCP SDK are built on anyio, so a server that cancels a request when its client goes away would have been broken by it.

Before it raises, the function reads what the dropped attempt raised. A refused attempt ends with an exception that nobody wants, and an exception that is never read is reported by the event loop as never retrieved.

The mark travels in a context variable, which is set inside the attempt's own task. A task copies the context it is started in. A task that is started inside an attempt and is to outlive it would therefore carry the attempt's mark, so it must be started outside the attempt or clear the mark first. VFS starts no such task today: the statistics pass is started after `with_retry` returns.

Every SQLite storage runs each attempt out of reach, whether it built its engine or was handed its sessions, and whether its database is in memory or in a file. `with_retry` and `install_extensions` do it when the dialect is SQLite. The dialect is read in `EngineHost._policy()` with no I/O, before the first attempt, so first touch is covered as well. The wait between two attempts stays in the caller's task, and a cancellation there is raised at once and touches no connection.

## Where a marked attempt is refused

A marked attempt is refused with `InvalidRequestError` at three places, and it is let through at a fourth.

| Place | What happens | Built as |
|---|---|---|
| The entry of a session | Refused before a connection is checked out | `AttemptSession.__aenter__` |
| Each statement, the `BEGIN` among them | Refused before it reaches the database | A `before_cursor_execute` listener on the session's own connection |
| The commit | Refused | A `before_commit` listener on the session |
| A rollback | Let through, to a savepoint or of the whole transaction | The statement listener passes a statement that begins `ROLLBACK` |

The refusal at the entry is what keeps a promise about a database that lives in one connection, where calls take turns. An attempt that was marked while it waited for its turn sends nothing and gives its turn up.

The commit has a refusal of its own because a commit is a call of the driver and not a statement, so the statement listener never sees it. The rollbacks are let through because they are what unwind a refused attempt and leave its connection clean.

The listeners get there in three steps. The host wraps the session factory it built or was handed, once, when its dialect is known to be SQLite, so that each session it takes is an `AttemptSession`. Entering an `AttemptSession` binds the session to a view of its engine. The view is made by `Engine.execution_options`, shares the engine's pool and carries the option `vfs_attempt`, and one view is made for each engine and kept. Last, the listener that VFS already has on the `begin` event of a SQLite engine calls `attempt_begins` before it sends the `BEGIN`. For a connection that carries the option, inside an attempt, `attempt_begins` puts the statement listener on that connection. The connection ends with its transaction, and the listener ends with it.

Nothing is put on what outlives a session. The engine, its pool, a DBAPI connection, the session class and the application's factory are given no listener. A session that the application makes for itself on the same engine carries no option, so it is refused nothing, even inside a marked attempt. A test counts the listeners on a handed engine after a cancelled call.

## What is still sent after a mark

Three things are still sent once an attempt is marked.

The first is the settings of a checkout that has begun. The pool's checkout listener sends a probe for the vector function and six `PRAGMA` statements, and on a file engine that VFS built it also reads the planner statistics. A refusal raised in that listener makes SQLAlchemy throw the connection away, which is the defect this page is about. So a checkout that has begun sends all its statements, and the attempt is refused at its `BEGIN`.

The second is every rollback, for the reason given above.

The third is not a statement. A `grep` checks its matches on a worker thread, and a cancelled `grep` is back when that thread has ended the batch it was checking.

## What was tried and is not built

Each of the designs below was built, as a spike or as an earlier build, and run. None is taken, and each for a reason that was seen and not guessed.

- **A second connection that keeps an in-memory database alive.** It never lost a row. After some cuts it left the storage refusing every call until the collector ran.
- **Running out of reach with no mark.** It kept the database, and a cancelled write then always landed. No other engine does that, and a caller who gave up on a write should not find it landed later.
- **The refusal on a session class that the host's own factory makes.** This was the first build. A handed storage has no factory of its own, so a cancelled write there always landed. The refusal now sits on each session the host takes, whoever made it.
- **A `do_orm_execute` listener on the session.** It sees only a statement that is passed to `session.execute`. First touch, the statistics step and the savepoints send theirs through `session.connection()`, and it would have missed them.
- **A refusal in the connection's `commit` event.** SQLAlchemy marks the transaction inactive, sends no rollback, and returns the connection to the pool with no reset. The row of the refused write was then made permanent by the next caller's commit.
- **A refusal of `ROLLBACK TO SAVEPOINT`.** It broke the close of a session that held a savepoint. The close raised half way, the transaction was not rolled back, and the connection never returned to its pool.
- **A refusal in the pool's checkout listener.** It costs the connection. The listener also belongs to the pool, so it cannot tell a session VFS took from one the application made.

## What it costs

A call that nobody cancels pays one wrapper object and one listener for its session, and one listener for its connection. Each statement calls that listener, which reads one attribute. No statement is added and no lock is taken.

A cancelled caller waits for the statement in flight. On a file it did so before as well. In memory it waited for nothing, and lost the database.

One cost falls on the event loop. A cancel scope of anyio cancels its task again on every turn of the loop until the task leaves the scope. The wait takes each cancellation and goes on, so the loop keeps turning for as long as the statement in flight runs.

## How it is tested

Every driver round trip of a call can be held. The helpers in `tests/support/cancelled_callers.py` name each round trip and hold the call inside one, so a cancellation lands at a place the test chose. No test reads a clock.

A sweep cuts a call at each of its round trips. After each cut it asserts that the storage is whole, that a write changed nothing or landed whole, that the next write works, that no connection was opened or thrown away, and that no statement was sent after the one in flight.

The four SQLite hosts are all run: built and handed, in memory and in a file. Every round trip is cut on the built in-memory host, and the first round trip of each kind on the other three, which keeps the sweeps inside the budget of the heavy tests.

The tests are in `tests/storage/test_cancelled_call.py`, and beside the code in `tests/storage/database/test_attempts.py` and `test_oneconnection.py`. The mutants that each test was seen to kill are rows of the mutant ledger.

## Not covered

Four cases are outside what this page promises.

- **A database server.** Cancellation has not been run on one. What a cancelled write has done there is read in the drivers' source, and whether a connection thrown away there can hold a lock is not known.
- **A session that is bound to a `Connection`, and not to an `Engine`.** It runs out of reach and is refused at its entry and at its commit. It is not refused at each statement, because there is no engine to make a view of.
- **A handed session factory over an in-memory database.** It has no turns, so a statistics pass that is still running can collide with the next call on the one connection.
- **A handed engine on Python 3.11.** It keeps the open cursor of a failed statement until the collector runs. VFS opens its own SQLite connections as `ClosingConnection`, which closes such a cursor at the failure, and the builder of a handed engine can pass `connect_args={"factory": ClosingConnection}` to get the same.
