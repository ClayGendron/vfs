# No test depends on the clock or on luck

A draft, written on 2026-11-21 from the tests seen to fail now and then. It is not reviewed, and nothing is built.

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

## One line

Each test that waited on time or luck waits on an event instead, prints what differed, closes what it opened, and fails without hanging.
