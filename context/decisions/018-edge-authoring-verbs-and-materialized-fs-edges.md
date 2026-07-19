# 018. Edge Authoring Verbs and Materialized FS Edges — mkedge/rmedge Batches, One Edge Table for Traversal

- **Status:** accepted
- **Date:** 2026-07-19
- **Deciders:** Clay Gendron
- **Decided by:** human (Clay directed the materialized-hierarchy design and
  the single-table traversal goal in the 2026-07-19 session; the assistant's
  prior-art research shaped the verb pair, the touch/removal semantics, the
  reserved-type protection, and the parent_id retention analysis; Clay
  adopted each in session)

## Context

ADR 016 took chunks, versions, and edges off the namespace and pinned verbs
as the sole metadata interface, but left the write surface unspecified.
Edges differ from the other two families: chunks and versions are minted
storage-side, while edges are **caller-authored** — an agent or pipeline
states that two entries relate. The live `mkedge` predates this: it takes
one `(source, target, edge_type)` string triple, has no removal
counterpart, and cannot express `Edge.weight`/`distance` at all
(`base.py:863-924`, `ops.py:50-52`).

The 2026-07-19 prior-art memo
(`research/2026-07-19-edge-authoring-api.md`; three parallel researchers,
file:line evidence) found: an explicit create/remove verb pair with
system-structural edges excluded from it is universal (POSIX `link(2)`
EPERM on directories, dirents minted only inside mkdir; juicefs's edge
table written only by metadata-engine transactions); batch, transactional,
identity-keyed mutation is the modern norm (SpiceDB `WriteRelationships`,
OpenFGA `Write`); upsert-vs-strict and missing-on-delete are the genuine
decision axes, with the field split (pjdfstest EEXIST/ENOENT and OpenFGA
strict defaults vs SpiceDB TOUCH/no-op and LightRAG `upsert_edge`).

The session then resolved where hierarchy lives. Clay's requirement: graph
traversal must walk containment and explicit relations **in one query over
one table** — no two-arm union inside recursive CTEs, uniform query
generation and pagination across dialects. Three shapes were weighed for
the parent→child edges (the only storage-side edges):

- **Read-time projection** — `parent_id` stays the only store; the graph
  verb unions a derived containment arm with the edges table (the SQL/PGQ
  / Apache AGE model: declare edges over existing FKs). Rejected for the
  traversal requirement: every graph query carries a second addressing arm
  and per-dialect union plumbing.
- **Edges table as the sole hierarchy store, `parent_id` dropped** —
  single source of truth by removal. Rejected on arbitration portability:
  `UNIQUE(parent_id, name)` is the concurrent-create arbiter and works on
  every engine because it is a plain unique index over non-null columns on
  one table. Moving it to a shared edges table requires either name-on-edge
  with per-dialect filtered/functional unique indexes (SQL Server's
  single-NULL rule, Oracle's composite-NULL collisions, nothing clean at
  the GENERIC floor) or application-level arbitration — a strict weakening
  of a deliberate write-path decision.
- **Materialized fs edges with `parent_id` retained as the write-side
  arbiter (chosen)** — hierarchy is mirrored into the edges table as
  reserved-type rows minted in the same transactions that mutate the
  namespace; `parent_id` remains authoritative for arbitration, restore
  identity, and path regeneration; readers answer every edge question from
  one table.

The survey found no precedent for system and caller edges sharing one
table guarded by a reserved type — where both kinds exist, protection is
structural (juicefs: separate table, no public edge API; Oak: internal
editor over a derived reference index). The chosen design imports those
systems' actual protections — single writer, gate-level refusal, invariant
enforcement — into the shared-table shape.

## Decision

Nine pins.

**The caller surface:**

1. **`mkedge` and `rmedge` are the caller verb pair, batch-native in the
   house `write` shape.** Native input `edges: Sequence[Edge]` (validated
   models — `weight`/`distance` reachable); the
   `source`/`target`/`edge_type` triple form is sugar constructing one
   `Edge` at the gate; the two forms are mutually exclusive. Both verbs
   join `MUTATING_OPS`, permission-gate at both endpoint paths, refuse
   cross-mount pairs, and chunk by dialect budgets — no hard batch cap;
   the 10,000+ ETL contract holds.
2. **`mkedge` is touch/upsert.** Per-row status reports `created` or
   `updated`; the per-edge `version` ticks on re-touch (ADR 013). A
   duplicate identity within one batch is `invalid` (SpiceDB/OpenFGA
   precedent — last-write-wins hides caller bugs). No strict-create mode
   until a consumer needs the guard; the per-row status already says what
   happened.
3. **`rmedge` removes by the creating coordinates** — exact
   `(source, target, edge_type)` triples. A missing edge is a per-row
   `not_found` observation, never a batch error. No filter-based mass
   delete in v1; if bulk clearing by type or endpoint proves needed, it
   arrives as a later verb with SpiceDB's guardrails (non-empty filter,
   explicit partial-delete semantics), never silently.
