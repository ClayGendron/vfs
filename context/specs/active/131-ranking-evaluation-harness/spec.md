# 131 — the ranking evaluation harness: golden sets, BEIR pairs, ranx metrics, determinism pins

- **Status:** ready — drafted 2026-08-26 from ADR 052 pin 8 ("the
  harness lands with or before the first backend"). Second of the glean
  arc; lands before the verb so every later slice is measured, not
  guessed.
- **Born from:** ADR 052 §8; memo
  `../../../research/2026-08-26-glean-fusion-and-cross-mount-merge.md`
  §6; ADR 053's accuracy study (memo §9).
- **Date:** 2026-08-26
- **Owner:** Clay Gendron
- **Kind:** dev-only test tooling and fixtures; no `src/` behaviour
  change beyond a tiny scoring driver over spec 130's tables.
- **Depends on:** spec 130 as rewritten under ADR 055 (the BM25
  baseline it measures first is the block-posting index read through
  the scorer, not an in-engine `SUM`).
- **Relates to:** every later glean spec (each adds arms and pins here);
  the accuracy research leg (SWE-bench Verified, a Wikipedia slice) runs
  on this harness but is research, not this spec.

## Intent

Every ranking knob the ADRs name — α, β, k, γ, fetch depth, K chunks —
is set by taste until a relevance set exists. The harness makes ranking
changes measurable and pins cross-engine determinism, so the fused
statement's "identical rankings on six dialects" is a test row rather
than a study result.

## Decided semantics

1. **Golden corpora**, all offline and deterministic:
   - a **vfs-native set**: ≈ 200 files from `docs/` + `context/` frozen
     as a fixture snapshot, ≈ 40 queries with graded qrels in TREC
     format, hand-labelled and checked in (it alone exercises path
     globs, code tokens and entry/chunk aggregation);
   - a **BEIR pair** (SciFact for precision@1; NFCorpus for recall
     under truncation) fetched by a `uv run` script into a cache
     *outside* the repo (`ir_datasets` in a dev group), and skipped —
     not failed — when absent or offline.
2. **Metrics via ranx** (dev-only dependency; never imported by
   `src/`): `nDCG@10`, `MRR@10`, `recall@10`, `recall@50`;
   `optimize_fusion` for sweeps; `compare` for significance when a
   change claims a gain.
3. **Embedders**: the hashing embedder (spec 134 ships it in core; until
   then the harness carries a local copy of the same function) as the
   zero-dependency floor; model2vec potion-base-8M as the semantic
   default *when installed and cached*, skipped otherwise; both pinned
   by the content hash of their vectors for one fixed sentence.
4. **Determinism pins**: for every golden query the conformance suite
   pins the *ordered* top-10 path list per backend, identical across
   SQLite, Postgres, MariaDB, MySQL, SQL Server and Oracle; the pin
   requires an explicit total order (`score DESC, entry_id ASC,
   chunk_index ASC`) and the fused score rounded to a fixed number of
   decimals before the order-by. Spec 130's BM25 baseline is the first
   pinned ranker.
5. **Regression gate**: nDCG@10 on each golden corpus may not drop by
   more than 0.005 without an ADR note; naive score sort and round-robin
   are kept as named baselines so the gate has a floor.
6. **Controls**: the uninformative-prior injection from the fusion study
   is a standing arm that no prior may worsen (used from spec 136 on).

## Scope

In: fixtures, the fetch script and cache contract, the metrics driver,
the pins for the BM25 baseline, the gate. Out: the arms that need later
specs (they add themselves), the research runs themselves (SWE-bench,
Wikipedia — a research leg on this harness).

## Slices

- **A — fixtures and qrels**: the vfs-native snapshot and hand labels;
  the BEIR fetcher with cache-outside-repo and skip-when-absent.
- **B — driver and metrics**: a `tests/ranking/` (or `benchmarks/`)
  driver that loads a corpus into the in-memory backend, runs a ranker
  callable, and reports ranx metrics; the BM25-baseline pin via spec
  130's tables.
- **C — determinism and gate**: the ordered-top-10 pin as a conformance
  row (engine legs), rounding and tie-break laws, the 0.005 gate.

## Landing criteria

- `scripts/ci.sh 3.13` green with the BEIR pair absent (skips) and
  green locally with it present.
- The BM25-baseline pin holds on all engine legs.
- The landing note records the baseline numbers (nDCG@10 / MRR@10 /
  recall@10 on all three corpora) that every later spec is measured
  against.
