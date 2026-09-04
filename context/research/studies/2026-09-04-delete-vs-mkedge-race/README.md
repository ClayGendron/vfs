# Study: the delete-vs-mkedge race, staged on five engines

Companion to the memo `../../2026-09-04-delete-vs-mkedge-race.md`.

`race_experiment.py` stages the race deterministically: storage A
freezes at the `mkedge:before-insert` seam, a handler drives a genuine
rival `delete` of the target endpoint through storage B (same table
namespace, its own connections) to commit, then A's insert resumes.
The script then checks whether the stray authored edge exists, whether
`reindex` reclaims it, and what `restore` resurrects. A second probe
(Postgres only) holds `FOR KEY SHARE` / `FOR UPDATE` on the target's
entry row and measures whether the rival delete blocks.

Rerun (engines up via `docker/compose.test.yml`, the four
`VFS_TEST_<ENGINE>_URL` vars exported):

    uv run python race_experiment.py

Result on 2026-09-04 (tree at `65646e5`): the stray lands on all four
client/server engines, survives reindex with zero warnings, and comes
back live after restore; sqlite is immune (the rival delete loses as a
retryable conflict against the single writer). Both Postgres lock
flavors block the rival delete — trash rewrites `path`, a unique key,
so even `FOR KEY SHARE` conflicts.

## Follow-up probes (2026-09-04, spec 144 slice A, tree at `c3903d7`+)

`mssql_lock_probe.py` (`--rcsi` also runs the arms on a database with
READ_COMMITTED_SNAPSHOT on): SQLAlchemy renders `with_for_update()` as a
bare SELECT on the T-SQL compiler, so the lock is silently dropped there.
Each hint arm holds the resolve in session A, launches a rival `delete`
through session B, and reports whether it blocks (3 s), plus the locks
`sys.dm_tran_locks` shows for A:

| arm | rival delete | locks held |
|---|---|---|
| plain `with_for_update()` | proceeds | none |
| `WITH (UPDLOCK)` | blocks | 1 KEY U |
| `WITH (UPDLOCK, HOLDLOCK)` | blocks | 3 KEY RangeS-U |
| `WITH (UPDLOCK, ROWLOCK)` | blocks | 1 KEY U |
| `WITH (REPEATABLEREAD)` | blocks | 1 KEY S (the `FOR KEY SHARE` analogue) |

Identical under locking READ COMMITTED (`master`) and under RCSI.
`UPDLOCK` alone is the minimal correct spelling; it is what the MSSQL
profile declares as `row_lock_hint`.

`mssql_lock_scale_probe.py`: one statement locking an `IN`-list of
paths on a 20,000-row entry table, by list size, then the whole 20k in
one transaction at chunk 500. The plan seeks (2 KEY U locks per row:
the path index key and the clustered key) up to 1,024 elements and
flips to a clustered index scan by 1,500 — the scan takes U locks on
every row and escalates to a table X lock (4–6 s per statement). At
the seeking chunk size the full 20k locks in 2.0 s, peaks at 40,000
KEY U locks, and never escalates. The binds arrive as `nvarchar` and
the column is `varchar` (UTF-8 BIN2), so every plan carries a
`CONVERT_IMPLICIT`; the scan flip is the pre-existing shape of every
chunked membership read on MSSQL, not something the lock introduces.
