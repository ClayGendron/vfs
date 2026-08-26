# glean ranking: the fusion function, chunk-to-entry aggregation, and merging top-n lists across mounts

- **Status**: research memo — design input for the glean *ranking* ADR.
  One of five memos synthesising the 2026-08-26 glean research leg
  (brief: [2026-08-26-glean-brief.md](2026-08-26-glean-brief.md)).
  Companions: [glean in the engine](2026-08-26-glean-in-the-engine.md)
  (the fused statement and the lexical index),
  [ranking signals and the ranker API](2026-08-26-glean-ranking-signals-and-ranker-api.md)
  (centrality, reads, where priors live),
  [the embedding seam](2026-08-26-glean-embedding-seam.md),
  [previews and the result shape](2026-08-26-glean-previews-and-result-shape.md).
  Commits us to nothing.
- **Date**: 2026-08-26
- **Owner**: Clay Gendron
- **Question**: Two decisions hide inside "glean returns one fused list".
  *Within a mount*: how are the vector leg and the lexical leg fused,
  with what parameters, at what grain (chunk or entry), and how do
  static priors enter without wrecking the ranking when they are absent
  or uninformative? *Across mounts* that run different embedders,
  different lexical implementations and different fusion functions:
  how does the router turn *k* top-*n* lists with incomparable scores
  into the corpus top-*n* — and is Clay's lean (fetch each mount's
  top-*n*, re-score the union in-process with one BM25, take the
  top-*n*) right?
- **Evidence gathered**: the executed fusion-and-merge study
  ([studies/2026-08-26-glean/fusion-and-merge.md](studies/2026-08-26-glean/fusion-and-merge.md):
  a fusion sweep on one index and a nine-strategy cross-mount simulation
  on two BEIR corpora with real relevance labels — SciFact, 5,183 docs /
  300 queries, and NFCorpus, 3,633 docs / 323 queries — scripts and raw
  results beside it); the lexical-leg study's aggregation section
  ([lexical-leg.md §4](studies/2026-08-26-glean/lexical-leg.md)); the
  engine-matrix study's verified fused statement
  ([engine-matrix.md §1](studies/2026-08-26-glean/engine-matrix.md));
  the independent no-requirements design
  ([unconstrained-design.md §5](studies/2026-08-26-glean/unconstrained-design.md))
  as a counter-position; the landscape study's vendor record
  ([landscape.md §7](studies/2026-08-26-glean/landscape.md)).
- **Headline**: *Within a mount*, reciprocal rank fusion at the
  universal k = 60 is not a safe default — on SciFact with a static
  embedder it scored **below BM25 alone** (0.606 vs 0.663 nDCG@10),
  reproducing Bruch et al. (TOIS 2023); a convex combination of
  min-max-normalised leg scores beat every RRF variant and both legs
  (0.675 at α = 0.3), and the normaliser choice moved nothing (≤ 0.005).
  Aggregate chunks to entries by max **inside each leg**, then fuse
  entries. Priors enter as *bounded multiplicative factors*, never as an
  extra rank list (an uninformative prior as an RRF list cost −0.20
  nDCG; as a bounded factor ≤ −0.05). *Across mounts*, Clay's lean is
  download-and-rerank — the federated-search record's fallback for
  heterogeneous engines — and it **recovered single-index quality**
  (0.637–0.664 nDCG@10, above the RRF oracle on SciFact, within 0.008 on
  NFCorpus, unhurt by an adversarial by-topic split) where today's
  `Result.top` scored 0.21–0.27 and every rank-interleaving or
  score-normalising alternative lost 0.1–0.4. Adopt it with two
  amendments: mounts export per-term `(df, N, avgdl)` so the reranker
  uses corpus-wide statistics (+0.01–0.03), and each mount answers
  `limit × 3`.

---

## 1. Where the verb stands

ADR 007 pinned the surface — `glean(query, *, limit, paths, …)`, no
strategy selector, "reciprocal rank fusion in the reference design",
scores across mounts "only loosely comparable" — and recorded re-fusing
at the router as a road not taken. The router today fans out with
`_route_fanout(row_cap=limit)` and trims the merged rows with
`Result.top(k)`, one sort by `Observation.score`
(`src/vfs/base.py:1252`, `:2635`; `src/vfs/results/envelope.py:580`).
No backend implements `SupportsGlean`, so nothing has yet had to be
comparable. This memo is where those three phrases — "RRF", "loosely
comparable", "road not taken" — meet numbers.

