# 144 — endpoint liveness under lock: closing the delete-vs-mkedge race

- **Status:** ready — drafted 2026-09-04 from the executed race study
  (the race is real on every client/server engine; restore resurrects
  the stray; the field closes it insert-side or not at all); Clay
  adopted the memo's recommendation in session the same day.
  Discharges the second recorded follow-up of spec 143's landing note.
- **Born from:** memo `../../../research/2026-09-04-delete-vs-mkedge-race.md`
  and its rerunnable study
  (`../../../research/studies/2026-09-04-delete-vs-mkedge-race/`);
  spec 143's landing review (the finding); ADR 018 pins 5–9 (the
  mirror and lifetime doctrine this completes).
- **Amends (record at the mining pass):** ADR 018 — the edge-lifetime
  law gains its enforcement clause: endpoint liveness is checked
  insert-side, under row locks, in the same transaction that inserts
  the edge; delete's cascade alone (the delete-side half) is proven
  insufficient by the staged race and by Oak's and gel's identical
  open windows.
- **Date:** 2026-09-04
- **Owner:** Clay Gendron
- **Kind:** two behavior changes in
  `storage/backends/database/edges.py` — the endpoint resolve locks
  its rows for `mkedge`, and reindex re-convergence reclaims authored
  edges touching trashed entries — plus the race pins, drift tests,
  and scale re-verification. No schema change, no verb-surface
  change, no new module.
- **Depends on:** spec 143 (the edge verbs, the mirror, the
  re-convergence pass — all live), the seam machinery
  (`storage/backends/database/seams.py`), the retryable-conflict
  classification (deadlocks already ride the retry channel), the
  `with_for_update()` guard shape (`repair_edge_drift`,
  `segments.py` — proven portable on all four engine legs).
- **Relates to:** spec 138 (the extractor writes edge rows at the row
  layer during reindex — it does not take the verb's locks, which is
  why arbitration stays; its rows are covered by the reindex reclaim
  instead), spec 136 (the in-degree signal is the first reader that
  would have consumed a stray), spec 067 (traversal — arrives to a
  table whose liveness invariant actually holds).

## Intent

Spec 143's landing review found, and the 2026-09-04 study proved on
all four client/server engines: a rival `delete` committing between
`mkedge`'s endpoint resolve and its insert leaves an authored edge
naming a trashed entry. Reindex is blind to it (the trashed entry
still has its row), and `restore` resurrects it as a live edge —
silently violating "restore never re-mints." The field's verdict is
clean: systems that enforce the reference only delete-side (Oak, gel)
leave exactly this window open; the systems that close it (juicefs,
Postgres's own FK machinery) both do it with an insert-side lock on
the referenced row. vfs already has the delete-side half — the
cascade. This spec adds the insert-side half, and extends reindex
re-convergence to reclaim any stray that reaches the table anyway.

## Decided semantics

1. **`mkedge` resolves its endpoints under row locks.** The endpoint
   resolve in `mkedge_rows` becomes a locking read
   (`with_for_update()` on the entry rows, the house guard shape),
   chunked under `membership_budget` with paths sorted, in the same
   transaction that probes and inserts. The lock is the liveness
   proof: a path that resolves under lock names a live entry that
   cannot be trashed before this transaction commits. A rival delete
   then serializes to one of two honest outcomes — it waits and its
   cascade removes the just-created edge (mkedge truthfully reported
   `created`; the endpoint died afterward), or it commits first and
   mkedge truthfully refuses `not_found`. No third state exists.
2. **`rmedge` takes no lock.** It only deletes. A rival endpoint
   delete cascading the same rows converges to the identical end
   state — the edge is gone either way — which is already `rmedge`'s
   documented arbitration posture. Adding locks there would buy
   nothing and cost hot-endpoint serialization on a read-mostly path.
3. **The lock is plain exclusive, everywhere.** `with_for_update()`
   with no dialect flourishes — the shape `repair_edge_drift` and the
   segment repair already run green on Postgres, MariaDB, SQL Server,
   and Oracle. The refinement the study surfaced — Postgres's
   `FOR KEY SHARE` is sufficient and shared, so concurrent `mkedge`
   batches naming one hot endpoint could avoid serializing against
   each other — is a recorded future direction, taken only if
   hot-endpoint contention measures as a real cost. Never a cap:
   correctness is identical either way.
4. **Deadlocks ride the existing retry channel.** Lock acquisition is
   chunked over sorted paths, so `mkedge` batches order consistently
   against each other. Against `delete`'s claim order a deadlock
   remains constructible; every engine's deadlock code is already
   classified retryable, and the write path's redrive discipline is
   the answer — a pin, not new machinery.
5. **Arbitration stays.** The savepoint redrive
   (`_insert_arbitrated`) remains: the verb's locks serialize
   verb-vs-verb duplicates, but row-layer writers — spec 138's
   extractor foremost — insert edge rows without the verb's locks,
   and the unique key remains the referee for that race.
6. **Reindex re-convergence reclaims trash-touching authored
   edges.** The collect pass learns each entry's liveness (the trash
   scope is a path fact it already streams past) and records any
   authored (non-`fs`) edge touching a trashed entry as drift; the
   repair pass deletes those rows under the same guard discipline as
   `FsDelta` — the entry row re-read locked, the delta applied only
   while the entry is still trashed, a rival restore's synchronous
   truth respected by skipping. Every reclaim surfaces as a
   warning-severity record: with pin 1 in place a stray means a
   mint-site bug, and it must surface. The fs mirror rows of trashed
   entries remain lawful — trash keeps its mirror; only authored
   rows are reclaimed.
