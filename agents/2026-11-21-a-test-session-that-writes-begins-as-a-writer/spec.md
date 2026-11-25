# A test session that writes begins as a writer

Written on 2026-11-21 from the cause of a flaky trash test found by the clock-and-luck work, and built the same day.

## The outcome wanted

Every session a test opens by hand on a SQLite storage, and then writes through, begins with `BEGIN IMMEDIATE` as a verb's writer does, so it waits for the file's write lock instead of being refused it.

## The problem

Shown by runs.

- **A read transaction that then writes is refused at once when another connection commits after its first read.** `test_a_create_whose_snapshot_predates_the_parents_delete_refuses` in `tests/storage/database/test_trash.py` failed 7 times in 100 under a load of eight spinners on four cores and branch coverage, each with `sqlite3.OperationalError: database is locked` on the `INSERT` of its stale plan. Its helper `_apply_stale` opened `host.session_factory()` with a plain `BEGIN`, read, then wrote. SQLite answers such an upgrade with `SQLITE_BUSY_SNAPSHOT`, whose message is also `database is locked`, and waits for nothing; the 100 runs took 23 seconds, so no five-second busy wait ran. The other connection is taken to be the host's background statistics pass. The helper now begins as a writer, `session.connection(execution_options={"vfs_writer": True})`, and passed 100 of 100 under the same load.
- **A second instance failed in CI.** `test_reclaim_built_epoch_never_touches_the_published_rows` in `tests/storage/database/test_lexical.py` failed on Python 3.11 in the pull request's Tests job, with `database is locked` on its `DELETE`: its session began as a plain transaction just after a rebuild whose statistics pass had been started. It passed 40 of 40 under load locally and was not reproduced; it now begins as a writer.
- **Many hand-built sessions share the shape.** `host.session_factory() as session` appears about 160 times in `tests/storage/`, 25 in `test_labels.py`, 23 in `test_coherence.py` and 20 in `test_writes.py`. Those that read and then write are open to the same refusal whenever a pass is running. Which of them write is not counted.

## Decisions

1. **One helper opens a test's writing session,** in `tests/support/database_helpers.py`, beginning as a writer; every hand-built session that writes uses it.
2. **A lint test refuses a hand-built session that writes without it,** if one can be told from the source; otherwise the helper's docstring says why it exists.

## Tests

Each changed file is run 20 times under the load generator with branch coverage, before and after.

## Scope

In: `tests/` only. Out: `src/`, where every verb's writer already begins with `BEGIN IMMEDIATE`.

## Not checked

- That the refusal was `SQLITE_BUSY_SNAPSHOT` (517) and not `SQLITE_BUSY` (5): the extended code was not read.
- That the rival in the trash test was the statistics pass. Nothing else of that storage was in flight.

## What was done

- **Which sites write was found by running them, not by reading.** A scratch pytest plugin listened on every SQLite statement of `tests/storage/` and `tests/support/` and recorded each transaction that began with a plain `BEGIN` and then wrote, with the frames that sent it. It found 218 such writes from 66 blocks: 27 `session_factory()` sessions and 39 `engine.begin()` blocks, the second shape not named in the problem above. Many write through `src/` functions a test calls inside its own session (`bump_revision`, `Relabeller.step`, the index lease seams), so a reading of the test's source does not tell which sessions write. No verb began such a transaction. The one `src/` path seen, `EngineHost._install_vector_function`, opens a plain session for the profile's install statement; SQLite's profile declares no install, and only `test_sqlite_vec.py`'s faked profile reaches it there.
- **Two helpers, not one.** `begin_as_writer(session)` in `tests/support/database_helpers.py` is the first statement of a writing session and returns its connection; `writer_engine(engine)` is the engine whose `.begin()` begins as a writer. One context manager cannot serve both session shapes: a `session.begin()` block refuses a session already begun, and a commit or rollback inside one is refused with `Can't operate on closed transaction inside context manager` (run). The in-memory storage's `SerializedSessions` takes no `bind`, so a session bound to a writer engine is not available either. Off SQLite the option changes nothing.
- **Every writing site uses them.** The 66 blocks above, and the 62 sessions that already began as writers inline with `session.connection(execution_options={"vfs_writer": True})`, now call the helpers.
- **A guard in place of a lint.** Decision 2's lint cannot tell a writing session from its source, for the reason above. `tests/conftest.py` instead follows each SQLite connection's plain transaction from its `BEGIN` and fails at teardown a test whose transaction read and then wrote, naming the statement and the frames that sent it. It flags only that shape: a plain transaction whose first statement writes takes the lock with a busy wait, as `BEGIN IMMEDIATE` does, and is not refused. It listens on the dialect's `do_execute` events, so it adds no statement listener a test counts. `test_a_plain_transaction_that_reads_then_writes_fails_its_test` in `tests/test_suite_guards.py` runs it in a child pytest: a plain session that reads and then writes errors at teardown with its statement and line; the same session begun by `begin_as_writer` passes, and so does a plain session whose first statement writes. A first form of the guard also failed that last session, because it moved a begun transaction to read on its first read wherever the read came (run).
- **Runs.** With the guard, the whole suite passed on the branch. The guard over `dev`'s tests as they were before this change, `tests/storage`, `tests/support`, `tests/ranking` and `tests/models`, errored 11 tests at teardown, each a plain transaction that read and then wrote, in `test_labels.py`, `test_rights.py`, `test_identity_portability.py` and the memory and SQLite legs of `test_conformance.py` (run). Every other write it recorded in the survey began with the write, which takes the lock with a busy wait.
- **Not run.** The declared runs of each changed file 20 times under load, before and after, were not made for the files changed on the guard's evidence; the guard's teardown errors stand as the before.

## One line

A test that writes through a session of its own begins it as a writer, so it waits for the lock rather than losing it.
