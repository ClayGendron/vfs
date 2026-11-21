# Cancellation

This page says what VFS does when the caller of a call is cancelled, how that is built in the code, and why. It is for people who change VFS.

## The rule

- **A cancelled call leaves its [storage](../reference/glossary.md#storage) whole.** Every row is there afterwards, and the next call works at once.
- **A cancelled write has changed nothing or has landed whole.** A write that is cancelled before its commit has begun changes nothing. A write that is cancelled at its commit or after has landed. The caller cannot know which, and that is so on every database engine.
- **The caller is raised the cancellation it was cancelled with.** It is the same exception object, and not a new one.
- **On SQLite, a cancelled call ends the statement in flight and sends no other.** Its transaction is then rolled back, and only then is the caller's cancellation raised.

## The words

- **An attempt is one try of one call's transaction.** `EngineHost.with_retry` runs a call as one attempt, and as another when the database asks for a retry.
- **An attempt is marked when its caller is cancelled.** The mark is the one fact the attempt is told. It is not interrupted.
- **An attempt runs out of reach** when it runs in a task of its own, which a cancellation of the caller does not enter.
- **A storage built its engine or was handed its sessions.** `DatabaseStorage(url=...)` builds an engine and owns it. `DatabaseStorage(session_factory=...)` is handed the application's session factory. Either way the storage opens and closes each session itself. What a handed storage does not own is the engine, the pool and the factory.

## Why SQLite needs it

A call spends its database time waiting for the driver's worker thread. A cancellation lands on that wait, and SQLAlchemy then throws the connection away.

- **In memory, the connection is the database.** After one cancelled `stat`, the next read failed with `no such table` and the next write started an empty database.
- **In a file, a connection thrown away with a cursor open keeps its write lock** until Python's collector frees the cursor. The next write was refused until then, in 3 of 81 cuts.
- **A database server has neither problem,** because its database does not live inside a connection. Nothing on this page changes what VFS does on Postgres, SQL Server, Oracle or MariaDB, where an attempt runs in its caller's task as it always did.

## How an attempt runs out of reach

`run_out_of_reach`, in `storage/backends/database/attempts.py`, is the whole of it.

- **It starts the attempt in a task and waits for the task.** Each cancellation that arrives during the wait is caught, the attempt is marked, and the wait goes on. A second cancellation does not cut the wait short.
- **When the attempt has ended, it raises the first cancellation it caught.** anyio knows its own cancellation by the message on the exception. An earlier build raised a new and empty `CancelledError`, and `anyio.move_on_after` and `anyio.fail_after` then let the error escape their blocks. Starlette, FastAPI, httpx and the MCP SDK are built on anyio.
- **It reads what the dropped attempt raised.** A refused attempt ends with an exception nobody wants. If it is never read, the event loop reports it as never retrieved.
- **The mark travels in a context variable,** set inside the attempt's own task. A task copies the context it is started in. So a task that is started inside an attempt and is to outlive it would carry the mark, and must be started outside the attempt or clear the mark first. VFS starts none: the statistics pass is started after `with_retry` returns.
- **Every SQLite storage runs each attempt out of reach,** built or handed, in memory or in a file. `with_retry` and `install_extensions` do it when the dialect is SQLite. The dialect is read in `EngineHost._policy()` with no I/O, before the first attempt, so first touch is covered too.
- **The wait between two attempts is in the caller's task.** A cancellation there is raised at once and touches no connection.

## Where a marked attempt is refused

A marked attempt is refused with `InvalidRequestError` at three places, and let through at a fourth.

| Place | What happens | Built as |
|---|---|---|
| The entry of a session | Refused before a connection is checked out. An attempt that was marked while it waited for its turn on a one-connection database sends nothing. | `AttemptSession.__aenter__` |
| Each statement, the `BEGIN` among them | Refused before it reaches the database. | A `before_cursor_execute` listener on the session's own connection |
| The commit | Refused. A commit is a call of the driver and not a statement, so it has its own refusal. | A `before_commit` listener on the session |
| A rollback | Let through, to a savepoint or of the whole transaction. The rollbacks are what unwind the attempt and leave the connection clean. | The statement listener passes a statement that begins `ROLLBACK` |

How the listeners get there:

- **The host wraps the session factory it built or was handed,** once, when its dialect is known to be SQLite. Each session it takes is an `AttemptSession`.
- **Entering an `AttemptSession` binds the session to a view of its engine.** The view is made by `Engine.execution_options`. It shares the engine's pool and carries the option `vfs_attempt`. One view is made for each engine and kept.
- **The listener VFS already has on the `begin` event of a SQLite engine calls `attempt_begins` first.** For a connection that carries the option, inside an attempt, `attempt_begins` puts the statement listener on that connection. The connection ends with its transaction, and the listener with it.

**Nothing is put on what outlives a session.** The engine, its pool, a DBAPI connection, the session class and the application's factory are given no listener. A session the application makes on the same engine carries no option, and is refused nothing, even inside a marked attempt. A test counts the listeners on a handed engine after a cancelled call.

## What is still sent after a mark

- **The settings of a checkout that has begun.** The pool's checkout listener sends a probe for the vector function and six `PRAGMA` statements, and on a file engine VFS built, a read of the planner statistics. A refusal raised in that listener makes SQLAlchemy throw the connection away, which is the defect this page is about. The attempt is refused at its `BEGIN`.
- **Every rollback,** as the table says.
- **The batch a `grep` is checking on a worker thread.** A cancelled `grep` is back when the thread has ended.

## What was tried and is not built

Each of these was built as a spike or in an earlier build, and run.

- **A second connection that keeps an in-memory database alive.** It never lost a row. After some cuts it left the storage refusing every call until the collector ran.
- **Running out of reach with no mark.** A cancelled write then always landed, which no other engine does.
- **The refusal on a session class the host's own factory makes.** It was the first build. A handed storage has no factory of its own, so a cancelled write there always landed.
- **A `do_orm_execute` listener on the session.** It sees only a statement passed to `session.execute`. First touch, the statistics step and the savepoints send theirs through `session.connection()`.
- **A refusal in the connection's `commit` event.** SQLAlchemy marks the transaction inactive, sends no rollback, and returns the connection to the pool with no reset. The refused row was then made permanent by the next caller's commit.
- **A refusal of `ROLLBACK TO SAVEPOINT`.** The close of the session raised half way, the transaction was not rolled back, and the connection never returned to its pool.
- **A refusal in the pool's checkout listener.** It costs the connection, and the listener cannot tell a session VFS took from one the application made.

## What it costs

- **A call nobody cancels pays one wrapper object and one listener for its session, and one listener for its connection.** Each statement calls that listener, which reads one attribute. No statement is added and no lock is taken.
- **A cancelled caller waits for the statement in flight.** It did before as well, on a file. In memory it waited for nothing, and lost the database.
- **A cancel scope of anyio cancels its task again on every turn of the event loop** until the task leaves the scope. The wait takes each one and goes on, so the loop keeps turning for as long as the statement in flight runs.

## How it is tested

- **Every driver round trip can be held.** The helpers in `tests/support/cancelled_callers.py` name each round trip of a call and hold the call inside one, so a cancellation lands at a place the test chose. No test reads a clock.
- **A sweep cuts a call at each round trip.** After each cut it asserts that the storage is whole, that a write changed nothing or landed whole, that the next write works, that no connection was opened or thrown away, and that no statement was sent after the one in flight.
- **The four SQLite hosts are run:** built and handed, in memory and in a file. Every round trip is cut on the built in-memory host, and the first round trip of each kind on the other three.
- **The tests are in** `tests/storage/test_cancelled_call.py`, and beside the code in `tests/storage/database/test_attempts.py` and `test_oneconnection.py`. The mutants each test was seen to kill are rows of the mutant ledger.

## Not covered

- **Cancellation has not been run on a database server.** What a cancelled write has done there is read in the drivers' source.
- **A session that is bound to a `Connection` and not to an `Engine`** runs out of reach and is refused at its entry and its commit, and not at each statement.
- **A handed session factory over an in-memory database has no turns.** A statistics pass that is still running can collide with the next call on the one connection.
- **A handed engine on Python 3.11 keeps the open cursor of a failed statement** until the collector runs. VFS opens its own SQLite connections as `ClosingConnection`, which closes such a cursor at the failure. The builder of a handed engine can pass `connect_args={"factory": ClosingConnection}`.
