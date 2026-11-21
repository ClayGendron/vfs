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

A storage builds its engine and owns it. `DatabaseStorage(url=..., engine_arguments={...})` passes the URL and the arguments to SQLAlchemy, and nothing but the storage makes a session, a connection or a transaction on the engine that comes back. That ownership is what lets the code on this page put a listener on the engine and on the class of its sessions. An application reaches the engine at `storage.engine`, and it is there for listeners alone: a `do_connect` hook or tracing, put on `storage.engine.sync_engine`. An application opens no connection and no session on it.

## Why SQLite needs it

A call spends its database time waiting for the driver's worker thread. A cancellation lands on that wait, and SQLAlchemy then throws the connection away. On SQLite that costs more than a connection.

In memory, the connection is the database. After one cancelled `stat`, the next read failed with `no such table`, and the next write started an empty database.

In a file, a connection that is thrown away with a cursor still open keeps its write lock until Python's collector frees the cursor. The next write was refused until then, in 3 of 81 cuts.

A database server has neither problem, because its database does not live inside a connection. Nothing on this page changes what VFS does on Postgres, SQL Server, Oracle or MariaDB. An attempt there runs in its caller's task, as it always did, and no listener of this page is put in place.

## How an attempt runs out of reach

`run_out_of_reach`, in `storage/backends/database/attempts.py`, is the whole of it. It starts the attempt in a task and waits for the task. Each cancellation that arrives during the wait is caught, the attempt is marked, and the wait goes on. A second cancellation does not cut the wait short.

When the attempt has ended, the function raises the first cancellation it caught, and not a new one. The reason is anyio, which knows its own cancellation by the message on the exception. An earlier build raised a new and empty `CancelledError`, and `anyio.move_on_after` and `anyio.fail_after` then let the error escape their blocks. Starlette, FastAPI, httpx and the MCP SDK are built on anyio, so a server that cancels a request when its client goes away would have been broken by it.

A caller can have two cancellers, such as an `asyncio.timeout` inside a cancel scope of anyio. The timeout's cancellation carries no message, so when it comes first the scope does not find its own message on the error that is raised. The function therefore keeps one cancellation for each message it has seen. It raises the first, and each later one is the `__context__` of the one before it, which is where anyio looks next. A scope cancels its task again on every turn of the loop, always with the same message, so the chain holds one error for each canceller and not one for each turn.

Before it raises, the function reads what the dropped attempt raised. A refused attempt ends with an exception that nobody wants, and an exception that is never read is reported by the event loop as never retrieved.

The mark travels in a context variable, which is set inside the attempt's own task. A task copies the context it is started in. A task that is started inside an attempt and is to outlive it would therefore carry the attempt's mark, so it must be started outside the attempt or clear the mark first. VFS starts no such task today: the statistics pass is started after `with_retry` returns.

Which storages do this is declared and not tested for by name. `DialectProfile.attempts_out_of_reach` is true for SQLite alone, and `with_retry` and `install_extensions` read it. The profile is known when the storage is constructed, with no I/O, so the first call of a storage is covered as well. The wait between two attempts stays in the caller's task, and a cancellation there is raised at once and touches no connection.

## Where a marked attempt is refused

A marked attempt is refused with `InvalidRequestError` at three places, and it is let through at a fourth.

| Place | What happens | Built as |
|---|---|---|
| The first use of a session | Refused before a connection is checked out | An `after_transaction_create` listener on the class `AttemptSession` |
| Each statement, the `BEGIN` among them | Refused before it reaches the database | A `before_cursor_execute` listener on the storage's engine |
| The commit | Refused | A `before_commit` listener on the class `AttemptSession` |
| A rollback | Let through, to a savepoint or of the whole transaction | The statement listener passes a statement that begins `ROLLBACK` |

The refusal at the first use is what keeps a promise about a database that lives in one connection, where calls take turns. An attempt that was marked while it waited for its turn sends nothing and gives its turn up.

The commit has a refusal of its own because a commit is a call of the driver and not a statement, so the statement listener never sees it. The rollbacks are let through because they are what unwind a refused attempt and leave its connection clean.

The three listeners are each put in place once. The statement listener is put on the engine when a SQLite storage is constructed. The other two belong to `AttemptSession`, an empty subclass of SQLAlchemy's `Session` that a SQLite storage's session factory is told to make. Nothing is made for a session, a transaction or a connection, and nothing is taken away when one ends.

Each listener reads the mark of the task it runs in. Outside an attempt there is no mark, so the statistics pass, which runs in a task of the storage, is refused nothing.

