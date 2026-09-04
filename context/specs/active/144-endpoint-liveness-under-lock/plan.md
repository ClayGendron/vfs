# 144 — plan

## Approach

Two behavior changes, both inside
`storage/backends/database/edges.py`, landed as two green slices plus
a legs-and-landing slice. No schema change and no verb-surface change
means no model or router work at all: the lock is a one-predicate
change to a resolve that already exists, and the reclaim is one more
drift class in a collect/repair pass that already exists. The race
pin is written first, red against the unlocked resolve on a real
engine, exactly how the study's script fails today.

## §1 The lock (slice A)

`edges.py`:

- `_endpoint_ids(session, tables, membership_budget, edges)` gains a
  keyword `for_update: bool = False`. When set, each chunk's
  `SELECT path, entry_id WHERE path IN (...)` gains
  `.with_for_update()` — the exact guard shape of
  `repair_edge_drift` (edges.py:313) and the segment repair
  (segments.py:204), both already green on all four engine legs.
  Paths are already sorted before chunking; that stays, and is now
  load-bearing (consistent lock order between mkedge batches).
- `mkedge_rows` passes `for_update=True`; `rmedge_rows` does not — a
  deletion-only verb converges with a rival cascade to the same end
  state, so a lock there buys nothing (spec pin 2).
- Docstring true-ups: the module docstring's lifetime paragraph and
  `mkedge_rows`' arbitration paragraph state the lock as the
  liveness proof; the sentence claiming the redrive is the only
  concurrency answer narrows to the row-layer-writer case.

Deadlocks: no new machinery. Each dialect profile already classifies
its deadlock code retryable (verify the four codes at
implementation: PG 40P01, MariaDB 1213, MSSQL 1205, ORA-00060 — all
in `dialects.py`'s retry tables); the pin is a comment plus the
existing hot-row storm coverage in `test_races.py`.

The race pin, `tests/storage/database/test_edges.py` (and its
engine-leg twin in `test_races.py`):

- Stage exactly the study's interleaving: install a handler on
  `"mkedge:before-insert"` that *launches* the rival
  `storage_b.delete(path=target)` as an `asyncio.Task`, then asserts
  it does **not** complete within a short window
  (`asyncio.wait(..., timeout=)` — the lock must be holding it), and
  returns with the task still pending. The handler must not await
  the rival to completion — the rival cannot commit until `mkedge`
  does, and awaiting it inline would deadlock the loop, which is
  itself the property under test.
- After `mkedge` returns: await the rival, assert both verbs
  succeeded, assert the cascade removed the just-created edge (the
  authored set is empty, the target is trashed), and run the mirror
  battery's invariant helper. This is the mkedge-first order; the
  delete-first order is already the existing `not_found` refusal
  row.
- The pre-existing arbitration pin (`TestMkedgeArbitration`) stays
  untouched: its rival is a same-session raw insert, the row-layer
  race the lock cannot see (spec pin 5).

Gate: `scripts/ci.sh 3.13` green at 100 %.

## §2 The reclaim (slice B)

`edges.py`:

- `collect_edge_drift` already streams every entry row; the entry
  scan adds `entry.c.path`, and a trashed id is one whose path sits
  under `TRASH_ROOT` (`paths.py:46`, the constant `topology.py`
  already imports; never a re-derived literal). The
  edge scan then records any **authored** row touching a trashed id
  into a new `EdgeRebuildState.strays: dict[int, set[str]]` — edge
  row id → the endpoint ids that were trashed at collect. fs rows
  are exempt: trash lawfully keeps its mirror.
- `repair_edge_drift` locks the recorded endpoint ids in chunks
  (`with_for_update()`, the existing guard read — merge with the
  `FsDelta` guard fetch where the chunks overlap), re-checks
  trashed-ness from the locked rows' paths, and deletes exactly the
  stray rows at least one of whose recorded endpoints is **still
  trashed**. A rival restore that already brought every recorded
  endpoint back wins: the delta is skipped, the rival's synchronous
  truth respected — the `FsDelta` discipline verbatim.
- A reclaim surfaces as a warning-severity record beside
  `_dangling_warning` ("reclaimed N authored edge row(s) touching
  trashed entries"), because with slice A in place a stray is a
  mint-site bug surfacing.

Tests, beside the existing drift-injection rows in `test_edges.py`:
inject a stray at the row layer (raw insert of an authored edge
naming a trashed entry's id), reindex, assert the row is gone and
the warning fired; the guard arm — restore the endpoint between
collect and repair (the existing two-phase drift-test shape), assert
the reclaim skips and the restored edge set is untouched. Coverage
keeps both branches.

Gate: `scripts/ci.sh 3.13` green at 100 %.

## §3 Legs, scale, landing (slice C)

- The race pin's engine-leg twin runs on all four `db_test` legs
  (`test_races.py`, env-gated like its siblings).
- Re-run the 10k-edge scale row on every leg — the batch now takes
  up to ~20k row locks in one transaction. On SQL Server observe
  lock escalation (`sys.dm_tran_locks` during the run, or simply the
  before/after wall time) and record the observed behavior in the
  landing note as a measurement; if escalation serializes the table
  for the transaction's duration, that is a recorded scale profile
  with the share-lock refinement (spec pin 3) as its named future
  direction — never a designed limit.
- Full matrix `scripts/ci.sh`; landing note (discharging spec 143's
  recorded follow-up by reference); archive.

## Why this shape

- **Lock at the resolve, not a second verify read:** the resolve
  already touches exactly the rows that need locking; making that
  read locking is one predicate and zero extra round-trips, and the
  path-addressed `IN` list can only find live entries — so lock
  acquisition and liveness proof are the same statement.
- **Exclusive everywhere over clever-per-dialect:** the study proved
  Postgres's `FOR KEY SHARE` would suffice there, but the portable
  exclusive guard is already proven in-tree on all four engines, and
  hot-endpoint mkedge-vs-mkedge serialization is a cost no workload
  has yet measured. Refinement waits for a number.
- **rmedge unlocked on purpose:** its rival-convergence argument is
  already its documented arbitration posture; symmetry for
  symmetry's sake would put locks on the one edge verb that cannot
  create a stray.
- **The reclaim lands even though the lock closes the race:** the
  extractor (spec 138) and any future row-layer writer mint edges
  without the verb's locks, and the segment pass won this exact
  argument — re-convergence is the backstop for the maintenance
  bug nobody has written yet, and it turns the conformance
  invariant from "true if every writer is correct" into "true".

## Verification

1. The race pin red-first against the unlocked resolve (the study's
   script shape), then green under the lock, on at least one real
   engine before slice A closes.
2. `scripts/ci.sh 3.13` per slice; the full matrix and all four
   `db_test` legs at slice C.
3. The 10k-edge scale row on every leg, with the MSSQL escalation
   observation recorded whatever it shows.
4. Landing checks: both landing-note follow-ups of spec 143 are
   accounted for (the race one discharged here; the hub-probe one
   explicitly left to its own study), and the `edges.py` docstrings
   are true.
