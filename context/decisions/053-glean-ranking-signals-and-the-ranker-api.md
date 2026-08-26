# 053. glean Ranking Signals: a `signals` Table Computed at Reindex, In-Degree with Hierarchy Smoothing, and a Declarative Ranker on the Storage

- **Status:** accepted 2026-08-26 — the signals half of the glean
  decision set, resolved by Clay in session (the R1 review and the
  hierarchy-edges spike of the 2026-08-26 research leg). Read-derived
  signals are **deferred** by Clay; their design is recorded in the memo,
  not decided here. Companions: ADR 051 (the statement), ADR 052
  (fusion), ADR 054 (the embedding provider). Refines ADR 007's
  "analytics are index-time data feeding glean's graph signal" into a
  concrete mechanism; spec 067's intent (centrality moves to index time)
  is satisfied by it.
- **Date:** 2026-08-26
- **Deciders:** Clay Gendron
- **Decided by:** human
- **Context source:**
  `context/research/2026-08-26-glean-ranking-signals-and-ranker-api.md`
  and its studies (`centrality-and-read-signals.md`,
  `hierarchy-edges-academic.md`, `hierarchy-edges-prior-art.md`,
  `hierarchy-edges-experiment.md`, `fusion-and-merge.md` §A.4).

## Context

Clay asked that glean be designed so PageRank, Katz or other centrality
computed in the reindex pipeline can join the fusion, that the
filesystem hierarchy — materialised as `edge_type='fs'` edges under ADR
018 — participate at a lower weight, that everything be computed at
reindex and never at query time, and that the ranker be a customisable
API. ADR 007 forbids a strategy selector on the verb. Edges are
user-minted today; an extractor for imports, markdown links and symbol
uses is the intended producer of reference edges and becomes its own
spec.

The research measured four centrality measures on two real graphs from
this repository and PageRank/Katz scaling to 10⁶ nodes across five
implementations; three further studies (a literature-grounded model with
mass-flow derivations, a fourteen-system prior-art survey, and an
executed experiment adding `fs` edges at five weights in three
directions) settled the hierarchy question; the fusion study measured
how a prior should enter.

## Options considered

- **Which link measure**: in-degree (one `GROUP BY`; ρ = 0.97–0.98 with
  PageRank and Katz on the link graph; Craswell 2005's in-degree weight
  collapsed to zero *beside* PageRank — substitutes) (chosen as default);
  PageRank / Katz via a numpy power-iteration kernel (0.76 s at 10⁶
  nodes, no new dependency; ρ = 0.58 with in-degree on a small dense
  import graph, so they may differ on code) (kept as declared
  alternatives); rustworkx (fastest, but an un-seamed second native
  dependency — rejected); HITS (ρ 0.65–0.74; not a usable global prior —
  rejected); iterative SQL (portable, 94 s at 4.8M edges — the
  out-of-core future direction, not the reference).
- **The hierarchy in the graph**: `fs` edges at a lower weight in the
  random walk (rejected with measurements: in the materialised
  direction every weight from 0.05 to 1.0 yields *identical* rankings
  because out-weights normalise per source and a directory has only
  `fs` out-edges; what the tree edges rank is depth — Katz-down ρ = 1.00
  with depth — and inverse parent fan-out — PageRank-down ρ = −0.995;
  reversed, directories score by child count; bidirectional, file
  agreement with the reference graph falls to 0.55); **the tree as a
  smoothing layer** — aggregate by directory, distribute down (Xue et
  al. SIGIR 2005; XRank 2003; ObjectRank 2004) (chosen: siblings'
  reference counts predict a file's own at ρ = 0.40–0.77 across five
  corpora, and no system in the field folds containment into a search
  prior); a separate declared path-shape signal (kept as an optional
  input, sign learned — measured opposite to the web prior here).
- **Storage**: columns on `entries` vs a `signals(entry_id, signal,
  value, generation)` table (chosen: sparse by construction, schema-
  stable, rename-proof, one `LEFT JOIN` per leg, plain on `GENERIC`).
- **Publish discipline**: ride the gram epoch's CAS pointer vs in-place
  generation replacement (chosen: advisory data; a torn read yields a
  slightly stale prior, never a wrong result).
