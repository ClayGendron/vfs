# No test depends on the clock or on luck

A draft, written on 2026-11-21 from the tests seen to fail now and then, and built on 2026-11-21. What each case turned out to be, and what was done, is under [What was found](#what-was-found). What was not done is in three specs of its own, named at the end.

## The outcome wanted

Every test in `tests/` and `docs-app/` passes on a loaded machine as it does on an idle one, fails with a message that shows the difference, and never hangs a run. A test that can fail on a slow machine is a test of the clock, which the working agreement forbids.

## The problem

Each was seen in a run, and passed when run again.

- **`test_two_writers_crossing_together_analyze_once` in `test_statistics.py` fails under load.** It needs a write of 30,000 files to end inside the 20 seconds its rival waits for the lock, over four attempts of five seconds. Seen on 2026-11-19 and 2026-11-20, with a load of 34 on 10 cores. No clock was found in its path on 2026-11-21, and the failure was not reproduced. Seen again on 2026-11-21, once, while `scripts/ci.sh` ran beside a second full run of the suite; a write in its second batch failed, and the test then passed 5 of 5 alone, at about 24 seconds a run.
- **`test_the_sync_facade_close_disposes_with_no_pending_task` in `test_statistics.py` failed once under load,** on 2026-11-21, while a full run of the suite shared the machine with `scripts/ci.sh`. It passed 3 of 3 alone. The cause was not looked for.
- **`test_scope_channel_searches_as_composition[composed]` in the storage contract failed under load once,** on 2026-11-20. The cause was not found.
- **`test_the_beat_keeps_ticking_through_a_slow_batch` in `test_embed.py` gives up after 100,000 turns of the loop.** It waits for five beats of a timer by yielding to the loop. Under load it ran out of turns in 2 of 38 runs before pull request 27 and in 1 of 38 on it.
- **`test_a_create_whose_snapshot_predates_the_parents_delete_refuses` in `test_trash.py` failed once under branch coverage,** which forces the slower tracer on Python 3.13, and passed in two plain runs of the suite and three times alone.
- **`TestPostgresRankingPin::test_ordered_top10_matches_the_pin` failed once on Postgres in CI,** on pull request 18 on 2026-11-20, with a bare `AssertionError`. It compares two lists and prints neither, so the difference was not seen.
- **A worker thread of aiosqlite was seen to end after its event loop had closed.** One `PytestUnhandledThreadExceptionWarning`, in two runs under coverage on pull request 27's branch and in no plain run. It was reported during a test that opens no connection, so an earlier test in the same worker left the thread.
- **`test_authorized.py` leaves SQLite connections unclosed.** Its helper builds storages no test closes, and the collector reports 12 `ResourceWarning`s for the file alone, 20 in one run of the gate.
- **A hold left armed hung CI for its whole budget, and the run never said where.** On pull request 29, `cancel_if_held` in `tests/support/cancelled_callers.py` returned with its hold still armed when the call ended before its cut, so the next round trip on any task, a statistics pass's, was held on its worker thread with nothing to let it go. The Tests job hung on Python 3.11 to 3.13 until it was cancelled. Pull request 29 fixed the helper and pinned it, and added `timeout = 600` with `timeout_method = "thread"` to `pyproject.toml` and job deadlines to both workflows. That guard names the test, but the thread method ends the whole worker, and pytest-xdist does not forward a worker's stderr, so the stack dump that shows where it hung is lost.
- **A build that loses the out-of-reach rule hangs a parallel run.** With the rule taken away, a call on a SQLite file that an anyio cancel scope cancels leaves a driver task that never ends. `TestACallerCancelledByATimeLimitAndByACancelScope` carries a timeout of 60 seconds, which ends a serial run. Under parallel workers a run had not ended after 20 minutes. A pin should fail, not hang.
- **Tests of the docs site may act before the page's scripts have started.** The back-to-top test did, failing three times on 2026-11-19, and now waits for the theme toggle to say it is ready. It failed again on 2026-11-21 (`a button that returns to the top shows once the reader scrolls back up`, `docs-app/tests/layout.spec.ts:219`), once, while `scripts/docs.sh check` ran beside a full run of the suite, and passed when the check ran alone, so waiting for the toggle is not enough under load. The drawer test on a phone and the test that the menu for scripts off is gone both need scripts and do not wait. Neither has been seen to fail.

## Decisions

1. **Each test that waits on a time or a count of turns waits on an event the code under test sets,** or runs with its budget set to `math.inf`, as the two counted `glob` tests have since pull request 26.
2. **Every list comparison in a pin prints both lists on failure.**
3. **A fixture closes every storage a test builds,** and the suite turns `ResourceWarning` and `PytestUnhandledThreadExceptionWarning` into errors so they cannot come back.
4. **A test that can hang carries a deadline that ends the test and not the worker,** and a hang that reaches the suite-wide `timeout` leaves its stack dump where CI keeps it, a file the job uploads, since xdist drops the worker's stderr.
5. **Every docs-site test that needs scripts waits for the page to say it is ready.**

## Tests

Each test is run under a load generator that holds every core, 20 times, before and after its change, and under a fake clock that jumps 1,000 seconds on every read, as the review of pull request 26 did.

## Scope

In: the tests named above, `tests/conftest.py`'s warning filters, and the Playwright tests. Out: any change to `src/`, unless a test shows a defect there.

## Not checked

- The cause of the two-writers failure and of the composed-scope failure.

## What was found

Each was run under eight busy loops on four cores, the load generator below, unless it says "read".

- **The two writers.** The rival's write ran out of SQLite's `busy_timeout`: five seconds, retried four times, while the other wrote 30,000 files. It failed 6 of 6 under load. `_waits_out_every_lock` in `tests/support/database_helpers.py` raises the test's `busy_timeout` to SQLite's largest, and it passed 6 of 6 under load and 20 of 20 in the after run. Its two `success` assertions now print the errors.
- **The sync facade close, and the close that interrupts a pass.** Each waited on a clock: `first.wait(timeout=10.0)`, the router's default `close_timeout` of ten seconds, and a bound of one second. Each now waits on its event and closes with `close_timeout=math.inf`; the rollback and the empty `sqlite_stat1` remain the proof that the pass was interrupted. The timed-out close's own wait for the pass lost its ten-second bound.
- **The composed scope.** Not reproduced: its SQLite leg passed 20 of 20 under load. The cause is still not found.
- **The beat.** The provider now waits on an event the statement listener sets at the fifth beat, not on 100,000 turns of the loop.
- **The trash snapshot.** The test's own helper opened a plain `BEGIN`, read, then wrote; when another connection committed in between, SQLite refused the upgrade at once with `database is locked`. It failed 7 of 100 under load with branch coverage. The helper now begins as a writer, and it passed 100 of 100.
- **The Postgres ranking pin.** `tests/ranking/pins.py`, like every helper module of `tests/support/`, `tests/ranking/` and `tests/lint/`, was not rewritten by pytest, so its assertions printed nothing. `tests/conftest.py` now registers the three packages for rewriting, and `test_every_helper_module_that_asserts_is_rewritten` holds it. Not run on Postgres.
- **The aiosqlite thread and the unclosed connections.** Four sources, each now closed: `with sqlite3.connect(...)` commits but never closes, in `test_authorized.py` and `test_statistics.py`; pytest-asyncio's setup asking for the current loop before one was set, which up to Python 3.13 makes a loop nobody closes; a test's own `engine.dispose()` while the statistics pass held a connection; and a timed-out close that leaves the pass's connection in the disposed pool, a defect in `src/` the test now reclaims by hand. `ResourceWarning`, `PytestUnraisableExceptionWarning` and `PytestUnhandledThreadExceptionWarning` are errors in `pyproject.toml`, and the full suite passes with them.
- **The armed hold that hung CI.** pytest-timeout cancels a test's deadline as soon as one of its phases fails, so a test that failed and then hung in teardown ran with no deadline and held its worker for good. With the out-of-reach rule taken away, `TestACallerCancelledByATimeLimitAndByACancelScope` hung that way under two workers, in pytest-asyncio's `Runner.close` waiting on the driver task. `tests/conftest.py` now arms its own deadline in place of pytest-timeout's signal timer: at the deadline every thread's stack goes to `test-hangs/<worker>-<pid>.txt` under the test's name and the test fails; the deadline is kept through teardown; and a backstop at half the deadline again writes the stacks from C and ends the worker. `timeout_method` is `signal`. The broken build then ended in under five minutes with 12 failures, 15 errors and the stacks of each in the files. Both workflows upload `test-hangs/` when a job fails or is cancelled. Three tests in `tests/test_suite_guards.py` run a child pytest under two workers with hanging tests and hold it.
- **The docs site.** The root layout sets `<html data-ready>` once the page has hydrated, and each of the 18 tests that run with scripts opens its page through `visit`, which waits for it. Waiting for the theme toggle had already meant the back-to-top listener was in place; its failure came from two scrolls inside one frame, which Chromium sends as one scroll event read at the second position, so the component never saw the reader turn back up (shown by an experiment). The scroll helper now resolves on the scroll event that reports its position. The two `waitForTimeout(300)` calls became waits on the list's end and on the row's transitions. The flake was not reproduced before the change (90 of 90 under load); after it, `layout.spec.ts` passed 400 of 400 under twice as many busy loops as cores, and the four scripted tests 200 of 200 under six times as many, on the preinstalled Chromium build 1243, not CI's 1248.
- **The inventory.** A search of `tests/` for other waits on a clock found about twenty more. The clearest were changed: `test_close_disposes_concurrently_not_sequentially` asserted elapsed time and now has two closes that each wait for the other to begin; the render budget tests slept past a ten-millisecond budget and now move a hand clock; the lease heartbeat tests polled with sleeps and now wait on events; `LoopTicker.hop` lost its five-second bound and says at once when it is called on the loop's own thread; and `test_planning_leaves_the_loop` hops instead of counting turns.

## Follow-up specs

- `agents/2026-11-21-a-timed-out-close-leaves-no-connection-open/spec.md`: the connection a timed-out close leaves open.
- `agents/2026-11-21-a-test-session-that-writes-begins-as-a-writer/spec.md`: the other hand-built test sessions open to the trash test's refusal.
- `agents/2026-11-21-every-wait-in-a-test-is-bounded-by-the-run-alone/spec.md`: the rest of the inventory, and the two causes not found.

## One line

Each test that waited on time or luck waits on an event instead, prints what differed, closes what it opened, and fails without hanging.
