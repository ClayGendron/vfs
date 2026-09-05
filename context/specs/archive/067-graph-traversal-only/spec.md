# 067 — Graph is traversal-only; centrality moves to index time

- **Status:** cancelled and archived 2026-09-05 (Clay) — every
  decision landed through other specs. The `graph` op is traversal
  only with a closed method vocabulary (`GRAPH_METHODS` in
  `src/vfs/ops.py`; the router validates it before dispatch and the
  envelope reports the one `graph` op); the per-method rendering
  vocabulary is gone; centrality is index-time row data — spec 136's
  `signals` table, computed at reindex over the one `edges` table
  spec 143 wired. What is *not* done is outside this seed's scope:
  no storage backend implements the graph verb yet
  (`SupportsGraph` is declared in `storage/protocol.py`; the router
  routes it; `DatabaseStorage` has no `graph`). That is an
  implementation spec of its own when the graph work starts. The
  July 2026 seed follows as the record; `src/vfs/graph/` no longer
  exists.
- **Date:** 2026-07-08
- **Owner:** Clay Gendron
- **Kind:** refactor (graph subsystem contract + rendering vocabulary)
- **Numbering:** 059–066 are reserved by the stable-ID namespace spec
  series (`context/research/2026-07-08-stable-id-namespace-proposal.md`
  §5); this story takes the next free number.
- **Depends on:** 057 result envelope (the `ops` vocabulary — this
  story's envelope consequence already landed as 057 decision 8's
  amendment), `src/vfs/graph/protocol.py` (current GraphProvider)
- **Prior art:** `src/vfs/graph/rustworkx.py` (pre-refactor
  implementation — stamps per-method `function` names and mixes
  traversal with analytics; rebuilt, not ported)

## Intent

The `graph` verb narrows to **traversal only**. Centrality — and any
whole-graph analytic of the same shape — is not a query-time operation:
it is an **index-time background process**, maintained alongside the
other derived indexes (grams, embeddings) and surfaced as row data, not
as a verb. Consequences:

- **One verb, one arrangement.** Graph results take the standard result
  projection shape; the per-method rendering vocabulary
  (`descendants`, `ancestors`, … in `projection.KNOWN_FUNCTIONS`)
  retires. This is what collapsed the envelope's `function` vocabulary
  into the op vocabulary (057 decision 8, as amended: `Result.ops`).
- **Analytics become data.** A centrality score is a materialized,
  refreshable column/field a caller reads (and sorts/filters on) like
  any other observation field — consistent with the stable-ID
  proposal's honest reframing: the namespace is virtual, derived
  indexes are materialized.

## Scope seed

- Graph protocol narrows to traversal methods; delete analytics from
  the query surface. `[NEEDS CLARIFICATION]` which traversals survive
  (descendants / ancestors / predecessors / successors / neighborhood —
  all five, or a smaller closed set?).
- Centrality index process: trigger, cadence, and storage.
  `[NEEDS CLARIFICATION]` where scores live (an `Observation` field, a
  metadata row, or the entry table) and what refreshes them (write-path
  hook vs periodic job).
- `projection.py` / `render.py`: graph-method function names retire;
  `graph` renders through the standard projection (the retirement
  itself ships with 057 Pass B, task 13; this story owns the
  graph-side rebuild).
- `src/vfs/graph/` rebuild against the storage-mount design (056) and
  the new envelope (057).

## Acceptance criteria (seed)

- No query-time verb computes a whole-graph analytic.
- `graph` results carry `ops=("graph",)` and render with the standard
  projection — no method-specific arrangement.
- Centrality scores are readable as row data and survive a rebuild of
  the derived index from source.