## 2. Fusion within a mount

### 2.1 The record

Cormack, Clarke & Büttcher (SIGIR 2009) fixed k = 60 "during a pilot
investigation" of four Wumpus configurations, fusing *thirty full-depth
TREC runs*; the constant exists "to mitigate the impact of high
rankings by outlier systems" — many noisy voters, not two complementary
legs. Bruch, Gai & Ingber (TOIS 2023) is the controlled comparison for
the two-leg case: convex combination (CC) of normalised scores beats RRF
on every dataset in their Table 2 (SciFact 0.753 vs 0.730, NFCorpus
0.327 vs 0.312, all p < 0.01); RRF rewritten as `1/(η_lex + π_lex) +
1/(η_sem + π_sem)` has one constant per leg and "NDCG swings wildly"
across η; the normaliser is "a rather small detail" because a CC of
min-max scores is rank-equivalent to a CC of z-scores at some other α;
and CC's α converges from a handful of labelled queries. OpenSearch's
own RRF launch post measured RRF 3.86 % below its score-based
processors across six datasets.

Every library inherits k = 60 unchanged — ranx, OpenSearch's
`score-ranker-processor` (`rank_constant` 60), LanceDB `RRFReranker(K=60)`,
haystack (k = 61 over 0-based ranks), llama_index, Elasticsearch,
pyserini, Weaviate before v1.24 — and every one exposes *weights* as the
escape hatch. Only ranx has a tuning loop (`optimize_fusion`). The SQL
vendors (landscape §7) are unanimous on RRF because rank is the only
thing portable across their *incomparable* lexical scorers (`ts_rank`,
InnoDB relevance, Oracle `SCORE`); Oracle's built-in primitive defaults
to RSF, a weighted score sum, and graphiti ships k = 1. k is contested
enough to be a parameter, never a constant.

### 2.2 The executed sweep (SciFact, BM25 k1 = 1.2 / b = 0.75 + potion-base-8M cosine, top-100 per leg, top-10 out)

