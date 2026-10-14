# 078. The Serialization Point Is Its Own Lock Row

- **Status:** accepted 2026-10-13 (Clay, in conversation: "go ahead and
  implement the vfs_lock table"). Refines the serialized-verb kit
  (`serialized.py`); the arbitration model and ADR 044's two-read
  protocol are unchanged.
- **Date:** 2026-10-13
- **Deciders:** Clay Gendron
- **Decided by:** human (Clay). Claude ran the spec 162 code review
  that found the coupling, a dedicated agent wrote the recommendation
  against a rubric Clay asked for, and Claude landed it.
- **Context source:** the review of commits `7d0bc3c..c1900be`
  (2026-10-13), finding 2: on SQL Server the version mint's read of the
  grant revision waited behind any in-flight delete, restore, sweep,
  move or copy, and the restore-versus-revive race test hung.

## Context

The serialized verbs — delete, restore, sweep, move and copy — run one
at a time per mount. Each takes the serialization point as its first
statement. Until this decision that point was three arms: nothing on
SQLite (the writer transaction is the lock), a transaction-scoped
advisory lock on Postgres, and a self-assignment `UPDATE` of the single
`vfs_meta` row everywhere else, which X-locked that row to commit.

The meta row is also a hot read row. The grant revision on it is read
by the version mint on every overwrite, edit and revive, by the rights
compile on every cache miss under an authority, by grep's epoch
pointer, by embed, and by cold first touch. On an engine where a plain
read waits behind an X-locked row — SQL Server at its default READ
COMMITTED, and any locking engine the GENERIC floor may meet — every one
of those reads waited for whatever serialized verb was in flight,
including a 10,000-row subtree delete. The write path's own promise,
"writes are deliberately not serialized with these verbs", did not hold
there. The 2026-08-14 SQL Server first-touch memo had already met this
coupling for cold first touch and filed it as by design.

## Decision

The serialization point gets a row of its own. `vfs_lock` is a one-row
table (`id INTEGER PRIMARY KEY, CHECK (id = 1)`), inserted by first
touch beside the meta row. `serialize()` is one statement on every
engine: the kit's locking read of that row (`lock_rows`), which
SQLAlchemy renders as `FOR UPDATE` on Postgres, MariaDB, Oracle and the
generic floor, as the profile's `UPDLOCK, FORCESEEK` hint on T-SQL, and
as a bare, inert `SELECT` on SQLite. Nothing else reads the row, so no
write, read, compile or first touch can wait behind a verb. The meta
row keeps its meanings — schema and identity, the grant revision, the
gram pointer, the reindex lease — and the admin writes keep bumping the
revision as their first statement and their lock. The verbs no longer
take a lock key; first touch keeps its own Postgres advisory lock for
provisioning, a separate mechanism.

Schema format version 21 → 22. A mount at format 21 refuses first touch
with the existing "upgrade or re-provision" message; greenfield, no
migration owed.

## Why this and not the alternatives

The agent's rubric, in order: the invariant holds on every engine; one
mechanism, not one per engine; no DBA prerequisite; fewest new concepts;
nothing added to the hot write path; the existing disciplines keep
their meaning; verifiable without a clock; honest about what stays
coupled.

- **Pin snapshot isolation on SQL Server.** `READ_COMMITTED_SNAPSHOT`
  and `ALLOW_SNAPSHOT_ISOLATION` are database options only an operator
  can set, with no other connection open. ADR 044 rejected the same pin.
- **Read the revision earlier, or carry it from the rights compile.**
  The compile's own reads still block on a cache miss; moving the read
  moves the wait.
- **`NOLOCK` or `READPAST` on the revision read.** A dirty read can stamp
  a revision that rolls back; `READPAST` returns no row, which reads as
  revision 0. A new engine arm for a wrong number.
- **Native advisory locks per engine** (`sp_getapplock`, `GET_LOCK`,
  `DBMS_LOCK`). Three new arms; Oracle's needs an `EXECUTE` grant,
  MariaDB's is session-scoped and released by hand.
- **Move the revision counter off the meta row instead.** Frees the mint
  and leaves grep, embed and first touch coupled; more functions change.
- **Lock the root entry row.** Every create under `/` bumps it.
- **A self-assignment `UPDATE` on the new row.** Works, but writes a dead
  tuple per verb on Postgres and raises serialization failures under
  REPEATABLE READ; the locking read is modelled by SQLAlchemy and is
  already the kit's spelling for guard reads.

One coupling remains by design: a hot-path revision read waits behind an
in-flight admin write's X-lock on the meta row (a grants write,
milliseconds; a relabel chunk, under two seconds). That is the admin
lock doing its job, bounded by the admin transaction.

## Consequences

- Zero dialect branches in the serialization point, down from three.
  The only engine fact involved, T-SQL's hint, was already declared on
  the profile and consumed by `lock_rows`.
- The write path issues exactly the statements it issued before. The
  serialized verbs issue the same count with a different first
  statement; on SQLite that statement is inert, one extra round trip
  per verb that the writer transaction already covers.
- Pins: for every profile, `serialize()` issues one statement naming
  `vfs_lock` and never `vfs_meta`, with the engine's spelling; on
  SQLite, the tables an overwrite, an edit, an attributed write and a
  grep touch never include the locked table; the SQL Server race test
  that hung now completes (`tests/storage/database/test_topology.py`,
  `tests/storage/database/test_races.py`).
- A follow-on decided separately, not here: carry the compile's opened
  revision on the resolution and stamp that, so the mint issues no read
  at all. It saves one statement per body-replacing write but changes
  what the stamp means for system-actor writes.
