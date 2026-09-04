# 143 — plan

## Approach

Slices land in spec order: schema and model (A), the mirror and the
cascade (B), the caller pair (C), legs and scale (D). Each slice leaves
the tree green. There is one implementation to write — `InMemoryStorage`
is `DatabaseStorage` over `:memory:` (ADR 028) — and one new backend
module, `storage/backends/database/edges.py`, owns everything
edge-shaped: fs-row minting helpers, the `mkedge`/`rmedge` row
implementation, and re-convergence. The battery is written first, like
`test_segments.py` was: it goes red against the missing mirror, then
each minting site turns its arm green.

## §1 Schema and model (slice A)

`models/rows.py`:

- `edges` gains `provenance` (`_string(16)`, NOT NULL, **no server
  default** — a mint site that forgets it fails loudly at insert
  instead of silently defaulting). `EdgeProvenance` (`Literal["user",
  "agent", "system", "extracted"]`) joins the module constants beside
  the table; `EDGE_ROW_ONLY_COLUMNS` (line 96) grows by `"provenance"`.
- `SCHEMA_FORMAT_VERSION` 9 → 10 (line 126). Old stores stay refused
  at connect (`engine.py:497`); no migration path.
- The single-parent index:
  `Index(..., "target_id", unique=True)` with the dialect `where`
  kwargs (`sqlite_where` / `postgresql_where` / `mssql_where` on
  `edge_type = 'fs'`) **and** `.ddl_if(dialect=("sqlite",
  "postgresql", "mssql"))` so it is not emitted at all elsewhere — a
  plain unique index on `target_id` alone would be wrong on MariaDB
  and Oracle, whose floor is the battery. Confirm at implementation
  that `ddl_if` and the `where` kwargs compose on create_all across
  the three engines; if not, fall back to the `_attach_pgvector_ddl`
  conditional-attach precedent (rows.py:458).

`models/edge.py`: delete `version` and its validator clause; add the
reserved-type refusal (`edge_type == "fs"` → ValueError naming it
reserved); docstring true-up — edges are caller-authored *except* the
fs family, and the stale "wiring spec adds the column" sentence dies.

`models/entry.py`: `Observation` gains `edge_target: Path | None` in
the mirror block (mirrors `Edge.target`; `OBSERVATION_MIRROR_OWNERS`
and the lockstep drift test update). The existing `edge_*` trio plus
this field is how §3's rows report.

## §2 The mirror, the cascade, re-convergence (slice B)

New `storage/backends/database/edges.py`, the one owner. Helpers:
`insert_fs_rows(session, tables, pairs)` (one `bulk_insert`, rows
carry `provenance="system"`), `repoint_fs_row` (id-keyed UPDATE),
`delete_edges_touching(session, tables, ids)` (both directions,
chunked under `membership_budget` — the `_purge_subtree` shape at
`topology.py:585-586`).

Minting sites, each inside the verb's existing transaction:

- **write/mkdir** — where created rows' ids are known
  (`writes.py:340` `_insert_creates`, including the `parents=True`
  minted chain; confirm at implementation that mkdir's path converges
  there, else add the same call at `mkdir_rows`). One `bulk_insert` of
  `(parent_id → id)` rows per commit.
- **move/copy** — `transfer_rows` (`topology.py:404`): move repoints
  the one moved root's fs row (descendants keyed on ids, untouched);
  copy bulk-inserts fs rows for the minted ids (`_PendingTransfer`'s
  `created` rows). Authored edges are never copied — existing
  contract, now pinned.
- **delete (trash)** — `delete_rows` (`topology.py:159`): after the
  subtree's ids are claimed, `delete_edges_touching(ids)` — every
  provenance, both directions. The edge graph covers live entries
  only.
- **restore** — `restore_rows` (`topology.py:267`): re-mint fs rows
  for the restored subtree from `parent_id`; authored edges stay gone
  (spec pin 6's documented consequence).
- **sweep/purge** — already deletes (`_purge_subtree`); keep as the
  belt-and-suspenders arm.

Re-convergence: `collect_edge_drift` / `repair_edge_drift` in
`edges.py`, mirroring `segments.py:162/187` — collect is a plain read
diffing live entries' `(id, parent_id)` against fs rows (missing /
orphaned / mispointed, plus any edge row touching a trashed id);
repair is id-keyed guarded statements; every delta becomes a
warning-severity `ResultError` in the segments `_drift_warning`
shape. Wired as a step in `backend.py:_reindex_phases` (line 728)
before `chunk_dirty`, off the gram epoch, with the lease beat the
phase driver already provides.