| Ranker | nDCG@10 | R@10 |
|---|---|---|
| BM25 only | 0.6625 | 0.7799 |
| cosine only | 0.5064 | 0.6618 |
| RRF k = 1 | 0.6596 | 0.8252 |
| RRF k = 10 | 0.6391 | 0.8189 |
| **RRF k = 60** | **0.6057** | 0.7561 |
| weighted RRF k = 60, w_vec = 0.25 | 0.6469 | 0.7932 |
| CC min-max α = 0.5 (untuned default) | 0.6620 | 0.8031 |
| **CC min-max α = 0.3** | **0.6747** | 0.8109 |
| CC z-score α = 0.2 | 0.6797 | 0.8064 |
| CC α = 0.8 (Bruch's strong-model default) | 0.6027 | 0.7506 |

Three readings, with the caveat that a static embedder is a *weak*
semantic leg (cosine alone is 0.16 below BM25; Bruch's dense models were
near parity):

- **Equal-weight RRF at large k flattens the good leg into the bad
  leg's noise.** The curve is monotone in k on this corpus; k = 1–10
  recovers most of the loss, which is the graphiti/Oracle end of the
  range.
- **CC with the weight tuned beats everything, and even the untuned
  α = 0.5 matches BM25 alone while beating RRF-60 by +0.056.** The
  weight is *the* knob and it tracks the legs' relative quality (0.2–0.3
  with a weak vector leg; Bruch's 0.8 with a strong one). Min-max vs
  z-score: ≤ 0.005 at any α.
- **Recall is where fusion earns its keep** (0.78 → 0.81–0.83): even a
  weak vector leg adds hits the lexical leg missed, *provided* the
  fusion does not let it demote the lexical leg's hits.

### 2.3 The counter-position, answered

The no-requirements design chose RRF k = 60 with the argument that CC
"needs labelled queries to set α per corpus; RRF does not. vfs ships to
corpora it has never seen" — and named untuned RRF as its own riskiest
assumption. The sweep answers it: the *untuned* CC (α = 0.5) already
dominates untuned RRF-60 here, and RRF-60 is itself a tuned constant
from a 2009 pilot on a setting unlike ours. Both functions ship with a
default; only one of them has a defensible one. What the counter-position
gets right is the *contract with the router*: whatever fuses inside a
mount must emit a bounded, documented scale so the mount's own ordering
and the `score` column mean something — CC over min-max-normalised legs
is already in [0, 1] and needs no post-normalisation.

### 2.4 Verdict for gap 7

- **Reference fusion: convex combination of per-leg normalised scores**,
  `f = α·norm(vec) + (1−α)·norm(lex)`. Normalise cosine by its
  theoretical range (`(cos + 1)/2`, no window function needed) and BM25
  by min-max over the candidate union (unbounded above; floor 0) —
  Bruch shows α absorbs the difference. Default α = 0.5, documented as
  a knob the evaluation harness tunes per corpus in the 0.3–0.8 range.
  Expressible in SQL on every dialect the engine-matrix study verified —
  the same CTE skeleton as RRF with `MIN()/MAX()` window functions and
  one arithmetic expression — so ADR 007's "reciprocal rank fusion in
  the reference design" is amended at no cost to the statement shape.
- **RRF stays as the rank-only floor** for a leg that yields ranks
  without a comparable score, with a *per-leg* k defaulting small
  (k = 10) for two-leg fusion over shallow lists, and weights exposed.
- The `Fusion` object (ranker API memo) must express both; the verb
  expresses neither.

## 3. Chunks in, entries out: aggregate, then fuse

Every signal scores chunks (the retrieval unit vfs stores: 2 KB
structure-aware pieces with line ranges); the verb returns entries. Dai
& Callan (SIGIR 2019) compared FirstP / MaxP / SumP on Robust04 and
ClueWeb09-B: MaxP wins or ties everywhere a document's relevance can sit
anywhere inside it (Robust04 description queries: 0.491 / **0.529** /
0.524 nDCG@20) — the code and technical-prose case. PARADE's
transformer aggregation beats MaxP only "where relevance signals can be
spread throughout the document", and is a rerank-stage idea, not a
first-stage one.

The order matters more than the operator. **Aggregate inside each leg,
then fuse entries** (lexical-leg §4), because fuse-then-collapse has
three defects: an entry with many mediocre chunks occupies many rank
positions in each chunk list and squeezes other entries out of the fused
window (a SumP-shaped bias the evidence rejects); a rank-based fusion is
defined on positions, and the position an entry "has" after a collapse
is ill-defined (its best chunk's — which *is* MaxP, computed later and
more expensively); and `LIMIT n` must count entries for the verb's
contract to be honest. In SQL, inside each leg:

```sql
lex AS (
  SELECT d.entry_id, MAX(c.score) AS score,
         -- the arg-max chunk rides along for the preview
         ...ROW_NUMBER() OVER (PARTITION BY d.entry_id ORDER BY c.score DESC, c.chunk_id) = 1...
  FROM (chunk scoring) c JOIN lex_docs d ON d.chunk_id = c.chunk_id
  GROUP BY d.entry_id
)
```

Measured cost of the MaxP wrapper: 0.1–0.7 ms at every corpus size in
the lexical study. The engine-matrix study's verified statement fused at
chunk grain and took the max afterwards; the memo's recommendation moves
the `MAX ... GROUP BY entry_id` *into* each leg's CTE, which the same
skeleton expresses. The preview memo needs the top-K (default 3) chunks
per winning entry, not only the arg-max; a `ROW_NUMBER() OVER (PARTITION
BY entry_id …) <= 3` in the same pass yields them.

gbrain's shared `DISTINCT ON (source, slug)` CTE, Oracle's `DOCUMENT`
mode with a `MAX` aggregator, and zoekt's max-line-score-per-file all
land on the same shape (landscape takeaway 3).

## 4. How a static prior enters

Three shapes are in use for a per-entry prior `p ∈ [0, 1]` (centrality,
reads, recency) over a fused score `f`; the study injected two synthetic
priors into the CC α = 0.5 ranker on SciFact — **noise** (uniform per
doc: what a centrality column looks like when the link graph is
unrelated to the queries) and **signal** (a leak-shaped upper bound):

| Prior | Injection | nDCG@10 (base 0.6620) |
|---|---|---|
| noise | extra RRF list, equal weight, k = 60 | **0.4603** (−0.20) |
| noise | multiplicative × (1 + 0.5 p) | 0.6155 (−0.05) |
| noise | multiplicative × (1 + 2 p) | 0.4842 (−0.18) |
| noise | additive + 0.1 p | 0.6561 (−0.01) |
| signal | extra RRF list | 0.7710 |
| signal | multiplicative × (1 + 0.5 p) | 0.7730 |
| signal | multiplicative × (1 + 2 p) | **0.8245** |
| signal | additive + 0.3 p | 0.7736 |

The asymmetry is the design fact: RRF gives every list one vote
regardless of its information content, so an uninformative prior as a
rank list costs a fifth of nDCG, while a *bounded* multiplicative or
additive term caps the damage at its weight and still captures most of
the upside when the prior is real. This agrees with the web-search
record (Craswell et al. SIGIR 2005: a linear weight on a power-law
feature is useless; log/saturation transforms are what work), with
zoekt's history (RRF with file rank → weighted sum → deleted), and with
the independent design's β = 0.15 multiplicative boost.

**Verdict**: priors enter as `f × ∏(1 + β_s · p_s)` over the fused
score, `β_s ≤ 0.5` by default, each `p_s` a reindex-time,
min-max-normalised, log/saturation-transformed stored value (the
signals memo); an absent signal is a missing row → factor 1 →
rank-preserving. Never an extra RRF list.

## 5. Merging across mounts

### 5.1 It is a federated-search problem, not a data-fusion problem

Shokouhi & Si (*Federated Search*, FnTIR 2011) state the constraint
exactly: collections "use different retrieval models and have different
ranking features … the document scores or ranks returned by multiple
collections are not directly comparable". Federated merging assumes
*disjoint* collections — our case: an entry lives in one mount — and is
distinct from data fusion (one collection, several rankers: §2) and
metasearch (overlapping web engines, where RRF and Condorcet were born).
RRF *across* mounts is therefore a category error: with disjoint
collections every document has exactly one rank, and RRF degenerates to
rank interleaving. The simulation confirms it to four decimals (0.4768
vs round-robin 0.4767).

### 5.2 The record's methods, in order of what they require

1. **Round-robin / pseudo-scores** — nothing to learn, no comparability.
2. **CORI merging** — a heuristic linear combination of the collection
   score and the document score; "strongly limits performance".
3. **SSL** (Si & Callan, TOIS 2003) — a centralised sample index; per-
   collection linear regressions from overlap documents; needs ≥ 3
   overlaps per collection and backs off to CORI.
4. **SAFE** (Shokouhi & Zobel, TOIS 2009) — sample-based curve fitting;
   no overlap needed; "minimum cooperation".
5. **Download-and-rerank** (Craswell, Hawking & Thistlewaite 1999) —
   fetch the returned documents, rerank them with one reference model
   over a reference index of term statistics; "comparable to a merging
   scenario where documents are downloaded completely". The
   multilingual-merging line (Si & Callan 2005) does the same. STARTS
   (Gravano 1997) is the cooperative variant: collections return tf/df/N
   with every answer.
6. **ReDDE** — collection *selection*; relevant here only as the knob for
   unequal per-mount limits.

Clay's lean is method 5 with the reference model = BM25 and the
reference index = the union itself: the oldest, most assumption-free
family, and the one every heterogeneous-engines paper falls back to. Its
academic cost objection (downloading documents) does not apply — the
chunk text is already on the result rows. Its known failure modes, each
measured below: statistics from a tiny union; vector-only hits zeroed;
per-mount truncation capping recall; the reranker being a *different*
ranker than the mounts' hybrid; and duplicates across mounts (the
`content_hash` column keys that).

