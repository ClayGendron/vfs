# 144 — tasks

Resumed 2026-09-04: the MSSQL finding is resolved (spec.md *Resolved on
resume*) — `dialects.lock_rows` spells the guard read from the
profile's `row_lock_hint` (`UPDLOCK` on SQL Server); every engine leg is
green on the race pin, the storm, and the 10k batch.

## Research gate — resolved, see spec.md *Resolved on resume*

- [x] R1 `UPDLOCK` alone: one KEY U lock per row, held to commit,
      blocks the rival delete under locking RC and RCSI alike;
      `HOLDLOCK` only adds range locks.
- [x] R2 No escalation at key granularity (40k KEY locks, 2.0 s for
      20k rows); the pre-existing `IN`-list scan past ~1k elements is
      what escalates, recorded as a follow-up, never a limit.
- [x] R3 `DialectProfile.row_lock_hint` + `lock_rows(stmt, table,
      profile)`; the mkedge resolve and both reindex repair guards
      route through it (they were no-ops on MSSQL).
- [x] R4 The mkedge-vs-delete storm pin on all four legs: only lawful
      race kinds, zero strays after every round.

## Slice A — the lock

- [x] A1 `edges.py`: `_endpoint_ids` takes `lock=profile`;
      `mkedge_rows` passes it, `rmedge_rows` stays plain; docstring
      true-ups; `segments.py`/`edges.py` repair guards through
      `lock_rows`.
- [x] A2 Deadlock pin: all four engines' deadlock codes confirmed in
      the retryable tables (`dialects.py`); comment at the lock site.
- [x] A3 The staged-race pin: `test_edges.py::TestEndpointLocks`
      (sqlite) and its engine-leg twin
      `test_races.py::TestMkedgeEndpointLocks` — green on all four.
- [x] A4 `test_dialects.py::TestLockRows` pins the rendering per
      dialect (FOR UPDATE, the hint, nothing on sqlite, no leak, the
      floor).

## Slice B — the reclaim

- [x] B1 `collect_edge_drift`: entry scan carries `path`; authored
      rows touching trashed ids recorded in `EdgeRebuildState.strays`.
- [x] B2 `repair_edge_drift`: guarded reclaim through `lock_rows`;
      rival restore wins by skip; `_stray_warning`.
- [x] B3 Tests: stray injected and reclaimed with the warning; the
      restore-between-collect-and-repair guard arm.

## Slice C — legs, scale, landing

- [x] C1 The race pin green on all four legs (2026-09-04).
- [x] C2 The 10k-edge batch re-verified under locks on every leg; the
      MSSQL escalation observation recorded (spec.md R2).
- [x] C3 `scripts/ci.sh 3.13` green at 100 % (2026-09-04); the full
      matrix runs before the push.
- [~] C4 Landing note written; the SQL Server membership-scan memo
      commissioned; ADR 018 amendment note and the archive move await
      Clay's go-ahead.
