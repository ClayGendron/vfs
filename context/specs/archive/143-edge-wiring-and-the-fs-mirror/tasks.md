# 143 — tasks

## Slice A — schema and model

- [x] A1 `models/rows.py`: `provenance` column (String(16), NOT NULL,
      no default) on `edges`; `EdgeProvenance` literal beside the
      table; `EDGE_ROW_ONLY_COLUMNS` + `"provenance"`;
      `SCHEMA_FORMAT_VERSION` 9 → 10; the single-parent filtered
      unique index gated to sqlite/postgresql/mssql (`ddl_if` +
      dialect `where` kwargs, falling back to conditional attach if
      they don't compose).
- [x] A2 `models/edge.py`: `version` field and clause deleted; the
      `"fs"` reserved-type refusal added; docstring true-up.
- [x] A3 `models/entry.py`: `edge_target: Path | None` mirror on
      `Observation`; `OBSERVATION_MIRROR_OWNERS` row; lockstep drift
      test updated.
- [x] A4 Model/schema tests: refusal rows for `"fs"` and the dropped
      `version`; column and index emission checks; every existing
      test touching `Edge.version` re-pointed.
- [x] A5 Gate: `scripts/ci.sh 3.13` green.

## Slice B — the mirror, the cascade, re-convergence

- [x] B1 `storage/backends/database/edges.py`: `insert_fs_rows`,
      `repoint_fs_row`, `delete_edges_touching` (both directions,
      chunked), `collect_edge_drift` / `repair_edge_drift` in the
      `segments.py` shape with warning-severity drift records.
- [x] B2 Minting sites: write/mkdir (`_insert_creates`, confirming
      mkdir converges there), move repoint + copy mint
      (`transfer_rows`), trash cascade (`delete_rows`), restore
      re-mint (`restore_rows`); purge already deletes — pinned, kept.
- [x] B3 Re-convergence wired into `backend.py:_reindex_phases`
      before `chunk_dirty`.
- [x] B4 `tests/storage/database/test_edges.py`: the mirror battery
      (every mutating verb + seeded randomized sequence; exactly one
      fs in-edge per live non-root entry matching `parent_id`; zero
      edge rows touching trashed ids), drift-injection repair tests.
- [x] B5 Gate: `scripts/ci.sh 3.13` green at 100 %.

## Slice C — the caller pair

- [x] C1 `ops.py`: `"rmedge"` in `Op` and `MUTATING_OPS`. `params.py`:
      rows for both verbs.
- [x] C2 `base.py`: batch `mkedge` (`edges` XOR triple sugar,
      `provenance` = `system`, per-edge gates, per-mount grouping);
      `rmedge` same skeleton minus payload params.
- [x] C3 `protocol.py`: `SupportsMutation.mkedge` batch signature +
      `rmedge`.
- [x] C4 `backend.py`: stub and `withheld` carve-out deleted; routes
      to `edges.py`. `edges.py`: endpoint resolution (chunked,
      live-only), triple probe (`source_id IN` + client pair filter),
      create/touch partition through `bulk_insert` + executemany
      UPDATE, arbitration race handling per profile mode; `rmedge`
      chunked delete with removed/`not_found` partition.
- [x] C5 Reporting: per-edge `Observation` (`path`=source,
      `edge_target`, `edge_type`, `status`); default projection.
- [x] C6 Verb tests: gate refusals (cross-mount, `"fs"`, `extracted`,
      batch duplicate, XOR), statuses, permission-gate both endpoints,
      capability derivation (`mkedge` served, `rmedge` present,
      carve-out gone).
- [x] C7 Gate: `scripts/ci.sh 3.13` green at 100 %.

## Slice D — legs and scale

- [x] D1 Conformance rows: statuses, trash-cascade, restore-re-mint,
      no-edges-on-trashed, arbitration race, single-parent refusal
      where the index is emitted.
- [x] D2 Scale row: 10,000-edge `mkedge` batch in one call, statements
      bounded by the declared budgets.
- [x] D3 Full matrix `scripts/ci.sh`; `db_test` engine legs.
- [ ] D4 Landing note; `STATUS.md`; ADR 013/018 amendment notes;
      archive the folder.