### 5.3 The executed simulation

Three deliberately heterogeneous mounts — A "pgvector-like" (potion-8M
256-d, BM25 1.2/0.75, RRF k = 60, exposes an RRF sum ≈ 0.03), B
"sqlite-like" (potion-4M 128-d, BM25 0.9/0.4, CC α = 0.5, exposes
[0, 1]), C "GENERIC floor" (feature-hashing 256-d, BM25 2.0/1.0, RRF
k = 10 **scaled ×100**) — over random and by-topic (k-means) splits,
per-mount limit m ∈ {10, 20, 50}, corpus top-10 out, ranx metrics.
Whole-corpus ceilings: RRF-60 oracle 0.6057 (SciFact) / 0.2948
(NFCorpus); BM25 0.6625 / 0.3053; CC-0.3 0.6747 / 0.3204.

SciFact nDCG@10 (topic split is the adversarial case for interleaving):

| Strategy | random m=10 | random m=50 | topic m=10 | topic m=50 |
|---|---|---|---|---|
| union recall ceiling @3m | 0.851 | 0.927 | 0.800 | 0.921 |
| (i) naive score sort — today's `Result.top` | 0.2125 | 0.2125 | 0.2743 | 0.2743 |
| (ii) round-robin | 0.4767 | 0.4767 | 0.3647 | 0.3647 |
| (iii) RRF across mounts | 0.4768 | 0.4768 | 0.4014 | 0.4014 |
| (iv-b) z-score then sort | 0.5050 | 0.4945 | 0.4378 | 0.4366 |
| **(v) Clay: union + BM25** | **0.6390** | **0.6527** | **0.6372** | **0.6635** |
| (v′) union + BM25, corpus-wide stats | 0.6684 | 0.6625 | 0.6537 | 0.6627 |
| (vi-b) union + CC(bm25, cosine) | 0.6092 | 0.6578 | 0.5616 | 0.6189 |