The rule that an application opens no connection on `storage.engine` is not a matter of taste. On an in-memory storage every checkout hands out the one connection. A checkout beside a running call stamps its settings on that connection inside the call's transaction, the stamp fails, and SQLAlchemy throws the connection away, and the database with it. Nothing prevents an application from doing this. The docstring of the property says not to.

## What is still sent after a mark

Three things are still sent once an attempt is marked.

The first is the settings of a checkout that has begun. The pool's checkout listener sends a probe for the vector function and six `PRAGMA` statements, and on a database in a file it also reads the planner statistics. These go straight to the driver's connection, so the statement listener does not see them, and that is wanted. A refusal raised in the checkout listener makes SQLAlchemy throw the connection away, which is the defect this page is about. So a checkout that has begun sends all its statements, and the attempt is refused at its `BEGIN`.

The second is every rollback, for the reason given above.

The third is not a statement. A `grep` checks its matches on a worker thread, and a cancelled `grep` is back when that thread has ended the batch it was checking.

## What was tried and is not built

Each of the designs below was built, as a spike or as an earlier build, and run. None is taken, and each for a reason that was seen and not guessed.

- **A second connection that keeps an in-memory database alive.** It never lost a row. After some cuts it left the storage refusing every call until the collector ran.
- **Running out of reach with no mark.** It kept the database, and a cancelled write then always landed. No other engine does that, and a caller who gave up on a write should not find it landed later.
- **A storage that is handed the application's session factory.** `DatabaseStorage(session_factory=...)` existed until this work. A handed storage owned no engine, so the refusals had to be a wrapper around each session and a listener on each connection, made and dropped for every transaction. A factory that returned the same session twice then recursed without end, and a handed in-memory database took no turns. A storage now always builds its engine, and three listeners that are put in place once do the same work.
- **A `do_orm_execute` listener on the session.** It sees only a statement that is passed to `session.execute`. First touch, the statistics step and the savepoints send theirs through `session.connection()`, and it would have missed them.
- **A refusal in the connection's `commit` event.** SQLAlchemy marks the transaction inactive, sends no rollback, and returns the connection to the pool with no reset. The row of the refused write was then made permanent by the next caller's commit.
- **A refusal of `ROLLBACK TO SAVEPOINT`.** It broke the close of a session that held a savepoint. The close raised half way, the transaction was not rolled back, and the connection never returned to its pool.
- **A refusal in the pool's checkout listener.** It costs the connection, as said above.

## What it costs

A call that nobody cancels pays for calls of the three listeners, and each call reads one context variable. A `stat` calls the statement listener twice and the first-use listener once. The first `write` to a storage calls the statement listener 16 times, the first-use listener 3 times and the commit listener twice. No statement is added, no lock is taken, and no object is made for a session or a connection.

A cancelled caller waits for its attempt to end, and for most calls that is the statement in flight. On a file it waited for that statement before as well. In memory it waited for nothing, and lost the database.

An attempt that has not yet got a connection is the exception. It may be waiting for its turn on a database that lives in one connection, or for a connection from a pool that has none free. Its caller is back when the attempt gets what it waits for and is refused, and not before. On a pool that wait is at most the pool's timeout, which is 30 seconds unless the application sets `pool_timeout` in `engine_arguments`. Before this work, a caller that was cancelled in the pool's queue was back at once. Making that wait end at the cancellation is not built.

One cost falls on the event loop. A cancel scope of anyio cancels its task again on every turn of the loop until the task leaves the scope. The wait takes each cancellation and goes on, so the loop keeps turning for as long as the attempt takes to end. One statement held for a second took 135,379 such cancellations, where a plain asyncio caller sent two.

## How it is tested

Every driver round trip of a call can be held. The helpers in `tests/support/cancelled_callers.py` name each round trip and hold the call inside one, so a cancellation lands at a place the test chose. No test reads a clock.

A sweep cuts a call at each of its round trips. After each cut it asserts that the storage is whole, that a write changed nothing or landed whole, that the next write works, that no connection was opened or thrown away, and that no statement was sent after the one in flight.

Both SQLite hosts are run, a database in memory and a database in a file. Every round trip is cut on the one in memory, and the first round trip of each kind on the one in a file, which keeps the sweeps inside the budget of the heavy tests.

The tests are in `tests/storage/test_cancelled_call.py`, and beside the code in `tests/storage/database/test_attempts.py` and `test_oneconnection.py`. The mutants that each test was seen to kill are rows of the mutant ledger.

## Not covered

A database server is outside what this page promises. Cancellation has not been run on one. What a cancelled write has done there is read in the drivers' source, and whether a connection thrown away there can hold a lock is not known.
