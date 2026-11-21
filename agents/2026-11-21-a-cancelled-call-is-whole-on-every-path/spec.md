# A cancelled call is whole on every path

A draft, written on 2026-11-21 from what the four readings of the cancellation fix left. It is not reviewed, and nothing is built.

## The outcome wanted

A cancelled call returns promptly, raises the cancellation it was cancelled with and no other, loses no second canceller, and leaves every storage, lease and background pass as a call that was never made would. This holds on every engine VFS serves, under asyncio, anyio and the synchronous `VirtualFileSystem`.

## Builds on

`agents/2026-11-18-a-call-that-reaches-several-mounts-bounds-each-mount/spec-a-cancelled-call-leaves-its-storage-intact.md`, built as pull request 27, and its review record beside it. `documentation/maintainers/cancellation.md` says how a cancelled attempt is handled today.

## Terms

- **Attempt.** One try of one call's transaction, run in a task of its own that the caller's cancellation does not enter.
- **Canceller.** Whatever cancels a caller: `task.cancel()`, an asyncio time limit, or an anyio cancel scope.

## The problem

Each was shown by a script that ran in a reading of pull request 27, unless it says "read". "Before the fix" marks a defect older than pull request 27.

### A cancelled caller waits

- **A caller cancelled while its attempt waits for a connection is not back until the wait ends.** On a SQLite file whose pool has no connection free, the attempt is refused when it gets one, so the caller is back at the pool's timeout at the latest, 30 seconds unless `pool_timeout` is set. Before the fix, it was back at once. The same holds for a wait for a turn on an in-memory storage, as it did before. A wait in the pool's queue touches no connection and could end at the cancellation; a checkout that has begun cannot.
- **Under an anyio cancel scope, a cancelled caller keeps the event loop turning until its attempt ends.** The scope cancels its task again on every turn, and the wait takes each cancellation and goes on. One statement held for a second took 135,379 cancellations, where a plain asyncio caller sent two. The loop serves other tasks between them. SQLite only.

### A canceller is lost

- **Of two cancellers that land while one call waits for its attempt, one can be lost.** The caller is raised one error for both. An anyio cancel scope takes any error that carries its message, so a `task.cancel()` or an asyncio time limit from outside the scope is lost when the scope is cancelled in the same wait: the task runs on and no `TimeoutError` is raised. The order before, the first cancellation raised alone, lost the scope's and let `CancelledError` escape the scope. Both need two cancellations inside one statement's wait.
- **A second canceller is lost when the first carries a message and the call is awaited inside an `except` block.** Python replaces the `__context__` of an error that leaves a block that is handling another, and the second canceller's error was kept there. `task.cancel("shutdown")` followed by a cancel scope is one such pair.
- **A cancelled `tree` can raise a new `CancelledError` with no message.** The kernel's `tree` raises a `CancelledError()` of its own where its caller was cancelled, so a canceller that knows its cancellation by its message, as an anyio cancel scope does, does not know this one. Seen on three mounts in the second reading and not in the third, so it depends on how the mounts are arranged. Before the fix.

### A background pass is left in a wrong state

- **A rebuild cancelled as it claims or releases the index lease leaves the lease held.** The next rebuild is refused as a rival until the lease's five minutes pass. One cut in 125 on each SQLite host. Before the fix.
- **A rebuild's beat is awaited under a `suppress` of `CancelledError`.** `maintenance.py` suppresses it around `await beat`, so a second cancellation of the rebuild's caller that lands there is swallowed. Read, and before the fix.
- **What the statistics pass's interrupt does at `close()` is not run against the fix.**

### Not run

- **Cancellation is not run on a server engine.** What a cancelled write has done on Postgres is read in driver source. Whether a connection thrown away there can hold a lock, as on a SQLite file, is not known.
- **The synchronous `VirtualFileSystem` and uvloop are not run under cancellation.**

## Decisions

1. **Each later cancellation is delivered again at the caller's next `await`,** and the first is raised alone. That is what a plain `await` would have done, and it loses neither canceller. This changes what a caller with two cancellers sees, so it is a choice below.
2. **A wait in the pool's queue ends at the cancellation.** A checkout that has begun runs to its end and is then refused, as today.
3. **The wait for an attempt takes a scope's cancellation once,** and then waits without being woken for each repeat.
4. **The kernel's `tree` raises the caller's own cancellation,** not one of its own.
5. **The lease is claimed and released inside a shielded step,** and the `suppress` around the beat is removed.
6. **The engine leg runs the cancellation tests on Postgres,** and a sync and a uvloop leg are added to `tests/storage/test_cancelled_call.py`.

## Tests

Each defect gets its reproducing test first. A build that drops the out-of-reach rule must fail a test and must not hang a parallel run, so every test in the file carries a deadline that ends the test itself, not the run.

## Scope

In: `attempts.py`, the kernel's `tree`, `maintenance.py`'s lease and beat, and the cancellation tests. Out: the time limit, which has its own spec, and the engine's construction, which is `agents/2026-11-21-a-storage-owns-its-engine-well/spec.md`.

## Not checked

- Whether decision 2 can be built without changing SQLAlchemy's pool.
- What Postgres leaves after a cancelled commit.

## Choices to confirm

1. **Decision 1: deliver each later cancellation again?** Recommended: yes. Its cost: a caller with two cancellers sees two cancellations where today it sees one.
2. **Decision 2: end a wait in the pool's queue at the cancellation?** Recommended: yes.

## One line

A cancelled call returns at once, raises its own cancellation, loses no other, and leaves no lease or pass behind, on every engine and every event loop VFS runs on.
