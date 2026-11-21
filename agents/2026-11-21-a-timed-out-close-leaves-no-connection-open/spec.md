# A timed-out close leaves no connection open

A draft, written on 2026-11-21 from a leak the clock-and-luck work found once `ResourceWarning` became an error in the suite. It is not reviewed, and nothing is built.

## The outcome wanted

A storage whose `close()` is cut short by its caller's timeout, while the planner-statistics pass holds a connection, ends with every driver connection closed once the pass has ended. No connection is left for the garbage collector.

## The problem

Shown by a test that ran.

- **The pass's connection is checked back in to a pool nobody closes.** `test_a_timed_out_close_leaves_no_pass_running` in `tests/storage/database/test_statistics.py` holds the pass at its `BEGIN IMMEDIATE`, closes the router with `close_timeout=0.01`, and lets the pass end. `EngineHost.close` still runs `engine.dispose()` in its `finally`, and SQLAlchemy's dispose leaves a checked-out connection open and replaces the pool. When the pass ends, its connection goes back to the old pool: after the test, `old_pool.checkedin()` is 1, and the `aiosqlite` connection is collected unclosed in a later test, with `ResourceWarning: ... was deleted before being closed`.
- **A sync `dispose()` of the old pool does not close it.** The aiosqlite adapter's `close` awaits the driver, so only a dispose run inside a greenlet (`sqlalchemy.util.greenlet_spawn(pool.dispose)`) closes it. The test now does that itself, with a comment saying why.
- **The same shape follows any `engine.dispose()` while a pass runs.** `test_each_candidate_is_metered_once_a_pass` in `tests/storage/database/test_indexing.py` disposed the engine with a pass in flight and leaked the same way; it now settles the statistics first.

## Decisions

1. **The pass that outlives a close disposes what it returns to.** Either the pass's own `finally` closes its connection when the host was closed under it, or `close()` keeps the old pool and disposes it again once the pass has ended.
2. **The test's own reclaiming goes,** once the fix lands, and the test asserts that the old pool holds no connection.

## Tests

`test_a_timed_out_close_leaves_no_pass_running` asserts `disposed_pool.checkedin() == 0` after the pass ends and runs with no `greenlet_spawn` of its own; the suite's `error::ResourceWarning` filter holds it after.

## Scope

In: `EngineHost.close`, `EngineHost.stop_analysis` and the analysis pass in `src/vfs/storage/backends/database/engine.py`. Out: the busy-handler wait the close docstring already describes.

## Not checked

- Whether Postgres's pass leaves the same connection behind; the test is SQLite-only.

## One line

A close cut short by its caller still closes, once the pass ends, the connection the pass gives back.
