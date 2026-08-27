# 137 — the cross-mount merge: download-and-rerank in the router and the `Reranker` seam

- **Status:** ready — drafted 2026-08-26 from ADR 052 (pins 4, 5, 6).
  Eighth of the glean arc; the router half of glean.
- **Born from:** ADR 052 §4–6; memo
  `../../../research/2026-08-26-glean-fusion-and-cross-mount-merge.md`
  §5, §7; study `fusion-and-merge.md` Part C (the nine-strategy
  simulation).
- **Date:** 2026-08-26
- **Owner:** Clay Gendron
- **Kind:** router change in `base.py` (`_route_fanout` / `_cap_rows`
  for glean), a `Reranker` protocol and the `BM25Rerank` stage, a
  `Candidate` model.
- **Depends on:** spec 132 (term-statistics export on every glean
  answer), spec 130 (the tokenizer the rerank reuses), spec 135
  (`Fusion.fuse` is not needed here — the rerank is BM25 — but the
  entries' bounded scores are), spec 051 fan-out deadline budget
  (active) for stage timeouts.
- **Relates to:** ADR 007's "road not taken", now taken; the dense-
  embedder re-run of the simulation (fork B2) before cosine joins the
  rerank by default.

## Intent

Today the router merges glean by sorting on `Observation.score` —
measured as the worst possible merge (0.21–0.27 nDCG against a
0.61–0.67 ceiling) because mounts' scores are not comparable. The
simulation showed Clay's lean — re-score the union of each mount's
top-n with one BM25 — recovers single-index quality (0.64–0.66) and is
the federated-search record's download-and-rerank. This spec lands it,
with the two amendments (corpus-wide statistics; fetch depth).

## Decided semantics

1. **Fan-out depth**: for `glean` only, `_route_fanout`'s `row_cap`
   becomes `min(limit × 3, 256)` per mount; the merged result is trimmed
   to `limit` after the rerank. A constant, never a parameter.
2. **Single mount in scope**: no rerank; the mount's own order and
   scores stand (the common case pays nothing).
3. **Union**: rows from all answering mounts, deduplicated on
   `content_hash` (first mount in mount-table order wins the row; the
   others' provenance is dropped), carried as `Candidate(entry_id,
   path, mount, chunk text, line bounds, native score, per-leg scores,
   prior values, term stats)` — everything the rows already hold; no
   stage re-fetches.
4. **`BM25Rerank`**: one BM25 (spec 130's formula and tokenizer — the
   same `vfs.native` scorer over freshly tokenized chunk texts, numpy
   fallback; ADR 055) over the union's chunk texts, **with corpus-wide
   statistics summed across the answering mounts' exported `(df, N,
   avg_dl)`** — a
   `SupportsGlean` requirement, so there is no union-only fallback; ties
   broken on `(score, path)`; then MaxP to entries; then `limit`. The
   mounts' exposed scores are not used; there is no cross-mount RRF and
   no per-mount normalisation. `Observation.score` on the merged rows is
   the rerank score, min-max-normalised to [0, 1]; previews (spec 133)
   are left as the mounts filled them.
5. **`Reranker` protocol**: `async rerank(query, candidates, *, limit)
   -> Sequence[Candidate]`; stages compose in order on the `VFS`
   instance (`VirtualFileSystem(rerankers=(BM25Rerank(), …))`), `BM25Rerank`
   first and the only built-in shipped; each stage is a pure function of
   its candidates, may reorder but never retrieve, runs under the
   fan-out deadline, and answers with a warning record when skipped for
   time. Configured on the instance, never chosen per call (ADR 007).
6. **Records**: a warning-severity `truncated` record when any mount's
   cap (256) was reached — the union may have lost recall — naming the
   mount; the per-mount tier and lexical-only records are preserved
   through the merge.
7. **Determinism**: the merged ordered top-10 is pinned in the
   multi-mount conformance fixture across engine mixes (e.g. sqlite +
   postgres), with the rounding-before-order law.

## Scope

In: the router path, `Candidate`, `Reranker`, `BM25Rerank`, records,
pins, harness arm (the simulation's strategy (v′) reproduced in-tree
on two in-memory mounts). Out: cross-encoder / LLM / MMR stages (later,
same seam), re-fusing the mounts' cosine (fork B2: no until the dense
re-run), Rust rerank (fork B1), duplicate handling beyond
`content_hash`.

## Slices

- **A — protocol and candidates**: `Candidate`, `Reranker`,
  `BM25Rerank` with corpus-wide stats, unit pins against a pure BM25
  over the same tokens.
- **B — the router**: depth, union, dedup, single-mount skip, trim,
  records; multi-mount pins (a ×100-scaled mount cannot win by scale;
  a by-topic split does not starve a mount).
- **C — harness and docs**: the in-tree two-mount simulation arm with
  its numbers in the landing note; `docs/api.md` glean semantics
  updated (scores comparable across mounts; depth constant).

## Landing criteria

- `scripts/ci.sh 3.13` green; the multi-mount ordered pin holds on a
  sqlite + one real engine mix.
- Harness: the two-mount arm within 0.02 nDCG of the single-index
  ceiling on the vfs-native set; today's naive sort kept as the named
  baseline it must beat.
- Ledger rows: a single mount never enters the rerank; a stage that
  returns more rows than it received is refused; the depth constant is
  refereed by a declared-value assert.
