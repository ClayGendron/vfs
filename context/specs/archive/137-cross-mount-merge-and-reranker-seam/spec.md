# 137 — the cross-mount merge: download-and-rerank in the router, under each mount's own order

- **Status:** landed and archived 2026-09-05 — commit `1f76b67`; landing note below — drafted
  2026-08-26 from ADR 052 (pins 4, 5, 6). Eighth of the glean arc; the
  router half of glean. **Amended 2026-09-05 (Clay) before
  implementation:** (a) the BM25 union rerank is the only stage
  shipped and it runs only when results are merged across mounts; (b)
  the **order law** — the rerank may never change the order a mount
  gave its own rows; the semantics below carry the revisions marked
  *(revised 2026-09-05)*, and the law was measured on the study's
  simulation before landing (see *Learnings*).
- **Born from:** ADR 052 §4–6; memo
  `../../../research/2026-08-26-glean-fusion-and-cross-mount-merge.md`
  §5, §7; study `fusion-and-merge.md` Part C (the nine-strategy
  simulation); the 2026-09-05 order-law re-run
  (`../../../research/studies/2026-08-26-glean/fusion-and-merge/results_order_law.md`).
- **Date:** 2026-08-26
- **Owner:** Clay Gendron
- **Re-read under ADR 057 decision 4 (2026-08-27):** `BM25Rerank`'s
  "numpy fallback" clause is void — the Rust scorer already serves and
  there is no fallback engine. No new kernel needed.
- **Kind:** router change in `base.py` (`_route_fanout` and the grouped
  dispatch for glean), a new `vfs/rerank.py` holding the `Reranker`
  protocol, the `BM25Rerank` stage, the `Candidate` row, the order law
  and `merge_ranked`.
