# A SQLite writer beside a batch waits for its commit

Written on 2026-11-21 from the cause of the two-writers flake that the clock-and-luck work found. Decided and built the same day: choice 1.

## The outcome wanted

Whether a write on SQLite may fail because another writer held the file's lock for longer than vfs's busy budget is decided and written where a user reads it, and the shipped budget matches the decision.

## The problem

Shown by runs.

- **A rival write gives up after about twenty seconds beside a batch.** SQLite sends `PRAGMA busy_timeout = 5000` on every connection (`src/vfs/storage/backends/database/dialects.py`), and `EngineHost` retries a busy writer four times (`retry_attempts=4` in `src/vfs/storage/backends/database/engine.py`). `test_two_writers_crossing_together_analyze_once` in `tests/storage/database/test_statistics.py` writes 30,000 files beside a second writer of 30,000; under eight busy loops on four cores the second write failed 6 of 6 runs. The test now lifts its own `busy_timeout`.
- **The reference deployment runs a 10,000-file batch beside single-file writes overnight.** The working agreement's table has a batch running almost all night beside the day's writes. On SQLite, which serves local and demo use, a batch of that size holds the lock for seconds; a slower machine or a larger batch holds it past the budget.

## Choices it leaves

1. Keep the budget, and say in `DatabaseStorage`'s docstring that a write beside a long writer on SQLite can come back `unavailable` and retryable after about twenty seconds.
2. Make the busy budget a declared, documented setting a caller can raise.
3. Let a writer wait for as long as the lock is held, bounded only by the caller's own cancellation.

## Decision

Choice 1: the budget stays. A write on SQLite beside a long writer can give up after about twenty seconds, and the storage says so.

## What was done

- **The docstring.** `DatabaseStorage` says that one writer holds the file at a time, that a write behind another writer's lock waits five seconds a try for four tries, and that beside a long writer, such as a 10,000-file batch, it can give up after about twenty seconds, change nothing, and return a retryable `conflict` that succeeds once that writer has committed. The problem above names the outcome `unavailable`; the code returns `conflict`, `retryable=True`, through the `StaleSnapshot` channel of `EngineHost.with_retry`, and the docstring follows the code.
- **The pin.** `test_a_write_behind_a_held_lock_gives_up_after_four_tries_and_changes_nothing` in `tests/storage/database/test_engine.py` holds the lock with a rival `BEGIN IMMEDIATE`, sets each checkout's `busy_timeout` to 0 so no try waits, and counts four `BEGIN IMMEDIATE` statements, one retryable `conflict`, no file written, and a second write that succeeds once the rival commits. It also asserts the shipped `PRAGMA busy_timeout = 5000` and the default of four attempts, so a change to either fails it.
- **The size ratchet.** `backend.py` is held at 1,537 lines; the class docstring's paragraphs were rewrapped to the 120 columns the rest of it uses, and the three identical wall-budget checks in `__init__` became one loop with the same messages.

## Scope

In: SQLite's session settings and the retry of a busy writer. Out: Postgres, whose writers wait on row locks.

## One line

Whether a SQLite write may fail beside a long batch is decided and written down, and the busy budget follows.