NFCorpus (~38 relevant per query — the recall-starved regime): naive
0.14; round-robin 0.26/0.23; z-score 0.27/0.24; **Clay 0.287–0.296**;
corpus-wide stats 0.306–0.310; (vi-b) 0.276–0.299; the union recall
ceiling at 3m is only 0.18 (m = 10) → 0.28 (m = 50).

What the numbers say:

1. **Today's `Result.top` is the worst possible merge** — and the ×100
   scale on mount C is not a straw man: an RRF sum (≈ 0.03), a [0, 1]
   convex score and a raw BM25 (≈ 5–20) are what three real dialect
   backends would expose. With equal scales it is round-robin in
   disguise.
2. **Rank-only merges leave a third of the quality on the table**, and
   are *worse* on the topic split, where the mount holding most of the
   relevant docs is capped at one slot per round.
3. **Per-mount score normalisation barely helps** (0.44–0.51): the
   normalised score of a mount with *no* relevant docs still spans
   [0, 1]. This is the federated record's claim measured — and the
   answer to the independent design's proposal that a normalised
   in-mount scale makes `top(limit)` honest: it makes the scores
   *bounded*, not *comparable*.
4. **Clay's union + BM25 recovers single-index quality**: above the
   RRF-60 oracle by +0.03–0.06 on every SciFact split and limit,
   0.96–1.00 of the honest BM25 ceiling, within 0.005–0.008 of the
   oracle on NFCorpus, and the topic split costs it *nothing* — the
   rerank does not care which mount a document came from.
5. **Union-only statistics cost 0.01–0.03 nDCG, shrinking with m**: the
   corpus-wide-stats variant beats it by +0.029 (SciFact random m = 10)
   and +0.010 (m = 50). Real, modest, and fixable two ways at once —
   fetch deeper, and let mounts export their term statistics.
6. **Zeroed vector-only hits cost ≈ 0 here** (SciFact: 5–14 % of the
   union, at most 3 of 339 relevant docs among them; NFCorpus: 30–50 %
   of the union, hundreds of relevant — yet re-fusing the cosine
   in-process did not beat plain BM25, because these static embedders'
   cosine is the weaker signal). **This result is embedder-conditional**:
   with a dense model at BM25 parity, (vi-b) would be expected to
   overtake (v). The seam must allow it; the default need not use it.
7. **Per-mount truncation is the dominant ceiling on recall-heavy
   corpora** — fetch depth, not merge arithmetic, is the lever.
8. **In-process re-fusion by RRF is consistently the worst union
   strategy** (0.52–0.58) — RRF's equal-vote flattening again.

### 5.4 Verdict on R3

**Adopt the lean, with two amendments.**

1. **Corpus-wide statistics are a `SupportsGlean` requirement** (Clay,
   2026-08-26): every backend's glean answer carries, per query term,
   `(df, N, avgdl)` — three integers per term per mount, one `GROUP BY`
   over the lexical index's term table — so the router's BM25 always
   sums corpus statistics (the STARTS-style cooperative merge). A
   backend that cannot supply them does not implement `SupportsGlean`;
   there is no union-statistics degradation path.