- **Depends on:** spec 132 (term-statistics export on every glean
  answer), spec 130 (the tokenizer the rerank reuses), spec 135 (the
  entries' bounded scores). Spec 051 (fan-out deadline) is **not** a
  dependency any more *(revised 2026-09-05: stages run unbounded
  in-process; the deadline clause waits on 051)*.
- **Relates to:** ADR 007's "road not taken", now taken; the dense-
  embedder re-run of the simulation (fork B2) before cosine joins the
  rerank — still open, and Clay's 2026-09-05 rescope keeps cosine out.

## Intent

The router merged glean by sorting on `Observation.score` — measured
as the worst possible merge (0.21–0.27 nDCG against a 0.61–0.67
ceiling) because mounts' scores are not comparable. The simulation
showed Clay's lean — re-score the union of each mount's top-n with one
BM25 — recovers single-index quality (0.64–0.66) and is the federated-
search record's download-and-rerank. This spec lands it, with the two
amendments (corpus-wide statistics; fetch depth) and one law of Clay's:
the rerank exists to put mounts on one scale, not to overrule a mount
about its own rows.

## Decided semantics

1. **Fan-out depth**: for `glean` only, when more than one entry may
   answer, each is asked for `min(limit × 3, 256)` rows and the merged
   result is trimmed to `limit` after the rerank. A constant, never a
   parameter. One entry in scope is asked for `limit` and its answer
   stands *(revised 2026-09-05: the depth is decided from the fan-out
   plan, so a scope naming one mount never over-fetches)*.
2. **Single mount in scope**: no rerank; the mount's own order, scores
   and `legs` explanation stand (the common case pays nothing).
3. **Union**: rows from all answering mounts, deduplicated on
   `content_hash` (first mount in dispatch order keeps the row; the
   others' rows are dropped and counted), carried as `Candidate(source,
   mount, rank, row, score, chunk_scores, stats)` — the row itself with
   its provenance (the answering mount's dispatch position and the
   row's rank in that mount's answer), the scores each stage rewrites,
   and the union's shared statistics. Nothing is re-fetched.
4. **`BM25Rerank`**: one BM25 (spec 130's formula and tokenizer — the
   index's own `tokenize`, `idf`, `term_weight`) over every `Match`
   region's text (its content, else its preview for an overlay row),
   **with corpus-wide statistics summed across the answering mounts'
   exported `lexical_stats`** (`N` summed, `avg_dl` length-weighted,
   `df` per term summed); MaxP to entries. A mount that exports no
   statistics contributes none; when no mount exports any, the union's
   own chunk texts supply them and the explanation says `"union"`
   *(revised 2026-09-05: the doubles and any non-database backend
   answer without an export; the router must still merge)*. The
   mounts' exposed scores are not used; there is no cross-mount RRF
   and no per-mount normalisation. `Observation.score` on the merged
   rows is the rerank score after the order law, min-max scaled to
   [0, 1] and rounded like a mount's; each entry's best chunk carries
   the entry's score and the other chunks scale with it; previews are
   left as the mounts filled them.
5. **The order law** *(new 2026-09-05, Clay)*: **no stage may change
   the order a mount gave its own rows.** After the stages run, each
   mount's rerank scores are repaired to be non-increasing along the
   mount's list by isotonic regression (pool adjacent violators — a
   violating run pools to its mean), then the union sorts by repaired
   score with ties to dispatch order, then mount rank. Consequences:
   the rerank decides only how many rows each mount contributes and how
   the mounts interleave; every mount's surviving rows are a prefix of
   its answer; in Clay's example (mount 2 said 1 > 2 > 3, the rerank
   prefers 2) row 1 rides up beside row 2 and row 3 is the one bumped.
   The naive alternatives were measured and rejected: a k-way merge on
   head scores lets one weak head block a strong row; suffix-max lifts
   a whole prefix on one strong row.
6. **`Reranker` protocol**: `async rerank(query, candidates, *, limit)
   -> Sequence[Candidate]`; stages compose in order on the `VFS`
   instance (`VirtualFileSystem(rerankers=(BM25Rerank(), …))`, the
   default is the one built-in), validated at construction. Each stage
   is a pure function of its candidates: it returns exactly the rows it
   received, rescored — a different row set is a raised `ValueError`
   (a configured stage is developer code; its bug is not a classified
   result) *(revised 2026-09-05)*. Stages never retrieve. The order law
   binds every stage; `rerankers=()` orders the mounts' own scores
   under the law. Configured on the instance, never chosen per call
   (ADR 007). The deadline clause waits on spec 051.
7. **Records and explanation**: a warning-severity `truncated` record
   naming the mount when a mount filled the 256-row cap — the union may
   have lost recall. The merged answer's `legs` extra carries `merge`
   (`mounts`, `depth`, `rerankers`, `statistics`, `candidates`,
   `duplicates`) and `mounts` (each answering mount's own `legs`);
   `Result.with_mount` / `without_mount` now carry a result's extras
   across the seam so the mounts' explanations and statistics reach
   the merge *(revised 2026-09-05: they were dropped before, so no
   extra survived the router)*. A dead mount among answering ones stays
   loss on record (the zero-progress rule is untouched).
8. **Determinism**: the merged ordered top-10 is pinned in
   `top10_merge.json` on two sqlite mounts and asserted on every
   sqlite-plus-server mix, with the rounding-before-order law.

## Scope

In: the router path (fan-out and grouped-observation dispatch alike),
`Candidate`, `Reranker`, `BM25Rerank`, the order law, records, the
explanation, pins, the harness arm and pin. Out: cross-encoder / LLM /
MMR stages (later, same seam), re-fusing the mounts' cosine (fork B2:
no until the dense re-run — and Clay's rescope keeps it out), Rust
rerank (fork B1), duplicate handling beyond `content_hash`, a stage
deadline (spec 051).

## Learnings from the order-law re-run (2026-09-05)

The study's `sim_merge.py` was re-run with the order-preserving
variants beside the unconstrained rerank (SciFact, three mounts, both
splits; `results_order_law.md`). What it settled:

| question | measured (nDCG@10) | consequence |
|---|---|---|
| the law on the study's mounts A/B/C (C a deliberately bad local ranker) | unconstrained 0.654–0.668; isotonic 0.594–0.620 | the named trade-off is real: the rerank can no longer repair a bad mount's order — 0.05–0.07 against an adversarial one |
| the law on vfs-shaped mounts (one engine, one fusion law, one embedder) | 0.6672 → 0.6688 random; 0.6676 → 0.6582 topic | near free: +0.002 / −0.009 |
| same law, embedders differ (potion-8M / potion-4M / hash) | 0.6647 → 0.6625 random; 0.6567 → 0.6349 topic | −0.002 / −0.022 — the topic split is where a weaker mount's order costs |
| lexical-only mounts | 0.6625 → 0.6612; 0.6636 → 0.6583 | −0.001 / −0.005 |
| which repair | isotonic beats suffix-max by 0.01–0.02 and the k-way head merge by 0.02–0.03 on every row | isotonic (PAVA) it is |
| prefix property | 0 violations over every query, split and limit | pinned as the law's invariant |
| depth | isotonic's numbers are identical at m = 10, 20, 50 | under the law, deeper fetching adds nothing on SciFact — the prefix is what it is |

Adopted with the numbers on record: on the mounts vfs ships the law
costs 0.00–0.02 and buys the guarantee Clay asked for; the 0.05 case
needs a mount whose own ranking is bad, which vfs does not ship.

## Slices

- **A — protocol and candidates**: `Candidate`, `Reranker`,
  `BM25Rerank` with corpus-wide stats, the order law, unit pins
  against the index formula.
- **B — the router**: depth from the plan, union, dedup, single-mount
  skip, trim, records, the explanation; the grouped-observation path;
  extras across the seam; router pins (the law through the router, a
  scope naming one mount, the cap, a dead mount, the stage seam).
- **C — harness and docs**: the two-mount arm through a real
  `VirtualFileSystem` gated beside the floors; the merge pin on sqlite
  and on the server legs; `docs/api.md`; ADR 052 amended.

## Landing criteria

- `scripts/ci.sh 3.13` green; the multi-mount ordered pin recorded on
  two sqlite mounts and asserted on the sqlite + server mixes.
- Harness: the two-mount arm within 0.02 nDCG of the single-index arm
  on the vfs-native set; today's naive sort and round-robin kept as the
  named floors it must beat.
- Ledger rows: a single mount never enters the rerank; a scope naming
  one mount never over-fetches; a stage that returns a different row
  set is refused; the depth constant is refereed by a declared-value
  assert; the law holds through the router and in isolation.

## Landing note (2026-09-05)

**What landed.**

- `src/vfs/rerank.py`: `fanout_depth`, `Statistics` (the summed
  exports, or the union's own), `Candidate`, the `Reranker` protocol,
  `BM25Rerank` (the index's tokenizer, `idf` and `term_weight` over
  every region's text, MaxP), `isotonic_nonincreasing` and `order_law`,
  `merge_ranked` (union, dedup, stages, the law, unit scaling, the cap
  record, the explanation) and `RankedMerge`.
- `src/vfs/base.py`: `VirtualFileSystem(rerankers=…)` validated at
  construction; `_Ranked` (query, limit, depth) rides `_route_fanout`
  and `_dispatch_grouped_observations`; the depth overrides `limit`
  only when the plan holds more than one entry — the one declared
  exception to "forwards kwargs verbatim"; `_rank_fanout` composes the
  merge onto the fan-out envelope; `_cap_rows` no longer sorts glean.
- `src/vfs/results/envelope.py`: `with_mount` / `without_mount` carry
  a result's extras. `src/vfs/storage/ranking.py`: `SCORE_DECIMALS`
  and `REFINE_GUIDANCE` moved up from the backend so the router shares
  them.
- Tests: `tests/test_rerank.py` (the pieces, the law, the merge over
  canned answers), `tests/base/test_glean_merge.py` (through the
  router), the harness arm `merge/rerank` and the pin
  `top10_merge.json` (`tests/ranking/merge.py`, `pins.py`,
  `test_harness.py`; the server-mix pin is parametrised over the four
  engine legs).
- `docs/api.md` (the cross-mount paragraph); ADR 052 amended.

**Harness** (vfs-native golden set, two sqlite mounts split by
top-level directory, nDCG@10 / MRR@10 / recall@10):

| arm | nDCG@10 | MRR@10 | recall@10 |
|---|---|---|---|
| `glean`, single index (the ceiling) | 0.7589 | 0.9833 | 0.4134 |
| **`merge/rerank`** (the router, under the law) | **0.7531** | 0.9833 | 0.4076 |
| `merge/naive_score_sort` (the former router) | 0.7353 | 0.9688 | 0.3989 |
| `merge/round_robin` | 0.5600 | 0.7542 | 0.3187 |

Within 0.006 of the single index, +0.018 over the sort it replaces.

**Gates.** `scripts/ci.sh 3.13` green — 3,240 passed, 968 skipped,
100 % coverage, `ruff` and `ty` at zero; the merge pin holds on all
four sqlite + server mixes (Postgres, MariaDB, SQL Server, Oracle: 4
passed on the running containers).

**Follow-ups, named.**

- Fork B2 (the mounts' cosine in the rerank): the dense re-run with the
  MiniLM default (ADR 060) has still not happened; the seam carries
  the cosine on every row's `Match.score` so a stage can read it.
- A stage deadline once spec 051 lands.
- The k-way and suffix-max repairs are recorded as rejected; if a
  mount with a poor local ranker ever ships (a remote mount speaking
  the vfs dialect over an unknown engine), the 0.05 case becomes real
  and the law would need a per-mount opt-out — not designed.
