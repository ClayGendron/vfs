# Every wait in a test is bounded by the run alone

A draft, written on 2026-11-21 from the inventory of clock-dependent tests made for the clock-and-luck work, holding what that work did not change, and built on 2026-11-21. What was done, what was not, and the defects found are under [What was done](#what-was-done).

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

## What was done

Each site below was read, changed and run; "read" marks a site changed by reading alone. "Under load" is eight busy loops on four cores, each test repeated 20 times.

### The fixtures

- **`thread_gate` in `tests/conftest.py`** makes a `threading.Event` the test's teardown sets. A thread waits on it with no bound; a test that fails or reaches its deadline before it opens the gate frees the thread as it tears down. It is asked for after any fixture that joins that thread (`pool`, `one_worker_pool`, `fresh_process_pool`), so it is torn down first.
- **`_unbounded_budgets` in `tests/conftest.py`** is autouse and session-scoped, so a storage a module-scoped fixture builds is covered too. It sets to `math.inf` the defaults of `grep_wall_seconds`, `search_wall_seconds`, `glob_wall_seconds`, `embed_timeout_seconds` and `close_timeout` on the constructors of `DatabaseStorage`, `SQLiteStorage`, `PostgresStorage`, `InMemoryStorage`, `AsyncVirtualFileSystem` and `VirtualFileSystem`; `WALL_TIME_BUDGET` in `vfs.base`, `vfs.chain`, `vfs.fanout` and `vfs.listing`, which the router's own matching stages read at each call; and the `seconds` default of `RenderLimits`. A function-scoped first version left the module-scoped storages of `test_rights.py`, the prefilter tests and the SQLite conformance on the shipped budgets, and 51 of them failed under the jumping clock.
- **Every constructor and consumer takes `math.inf`.** Each storage refuses only a budget `<= 0`, and `RenderLimits` the same; `Deadline.after(math.inf)` holds an instant of `inf` whose `remaining()` is `inf`; the Rust deadline treats an infinite budget as none (`crates/vfs-core/src/deadline.rs` pins it); `asyncio.wait_for` takes it. No `src/` defect was found here.
- **The tests of a budget name theirs.** `test_each_batch_gets_the_wall_budget_cut_at_worker_start` sets `chain_module.WALL_TIME_BUDGET` to 10 and asserts a budget of 7; `test_chained_glob_reads_its_wall_before_it_materializes_the_rows` and `test_one_large_root_stops_inside_its_walk` set the constant of `vfs.base` and `vfs.fanout`; `test_a_gate_past_its_wall_refuses_the_call` builds its storage with `glob_wall_seconds=WALL_TIME_BUDGET`; the two overlay wall tests of `test_search.py` pass `search_wall_seconds=WALL_TIME_BUDGET` and now read a hand clock, which stands still until their kernel moves it, in place of the real clock plus a skew; the Builder clock tests of `test_markdown.py` and the cadence test of `test_seam.py` pass `RenderLimits(seconds=RENDER_SECONDS)`.

### Bounds that failed the test when they ran out

- **`_GatedMatcher`** in `tests/test_offload.py` waits on a `thread_gate` with no bound, in its five tests.
- **`_QueueClock`** waits on an event its pool's next `submit` sets, a `thread_gate`, in place of five seconds of polling the queue.
- **`test_concurrent_hops_build_the_set_once`**: the first builder waits on an event `_CountingExecutor` sets as the second hop starts, a `thread_gate`, in place of five seconds of polling `started`.
- **`.result(timeout=5.0)`** on the process pool, four sites in `test_offload.py`, is `.result()`. The fork script's 30-second waits and its 120-second `subprocess.run` were left: they bound a child process, whose stacks the hang guard does not write.
- **`threading.Timer(5.0, release.set)`** in `test_close_never_waits_for_a_running_batch` and `test_a_batch_queued_at_close_still_finishes` is gone: `started` and `release` are `thread_gate`s. The two `asyncio.sleep(0)` before the close in the second test became a wait for the batch to be in the pool's queue.
- **`RETURNS_WITHIN = 5.0`** in `tests/base/test_mount_posture.py`, 31 `wait_for` sites, and the nine five-second `wait_for` sites of `tests/base/test_mount_listing.py` await their event or task alone; the constant is removed.
- **The 30-second gather** of `test_a_close_during_the_planning_hop_answers_a_result` and the 60-second `wait_for` of `test_both_prefilters_answer_alike` in the glob and grep namespace tests, and the 60-second `wait_for` of `test_splitting_never_holds_a_slot_at_concurrency_one` in `test_embed.py`, are plain awaits.
- **`tests/test_sync.py`**: the ten-second `started.wait` and `join` of the three drain tests, and the 30-second `warm.wait` and `join` of `test_close_under_load_on_a_real_storage_returns_cleanly`, have no bound, and the `is_alive` checks a bare `join` makes true are gone; the ipykernel test's two 120-second timeouts are gone. The `pytest.mark.timeout(60)` markers stay: they are each test's deadline, the run's own guard.
- **`_HUNG_AFTER_SECONDS`** in `tests/storage/database/test_races.py` is removed and its gather awaited alone (read; Postgres only).

### Two writers on one file

- **`TestClosedWindows`** sqlite legs in `test_authorized.py` take `_waits_out_every_lock` for both storages.
- **`test_two_instances_first_touch_concurrently`** in `test_engine.py` takes it for both.
- **`test_a_rival_delete_converges_after_the_window`** in `test_edges.py` takes it for the rival, first-touches the rival before the window, and no longer holds the window open half a second. Inside the window it waits until the rival's writer connection is given its `vfs_writer` option (SQLAlchemy's `set_connection_execution_options` event, which comes just before its `BEGIN IMMEDIATE`), then proves the file's write lock is held by a `BEGIN IMMEDIATE` on a raw connection with `timeout=0`, which must be refused as locked, and that the rival has not finished. A first try that waited on `trash.serialize` deadlocked: the rival blocks at its `BEGIN IMMEDIATE`, before that call. A `begin` listener, even with `insert=True`, ran after vfs's own, which emits the `BEGIN IMMEDIATE`, so it could not be the event.