2. **Fetch deeper than the limit.** Each mount answers `limit × 3`,
   **bounded at 256 rows per mount** (Clay, 2026-08-26) —
   `_route_fanout`'s existing `row_cap` changes from `limit` to
   `min(limit·3, 256)` for glean only, and the rerank trims back.

The router: fan out `glean(query, limit·depth)` to every mount in
scope → union the rows, deduplicating on `content_hash` → rerank the
union with one BM25 over the returned chunk text → aggregate chunks to
entries (MaxP, §3) → return the top-`limit`, with a warning-severity
record when any mount's cap truncated the union or when statistics were
union-only. **A single mount in scope skips the rerank entirely** — its
own fused order stands, so the common case pays nothing. Two things the
lean does *not* need: per-mount score normalisation (the mounts' exposed
scores drop out of the merge; they remain the `score` column's
provenance), and any form of cross-mount RRF.

The tokenisation the router's BM25 uses must be the lexical index's own
(engine memo) — the same folding and identifier splitting — or the
merge and the mounts disagree on what a term is.

## 6. The evaluation harness (gap 8)

A ranking change without a relevance set is unmeasurable; every knob
above (α, β, k, depth, K chunks) is set by taste until one exists. Keep
in-tree, deterministic and offline:

- **Golden corpora**: a hand-labelled vfs-native set (≈ 200 files from
  `docs/` + `context/`, ≈ 40 queries, graded qrels in TREC format,
  checked in — the only set that exercises path globs, code tokens and
  entry/chunk aggregation) **and** a downloaded BEIR pair (SciFact for
  precision@1, NFCorpus for recall under truncation) fetched into a
  cache outside the repo and skipped when absent.
- **Embedders**: the offline provider (model2vec potion-base-8M) as the
  semantic default, the zero-dependency hashing embedder as the floor;
  both pinned by content hash of the vectors for one fixed sentence
  (embedding memo).
- **Metrics**: ranx `evaluate` (nDCG@10, MRR@10, recall@10/50),
  `optimize_fusion` for the α/β/k sweeps, `compare` for significance
  when a change claims a gain. ranx is dev-only (numba); `src/` never
  imports it.
- **Determinism pins**: for every golden query the conformance suite
  pins the *ordered* top-10 path list per backend — identical across
  SQLite, Postgres, MariaDB, MySQL, SQL Server and Oracle — which forces
  an explicit total order (`ORDER BY score DESC, entry_id ASC,
  chunk_index ASC`) and a `(score, path)` tie-break in the router's
  rerank, with the fused score rounded to a fixed number of decimals
  *before* the order-by (OpenSearch quantises RRF scores to 10 decimals
  for the same cross-shard reason). The engine-matrix study already
  produced byte-identical top-5 rankings on five engines from one
  statement; this is the pin that keeps it so.
- **Regression gate**: nDCG@10 on each golden corpus may not drop by
  more than 0.005 without an ADR note; strategies (i) and (ii) stay as
  named baselines so the gate has a floor.
- **Before the ADR fixes fork B2**: re-run `sim_merge.py` with a dense
  embedder at BM25 parity — the one embedder-conditional result.

## 7. One rerank seam (gap 13)

Clay's union reranker, a cross-encoder, an LLM listwise reranker and an
MMR diversity stage are all "reorder the merged candidates"; one shape
serves them:

```python
class Reranker(Protocol):
    async def rerank(self, query: str, candidates: Sequence[Candidate], *, limit: int) -> Sequence[Candidate]: ...
```