Battery: `tests/storage/database/test_edges.py` in the
`test_segments.py` mold — the mirror battery over every mutating verb
plus a seeded randomized sequence, asserting after each step: exactly
one fs in-edge per live non-root entry, matching `parent_id`; zero
edge rows touching trashed ids. Drift-injection tests hand-break rows
and assert reindex repairs and warns.

## §3 The caller pair (slice C)

- `ops.py`: `"rmedge"` into the `Op` literal and `MUTATING_OPS`.
- `params.py`: `ParamSpec` rows for both verbs (`edges`, the
  triple-sugar params, `weight`/`distance`, `provenance` on mkedge
  only, `user_id`).
- `base.py`: rewrite `mkedge` (953–1014) to the `write` shape —
  `edges: Sequence[Edge] | None` XOR the triple sugar (the gate
  constructs one `Edge`), `provenance: Literal["user", "agent",
  "system"] = "system"` (`extracted` unreachable by construction; a
  string form arriving via MCP later classifies `invalid`). Per edge:
  resolve both endpoints, per-edge cross-mount refusal, permission
  gate at both paths; batch groups per mount and dispatches once per
  binding, the write-batch routing. `rmedge` is the same skeleton
  minus `provenance`/`weight`/`distance`. Duplicate identity within a
  batch refuses `invalid` at the gate (pin 2).
- `protocol.py` `SupportsMutation`: `mkedge(*, edges: list[Edge],
  provenance: str, user_id)` and `rmedge(*, edges: list[Edge],
  user_id)` — storage receives validated, mount-relative models only.
- `backend.py`: the stub (line 644) and the `withheld = {"mkedge"}`
  carve-out (line 196) die; both verbs route to `edges.py`.
- `edges.py` verb rows: resolve the batch's distinct endpoint paths →
  live ids in chunks under `membership_budget` (missing or trashed →
  per-row `not_found`); probe existing triples by `source_id IN
  (chunk)` and filter the pairs client-side (tuple-IN varies by
  dialect; the client filter is bounded by the batch's own size);
  partition into creates and touches. Creates go through
  `bulk_insert`; touches are one executemany UPDATE setting `weight`,
  `distance`, `provenance`. A concurrent duplicate: on `upsert`
  profiles the create arm uses the dialect's native insert (the
  `_upsert_constructor` shape, writes.py:987, edges edition) so a race
  lands as the update; on `catch_retry` profiles an `IntegrityError`
  reclassifies that row as a touch and redrives. `rmedge` deletes by
  id triple in chunks; rowcount partitions removed vs `not_found`.
- Reporting: one `Observation` per edge — `path` = source,
  `edge_target`, `edge_type`, `edge_weight`/`edge_distance`, `status`
  (`created`/`updated`; rmedge uses `deleted`). Default projection
  `path, edge_target, edge_type, status`.

## §4 Legs and scale (slice D)

Conformance rows on every leg: per-row statuses for touch/remove;
trash-cascade; restore-re-mint; no-edges-on-trashed; the arbitration
race per mode; the single-parent index refusing a second fs in-edge
where emitted. The 10k-edge batch scale row asserts one call, every
statement chunked under the declared budgets (the existing
statement-count assertion pattern). Then `db_test` on all engine legs.

## Trade-offs

- **Probe-partition (two statement families) over blind upsert
  (one):** portable `created` vs `updated` reporting needs to know
  what existed — RETURNING/rowcount semantics diverge across the five
  engines. The probe is chunked and costs one read per batch; races
  are reclassified by the arbitration mode, so the report stays
  truthful under concurrency.
- **No server default on `provenance`:** a forgotten mint site is a
  loud IntegrityError, not a silently mislabeled row.
- **`ddl_if`-gated filtered index:** emitting a partial index only
  where the engine has one keeps MariaDB/Oracle from getting a wrong
  full-unique index; their guarantee is the battery, exactly ADR
  018's stated floor.
- **`edge_target` as a real Observation mirror** rather than an extras
  blob: the lockstep drift test keeps the row shape honest, and the
  renderer's column machinery works unchanged.

## Verification

1. Battery first (`test_edges.py` red), minting sites land arm by arm
   (green), drift injection proves re-convergence repairs and warns.
2. `scripts/ci.sh 3.13` per slice; the full matrix before push.
3. `db_test` legs at slices B and D (the mirror and the verbs are
   storage behavior; the schema and index shapes differ per engine).
4. The 10k-edge scale row and the arbitration race rows on the real
   engines.
5. Landing checks from the spec: no classified stubs remain; specs
   136/138 dependency lines satisfied; `Edge` docstring and the
   ADR 013/018 amendment notes true in the tree.