### Sleeps that set up a race

- **`test_a_cancelled_caller_still_lands_the_statistics`**: the `asyncio.sleep(0.005)` is gone; the cancel lands as the first `ANALYZE` is handed to the driver.
- **`test_a_cancel_before_the_worker_starts_never_runs_the_matcher`**: the worker is held by a `thread_gate` and the test waits until the hold has started; the cancel comes once the batch is in the queue; after the release, a job submitted behind the batch is awaited, so the worker has passed the cancelled batch when the assertion runs.
- **`test_overlapping_calls_are_refused`**: its `asyncio.sleep(0.05)` became a wait for the matcher to start.
- **`_serialization_point_blocks_a_rival_topology_verb`** in `tests/storage/test_conformance.py`: the `asyncio.sleep(0.5)` became a wait on the move's `vfs_writer` option, set just before its first statement, the point; the 60-second `wait_for` is a plain await. Postgres only: not run on Postgres. The helper was run once against a SQLite file through a scratch script that stood in for `_server_storage`, and passed.
- **`test_a_rival_delete_serializes_behind_the_locked_resolve`** in `test_races.py`: the 60-second `wait_for` is a plain await (read; Postgres only).
- **`test_a_timed_out_close_leaves_no_pass_running`** was left alone, as another change edits it.

### Runs

- **Under load**: the 167 changed tests that run here, 20 times each, 3,340 runs: 3,339 passed. The one failure is `test_a_close_during_the_planning_hop_answers_a_result[1-grep]`, below. No before run under load was made.
- **Under the jumping clock**: the 17 changed test files and `test_render.py`, 1,752 tests. Before, at a 60-second deadline: 414 failed, 5 errors, 1,322 passed, 11 skipped; four tests hung until the deadline, the two close tests of `test_grep_namespace.py` and two `_GatedMatcher` tests of `test_offload.py`, each waiting for a batch that a fired budget never started. After, at the shipped 600-second deadline: 1,741 passed, 11 skipped, none failed. At a 60-second deadline the five errors return in both trees: a shared plan-store build of the SQLite conformance outlasts 60 seconds under that clock.
- **The whole suite**: 6,038 passed, 18 skipped, one failed, below. `ruff check`, `ruff format --check` and `ty check` are at zero across `src/` and `tests/`.

### Not done, and defects found

- **A close during a glob's or grep's planning hop can answer `unavailable`, a `src/` defect.** On an `InMemoryStorage`, the call reaches the storage after the close has dropped the in-memory database, and answers `vfs.unavailable` "glob failed: no such table: vfs_principal_revisions" beside `backend_unavailable` "Cannot operate on a closed database", where the test accepts success or `backend_unavailable` alone. Reproduced by a scratch script that repeats the race under load. `test_a_close_during_the_planning_hop_answers_a_result` failed 1 of 800 under load on the base commit and 4 of 800 after this change; the wait removed from it was `asyncio.wait_for`, which on Python 3.12 and later awaits the gather in the same task, so the difference is read as noise.
- **`test_a_listed_module_never_grows_and_an_unlisted_one_stays_under_the_ceiling` fails on the base commit.** `bcb3f2b` grew `backend.py` from 1,537 to 1,542 lines and `engine.py` from 1,008 to 1,023; this change touches no `src/` file.
- **The one-second probe of `test_a_rival_delete_serializes_behind_the_locked_resolve` stays.** It waits a second and asserts the rival delete has not finished; a slow machine weakens it and cannot fail it. Its event-based form needs a Postgres lock observation, such as a `FOR UPDATE NOWAIT` read of the endpoint row from another connection inside the window, and no Postgres was available to run it.
- **The Postgres legs were not run**: the conformance serialization-point test and the two sites of `test_races.py`.

## One line

A test waits on an event and lets the run's deadline end a wait that never ends, so no bound of its own fails it on a slow machine.
