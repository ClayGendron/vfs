# 143 — edge wiring: batch `mkedge`/`rmedge`, the materialized fs mirror, and edge provenance

- **Status:** landed 2026-09-04 (landing note below; **the pin-5 trash
  refinement decided while landing**: the fs mirror follows
  `parent_id` uniformly — into trash and back out — so a trashed root
  repoints to its bucket and restore repoints again, never re-mints;
  the header's "restore re-mints fs rows" phrasing below is superseded
  by that uniform law) — drafted 2026-08-27; the four forks ruled by
  Clay the same day (provenance vocabulary `user`/`agent`/`system`/
  `extracted`; edges deleted only by `rmedge` or endpoint deletion,
  soft delete included; no edge versions; the re-convergence phase
  ships; the provenance parameter and fs rows both default `system`).
  Prerequisite of specs 136 and 138: it makes the `edges`
  table real — the last classified stub in the database backend falls
  with it.
- **Born from:** ADR 018 (pins 1–8; pin 9's deferrals settled here);
  memo `../../../research/2026-07-19-edge-authoring-api.md`; spec 138
  §3 (the provenance requirement, routed here because it touches the
  table schema); Clay's 2026-08-27 fork rulings.
- **Amends (record at the mining pass):** ADR 018 pin 2 (no per-edge
  version — the touch updates payload only), pin 5 (trash no longer
  rides move logic on the mirror: soft delete cascades edges, restore
  re-mints fs rows), pin 9 (fate resolved: deletion-cascade at soft
  delete, not sweep); ADR 013's per-edge version clause (dropped —
  `Edge.version` leaves the model).
- **Date:** 2026-08-27
- **Owner:** Clay Gendron
- **Kind:** schema format bump (9 → 10: `provenance` on `edges`,
  single-parent hardening where the engine supports it), the `Edge`
  model true-up (reserved-type refusal in, `version` out), fs-edge
  minting in every namespace-mutating transaction, edge cascade at
  soft delete, a reindex re-convergence phase, the batch caller pair
  in `base.py` (`mkedge` rewritten, `rmedge` new), the backend
  implementation replacing the stub.
- **Depends on:** the `edges` table (`models/rows.py` — live, close to
  final), `bulk_insert` (ADR 056 / spec 139), the dialect arbitration
  modes and `membership_budget` (`dialects.py`), the segments
  re-convergence pattern (spec 104, `segments.py`), the trash arc
  (ADRs 014/027 — delete trashes, sweep is the only destroyer).
- **Relates to:** spec 136 (reads these rows at reindex), spec 138
  (writes `extracted` rows at reindex), spec 067 and ADR 016 pin 4
  (the read-side verb surface — deferred again here, not owned),
  spec 070 (verified principals later replace declared provenance),
  the dirent end-state parked in `../../open-questions.md`.

## Intent

ADR 018 decided how edges are authored; nothing implements it. `mkedge`
is a pre-ADR single-triple verb routing to a classified stub, `rmedge`
does not exist, and no verb mints the fs hierarchy mirror. This spec
lands pins 1–8 against the database backend, settles pin 9 by Clay's
ruling, and adds the one post-ADR fact: a provenance column so
spec 138's extracted edges and authored edges share the table without
either ever deleting the other.

## Decided semantics

1. **Schema, format 9 → 10.** `edges` gains `provenance` (String(16),
   NOT NULL: `user` | `agent` | `system` | `extracted`). No `version`
   column — edges carry no per-edge monotone value (Clay, 2026-08-27),
   and `Edge.version` leaves the model. The unique key stays the id
   triple `(source_id, target_id, edge_type)`; provenance is a fact
   about a row, never part of its identity. Single-parent hardening —
   a unique index on `(target_id)` filtered to `edge_type = 'fs'` — is
   emitted where the engine has partial/filtered indexes (SQLite,
   Postgres, SQL Server); everywhere else the portable floor is the
   pin-7 invariant test, per ADR 018. `EDGE_ROW_ONLY_COLUMNS` grows by
   `provenance` (the model never carries it).
