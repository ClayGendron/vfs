# 052. glean Ranking: Convex Fusion, Aggregate-then-Fuse, Bounded Priors, and Download-and-Rerank Across Mounts

- **Status:** accepted 2026-08-26 — the ranking half of the glean
  decision set, resolved by Clay in session (the R1 and R3 review of
  the 2026-08-26 research leg). **Amends ADR 007**: the reference fusion
  is a convex combination of normalised leg scores, not reciprocal rank
  fusion; ADR 007's verb surface, no-selector rule and capability split
  stand. Companions: ADR 051 (the statement), ADR 053 (signals), ADR
  054 (the embedding provider).
- **Date:** 2026-08-26
- **Deciders:** Clay Gendron
- **Decided by:** human
- **Context source:**
  `context/research/2026-08-26-glean-fusion-and-cross-mount-merge.md`,
  `context/research/2026-08-26-glean-previews-and-result-shape.md`, and
  their studies (`fusion-and-merge.md`, `lexical-leg.md` §4,
  `preview-and-snippets.md`).

## Context

ADR 007 wrote "reciprocal rank fusion in the reference design" and
called cross-mount scores "only loosely comparable", with re-fusing at
the router a road not taken; the router trims the merged list with
`Result.top(k)`, a single sort by `Observation.score`. Clay's
requirements: RRF of vector and lexical legs; top-*n* entries, not
chunks; and a merge of top-*n* lists from mounts that may run different
embedders and lexical engines — his lean an in-process BM25 rerank over
the union of each mount's top-*n*, to be tested against the academic
record.

The research leg ran a fusion sweep on one index and a nine-strategy
cross-mount simulation on two BEIR corpora with real relevance labels
(SciFact, NFCorpus), three deliberately mismatched mounts, random and
by-topic splits, ranx metrics; measured passage-to-entry aggregation;
and prototyped and timed the preview selector on 10,000 real chunks.

## Options considered

- **Fusion within a mount**: RRF at k = 60 (the universal library
  default, inherited from a 2009 pilot fusing thirty TREC runs) —
  measured **below BM25 alone** on SciFact (0.606 vs 0.663 nDCG@10),
  reproducing Bruch, Gai & Ingber (TOIS 2023); weighted RRF (0.647);
  convex combination of min-max-normalised scores (0.662 untuned at
  α = 0.5, 0.675 tuned) (chosen); RRF with a small per-leg k as the
  rank-only floor (kept).
- **Chunks to entries**: fuse chunk lists then collapse vs **aggregate
  by max inside each leg, then fuse entries** (chosen: MaxP wins or ties
  everywhere relevance can sit anywhere in a document — Dai & Callan
  SIGIR 2019 — and fuse-then-collapse lets one entry's many mediocre
  chunks crowd the fused window, makes rank-based fusion ill-defined,
  and breaks `LIMIT n` on entries).
- **How a static prior enters**: as an extra ranked list (an
  uninformative prior cost −0.20 nDCG); as a bounded multiplicative
  factor (≤ −0.05 uninformative, +0.16 real) (chosen); as an additive
  term (equivalent, kept as an option in the transform vocabulary).
- **Across mounts**: today's naive score sort (0.21–0.27); round-robin
  and cross-mount RRF (0.36–0.48 — a category error for disjoint
  collections, degenerating to interleaving); per-mount min-max or
  z-score normalisation (0.44–0.51: bounded is not comparable); SSL /
  SAFE sample-index merging (a second index to keep in sync);
  **download-and-rerank** — Clay's lean, the federated-search record's
  fallback for heterogeneous engines (Craswell 1999; Shokouhi & Si 2011)
  — 0.637–0.664, above the RRF oracle on SciFact, within 0.008 on
  NFCorpus, unhurt by the by-topic split (chosen, with two amendments).
- **Result shape**: overload `Match.content` with the bolded excerpt vs
  an `Observation.preview` string vs **`Match.preview` with its own line
  bounds beside the untouched `content`** (chosen).

## Decision

1. **Reference fusion is a convex combination** of per-leg normalised
   scores, `f = α·norm(vec) + (1−α)·norm(lex)`, cosine normalised by its
   theoretical range (`(cos+1)/2`), BM25 by min-max over the leg's
   candidate union; α = 0.5 default, tuned per corpus by the harness in
   the 0.3–0.8 range, declared on the Storage's `Ranker` (ADR 053), never
   on the verb. It compiles into ADR 051's statement with `MIN()/MAX()`
   window functions and one arithmetic expression. **RRF stays as the
   rank-only floor** for a leg that yields ranks without a comparable
   score, with a per-leg k defaulting small (10) and weights exposed.
   This amends ADR 007's reference-design sentence and nothing else.
2. **Aggregate, then fuse.** Each leg emits an *entry* ranking — `MAX`
   over its chunks inside the leg's CTE — and fusion runs over entries;
   `LIMIT n` counts entries. The arg-max and top-K (default 3) chunks per
   winning entry ride along in the same pass for the result.
