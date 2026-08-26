# Study — set-based topology statements (specs 080 and 102)

Executed 2026-08-25 on the five Docker engines (`docker/compose.test.yml`,
including the `mariadb` profile added for this study). Memos:
`../../2026-08-25-mysql-family-batch-update-shapes.md` (spec 080) and
`../../2026-08-25-set-based-scattered-delete.md` (spec 102).

- `common.py` — minted-namespace harness, corpus builder, per-statement profiler.
- `mysql_update_shapes.py` — spec 080: rowcount semantics, three guarded
  batch-UPDATE shapes timed at 1k/10k, mismatch attribution, both family members.
- `profile_scattered_delete.py` — spec 102 Q1/Q4: the live delete arm profiled
  with a rival move measuring the lock hold.
- `prototype_set_based_delete.py` — spec 102 Q2–Q4: the set-based prototype in
  a sibling namespace, a parity referee over both end states, EXPLAIN on Postgres.
- `mssql_snapshot_fetch.py` — the MSSQL residual: IN-list vs VALUES-join snapshot fetch.
- `results/*.json` — every run's numbers, statement profiles, and plans.

Rerun: `export VFS_TEST_<ENGINE>_URL=...` for any subset of engines, then
`uv run python <script> 1000 10000` from this directory.