2. **Provenance names the author class.** `user` is a human caller,
   `agent` an AI caller, `system` the admin/storage plane, `extracted`
   the reindex extractor (spec 138). `mkedge` takes a declared
   `provenance` parameter restricted to `user`/`agent`/`system` —
   `extracted` is refused at the gate, reserved to the extractor's
   row-layer writes — and stores it verbatim; verified principals
   (spec 070) later replace self-declaration. The parameter's default
   is **`system`** and storage-minted fs rows carry **`system`**
   (Clay, 2026-08-27); callers on the agent/user surfaces declare
   themselves explicitly. The extractor's wholesale replace deletes
   only `provenance = 'extracted'` rows and inserts-if-absent (an
   existing authored row wins and is left untouched). `rmedge` removes
   whatever matches the triple regardless of provenance — with the
   documented wrinkle that a removed `extracted` edge returns at the
   next reindex if the reference still exists.
3. **The caller pair** (ADR 018 pins 1–4, implemented as decided).
   `mkedge(edges: Sequence[Edge])` with the
   `source`/`target`/`edge_type` triple as sugar constructing one
   `Edge` at the gate, mutually exclusive with the batch form — the
   house `write` shape. `rmedge` mirrors it, removing by exact triple.
   `rmedge` joins the `Op` vocabulary and `MUTATING_OPS`; both verbs
   permission-gate at both endpoint paths per edge, refuse a
   cross-mount pair per edge (`cross_mount`), and route a batch grouped
   per mount exactly as `write` batches route by path. A duplicate
   identity within one batch is `invalid` (pin 2). Per-row statuses:
   `created`/`updated` on `mkedge`, removed/`not_found` on `rmedge`.
   The `withheld = {"mkedge"}` carve-out in the backend's capability
   derivation dies; the mutation family is served whole.
4. **Touch at the backend, bounded at 10k+.** Endpoint paths resolve
   to live entry ids in chunks under `membership_budget` (a missing or
   trashed endpoint is that row's `not_found`). Existing triples are
   probed the same way; the batch partitions into creates and touches —
   creates through `bulk_insert`, touches as one executemany `UPDATE`
   refreshing the payload (`weight`, `distance`, `provenance`). A
   concurrent duplicate lands as `updated`, arbitrated by the unique
   constraint through the profile's arbitration mode (`upsert` |
   `catch_retry`), the write pipeline's existing discipline. No
   statement grows with batch size.
5. **The fs mirror** (ADR 018 pins 5–7, trash handling amended).
   `"fs"` is refused at the public gate *and* in the `Edge` model's
   validator (a new clause — today the model allows it); storage mints
   fs rows at the row layer, never through the model. Minting sites,
   all inside the mutating verb's own transaction: `write`/`mkdir`
   (including a `parents=True` chain) insert one `(parent → entry)`
   row per new entry as one more `bulk_insert`; `move` updates the one
   moved row's `source_id` (id-keyed — descendants untouched); `copy`
   mints fs rows for the new ids (authored edges are still never
   copied — the existing `topology.py` contract stands); `restore`
   re-mints the restored subtree's fs rows from `parent_id`. fs rows:
   `weight`/`distance` NULL, `provenance = 'system'`. `parent_id`
   remains authoritative; no reader unions the two stores.
6. **Edge lifetime** (pin 9, ruled by Clay 2026-08-27). An edge is
   deleted in exactly two ways: `rmedge` removes it by triple, or an
   endpoint entry is deleted — **soft delete included**. `delete`
   (trash) cascades: the trashed subtree's edge rows, every provenance,
   both directions, are removed in the same transaction, chunked by
   the id budgets. The edge graph therefore covers live entries only —
   traversal and spec 136's centrality walk never see trash. `restore`
   brings entries back with fs rows re-minted from `parent_id`
   (authoritative) but authored edges gone — a documented consequence,
   not a bug; `extracted` edges return at the next reindex. `sweep`'s
   existing endpoint-id delete (`topology.py:585-586`) stays as the
   purge-path arm and as belt-and-suspenders.