7. **The invariant sharpens from aspiration to law.** "Zero authored
   edge rows touching trashed ids" is now enforced at both ends —
   prevented at insert, reclaimed at reindex — and the staged race
   from the study becomes a permanent pin in both commit orders.

## Scope

In: the locking resolve for `mkedge`, the deadlock-retryable pin, the
staged-race pins (seam-staged locally, natural-timing on the engine
legs), the reindex reclaim with its drift tests and restore-race
guard test, docstring true-ups in `edges.py`, scale re-verification
of the 10k-edge batch under locks (including observing and recording
SQL Server's lock-escalation behavior — a measurement, never a
designed limit). Out: any schema change; FK constraints (they cannot
express soft-delete liveness — the memo's gel section); share-lock
refinements (future direction, pin 3); restore-side edge sweeping
(redundant once insert-side prevention lands); the hub-probe cost
(spec 143's other follow-up — separate decision, needs the degree
study first).

## Slices

- **A — the lock**: the locking endpoint resolve in `mkedge_rows`
  (mkedge-only; `rmedge` keeps the plain read), the staged-race pin
  in both orders, the deadlock classification pin,
  `scripts/ci.sh 3.13` green at 100 %.
- **B — the reclaim**: liveness in `collect_edge_drift`, guarded
  reclaim in `repair_edge_drift`, the warning vocabulary, stray
  injection and restore-race guard tests, green again.
- **C — legs, scale, landing**: the race pins on all four engine
  legs (`test_races.py`), the 10k-edge batch re-verified under locks
  with the MSSQL escalation observation recorded, full matrix,
  landing note, archive.

## Landing criteria

- The staged race from the study, re-run against all four engines,
  produces no stray in either commit order: delete-first yields
  `not_found`, mkedge-first yields a created edge that the delete's
  cascade removes.
- An injected stray (row-layer insert of an authored edge touching a
  trashed id) is reclaimed by the next reindex with a loud warning; a
  restore racing the repair wins cleanly (the reclaim skips).
- The 10,000-edge `mkedge` batch still lands in one call on every
  engine leg; SQL Server's behavior at ~20k row locks is measured
  and recorded in the landing note, whatever it is.
- `scripts/ci.sh` full matrix green; all engine legs green;
  coverage 100 %.
- `edges.py`'s docstrings state the lock as the liveness proof and
  the reclaim as the backstop; spec 143's landing-note follow-up is
  discharged by reference to this spec.