- **API shape**: the request carries the ranking program (Elasticsearch
  DSL, LanceDB's per-call `.rerank()` — the shape ADR 007 rejects) vs
  the deployment declares it (OpenSearch pipelines, Vespa rank profiles,
  haystack) (chosen: a frozen `Ranker` on the Storage plus `Fusion` /
  `Reranker` protocols); named profiles selected on the mount (deferred
  until the harness gives a reason to hold two).

## Decision

1. **A `signals(entry_id, signal, value, generation)` table**, PK
   `(entry_id, signal)`, refreshed as a phase of `reindex`: extract
   (keyset-paginated, no statement grows with the graph) → compute off
   the event loop through `call_offloaded` with the lease heartbeat
   between steps → chunked writes under a new generation, then delete
   the previous generation. Each signal carries an `options_hash`
   (measure, transform, γ, β) so a configuration change forces a
   recompute. Recompute is whole-corpus at every reindex; no incremental
   path.
2. **`signals` is read, never computed, on the query path.** The fused
   statement `LEFT JOIN`s the stored float on `entry_id` and multiplies
   by `(1 + β·value)` (ADR 052 pin 3). No graph walk, aggregate or
   smoothing pass runs per query; a missing row is factor 1.
3. **One link signal, `centrality`, over reference edges only** —
   `edges WHERE edge_type <> 'fs'` (declared edges today; extracted
   imports, links and symbols once the extractor exists). **Default
   measure in-degree**, `log1p`-transformed; PageRank and Katz as
   declared alternatives (`Centrality(measure=InDegree() | PageRank(…) |
   Katz(…))`) on a numpy power-iteration kernel behind the offload hop;
   the default flips to PageRank only if the accuracy study shows a
   gain on a real corpus. HITS is out.
4. **The hierarchy is a smoothing layer, never an edge type in the
   walk**: `p(f) = (1−γ)·m(f) + γ·p(parent(f))` with bottom-up directory
   means of the transformed measure and top-down propagation, γ = 0.2
   default, ≤ 0.3, harness-gated (adopted above 0 only on ≥ +0.01 nDCG on
   two of three corpora with the uninformative-prior control unmoved).
   Two O(N) numpy passes inside the same reindex phase; the tree is read
   from `parent_id` there and nowhere else in the prior path;
   directories are never candidates and never normalised against. A
   zero-edge mount has no `centrality` rows and the leg is absent from
   the statement, with an envelope record — never a zero-weighted
   column. An optional declared `path_shape` signal (depth, name length;
   sign learned) is the separate structural input.
5. **Read-derived signals are deferred** (Clay, 2026-08-26). The recorded
   design for later — opt-in, `read` only, host-buffered events flushed
   in a short separate writer transaction after the read-only op, rolled
   up at reindex with a 30-day half-life — is in the memo; nothing in
   this ADR depends on it.
6. **The ranker API is declarative data plus protocol seams**, declared
   on the Storage at construction, frozen and hashable, never a verb
   parameter:
   ```python
   DatabaseStorage(url=..., embedder=..., ranker=Ranker(
       signals=(Signal("centrality", measure=InDegree(), smoothing=0.2,
                       transform=Saturation(pivot=4.0), weight=0.15),),
       fusion=Convex(weights={"vector": 0.5, "lexical": 0.5}),
       aggregate=MaxP(chunks_per_entry=3)))
   ```
   with `Fusion` (`to_sql` for the in-engine statement where
   expressible, `fuse` for the client floor and the router) and
   `Reranker` (ADR 052 pin 6) as the extension protocols the built-ins
   implement. A signal the ranker names with no rows in the current
   generation is dropped with a warning record. The envelope explains
   what applied: per-leg ranks and raw scores, the signal factors, which
   legs were present, whether fusion compiled in-engine.

## Consequences

- **Easier:** adding a signal is inserting rows and one config line — no
  `ALTER TABLE` per dialect; every prior is a stored float and a join;
  zero-edge mounts pay nothing and claim nothing; PageRank/Katz are one
  config value away when the evidence arrives.
- **Harder:** a reference extractor is now load-bearing for the signal's
  usefulness on code (a spec of its own); the accuracy study (SWE-bench
  Verified for code, a Wikipedia slice with hyperlinks for prose, the
  vfs-native set as the gate) must run before γ, the default measure, or
  the anchor-text field (ADR 051's lexical fork E8 / memo F10) are
  finalised; the numpy kernel holds two int64 edge arrays and three
  float vectors at 10⁶ nodes (~104 MB) — acknowledged, with iterative
  SQL named as the out-of-core direction, never a declared cap.
- **Committed to:** no `fs` edges in any centrality walk; no directory
  fallback graph; no per-query graph work; no learned or de-biased
  click model at vfs traffic.

Evidence: `centrality-and-read-signals.md` (measure correlations on two
real graphs; the scaling table; zoekt's #523 → #853 arc; the Craswell
2005 transform table); `hierarchy-edges-experiment.md` (19
configurations on 977 nodes: weight-invariance in the materialised
direction, depth and fan-out correlations, the BM25 sanity check);
`hierarchy-edges-academic.md` (the normalisation lemma, the mass-flow
bounds, the five-corpus sibling test, the XRank/ObjectRank/Xue model);
`hierarchy-edges-prior-art.md` (fourteen systems; SharePoint,
HostRank/DirRank, Neo4j GDS); `fusion-and-merge.md` §A.4 (prior
injection).
