# A storage owns its engine well

A draft, written on 2026-11-21 from what pull request 27 left about the engine a storage builds. It is not reviewed, and nothing is built.

## The outcome wanted

A storage builds its engine once, sends its session settings once per connection, refuses every engine argument it cannot honour with a `ValueError` that names it, and several storages on one database can share one pool.

## Builds on

Pull request 27, which removed `DatabaseStorage(session_factory=...)` and added `engine_arguments=`, and `agents/2026-11-21-a-storage-always-owns-its-sessions/research.md`.

## The problem

Each was shown by a script that ran, unless it says "read".

### Cost per call

- **A SQLite storage stamps its session settings at every checkout.** A probe for the vector function and six `PRAGMA` statements are sent each time a connection leaves the pool, which is 7 of the 9 statements of a `stat` on an in-memory storage. At the reference deployment's 150,000 verb calls a day, that is about a million statements a day that change nothing.
- **Several storages on one database each build an engine and a pool.** One mount for each schema of one database is a supported shape, and each such mount holds its own pool. The research names an engine that VFS builds once and several storages share as the later step.

### Arguments that are not refused

- **A wrong engine argument found at first touch is answered `unavailable` and `retryable`.** A synchronous `creator` and `connect_args={"autocommit": True}` were run. A caller that retries on `retryable` never stops. The classifier's default for a failure it does not know is the same before pull request 27, and `engine_arguments` makes it reachable.
- **One `pool=` given to two storages is not refused.** The two would share connections, and each would put its checkout listener on the pool. Read.
- **An in-memory SQLite database named with `file::memory:` is served by a pool of several connections.** SQLAlchemy classes `sqlite+aiosqlite:///file::memory:?cache=shared&uri=true` as a file, so the storage gets a queue pool and takes no turns. Eight writes at once all failed with `database table is locked`, and a `NullPool` or a `pool_recycle` there loses the database, where the other in-memory spellings refuse both.
- **A creator on SQLite gives up the closing of a failed statement's cursor.** SQLAlchemy ignores `connect_args` when `engine_arguments` holds `creator` or `async_creator`, so the connections are not `ClosingConnection`. On Python 3.11 that is the open cursor `drivers.py` describes. The docstring says so, and it is not refused. Not run on Python 3.11.
- **A connection that an application opens on `storage.engine` beside a call costs an in-memory storage its database.** The checkout stamps its settings on the one connection inside the call's transaction, the stamp fails, and SQLAlchemy throws the connection away. The docstring says no connection is to be opened on the engine, and nothing prevents it.

### Names and pins

- **The engine host's attribute `session_factory` keeps the name of the removed constructor argument, and `EngineHost.engine` can be assigned to.** About 270 uses in the tests read the first. `DatabaseStorage.engine` is a read-only property, and the host's is a plain attribute.
- **No test pins `expire_on_commit=False` on a storage's sessions.** A build without it passed the six test files of the cancellation branch.

### Not run

- **`engine_arguments` is not run on a server engine.** A pool class, `async_creator` and a `do_connect` hook behind a connection pooler are the uses the constructor is for. Only the merge of the arguments is tested.

## Decisions

1. **Settings that last for a connection's life are sent once, at `connect`,** and only what a checkout must reset is sent at checkout.
2. **A failure at first touch that comes from an engine argument is classed `invalid`, not retryable.**
3. **The SQLite in-memory test covers every spelling SQLAlchemy accepts,** `file::memory:` with `uri=true` among them, before the pool is chosen.
4. **A `creator` or `async_creator` on SQLite is refused unless the caller also opts out of the closing connection by name.**
5. **A pool given to a second storage is refused,** by a mark the first storage leaves on it.
6. **The host's attribute is renamed `sessions`, and `EngineHost.engine` becomes read-only.**
7. **A test pins `expire_on_commit=False`.**
8. **A shared engine is its own later spec.** It needs the research's next step, and it changes how a storage is built.

## Tests

Each defect gets its reproducing test first. A counted test pins decision 1: a second `stat` on an in-memory storage sends no `PRAGMA`. The engine leg runs `engine_arguments` with a pool class and a `do_connect` hook on Postgres.

## Scope

In: `engine.py`, `drivers.py`, `oneconnection.py`, the classifier's default, and the engine host. Out: a shared engine, by decision 8.

## Not checked

- Which of the six `PRAGMA`s must be reset at checkout.
- Whether the rename in decision 6 touches anything outside `tests/`.

## Choices to confirm

1. **Decision 4: refuse a creator on SQLite, or keep the docstring's warning?** Recommended: refuse.
2. **Decision 8: is the shared engine wanted for the first release?** Recommended: no. Its cost: one pool for each mount of one database.

## One line

A storage sends its settings once per connection, refuses every engine argument it cannot honour, and names its own parts as what they are.
