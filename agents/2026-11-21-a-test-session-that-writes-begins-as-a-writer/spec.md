# A test session that writes begins as a writer

A draft, written on 2026-11-21 from the cause of a flaky trash test found by the clock-and-luck work. It is not reviewed, and nothing is built.

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

## One line

A test that writes through a session of its own begins it as a writer, so it waits for the lock rather than losing it.
