# A close during a planning hop answers one refusal

Written on 2026-11-21 from a failure the work on bounded test waits found under load; not built.

## The outcome wanted

A `glob` or `grep` whose router is closed while the call is in its planning hop answers either its result or a single `backend_unavailable` refusal. It never answers `backend_unavailable` together with a second, unclassified `unavailable` error that carries a storage's internal SQL message.

## The problem

Shown by runs of the existing test, not yet by a deterministic one.

- **The test sometimes fails.** `test_a_close_during_the_planning_hop_answers_a_result` in `tests/base/test_glob_namespace.py` builds an `AsyncVirtualFileSystem` over an `InMemoryStorage`, starts a `glob` or `grep`, and closes the router after zero or one yields. It asserts the result is a success or carries exactly `[ErrorKind.backend_unavailable]`.
- **Under load the call answers two errors.** The test was run 800 times with eight busy loops on four cores. It failed once on the commit before the bounded-waits work and four times after it, always with `yields=1`, for both verbs. The `Result` carried `backend_unavailable` and also `vfs.unavailable` with the message "glob failed: no such table: vfs_principal_revisions" (run).
- **The second error comes from a storage reached after its close.** The message names a table of the in-memory database. So the call reached the storage after `close()` had dropped that database, instead of being refused at the closed gate.
- **Those runs and their logs** are `a8-close-hop.log` and `a8-close-hop-before.log` in the session scratchpad. They are not kept in the repo.

## Choices left open

1. **Where the refusal is decided.** Either the router checks for a close again after the planning hop and before it dispatches to a storage, or `InMemoryStorage` (and any storage that drops its state on close) answers `backend_unavailable` for any call that arrives after `close()` began.
2. **Whether a lost database is ever an unclassified `unavailable`.** An `OperationalError` about a missing table on a storage being closed could be classified at the storage's error funnel rather than at the router.

## Tests

- First, a deterministic reproduction: hold the planning hop on an event, close the router, then release the hop. It must fail on the current tree, with the two errors, before any fix.
- The existing test's assertion stays as it is.

## Scope

- In: the router's glob and grep planning path in `src/vfs/base.py` and `src/vfs/fanout.py`, and the closed-state handling of `InMemoryStorage`.
- Out: the close timeout and the statistics pass, which have specs of their own.

## Not checked

- Whether a `DatabaseStorage` on a SQLite file or on Postgres shows the same second error. The failing runs were all on `InMemoryStorage`.
- Which of the two hops (the namespace hop or the mount hop) the call was in when the close landed.

## One line

A call caught by a close is refused once, cleanly, and never reaches a storage that has already been closed.