`Candidate` carries what the router already holds — entry id, path,
chunk text and line bounds, mount, native score, per-leg raw scores,
prior values, term statistics if supplied — so no stage re-fetches.
Stages compose in order on the `VFS` instance (a cross-mount stage
cannot belong to one mount): the BM25 union rerank ships first; a
cross-encoder (LanceDB's `CrossEncoderReranker` shape), an LLM
reranker, or MMR over the cosine column come later. Every stage is a
pure function of its candidates, bounded by the fan-out deadline
(spec 051), and answers with a warning record when skipped for time.
Stages *reorder*; they never retrieve — the union is the contract. ADR
007 holds because stages are configured on the instance, never chosen
per call.

## 8. Recommendation for the ADR

1. **Amend ADR 007's reference fusion** from "reciprocal rank fusion"
   to *convex combination of normalised leg scores*, α = 0.5 default,
   harness-tuned; RRF with a small per-leg k as the rank-only floor;
   both behind one `Fusion` object on the Storage.
2. **Aggregate inside each leg by max, then fuse entries**; `LIMIT n`
   counts entries; the arg-max and top-K chunks ride along for the
   preview.
3. **Priors are bounded multiplicative factors** on the fused score with
   absent = 1; never rank lists.
4. **Cross-mount merge is download-and-rerank**: union of
   `min(limit × 3, 256)` per mount, deduplicated on `content_hash`,
   reranked by one BM25 with corpus-wide statistics — which every
   `SupportsGlean` backend must export — trimmed to `limit`, with a
   truncation record in the envelope; skipped when one mount is in
   scope.
5. **One `Reranker` seam** on the `VFS`, BM25 first.
6. **The harness lands with or before the first backend**, and its
   determinism pin is a conformance-suite row.

## 9. Forks the ADR must close

- **A1** — α as mount config (recommended) vs learned at reindex from a
  stored query set (a later producer writing the same field).
- **A2** — cosine normalised by theoretical range (recommended) vs
  union min-max; BM25 by union min-max (no theoretical ceiling). Bruch:
  absorbed by α either way.
- **A3** — aggregate-then-fuse (recommended; §3) vs the engine study's
  fuse-then-max. Same skeleton; different CTE nesting.
- **B1** — router rerank in Python (recommended first; ≤ a few hundred
  short texts) vs the Rust core. Tokenisation must match the index.
- **B2** — re-fuse the mounts' cosine into the router rerank: **no** by
  default (lost to plain BM25 with static embedders) but carried on the
  row for a reranker stage; re-decide after the dense-embedder re-run.
- **B3** — fetch depth: settled by Clay 2026-08-26 as a constant 3
  bounded at 256 rows per mount; never a strategy selector.
- **C1** — reranker stages on the `VFS` constructor (recommended) vs
  mount config.
- **C2** — may a stage see more than `limit·depth` candidates: no.

## Sources

Studies (this repo): `studies/2026-08-26-glean/fusion-and-merge.md`
(scripts `common.py`, `sim_merge.py`, `sweep_fusion.py`, `oracles.py`;
results `results_scifact.md`, `results_nfcorpus.md`, `sweep_scifact.md`,
`oracles_*.md`, `results_*.json`); `lexical-leg.md` §4;
`engine-matrix.md` §1; `unconstrained-design.md` §5; `landscape.md` §7.

Papers: Cormack, Clarke & Büttcher, SIGIR 2009
(https://doi.org/10.1145/1571941.1572114); Bruch, Gai & Ingber, TOIS
42(1) 2023 (https://doi.org/10.1145/3596512, arXiv 2210.11934); Dai &
Callan, SIGIR 2019 (https://arxiv.org/abs/1905.09217); Li et al.,
PARADE, TOIS 2023 (https://arxiv.org/abs/2008.09093); Shokouhi & Si,
*Federated Search*, FnTIR 5(1) 2011 (https://doi.org/10.1561/1500000010);
Si & Callan, TOIS 21(4) 2003 (https://doi.org/10.1145/944012.944017);
Shokouhi & Zobel, TOIS 27(3) 2009 (https://doi.org/10.1145/1508850.1508852);
Craswell, Hawking & Thistlewaite, ADC 1999; Craswell, Robertson,
Zaragoza & Taylor, SIGIR 2005
(https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/craswell_sigir05.pdf);
"Balancing the Blend", 2025 (https://arxiv.org/abs/2508.01405).

Libraries and docs (refreshed 2026-08-26, read-only): ranx @ 7363db0,
lancedb @ 2fbf6d6, haystack @ 71b0ee6, llama_index @ d802122,
neural-search @ 972d698, zoekt @ a9206004; OpenSearch RRF post
(https://opensearch.org/blog/introducing-reciprocal-rank-fusion-hybrid-search/);
Elasticsearch RRF retriever
(https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion);
Weaviate fusion algorithms
(https://weaviate.io/blog/hybrid-search-fusion-algorithms). Data: BEIR
SciFact and NFCorpus via `ir_datasets` (https://ir-datasets.com/beir.html);
model2vec potion-base-8M/4M (MIT); bm25s (MIT).