4. **User edges are unconstrained by endpoint kind.** Directories may be
   sources and targets (`(src/auth/, depends_on, src/db/)` module edges
   are legitimate); a file may link to a directory. Endpoint lawfulness
   stays what the `Edge` validators already pin: user-space paths only —
   never root, never `/.vfs`. The only refused type name is the reserved
   one (pin 6).

**The hierarchy mirror:**

5. **Parent→child edges are materialized in the edges table.** Every live
   non-root entry has exactly one in-edge `(parent → entry)` with the
   reserved type, minted and maintained storage-side inside the same
   transactions as the namespace mutation: create (`write`, `mkdir`,
   including a `parents=True` chain) inserts; `move` updates the one moved
   row's source id (id-keyed, ADR 004 — descendants untouched); trash and
   restore ride the move logic (ADR 014: trash is ordinary writes);
   `copy` mints edges for the new ids; permanent delete removes the
   subtree's fs edges. Bulk writes mint fs edges as one more executemany
   in the write transaction — the ADR 017 version-row pattern.
6. **`"fs"` is the reserved edge type, refused at two layers.** The
   public gate (`mkedge`/`rmedge`) refuses it, and the `Edge` domain
   model refuses it — storage mints fs rows directly at the row layer,
   never through the model, exactly as versions and chunks are minted
   (ADRs 015/017: no pipeline caller holds a domain model at minting
   time). Fs-edge invariants: source is a directory; exactly one fs
   in-edge per live non-root entry. A partial/filtered unique index on
   `(target_id) WHERE edge_type = 'fs'` hardens single-parent where the
   engine supports one; the portable floor is the conformance invariant
   (pin 8). Future system edge families reserve their own names through
   an ADR; callers never gain a path to author them.
7. **`parent_id` stays, narrowed to the write side.** It is the
   concurrent-create arbiter (`UNIQUE(parent_id, name)`), the restore
   identity (`original_parent_id`), and the path-cache regenerator — and
   it is **authoritative**: on any disagreement with the fs edges, the fs
   edges are wrong. Readers answering edge questions — graph traversal,
   `tree`, and `ls` if uniformity proves worth the join — use the edges
   table alone; no reader unions the two stores.
8. **The mirror is invariant-tested, both backends.** A storage
   conformance test pins that fs edges exactly mirror `parent_id` —
   presence, direction, one-per-entry — after every mutating verb the
   suite exercises. Drift is a loud test failure, not a latent divergence.
   This test is the load-bearing guard on pin 5 and is not optional.

**Deferred, explicitly:**

9. **User-edge fate on entry delete is the wiring spec's decision.** The
   graph consensus is cascade-on-node-delete; Oak's strong/weak reference
   split is the alternative; tuple stores let edges dangle. The wiring
   spec must name the default (cascade aligns with `delete`'s existing
   `cascade=True` posture) and settle the trash interaction — a trashed
   entry keeps its identity, so its user edges plausibly survive trash and
   die on permanent delete. Also deferred: the `edges.version` column
   (spec 076 plan's declared model-only exemption) and the read-side verb
   surface (`edges(path, direction, type)` — ADR 016 pin 4's future
   interface spec).

## Consequences

- **Easier:** graph traversal is one recursive query over one table —
  uniform filtering, pagination, and query generation across dialects,
  with `"fs"` behaving as an ordinary type name callers include or
  exclude; `mkedge` finally expresses the whole `Edge` model; removal
  exists; moves stay O(1) on the hierarchy mirror because edges key on
  stable ids; trash needs no special edge handling at all.
- **Harder:** hierarchy is stored twice — every future namespace verb
  must remember the fs-edge write, and the conformance invariant (pin 8)
  is what keeps that honest; the edges table grows by one row per entry
  (N−1 fs rows), which read-side type filters must account for; the
  reserved-type refusal is permanent API surface in two layers.
- **Committed to:** the edge-wiring spec implements pins 1–8 against the
  database backend (the memory backend follows the same contract);
  `Edge`'s module docstring stops describing edges as purely
  caller-authored (they are caller-authored *except* the fs family);
  the fs-edge maintenance matrix in pin 5 is the checklist the wiring
  spec's tests walk; pin 9's deferrals are named in that spec, not
  rediscovered.

Evidence: `research/2026-07-19-edge-authoring-api.md` (the three-line
survey: POSIX verb pairing and dirent protection, SpiceDB/OpenFGA batch
and strictness semantics, graph-system upsert/removal norms; juicefs
`pkg/meta/sql.go:65-71` and Oak `ReferenceEditor` as the
system-edge-protection precedents); `research/2026-07-18-metadata-
namespace-vs-verbs.md` (edges leave the namespace);
`context/decisions/004-stable-identity.md` (id-keyed edges make the
mirror move-stable); ADR 013 (per-edge version), ADR 014 (trash rides
move), ADRs 015/017 (row-layer minting with the domain model as the
caller door); `models/rows.py` (`UNIQUE(parent_id, name)` arbitration,
the edges table's id-triple key); `base.py:724-767` (the `write` batch
shape pins 1 mirrors). Refines ADR 016 (which pinned verbs but not the
write surface); supersedes no numbered ADR. The full dirent end-state
(name-on-edge, `parent_id` dropped, hard links) is parked in
`open-questions.md`, not decided here.
