# 136 — ranking signals: the `signals` table computed at reindex, in-degree with hierarchy smoothing, and the declarative `Ranker`

- **Status:** ready — drafted 2026-08-26 from ADR 053 (all pins) and
  ADR 052 pin 3. Seventh of the glean arc.
- **Born from:** ADR 053; memo
  `../../../research/2026-08-26-glean-ranking-signals-and-ranker-api.md`
  §2.5, §4, §6; studies `centrality-and-read-signals.md`,
  `hierarchy-edges-*.md`.
- **Date:** 2026-08-26
- **Owner:** Clay Gendron
- **Kind:** new table, a new reindex phase, a numpy kernel behind the
  offload hop, the `Ranker` configuration object compiled into the
  fused statement; schema format bump.
- **Depends on:** spec 135 (the statement and `Fusion`), the reindex
  phase discipline (`indexing.py`, `call_offloaded`), `edges` (ADR 018;
  `fs` edges materialised), `parent_id` on entries.
- **Relates to:** spec 138 (the extractor that makes the signal useful
  on code), spec 131 (the uninformative-prior control arm), the
  accuracy research leg (sets γ and the default measure).

## Intent

A query-independent importance prior, computed once per reindex and
read as one stored float at query time — never computed on the query
path. In-degree over reference edges by default; the filesystem
hierarchy as a smoothing layer, never an edge in the walk; PageRank and
Katz as configuration; everything behind a frozen `Ranker` on the
Storage so the verb never grows a selector.

## Decided semantics

1. **Table**: `signals(entry_id ULIDKey, signal String(32), value
   Float, generation String(32))`, PK `(entry_id, signal)`; sparse (no
   row → factor 1). Per-signal `options_hash` stored in `meta`-style
   bookkeeping so a configuration change forces a recompute.
2. **The phase** (after `chunk_dirty`, independent of the gram epoch):
   extract — `SELECT target_id, COUNT(*) FROM edges JOIN entries …
   WHERE edge_type <> 'fs' GROUP BY target_id` for in-degree, or the
   keyset-paginated edge list for PageRank/Katz, plus `parent_id` for the
   tree — → compute through `call_offloaded` with the lease beat between
   steps → transform `log1p` → **smoothing**: bottom-up directory means,
   top-down `p = (1−γ)·m + γ·p(parent)`, γ = 0.2 default (≤ 0.3) → min-max
   over *files* (directories never candidates, never normalised
   against) → chunked writes under a new generation → delete the prior
   generation. In-place replacement; not on the epoch CAS.
3. **Measures**: `InDegree()` default; `PageRank(damping=0.85,
   iterations=20)` and `Katz(alpha=…)` on one ~30-line numpy power-
   iteration kernel (`np.bincount` over edge arrays; in-degree is its
   zeroth iteration), with a pure-Python fallback pinned byte-identical
   at a tolerance. HITS not offered. The memory profile (two int64 edge
   arrays + three float vectors) is acknowledged in the docstring with
   iterative SQL named as the out-of-core direction — no declared cap.
4. **`fs` edges are never in the walk**; the tree is read from
   `parent_id` in the smoothing step and nowhere else in the prior
   path. A zero-edge mount writes no `centrality` rows; the statement
   omits the leg and the envelope carries a warning-severity record.
5. **Query path** (as amended by ADR 055 — fusion is client-side):
   after the legs' ranked lists are known, one probe `SELECT entry_id,
   signal, value FROM signals WHERE entry_id IN (<candidate union>) AND
   signal IN (:names) AND generation = :gen` (chunked under
   `membership_budget`; the union is at most the legs' depths) and the
   factor `(1 + β · transform(value))` multiplies the fused score in
   `Fusion.fuse`'s signal step — nothing else. The vector leg's
   in-engine statement never joins `signals`. Transform vocabulary:
   `Log1p()`, `Saturation(pivot)`, `Sigmoid(pivot, exponent)`,
   `Linear()`, each a one-line Python function (no SQL twin needed).
6. **`Ranker`** (frozen, hashable, declared on the Storage):
   `Ranker(signals=(Signal(name, measure=…, smoothing=γ, transform=…,
   weight=β), …), fusion=Convex(...) | RRF(...), aggregate=MaxP(chunks_per_entry=3))`;
   `path_shape` (depth, name length; sign a parameter) as an optional
   declared signal computed as a column expression in the same phase. A
   named signal with no rows in the current generation is dropped with a
   record. The envelope's explain data names the signal factors applied,
   per-leg ranks and raw scores, and whether fusion compiled in-engine.
7. **Reads are deferred** (ADR 053 pin 5): no event table, no `reads`
   signal in this spec.

## Scope

In: the table, the phase, the kernel, smoothing, the `Ranker` object
and its SQL compilation, `path_shape`, the explain data, harness arms
(each measure × γ ∈ {0, 0.2}) with the control arm. Out: the extractor
(138), reads, named rank profiles (fork F7), the anchor-text field
(spec 130 follow-up).

## Slices

- **A — table and phase**: schema bump, extract/compute/write with
  generation replacement, the in-degree path, `options_hash`
  invalidation, lease-beat pins.
- **B — kernel and smoothing**: PageRank/Katz kernel with the pure
  fallback and parity pin; the two tree passes; the zero-edge and
  sparse-graph pins (absent leg vs floor-mapped zero).
- **C — `Ranker` and the probe**: the config object, transforms, the
  candidate-union signal probe and the factor step, the explain data,
  conformance rows (a declared signal with no rows is dropped with a
  record; a prior never reorders when uniform), harness arms and the
  landing-note table.

## Landing criteria

- `scripts/ci.sh 3.13` green; engine legs green (the probe runs and
  the fused pin holds with a signal present on all five engines).
- Harness: the uninformative-prior control arm is not worsened by more
  than 0.005 at the default β; the landing note records nDCG for each
  measure × γ on the vfs-native set (the only edge-bearing golden set
  until spec 138 lands).
- Ledger rows: no statement on the query path touches `edges`; the
  phase never runs a graph aggregate per query; `fs` edges never enter
  the kernel's arrays.