3. **Static priors enter as bounded multiplicative factors** on the
   fused score, `f × ∏(1 + β_s·p_s)`, `β_s ≤ 0.5` by default, each `p_s`
   a stored, transformed, min-max-normalised value read from the
   `signals` table (ADR 053); an absent signal is factor 1. Never an
   extra rank list.
4. **Cross-mount merge is download-and-rerank.** The router fans
   `glean(query, min(limit × 3, 256))` to every mount in scope, unions
   the rows deduplicated on `content_hash`, reranks the union with one
   BM25 over the returned chunk text using the lexical index's own
   tokenizer and **corpus-wide statistics**, aggregates chunks to entries
   (MaxP), and returns the top-`limit` with a warning record when any
   mount's cap truncated the union. A single mount in scope skips the
   rerank; the mounts' own scores drop out of the merge; there is no
   cross-mount RRF and no per-mount normalisation.
5. **Corpus-wide statistics are a `SupportsGlean` requirement**: every
   backend's glean answer carries, per query term, `(df, N, avgdl)`; a
   backend that cannot supply them does not implement `SupportsGlean`.
   There is no union-statistics degradation path.
6. **One `Reranker` seam on the `VFS` instance** —
   `rerank(query, candidates, *, limit)` over `Candidate` rows carrying
   entry id, path, chunk text and bounds, mount, native and per-leg
   scores, prior values and term statistics — composed in order: the
   BM25 union rerank ships first; a cross-encoder, an LLM reranker or an
   MMR stage may follow. Stages reorder and never retrieve; each is
   bounded by the fan-out deadline and answers with a warning record
   when skipped. Configured on the instance, never chosen per call.
7. **The result shape.** One `Observation` per entry with its top-K
   chunk `Match` rows (`start`/`end` the chunk's line bounds,
   `match=None`, `content` the chunk text, `score` the chunk's fused
   score); `Observation.score` is the entry's fused score. `Match` gains
   `preview: str | None` with `preview_start`/`preview_end` — the
   query-biased, `**term**`-bolded, character-capped excerpt selected by
   a line-window density scorer over the chunk text already in hand
   (distinct-term coverage first, occurrences and adjacency as
   tie-breakers, earliest window on ties, overlapping spans merged); a
   vector-only hit gets the head of its top chunk with bounds and no
   spans. The preview is built from the fused statement's own rows —
   never a second content fetch — and is a pure function in
   `src/vfs/results/`; display budgets (window lines, per-line and
   per-preview character caps, K) are render-layer constants, not glean
   parameters. `_render_body` gains a `glean` branch that prints in
   **rank order** (today glean falls through to the path-sorted list).
8. **The evaluation harness lands with or before the first backend**:
   a hand-labelled vfs-native golden set over `docs/` + `context/`, a
   downloaded BEIR pair (SciFact, NFCorpus) skipped when absent, the
   offline embedders of ADR 054, ranx metrics (`nDCG@10`, `MRR@10`,
   `recall@10/50`) with `optimize_fusion` for every knob and `compare`
   for significance, an ordered top-10 determinism pin per backend
   across all six dialects (fused score rounded before the order-by; ties
   on `(score, entry_id, chunk_index)`), and a regression gate of 0.005
   nDCG. The uninformative-prior injection is the standing control.

## Consequences

- **Easier:** one bounded, documented score scale per mount; the merge
  no longer depends on what any mount's score means; the common
  single-mount case pays nothing for the merge; every knob (α, β, k,
  depth, K) has a measurement behind it and a harness to change it.
- **Harder:** α needs tuning to be better than "as good as BM25" — the
  harness is not optional; `SupportsGlean` is a heavier contract (term
  statistics per query); the router carries a BM25 implementation whose
  tokenizer must match the index's; `Match` grows three fields and a
  renderer branch.
- **Committed to:** re-running the merge simulation with a dense
  embedder at BM25 parity before deciding whether the mounts' cosine
  joins the router rerank by default (fork B2 — no, until then); fetch
  depth 3 bounded at 256 as a constant, never a strategy selector;
  preview budgets on the render side, never on the verb.

Evidence: `fusion-and-merge.md` (the sweep table; the prior-injection
table; the nine-strategy simulation on SciFact and NFCorpus with the
union-recall ceilings and zero-overlap counts); `lexical-leg.md` §4
(MaxP cost 0.1–0.7 ms; the three defects of fuse-then-collapse);
`preview-and-snippets.md` (10–22 µs per chunk, 314 µs per page; the
path-sorted render defect). Papers: Cormack, Clarke & Büttcher 2009;
Bruch, Gai & Ingber 2023; Dai & Callan 2019; Shokouhi & Si 2011; Si &
Callan 2003; Craswell, Hawking & Thistlewaite 1999; Turpin et al. 2007.