7. **The mirror is invariant-tested** (ADR 018 pin 8). A conformance
   battery pins, after every mutating verb the suite exercises: every
   live non-root entry has exactly one fs in-edge matching its
   `parent_id`; no trashed entry has any edge row; drift is a loud
   failure.
8. **Re-convergence, the repair arm.** A reindex phase in the
   `segments.py` shape: collect drift by comparing `parent_id` against
   the fs rows (a plain read), repair under guards keyed on the id
   (insert the missing, delete the orphaned, re-point the wrong),
   report drift as loud warnings on the verb `Result`. Off the gram
   epoch, in-place. In-transaction minting means drift should never
   occur; this phase is what makes pin 7's invariant self-healing when
   a bug proves otherwise. Old-format stores stay refused at connect
   (`engine.py`'s posture) — there is no in-place migration story and
   greenfield needs none.
9. **Deferred, again and explicitly:** the read-side verb
   (`edges(path, direction, type)` — ADR 016 pin 4, spec 067's
   territory), cross-mount edges, filter-based bulk clearing
   (ADR 018 pin 3's guardrailed later verb), the dirent end-state,
   verified principals as the provenance source (spec 070).

## Scope

In: the schema bump, the model true-up (reserved-type refusal in,
`version` out, docstring trued — edges are caller-authored *except*
the fs family), the fs mirror in every mutating verb, the soft-delete
cascade, the re-convergence phase, batch `mkedge`/`rmedge` end to end,
the pin-7 invariant battery, scale rows. Out: the extractor (138), the
signals consumer (136), the read-side verb and graph traversal (067),
any MCP surface change beyond the ops vocabulary.

## Slices

- **A — schema and model**: format 10, the `provenance` column, the
  filtered single-parent index where supported, `Edge` refuses `"fs"`
  and drops `version`, row/model constant true-ups, schema conformance
  rows.
- **B — the fs mirror and the cascade**: minting in
  `writes.py`/`topology.py` per the pin-5 matrix, the soft-delete
  cascade and restore re-mint, the invariant battery (pin 7), the
  re-convergence phase with drift-injection tests.
- **C — the caller pair**: `base.py` batch `mkedge` + new `rmedge`
  with the `provenance` parameter, `ops.py` vocabulary and gate
  tables, the `SupportsMutation` protocol change, the backend
  probe/partition/insert/touch implementation, the capability
  derivation cleanup, per-row status conformance rows.
- **D — legs and scale**: the battery and the touch/remove rows on
  every engine leg; the 10k-edge batch scale row (one call, statements
  chunked under the declared budgets); trash-cascade, restore-re-mint,
  and no-edges-on-trashed rows; the arbitration race row per mode.

## Landing criteria

- `scripts/ci.sh 3.13` green; the full matrix before push; all engine
  legs green with the invariant battery live.
- The pin-7 invariant holds after every mutating verb on every leg;
  drift injected by hand is repaired by the re-convergence phase and
  reported loudly.
- A 10,000-edge `mkedge` batch lands in one call with every statement
  bounded by the dialect budgets; per-row statuses correct throughout.
- Trashing a subtree leaves it with zero edge rows; restoring it
  yields exactly the fs rows `parent_id` implies and no authored rows.
- The backend has no classified stubs; specs 136 and 138 list nothing
  unmet in their dependency lines.
- `Edge`'s docstring, the ADR 018 amendments listed above, and the
  "committed to" items are true in the tree.

## Landing note (2026-09-04)

The edges table is real and the last classified stub is gone.

**Landed**

- Schema format 9 → 10: `provenance` on `edges` (String(16), NOT NULL,
  no default — a forgetful mint site fails loudly), the filtered
  single-parent unique index `(target_id) WHERE edge_type = 'fs'`
  emitted on sqlite/postgresql/mssql via `ddl_if`; MariaDB and Oracle
  hold the invariant through the conformance battery, ADR 018's stated
  floor.
- `Edge` trued: the reserved `"fs"` type refuses at the model,
  `version` is gone (no `edges.version` column will exist — the touch
  refreshes `weight`/`distance`/`provenance` only).
- The fs mirror (`storage/backends/database/edges.py`): minted beside
  segment postings on every create (write, mkdir, the trash-chain
  mint, copy's fresh ids), repointed id-keyed on move — and uniformly
  on trash and restore, which ride the same shape. `parent_id` stays
  authoritative.
- The cascade: soft delete removes the trashed subtree's authored
  edges in both directions inside the delete transaction; restore
  brings entries back with authored edges gone, by design; purge
  already deleted every edge touching a destroyed id and still does.
- Reindex re-convergence: `collect_edge_drift`/`repair_edge_drift` in
  the segment pass's collect/guarded-repair shape, sharing the new
  `_reconverge` skeleton in `backend.py`; repairs surface as
  warning-severity records, dangling rows (an endpoint with no entry
  row) are reclaimed in the same pass.
- The caller pair: batch-native `mkedge` (touch/upsert, per-row
  `created`/`updated`, `provenance` gated to `user`/`agent`/`system` —
  `extracted` is reserved to the reindex extractor) and the new
  `rmedge` (removal by exact triple, absent rows are per-row
  warning-severity `not_found`), both with the sugar triple form,
  duplicate-identity-in-batch refusal, both endpoints
  permission-gated, cross-mount refused. Arbitration: a racing
  duplicate create redrives row-by-row under savepoints and lands as
  the touch it raced (seam-pinned).
- `Observation.edge_target` as a real mirror field, rebased alongside
  `path`/`trash_path`; `rmedge` renders as "Disconnected".

**Recorded follow-ups** (review pass at landing, 2026-09-04)

- `_existing_triples` probes by `source_id IN` and filters
  client-side: the fetch is bounded by the probed sources' out-degree,
  not the batch — a high-degree hub makes a small mkedge read the
  hub's whole out-edge set. Acknowledged in the docstring; a
  tighter predicate (edge_type, or tuple-IN where the dialect has it)
  is the future direction.
  **Closed 2026-09-04** (the hub-cost follow-up): the probe binds the
  chunk's sources, targets, and types as three membership lists — the
  portable stand-in for tuple-IN, the chunk sharing the bind budget
  three ways — and returns row ids; the touch and the delete key on
  the id (`WHERE id = ?` executemany, or one `VALUES` join per chunk
  where the profile declares `values_join`, each assignment cast to
  its column's type so all-NULL payloads do not type as text; the
  delete `id IN` chunks). The cost was never the probe alone: the
  per-row touch keyed by the full triple was planned on the
  `(source_id, edge_type)` index under fresh statistics and filtered
  9,999 rows per row on Postgres (0.68 ms → 0.017 ms by id). 10k-edge
  batch, touch/remove: Postgres 8.4/5.1 s → 0.7/0.3 s, Oracle
  8.4/4.9 s → 0.7/0.9 s, SQL Server 7.5/7.9 s → 1.2/1.5 s (zero
  escalations), MariaDB 7.1/7.4 s → 7.6/0.3 s — the MariaDB touch is
  the per-row driver round trip spec 080 owns, not this cost.
- A narrow race: a rival delete committing between mkedge's endpoint
  resolve and its insert can leave an authored edge naming a trashed
  entry (no FK exists to refuse it, and re-convergence only reclaims
  rows whose endpoint entry row is *gone*). The edge dies at purge but
  would resurface on restore. Closing it would mean locking the
  endpoint entry rows in the mkedge transaction; left open for a
  ruling.

**Gates**

- `scripts/ci.sh` full 3.11–3.14 matrix green (2026-09-04); the 3.13
  coverage leg 3,091 passed / 942 skipped at 100 % coverage,
  ruff/format/ty zero.
- All four engine legs green: the full conformance suite plus the
  race-pin suite (`test_races.py`) — 933 passed / 8 skipped across
  Postgres 17, MariaDB 11.8, SQL Server 2025, Oracle 23ai; the edge
  battery, trash-cascade, restore, and no-edges-on-trashed rows
  identical on every engine.
- The 10,000-edge `mkedge` batch lands in one call — create, touch,
  and remove all bounded by the declared dialect budgets.
