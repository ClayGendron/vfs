# Every wait in a test is bounded by the run alone

A draft, written on 2026-11-21 from the inventory of clock-dependent tests made for the clock-and-luck work, holding what that work did not change. It is not reviewed, and nothing is built.

## The outcome wanted

No wait inside a test carries a bound of its own that fails the test when it runs out. A test waits on an event, and the run's deadline, which since the clock-and-luck work fails the test alone and keeps every thread's stack in `test-hangs/`, is the only bound on a wait that never ends.

## Builds on

`agents/2026-11-21-no-test-depends-on-the-clock-or-on-luck/spec.md`, which moved the named flaky tests and the clearest of the inventory onto events, a hand-moved clock or `math.inf`, and gave every test a deadline that ends the test and not the worker.

## The problem

Read, unless it says run. None of these has been seen to fail.

### Bounds that fail the test when they run out

- **`_GatedMatcher` asserts `self.gate.wait(timeout=5.0)`** in `tests/test_offload.py`. The bound also frees a pool thread a failed test would leave blocked, and a thread left blocked holds its worker at exit; the gate is the thing to make releasable, not the bound to drop.
- **`_QueueClock` waits up to five seconds for the queue** in `tests/test_offload.py`, and `test_concurrent_hops_build_the_set_once` busy-waits up to five seconds for its second hop, which only weakens the test when it runs out.
- **`threading.Timer(5.0, release.set)`** in `test_close_never_waits_for_a_running_batch` and `test_a_batch_queued_at_close_still_finishes` in `tests/base/test_grep_namespace.py` fails them when `close()` takes more than five seconds.
- **`RETURNS_WITHIN = 5.0`** in `tests/base/test_mount_posture.py`, about 20 sites, five-second bounds in `tests/base/test_mount_listing.py`, 30 and 60 seconds in the glob and grep namespace tests and `test_embed.py`, and 10 to 30 seconds of `wait` and `join` in `tests/test_sync.py`.

### Two writers on one file under the shipped busy budget

- **A rival writer waits on the shipped `busy_timeout` of five seconds, retried four times.** `TestClosedWindows` in `tests/storage/database/test_authorized.py` (the `sqlite` legs), `test_a_rival_delete_converges_after_the_window` in `tests/storage/database/test_edges.py`, which also holds its window open for half a second, and `test_two_instances_first_touch_concurrently` in `tests/storage/database/test_engine.py`. `_waits_out_every_lock` in `tests/support/database_helpers.py` is the lift the two-writers statistics test now takes: it failed 6 of 6 under load before and passed 6 of 6 after (run).

### Budgets every test-built storage carries

- **Every storage a test builds carries the shipped budgets:** ten wall seconds for `grep`, `glob` and `search`, and ten seconds of `close_timeout` on a router. A test that does not test a budget can run out of one on a machine slow enough. A fixture default of `math.inf` for each, with the budget tests setting theirs, would end that.

A run of the clock-and-luck work's touched test files with vfs's own clock jumping 1,000 seconds on every read failed 116 of 678, each read a shipped budget firing in a test that sets none: the glob, grep and search wall budgets, and the render budget behind twelve tests of `tests/rendering/test_markdown.py` and the PDF tests of `tests/storage/database/test_render.py` (run).

### Sleeps that set up a race

- **`asyncio.sleep(0.02)` "lets the pass reach the lock"** in `test_a_timed_out_close_leaves_no_pass_running`, and `asyncio.sleep(0.005)` before a cancel in `test_a_cancelled_caller_still_lands_the_statistics`, both in `tests/storage/database/test_statistics.py`. Either outcome passes today, so a slow machine weakens them rather than fails them.
- **`pool.submit(blocker.wait, 5.0)` with two `asyncio.sleep(0.05)`** in `test_a_cancel_before_the_worker_starts_never_runs_the_matcher` in `tests/test_offload.py`: a stall past five seconds frees the worker and the matcher runs; the sleeps can only make it pass falsely.
- **`asyncio.sleep(0.5)` "Give the rival time to reach — and block on — the point"** in `tests/storage/test_conformance.py`, with `wait_for(..., timeout=60)` after it there and in `tests/storage/database/test_races.py`, on Postgres only.

### Causes not found

- **`test_scope_channel_searches_as_composition[composed]`** failed once under load on 2026-11-20. Its SQLite leg passed 20 of 20 under eight spinners on four cores on 2026-11-21 (run); the memory leg skips by design. Its helper module's assertions now print both sides, so a next failure shows the difference.
- **`TestPostgresRankingPin::test_ordered_top10_matches_the_pin`** failed once on Postgres in CI with a bare `AssertionError`. `tests/ranking/pins.py` is now rewritten by pytest, so a next failure prints both lists. Not run on Postgres.

## Decisions

1. **A wait that frees a thread becomes a gate the test's teardown opens,** so the thread is freed without a bound.
2. **The rival tests take `_waits_out_every_lock`,** or prove their order by an event the verb sets, never by the busy budget.
3. **A test-built storage defaults its wall budgets and a router its `close_timeout` to `math.inf`,** through one fixture or helper; the tests of a budget name theirs.
4. **A sleep that sets up a race waits on the event it stands for,** the seam or listener the code under test passes.

## Tests

Each changed test is run under the load generator that holds every core, 20 times, before and after, and under a clock that jumps 1,000 seconds on every read.

## Scope

In: `tests/`. Out: `src/`, and the shipped defaults.

## One line

A test waits on an event and lets the run's deadline end a wait that never ends, so no bound of its own fails it on a slow machine.
