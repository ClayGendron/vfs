# 136 — ranking signals: the `signals` table computed at reindex, in-degree with hierarchy smoothing, and the declarative `Ranker`

- **Status:** landed and archived 2026-09-04 — commit `3465393`; landing note below — drafted
  2026-08-26 from ADR 053 (all pins) and ADR 052 pin 3. Seventh of the
  glean arc.
- **Born from:** ADR 053; memo
  `../../../research/2026-08-26-glean-ranking-signals-and-ranker-api.md`
  §2.5, §4, §6; studies `centrality-and-read-signals.md`,
  `hierarchy-edges-*.md`.
- **Date:** 2026-08-26
- **Owner:** Clay Gendron
- **Re-read under ADR 057 decision 4 (2026-08-27):** the PageRank /
  Katz power iteration is a crate kernel in the reindex phase (the
  `bincount`-over-edges shape Rust wins by 15–35× in the 2026-08-27
  memo), not a numpy kernel; the "pure-Python fallback" clause is void.
  No numpy enters this spec.
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

## Landing note (2026-09-04)

**What landed** — the signals half of the glean decision set, in
three modules and one kernel:

- `models/rows.py`: schema format 11 — `signals(entry_id, signal,
  generation, value)` and `signal_epochs(signal → generation,
  options_hash, row_count)`. **Refinement of semantics 1**: the
  unique key carries the generation, because a refresh writes the new
  generation *beside* the old and flips the pointer row in the same
  transaction — a reader sees the whole prior generation or the whole
  new one, never a torn mix and never an empty window. The pointer is
  a plain row update under the reindex lease (no CAS; ADR 053's
  "advisory data, not on the epoch pointer" holds).
- `crates/vfs-core/src/signals.rs` (protocol 9) — the kernel: in-degree,
  PageRank (dangling mass spread, mean rank one) and Katz (less the
  unit, so nothing-refers-to-it is zero like in-degree) over the
  reference edges; `log1p`; the two tree passes (directory means
  bottom-up with empty directories contributing nothing, the
  `(1 − γ)·own + γ·p(parent)` blend top-down); min-max over files.
  One call, bit-reproducible (edge order and node index fix every
  sum). `tests/support/oracles/signals.py` referees it on random
  forests for every measure × γ ∈ {0, 0.2, 0.3}. **Refinement of
  semantics 3**: the kernel is Rust under ADR 057, not numpy; there
  is no pure-Python fallback, only the oracle.
- `storage/ranking.py`: `Signal(name, measure, smoothing, transform,
  weight)`, the measures (`InDegree`, `PageRank`, `Katz`, `PathShape`),
  the transforms (`Linear`, `Log1p`, `Saturation`, `Sigmoid`), and
  `Ranker(signals=…)`. The options fingerprint covers what is
  *stored* — measure and γ; transform and β shape the factor at query
  time and change nothing stored, so retuning them needs no reindex.
  `smoothing ≤ 0.3`, `0 < weight ≤ 1`.
- `storage/backends/database/signals.py`: the phase — `collect_graph`
  (keyset pages of live entries with parent, kind and depth, then of
  non-`fs` edges between live entries), `compute_signal` (through
  `call_offloaded`), `publish_signal` (bulk insert, pointer flip,
  sweep of the prior generation, one transaction), and
  `sweep_undeclared_signals`; and the probe — `signal_factors`, which
  reads the pointers, drops a signal that is missing, computed under
  other options, or empty (each a warning-severity `unavailable`
  record with `data.leg = "signal"`), probes the stored values for
  the candidate union in chunks, and answers `∏ (1 + β·t(v))` per
  entry. glean multiplies the fused entry score by it before the
  final min-max; the envelope's `legs.signals` explains each signal
  (applied, generation, entries with a factor, weight, transform) and
  `legs.fused = "client"` says where fusion ran.
- The reindex driver runs the phase after the edge re-convergence
  pass: the graph is collected once, each signal computes and
  publishes on its own, the lease's `lost` flag checked between them.
- **A file's stored value is sparse by scaling too**: min-max maps the
  lowest file to zero, and zero stores no row (factor one). A uniform
  prior therefore stores nothing and reorders nothing (pinned).

**Harness** (`tests/ranking/test_harness.py::TestSignalArms`) — the
golden set carries no reference edges until spec 138's extractor
lands, so the measure × γ table this spec's landing criteria ask for
is deferred to 138's landing note. What it does record: a declared
link signal on the edge-less set leaves glean *byte-identical* to the
baseline (0.7589 nDCG@10), and the `path_shape` prior scores 0.7579
— within the gate, and above the 0.7355 uninformative control.

**Gates** — `scripts/ci.sh 3.13` green at 100 % coverage (3,168 passed / 960 skipped);
`cargo test -p vfs-core` green (the kernel's six unit tests among
them); four engine legs green — signals, conformance, edges and races,
1,403 passed / 8 skipped across Postgres 17, MariaDB 11.8, SQL Server
2025 and Oracle 23ai, the prior stored and reordering glean on every
one. Not run: the full 3.11–3.14 matrix (before the push).

**Environment note** — `uv sync --reinstall-package vfs-py` is exact
and stripped the database drivers (the extras) from `.venv`; the first
leg run failed on `No module named 'asyncpg'`. CLAUDE.md now spells
the command with `--all-extras --group dev`.
