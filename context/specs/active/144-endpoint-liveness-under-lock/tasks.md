# 144 — tasks

## Slice A — the lock

- [ ] A1 `edges.py`: `_endpoint_ids` gains `for_update: bool = False`
      (`with_for_update()` per chunk); `mkedge_rows` passes True,
      `rmedge_rows` stays plain; docstring true-ups (module lifetime
      paragraph, `mkedge_rows` arbitration paragraph).
- [ ] A2 Deadlock pin: confirm all four engines' deadlock codes sit
      in the retryable tables (`dialects.py`); comment at the lock
      site.
- [ ] A3 The staged-race pin in `test_edges.py`: rival delete
      launched as a task at `"mkedge:before-insert"`, asserted
      blocked inside the window, converged after commit (cascade
      removed the edge, mirror invariant holds). Red-first against
      the unlocked resolve on a real engine.
- [ ] A4 Gate: `scripts/ci.sh 3.13` green at 100 %.

## Slice B — the reclaim

- [ ] B1 `collect_edge_drift`: entry scan carries `path`; authored
      rows touching trashed ids recorded in
      `EdgeRebuildState.strays` (fs rows exempt).
- [ ] B2 `repair_edge_drift`: guarded reclaim — endpoint rows locked,
      trashed-ness re-checked, rival restore wins by skip; the
      stray-reclaim warning beside `_dangling_warning`.
- [ ] B3 Tests: row-layer stray injected and reclaimed with the
      warning; the restore-between-collect-and-repair guard arm.
- [ ] B4 Gate: `scripts/ci.sh 3.13` green at 100 %.

## Slice C — legs, scale, landing

- [ ] C1 The race pin's engine-leg twin in `test_races.py`; all four
      `db_test` legs green.
- [ ] C2 The 10k-edge scale row re-verified under locks on every
      leg; the MSSQL lock-escalation observation recorded.
- [ ] C3 Full matrix `scripts/ci.sh`.
- [ ] C4 Landing note (spec 143's race follow-up discharged by
      reference); ADR 018 amendment note recorded at the mining
      pass; archive.
