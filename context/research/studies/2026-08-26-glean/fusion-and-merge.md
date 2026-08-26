# Fusion functions and merging top-n lists from heterogeneous mounts

- **Study for**: `context/research/2026-08-26-glean-brief.md` — questions 5
  (fusion function and its parameters) and 10 (merging top-*n* lists from
  heterogeneous mounts); gaps 7 (fusion arithmetic), 8 (evaluation
  harness), 13 (rerank seam).
- **Date**: 2026-08-26
- **Sources** (reference checkouts, read-only; code described, never
  copied):
  - `~/Git/Repos/ranx` @ 7363db0 (2025-08-07) — `ranx/fusion/*`,
    `ranx/normalization/*`, `ranx/meta/{fuse,optimize_fusion}.py`
  - `~/Git/Repos/lancedb` @ 2fbf6d6 (2026-08-26) —
    `python/python/lancedb/rerankers/{base,rrf,linear_combination,cross_encoder}.py`
  - `~/Git/Repos/haystack` @ 71b0ee6 (2026-08-26) —
    `haystack/components/joiners/document_joiner.py`, `haystack/utils/misc.py`
  - `~/Git/Repos/llama_index` @ d802122 (2026-08-20) —
    `llama-index-core/llama_index/core/retrievers/fusion_retriever.py`
  - `~/Git/Repos/neural-search` @ 972d698 (2026-08-25) —
    `processor/normalization/{MinMax,ZScore,RRF}*Technique.java`,
    `processor/combination/*`
  - `~/Git/Repos/bm25s` @ a213158, `~/Git/Repos/model2vec` @ 280b341
    (simulation dependencies, both MIT)
  - Papers and docs: see *Sources* at the end (URLs).
- **Scripts and results**: `fusion-and-merge/` beside this file —
  `common.py`, `sim_merge.py`, `sweep_fusion.py`, `oracles.py`, and the
  executed outputs `results_scifact.md`, `results_nfcorpus.md`,
  `sweep_scifact.md`, `oracles_*.md`, `results_*.json`.

## Question

Two decisions hide inside "glean returns one fused list":

1. **Within one mount**, how are the vector leg and the lexical leg fused,
   with which parameters, and how do static priors (centrality, reads,
   recency) enter without wrecking the ranking when they are absent or
   uninformative?
2. **Across mounts** that use different embedders, different lexical
   engines and different in-mount fusion functions, how does the router
   turn *k* top-*n* lists with incomparable scores into the corpus
   top-*n*? Clay's lean — fetch each mount's top-*n*, re-score the union
   in-process with one BM25 over the returned text, take the top-*n* —
   is to be tested against the academic record and an executed
   simulation, not assumed.

Today's router does neither: `VFS.glean` fans out with
`_route_fanout(row_cap=limit)` and `_cap_rows` trims with `Result.top(k)`,
a single sort by `Observation.score` whose docstring concedes the scores
are "only loosely comparable" (`src/vfs/base.py:1252`, `:2635`;
`src/vfs/results/envelope.py:580`).

---

## Part A — Fusion within one mount

### A.1 The two canonical functions

**Reciprocal rank fusion** (Cormack, Clarke & Büttcher, SIGIR 2009):
`RRF(d) = Σ_r 1 / (k + rank_r(d))`. The paper fixed `k = 60` "during a
pilot investigation" of four Wumpus configurations on TREC collections and
reports that "k = 60 was near-optimal, but that the choice was not
critical"; RRF beat Condorcet fuse, CombMNZ and the best individual run by
4–5 % MAP. Two things are easy to forget about that result: the fused
inputs were *30 full-depth TREC runs* (deep lists, many systems), and the
constant exists "to mitigate the impact of high rankings by outlier
systems" — the setting is many noisy voters, not two complementary legs.

**Convex combination** of normalised scores (`f = α·norm(sem) +
(1-α)·norm(lex)`) is the other tradition (Fox & Shaw 1994's CombSUM with
normalisation; Lee 1997; Vogt & Cottrell 1999's linear combination). Bruch,
Gai & Ingber (TOIS 42(1), 2023, "An Analysis of Fusion Functions for
Hybrid Retrieval") is the modern controlled comparison:

- **CC beats RRF** on every dataset in Table 2 (nDCG@1000, TM2C2 α = 0.8
  vs RRF η = 60): MS MARCO 0.454 vs 0.425, NQ 0.542 vs 0.514, HotpotQA
  0.699 vs 0.675, **SciFact 0.753 vs 0.730**, NFCorpus 0.327 vs 0.312 (all
  significant at p < 0.01). The lexical/semantic legs alone were 0.698 /
  0.681 on SciFact — SciFact is a corpus where BM25 already carries most
  of the signal, which matters for reading Part C.
- **Normalisation is a "rather small detail"**: a CC of min-max scores
  with weight α is rank-equivalent to a CC of z-scores with some α′ (their
  §4, stated as a theorem), so the learned weight absorbs the normaliser. They use a
  "theoretical min-max" (`φ_tmm`: divide by the leg's theoretical range,
  e.g. cosine ∈ [-1, 1]) where one exists and plain min-max otherwise.
- **RRF is parametric and sensitive**: rewriting it as
  `1/(η_lex + π_lex) + 1/(η_sem + π_sem)` shows one constant per leg;
  sweeping η ∈ {1..100} per leg "NDCG swings wildly", the good region is
  off-diagonal (η_lex > η_sem in-domain, the opposite out-of-domain), and
  a tuned RRF does not transfer across domains. RRF also "ignores the raw
  scores and discards information about their distribution" — the
  Lipschitz argument: a tiny score change can flip ranks and produce a
  large fused-score jump.
- **CC is sample-efficient**: α converges with a handful of labelled
  queries, and α = 0.8 (semantic-heavy, with strong dense models)
  generalised zero-shot.
- **Missing scores**: fusion is computed over the *union* of the two
  top-*k* sets, and "when a document in the union set is not present in
  one of the top-k sets we compute its missing score prior to fusion" —
  i.e. they re-score the union with both models rather than imputing zero.
  For RRF, ranks of union documents are approximated "by ranking documents
  within the union set".

The practitioner record agrees on direction. OpenSearch's RRF launch post
reports RRF "3.86 % lower than traditional score-based methods" on
nDCG@10 across six datasets, in exchange for ~1.5 % lower latency and no
score-scale assumptions. The 2025 "Balancing the Blend" study (arXiv
2508.01405, 11 datasets, FTS + sparse + dense + tensor) adds the
"weakest link" warning: one bad leg drags the fusion down, so leg quality
must be assessed before combining.

### A.2 What the libraries choose (surveyed, not copied)

| Library | Fusion menu | Default and parameters | Missing-leg handling |
|---|---|---|---|
| **ranx** (`ranx/fusion`, 25 methods) | CombSUM/MNZ/ANZ/MAX/MIN/MED/GMNZ, RRF, ISR, log-ISR, logN-ISR, Borda, Condorcet, weighted Borda/Condorcet, WSUM, WMNZ, RBC, BayesFuse, PosFuse, ProbFuse, SegFuse, SlideFuse, MAPFuse, Mixed | `fuse(runs, norm="min-max", method="wsum")`; RRF `k=60` hard default (`rrf.py`: `1/(k+i+1)` then CombSUM); normalisers min-max, max, sum, z-score (`zmuv`), rank, borda; `optimize_fusion(qrels, runs, norm, method, metric)` grid-searches the trainable methods' hyper-parameters (weights for wsum/wmnz, k for rrf, …) against qrels | Score-based methods treat absence as 0 (`res.get(doc_id, 0.0)` in `wsum`); RRF only sums the lists a doc appears in |
| **OpenSearch neural-search** (`normalization-processor`, `score-ranker-processor`) | normalisation ∈ {`min_max` (with optional `lower_bounds`/`upper_bounds` per sub-query and a clamp/ignore mode), `l2`, `z_score`, `rrf` (`rank_constant` default 60, range 1..10 000)} × combination ∈ {`arithmetic_mean`, `geometric_mean`, `harmonic_mean`} with per-sub-query `weights` | `MinMax`: `MIN_SCORE = 0.001`, single result → 1.0; `ZScore`: std-based, same floor; `ArithmeticMean.combine` skips scores `< 0` and divides by the sum of the weights actually used (so a missing leg is *ignored*, not zeroed) | The RRF technique computes ranks globally across shards (a priority queue over `(score, shardId)`) — the multi-shard rank problem is exactly our multi-mount rank problem, and they solve it by pooling before ranking |
| **LanceDB** (`rerankers/`) | `RRFReranker(K=60)`, `LinearCombinationReranker(weight=0.7 vector, fill=1.0)`, `MRRReranker`, plus model rerankers: CrossEncoder, ColBERT (answerdotai), Cohere, Jina, OpenAI, Voyage, watsonx | One `Reranker` ABC with `rerank_hybrid(query, vector_results, fts_results)`, `rerank_vector`, `rerank_fts`, `rerank_multivector`; every implementation must emit `_relevance_score` (`util.check_reranker_result`) | Linear combination: a doc absent from one leg is penalised with `1 - fill` (= 0 by default); RRF: sums whichever lists it is in |
| **haystack** `DocumentJoiner` | `concatenate` (keep max score of duplicates), `merge` (weighted sum, weights normalised to 1), `reciprocal_rank_fusion` (weighted; `k = 61` because the code ranks 0-based), `distribution_based_rank_fusion` (DBSF: rescale each list by `mean ± 3σ`, then keep max) | default `concatenate`; `weights` ignored for concatenate/DBSF | `merge`: missing score counted as 0; DBSF: a list whose σ = 0 scores 0 ("uninformative for the query") |
| **llama_index** `QueryFusionRetriever` | `reciprocal_rerank` (k = 60 hard-coded), `relative_score` (min-max per list × retriever weight ÷ num_queries, then sum), `dist_based_score` (same with `mean ± 3σ` bounds), `simple` (max of raw scores) | default `simple`; `retriever_weights` normalised to sum 1 | absent = contributes nothing to the sum |

Reading across them: **k = 60 is cargo** (every library inherits Cormack's
pilot constant unchanged; Bruch shows it is not neutral), **weights are
the universal escape hatch** (weighted RRF, weighted sum, per-sub-query
weights), **DBSF is a normaliser, not a fusion function** (it is min-max
with robust bounds), and **the only library with a tuning loop is ranx**
(`optimize_fusion`) — which is why it belongs in the harness, not the
product.

### A.3 Executed sweep on one index (SciFact, potion-8M + BM25)

`sweep_fusion.py` fuses BM25 (k1 = 1.2, b = 0.75) and potion-base-8M
cosine (a 256-d static embedder, offline and deterministic) over the whole
SciFact corpus, top-100 per leg, top-10 out. Full table in
`fusion-and-merge/sweep_scifact.md`.

| Ranker | nDCG@10 | MRR@10 | R@10 |
|---|---|---|---|
| BM25 only | 0.6625 | 0.6310 | 0.7799 |
| cosine only | 0.5064 | 0.4666 | 0.6618 |
| RRF k = 1 | 0.6596 | 0.6106 | 0.8252 |
| RRF k = 10 | 0.6391 | 0.5864 | 0.8189 |
| **RRF k = 60** | **0.6057** | 0.5624 | 0.7561 |
| RRF k = 1000 | 0.6012 | 0.5593 | 0.7478 |
| weighted RRF k = 60, w_vec = 0.25 | 0.6469 | 0.6055 | 0.7932 |
| CC min-max α = 0.2 | 0.6744 | — | 0.8031 |
| **CC min-max α = 0.3** | **0.6747** | 0.6354 | 0.8109 |
| CC z-score α = 0.2 | 0.6797 | — | 0.8064 |
| CC min-max α = 0.5 | 0.6620 | 0.6205 | 0.8031 |
| CC α = 0.8 (Bruch's strong-model default) | 0.6027 | — | 0.7506 |

Findings, with the caveat that a static embedder is a *weak* semantic leg
(cosine alone is 0.16 nDCG below BM25 — Bruch's dense models were roughly
at parity with BM25 on SciFact):

- **RRF k = 60 is worse than BM25 alone here** (-0.057 nDCG). With two
  legs of unequal quality, equal-weight RRF at a large k flattens the good
  leg's ordering into the bad leg's noise. Small k (1–10) recovers most of
  it: the nDCG curve is monotone in k on this corpus. That is the
  Bruch result reproduced on a corpus and embedder they never used.
- **CC with a tuned α beats every RRF variant and both legs**, +0.012 over
  BM25 and +0.069 over RRF-60, and the optimum α is 0.2–0.3 (lexical-heavy)
  because the vector leg is weak. Bruch's α = 0.8 is for strong dense
  models; the weight is *the* knob and it depends on the legs' relative
  quality. Min-max vs z-score differs by ≤ 0.005 nDCG at any α — the
  normaliser is indeed a small detail.
- **Weighted RRF is a coarser version of the same knob**: w_vec = 0.25
  recovers +0.04 of RRF-60's loss but never reaches CC.
- **Recall@10 is where fusion earns its keep** (0.78 → 0.81–0.83): even a
  weak vector leg adds relevant docs the lexical leg missed, provided the
  fusion does not let it also demote the lexical leg's hits.

### A.4 How a static prior enters

Three shapes are in use. `p ∈ [0, 1]` is a per-entry prior (centrality,
read count, recency), `f` the query-dependent fused score.

| Shape | Formula | Doc in one leg only | Prior absent (zero-edge mount) | Prior uninformative |
|---|---|---|---|---|
| **Extra RRF list** | `f + 1/(k + rank_p(d))` | unaffected by leg count; but every union doc gets a prior rank, so the prior *always* votes with the same weight as a retrieval leg | a constant prior gives all-tied ranks: rank-neutral only if ties share one rank; with sequential tie-breaks it becomes an arbitrary reorder | **catastrophic** — see below |
| **Multiplicative boost** | `f · (1 + β·p)` | proportional: a single-leg doc with small `f` gains little in absolute terms | `p = c` scales every score by `(1 + βc)`: rank-preserving by construction | damage bounded by β |
| **Additive term** (learned linear / CC with one more feature) | `f + λ·p` | additive: a weak single-leg doc can be lifted over a strong two-leg doc if λ·p is large | `p = c` shifts every score equally: rank-preserving | damage bounded by λ |

`sweep_fusion.py` injects two synthetic priors into the CC α = 0.5 ranker
on SciFact: **noise** (uniform random per doc — what a centrality column
looks like on a corpus whose link graph is unrelated to the queries) and
**signal** (`0.5·[doc is relevant to some query] + 0.5·noise`, a
leak-shaped upper bound for "centrality that happens to correlate with
relevance"):

| Prior | Injection | nDCG@10 (base 0.6620) |
|---|---|---|
| noise | extra RRF list, equal weight, k = 60 | **0.4603** (-0.20) |
| noise | multiplicative ×(1 + 0.5p) | 0.6155 (-0.05) |
| noise | multiplicative ×(1 + 2p) | 0.4842 (-0.18) |
| noise | additive +0.1p | 0.6561 (-0.01) |
| noise | additive +0.3p | 0.6124 (-0.05) |
| signal | extra RRF list | 0.7710 |
| signal | multiplicative ×(1 + 0.5p) | 0.7730 |
| signal | multiplicative ×(1 + 2p) | **0.8245** |
| signal | additive +0.1p | 0.7023 |
| signal | additive +0.3p | 0.7736 |

The asymmetry is the design fact: **as an RRF list, an uninformative prior
costs a fifth of nDCG** because RRF gives every list one vote regardless of
its information content, while a *bounded* multiplicative or additive term
caps the damage at its weight and still captures most of the upside when
the prior is real. This is the reason to fuse priors as weighted terms in
a score-space combination, not as extra rank lists — and to default their
weight to a small value that an evaluation run can raise per corpus.

### A.5 Part A verdict (gap 7)

- **Reference fusion: convex combination of per-leg normalised scores**
  (`α·norm(vec) + (1-α)·norm(lex)`), min-max over the candidate union with
  a theoretical floor where one exists (cosine → `(cos + 1)/2`; BM25 →
  min-max over the union, floor 0). Default α = 0.5 with a documented
  expectation that the harness tunes it per corpus in the 0.3–0.8 range.
  It is expressible in SQL on every dialect (two CTEs, `MIN()/MAX()`
  window functions, one arithmetic expression) — the same statement shape
  as RRF, so ADR 007's "RRF in the reference design" costs nothing to
  amend.
- **Keep RRF as the no-score fallback** — the GENERIC floor where a leg
  yields ranks but no comparable score (e.g. an engine FTS whose score is
  an opaque integer). Use a *per-leg* k, default small (k = 10, not 60)
  for two-leg fusion over shallow lists; expose weights.
- **Priors enter as bounded multiplicative terms** `∏(1 + β_s·p_s)` over
  the fused score, each `β_s` defaulting to ≤ 0.5 and each `p_s` min-max
  normalised over the corpus at reindex time (so it is a stored column,
  not a query-time computation). An absent signal is a missing column →
  factor 1 → rank-preserving. Never an extra RRF list.

---

## Part B — Merging across mounts: the federated-search record

### B.1 The problem as the literature states it

Shokouhi & Si's *Federated Search* (FnTIR 5(1), 2011, ch. 4) opens the
merging chapter with the constraint exactly: "collections may use
different retrieval models and have different ranking features. Thus, the
document scores or ranks returned by multiple collections are not
directly comparable and are not reliable for merging. The goal of result
merging algorithms is to calculate a global score for each document that
is comparable to the scores of documents returned by other collections."
Federated merging assumes disjoint collections (overlap "none or
negligible"), which is our case (an entry lives in one mount) — and
distinguishes it from *data fusion* (one collection, several rankers —
Part A) and *metasearch* (overlapping web engines, where RRF/Condorcet
were born). Cross-mount merge is a federated-search problem, not a
data-fusion problem; RRF across mounts is a category error, and Part C
shows it degenerates to interleaving.

### B.2 The methods, in order of what they require

1. **Round-robin / pseudo-scores.** When collections report no scores,
   the broker assigns rank-derived pseudo-scores (1, 0.999, …; Rasolofo
   et al. 2003) and interleaves. Nothing to learn, no comparability.
2. **CORI merging** (Callan 1995/2000). Normalise the collection-selection
   score `C′ = (C - C_min)/(C_max - C_min)` and the document score `D′`
   likewise, then `D″ = (D′ + 0.4·D′·C′) / 1.4`. A heuristic linear
   combination of "how good is this collection for this query" and "how
   good is this document in its collection". The survey: "the heuristic
   weighting scheme strongly limits the performance of CORI merging as it
   may not adapt to different types of queries and collections."
3. **SSL — semi-supervised learning** (Si & Callan, TOIS 21(4), 2003).
   The broker keeps a *centralised sample index* (CSI) of documents
   sampled from every collection (query-based sampling, ~300 docs per
   collection in their testbeds). At query time the query is sent to the
   selected collections *and* to the CSI. Documents that appear in both a
   collection's list and the CSI's list ("overlap documents") give
   training pairs (collection score, CSI score); a per-collection linear
   regression `S_C(d) = a_i·S_i(d) + b_i` (Eq. 11–12, least squares) maps
   every returned score into CSI space, where they are comparable. It
   needs ≥ 3 overlap documents per collection, uses the top-10 overlaps,
   and backs off to CORI when > 40 % of collections lack training points.
   When engines are identical a single model with a collection-score term
   suffices (`D′ = a·E + b·E·C`); when engines differ ("KL-divergence
   produces negative likelihoods while INQUERY produces probabilities in
   [0, 1]") each collection needs its own model, the overlap rate drops,
   and "the broker may need to receive longer result lists from
   collections or download some documents on the fly". Reported gains
   over CORI (INQUERY + language-model engines, Table III): P@10 +10.4 %
   on trec123 and +98.9 % on trec4-kmeans, where CORI's normalisation
   fails outright.
4. **SAFE — sample-agglomerate fitting estimate** (Shokouhi & Zobel, TOIS
   27(3), 2009). Also CSI-based but needs **no overlap**: rank the CSI for
   the query; each collection's sampled documents form a *sub-ranking* of
   that collection's full ranking, so a curve fit over the sample's
   (rank, CSI score) pairs — scaled by `|c|/|S_c|` — predicts the CSI
   score of the collection's *unseen* top-ranked documents from their
   ranks alone. Designed for "minimum cooperation" (uncooperative engines
   that return ranks and nothing else).
5. **Download-and-rerank** (Craswell, Hawking & Thistlewaite 1999). Fetch
   the returned documents (they fetched the first 4 KB of each) and rerank
   them with one reference model using a *reference index of term
   statistics*; "the effectiveness of their approach is comparable to that
   of a merging scenario where documents are downloaded completely." The
   multilingual-merging line (Si & Callan 2005; Si et al. 2008) does the
   same: download the top-ranked documents from each list and score them
   with one centralised model, finding logistic regression "more robust"
   than linear. STARTS (Gravano 1997) and Kirsch (2003) are the
   cooperative variant: each collection returns tf/df/N with every answer
   so the broker can compute one similarity itself.
6. **ReDDE** (Si & Callan 2003a) is *collection selection*, not merging:
   it estimates the number of relevant documents per collection from the
   CSI ranking scaled by size (`R(c,q) ≈ Σ_{d∈S_c} P(R|d)·|c|/|S_c|`). It
   matters here only as the knob for *unequal per-mount limits* — a mount
   estimated to hold most relevant docs should get a larger share of the
   union budget.

### B.3 What the record says about Clay's lean

Clay's proposal — each mount returns its top-*n* with chunk text; the
router builds one BM25 over the union and takes the top-*n* — is method 5,
**download-and-rerank with the reference model = BM25 and the reference
index = the union itself**. It is the oldest and most robust family in
the survey, and the one every "heterogeneous engines" paper falls back
to when scores are incomparable (multilingual CLEF merging is exactly
"download the top-ranked documents and score them with one central
model"). The known properties:

**Strengths (all confirmed in Part C):**

- *Comparable by construction.* Every candidate is scored by one function
  over one vocabulary; no per-mount regression, no training pairs, no
  sample index to maintain, no assumption about what a mount's score
  means. It needs only what the mounts already return (path, chunk text).
- *Independent of the mounts' rankers.* A mount can change embedder,
  lexical engine or fusion function and the merge does not notice; a
  lexical-only mount and a vector-only mount merge the same way.
- *Cheap at glean's scale.* The union is `k·n` chunks (30–150 for
  n ∈ {10, 50}); a BM25 over 150 short texts is microseconds in Rust and
  low milliseconds in Python. The academic cost objection (downloading
  documents) does not apply — the text is already in the result rows.

**Failure modes (the record's, then what Part C measured):**

1. *Statistics from a tiny union.* IDF and average length are computed
   over 30–150 documents, so a query term that is rare in the corpus but
   present in many union docs (precisely because every mount matched on
   it) gets a *low* IDF; document-length normalisation is relative to the
   union's average. Craswell used "a reference index of term statistics"
   to avoid exactly this. Part C measures the penalty at 0.01–0.03 nDCG
   on SciFact and 0.01–0.02 on NFCorpus, shrinking as *n* grows.
2. *Vector-only hits are zeroed.* A chunk with no lexical overlap with the
   query — retrieved by a mount's vector leg on meaning — scores 0 under
   BM25 and sorts to the bottom in an order decided by tie-breaks. The
   merge throws away the semantic leg entirely. Part C measures how many
   union docs this hits (5–14 % on SciFact, 30–50 % on NFCorpus) and how
   many relevant docs are among them (≈ 0 on SciFact, hundreds on
   NFCorpus).
3. *Per-mount truncation caps recall.* A mount's top-*n* is the only
   window the router sees; a mount holding 20 relevant docs contributes at
   most *n* of them. The union's recall at `k·n` is a hard ceiling on any
   merge — SSL's authors note the same ("receive longer result lists").
   Part C reports the ceiling per *n*.
4. *The reranker is a different ranker.* The union is re-ordered by BM25,
   not by the mounts' hybrid function, so cross-mount glean is
   lexical-only glean at the top. Where the mounts' vector legs are the
   better signal (paraphrase-heavy corpora with a strong embedder), the
   merge undoes their work. Part C's (vi) variants re-fuse the vector
   signal in-process to test the fix.
5. *Duplicate and near-duplicate handling* is the router's job in every
   federated design (survey §4.5, GHV); the union may contain the same
   content from two mounts. Not measured here; the `content_hash` column
   already exists to key it.

**Alternatives the record offers, and why they are worse here.** CORI
needs a collection-selection score glean does not compute; SSL/SAFE need
a sampled central index kept in sync with every mount (a second index to
build under the reindex lease, for a gain SSL measured over CORI, not over
download-and-rerank); per-mount score normalisation (min-max, z-score)
assumes the mount's score distribution is informative, which Part C shows
it is not when the mounts' fusion functions differ. The cooperative
STARTS-style variant — mounts export `(df, N, avgdl)` alongside hits so
the router computes BM25 with global statistics — is the one alternative
that is strictly better than the union-only rerank, and it is cheap: a
few integers per query term per mount.

---

## Part C — Executed simulation

### C.1 Setup (reproducible; `fusion-and-merge/sim_merge.py`)

- **Corpora with real labels** (via `ir_datasets`, BEIR): **SciFact** test
  (5,183 abstracts, 300 claims with qrels, 339 judgments, ~1.1 relevant
  per query) and **NFCorpus** test (3,633 docs, 323 queries, graded,
  ~38 relevant per query — a sparse-recall regime). No hand labelling.
- **Environment**: throwaway `uv venv` (Python 3.13.11) with ranx 0.3.21,
  bm25s 0.3.11, model2vec 0.9.0, ir-datasets 0.6.3, numpy 2.5.2. Nothing
  touched the project's `pyproject.toml`/lock. Seed 20260826 everywhere;
  ties broken by document position; k-means is a 30-iteration spherical
  k-means in numpy.
- **Three mounts, deliberately heterogeneous** (`MOUNTS` in
  `sim_merge.py`):

  | Mount | Embedder | BM25 (k1, b) | In-mount fusion | Exposed score |
  |---|---|---|---|---|
  | A "pgvector-like" | potion-base-8M (256-d) | 1.2, 0.75 | RRF k = 60 | RRF sum (~0.03) |
  | B "sqlite-like" | potion-base-4M (128-d) | 0.9, 0.4 | CC min-max α = 0.5 | [0, 1] |
  | C "GENERIC floor" | signed feature-hashing of uni+bigrams (256-d) | 2.0, 1.0 | RRF k = 10, **scaled ×100** | ~1–15 |

  A second mount set makes C **lexical-only** (no vector leg). Each mount
  scores both legs over its candidate union (top-100 per leg) — what a
  database backend holding both columns does in one statement — and
  returns its top-*m* with the exposed score, raw BM25 and raw cosine.
- **Splits**: random thirds, and *by topic* (k-means k = 3 on potion-8M
  embeddings, sizes 1424/1404/2355 on SciFact) so relevant docs cluster in
  one mount.
- **Per-mount limit** m ∈ {10, 20, 50}; every strategy must return the
  corpus top-10 from the three lists.
- **Oracle**: mount A's stack over the whole corpus (RRF k = 60). Because
  Part A showed RRF-60 is not the best whole-corpus ranker on these
  corpora, `oracles.py` also reports BM25-only and CC α = 0.3 over the
  whole corpus; treat those as the honest ceiling.
- **Metrics**: ranx `ndcg@10`, `mrr@10`, `recall@10`; plus the union's
  recall ceiling at `3m` and the count of union docs with zero BM25
  overlap (and how many of those are relevant).

Strategies:

- (i) naive sort by exposed score — today's `Result.top`;
- (ii) round-robin interleave by local rank;
- (iii) RRF across the three lists (k = 60);
- (iv-a/b) per-mount min-max / z-score of the exposed score, then sort;
- (v) **Clay**: union + BM25 (1.2, 0.75) built on the union's text only;
- (v′) union + BM25 with **corpus-wide** statistics (the STARTS-style
  cooperative variant: mounts export df/avgdl, or the router keeps a
  global lexical index);
- (vi-a) union + RRF of (union-BM25 rank, per-mount min-max cosine rank);
- (vi-b) union + CC 0.5·minmax_mount(cos) + 0.5·minmax(union BM25);
- (vi-c) as vi-b with corpus-wide BM25 statistics.

### C.2 Whole-corpus ceilings

| Whole-corpus ranker | SciFact nDCG@10 | NFCorpus nDCG@10 |
|---|---|---|
| BM25 only | 0.6625 | 0.3053 |
| potion-8M cosine only | 0.5064 | 0.2434 |
| RRF k = 60 (the sim's "oracle") | 0.6057 | 0.2948 |
| RRF k = 5 | 0.6501 | 0.3096 |
| CC min-max α = 0.3 | **0.6747** | 0.3204 |
| CC min-max α = 0.5 | 0.6620 | **0.3205** |

### C.3 SciFact — hybrid mounts A/B/C (full tables: `results_scifact.md`)

nDCG@10 (recall@10 in parentheses). Oracle RRF-60 = 0.6057 (0.7561);
honest ceiling BM25 = 0.6625 (0.7799), CC-0.3 = 0.6747 (0.8109).

| Strategy | random m=10 | random m=20 | random m=50 | topic m=10 | topic m=20 | topic m=50 |
|---|---|---|---|---|---|---|
| union recall ceiling @3m | 0.851 | 0.886 | 0.927 | 0.800 | 0.863 | 0.921 |
| zero-overlap union docs (relevant) | 5.6 % (0) | 7.1 % (2) | 11.4 % (2) | 5.8 % (0) | 8.5 % (2) | 13.8 % (3) |
| (i) naive score sort | 0.2125 (0.284) | 0.2125 | 0.2125 | 0.2743 (0.367) | 0.2743 | 0.2743 |
| (ii) round-robin | 0.4767 (0.748) | 0.4767 | 0.4767 | 0.3647 (0.611) | 0.3647 | 0.3647 |
| (iii) RRF across mounts | 0.4768 (0.746) | 0.4768 | 0.4768 | 0.4014 (0.612) | 0.4014 | 0.4014 |
| (iv-a) min-max then sort | 0.4693 | 0.4624 | 0.4619 | 0.3717 | 0.3716 | 0.3669 |
| (iv-b) z-score then sort | 0.5050 (0.752) | 0.5032 | 0.4945 | 0.4378 (0.622) | 0.4380 | 0.4366 |
| **(v) Clay: union BM25** | **0.6390 (0.765)** | **0.6404** | **0.6527 (0.769)** | **0.6372 (0.750)** | **0.6515** | **0.6635 (0.781)** |
| (v′) union BM25, global stats | 0.6684 (0.789) | 0.6657 | 0.6625 (0.780) | 0.6537 (0.761) | 0.6607 | 0.6627 (0.780) |
| (vi-a) union RRF(bm25, cos) | 0.5759 | 0.5838 | 0.5731 | 0.5271 | 0.5197 | 0.5177 |
| (vi-b) union CC(bm25, cos) | 0.6092 (0.742) | 0.6401 | 0.6578 (0.786) | 0.5616 | 0.5947 | 0.6189 |
| (vi-c) union CC, global stats | 0.6067 | 0.6259 | 0.6452 | 0.5612 | 0.5784 | 0.6018 |

With mount C lexical-only the picture is the same (naive 0.25/0.33;
z-score 0.56/0.51; **Clay 0.626–0.645 random, 0.639–0.659 topic**; global
stats 0.658–0.667; vi-b 0.634–0.659 random, 0.597–0.609 topic).

### C.4 NFCorpus — hybrid mounts A/B/C (full tables: `results_nfcorpus.md`)

nDCG@10. Oracle RRF-60 = 0.2948; honest ceiling CC-0.5 = 0.3205, BM25
= 0.3053.

| Strategy | random m=10 | random m=20 | random m=50 | topic m=10 | topic m=20 | topic m=50 |
|---|---|---|---|---|---|---|
| union recall ceiling @3m | 0.183 | 0.219 | 0.276 | 0.185 | 0.216 | 0.278 |
| zero-overlap union docs (relevant) | 33 % (43) | 39 % (111) | 48 % (377) | 35 % (42) | 40 % (120) | 50 % (377) |
| (i) naive score sort | 0.1399 | 0.1399 | 0.1399 | 0.1433 | 0.1433 | 0.1433 |
| (ii) round-robin | 0.2580 | 0.2580 | 0.2580 | 0.2329 | 0.2329 | 0.2329 |
| (iii) RRF across mounts | 0.2371 | 0.2371 | 0.2371 | 0.2142 | 0.2142 | 0.2142 |
| (iv-b) z-score then sort | 0.2651 | 0.2645 | 0.2653 | 0.2392 | 0.2419 | 0.2461 |
| **(v) Clay: union BM25** | **0.2873** | **0.2898** | **0.2961** | **0.2898** | **0.2908** | **0.2956** |
| (v′) union BM25, global stats | 0.3097 | 0.3090 | 0.3077 | 0.3076 | 0.3091 | 0.3056 |
| (vi-b) union CC(bm25, cos) | 0.2764 | 0.2871 | 0.2989 | 0.2682 | 0.2835 | 0.2896 |

### C.5 What the numbers say

1. **Today's `Result.top` is the worst possible merge.** A naive sort by
   exposed score scores 0.21–0.27 nDCG on SciFact against a 0.61–0.67
   ceiling and 0.14 on NFCorpus against 0.30, because mount C's ×100 scale
   wins every query. The scale factor was injected deliberately, but it is
   not a strawman: an RRF sum (≈ 0.03), a [0, 1] convex score and a raw
   BM25 (≈ 5–20) are what three real dialect backends would expose, and
   *any* scale mismatch produces this. Even with equal scales, naive sort
   is only round-robin in disguise.
2. **Rank-only merges (round-robin, cross-mount RRF) leave a third of the
   quality on the table**: 0.36–0.48 on SciFact. Cross-mount RRF is
   provably rank interleaving when mounts are disjoint (each doc has one
   rank); the numbers confirm it (0.4768 vs 0.4767). On the topic split
   it is worse than on the random split because a mount holding most of
   the relevant docs is capped at one slot per round.
3. **Per-mount score normalisation (min-max, z-score) barely helps**
   (0.44–0.51) because the normalised score of a mount that has *no*
   relevant docs still spans [0, 1]. This is the federated-search
   record's claim ("scores are not comparable") measured: normalising an
   uninformative distribution does not make it informative. z-score beats
   min-max consistently (+0.03–0.07) — the DBSF intuition — but neither
   is close.
4. **Clay's union + BM25 rerank recovers the single-index quality and
   more.** On SciFact it beats the RRF-60 oracle by +0.03–0.06 nDCG on
   every split and limit, and reaches 0.96–1.00 of the honest BM25
   ceiling; on NFCorpus it is within 0.005–0.008 of the RRF oracle at
   m = 10 and matches it at m = 50. The topic split — the adversarial
   case for interleaving — costs it *nothing* (0.637 vs 0.639), because
   the rerank does not care which mount a doc came from.
5. **Union-only statistics cost 0.01–0.03 nDCG, shrinking with m.** The
   corpus-wide-stats variant (v′) beats (v) by +0.029 (SciFact random
   m = 10), +0.017 (topic m = 10), +0.010 (m = 50) and +0.022/+0.018/+0.012
   on NFCorpus. At m = 50 on the SciFact topic split the two are equal
   (0.6635 vs 0.6627). The failure mode is real, modest, and disappears
   as the union grows — which argues for a per-mount fetch depth larger
   than the caller's limit (2–5×) *and* for mounts exporting their term
   statistics when they can.
6. **Zeroed vector-only hits cost nothing on SciFact and are not the
   bottleneck on NFCorpus.** On SciFact 5–14 % of union docs have no
   lexical overlap but at most 3 of 339 relevant docs are among them.
   On NFCorpus 30–50 % of the union has no overlap and hundreds of
   relevant docs are in that set — yet re-fusing the vector signal
   in-process (vi-b) does not beat the plain BM25 rerank, because these
   static embedders' cosine is a weaker relevance signal than BM25 even
   on those docs. The failure mode is *conditional on the embedder*: with
   a dense model at parity with BM25 (Bruch's SciFact numbers), (vi-b)
   would be expected to overtake (v). The seam must allow it; the
   default need not use it.
7. **Per-mount truncation is the dominant ceiling on recall-heavy
   corpora.** NFCorpus union recall at 3m is 0.18 (m = 10) → 0.28
   (m = 50) against ~38 relevant per query; no merge can exceed it. On
   SciFact (one relevant per query) the ceiling is 0.80–0.93 and the
   rerank reaches ~0.77 recall@10 against 0.78 single-index. Fetch depth,
   not merge arithmetic, is the lever here.
8. **In-process re-fusion with RRF (vi-a) is consistently the worst of the
   union strategies** (0.52–0.58) — RRF's equal-vote flattening again,
   now between a strong union-BM25 rank and a weak cosine rank. If the
   vector signal is re-fused at the router, it should be a weighted
   score-space combination, never RRF.

---

## Bearing on vfs

### Verdict on Clay's lean

**Adopt it, with two amendments.** The record classifies it as
download-and-rerank — the robust, assumption-free family that federated
search falls back to whenever engines are heterogeneous — and the
simulation shows it recovering single-index quality (within 0.01 nDCG of
the RRF oracle on NFCorpus; above it on SciFact) where every
score-normalisation and rank-interleaving alternative loses 0.1–0.4 nDCG.
Its measured costs are modest and have known fixes:

1. **Statistics: prefer corpus-wide, fall back to union-only.** Let a
   backend's glean answer carry, per query term, its `(df, N, avgdl)`
   — three integers per term per mount — so the router's BM25 uses summed
   corpus statistics (the STARTS-style cooperative merge, +0.01–0.03
   nDCG). A mount that cannot (a foreign backend) contributes nothing and
   the router degrades to union statistics for its share. The lexical
   index study should confirm the term-frequency table can answer `df`
   cheaply; it is one `GROUP BY` over the query's terms.
2. **Fetch deeper than the limit.** Each mount answers `limit × depth`
   with depth defaulting to 3 (bounded, e.g. ≤ 100 rows per mount). The
   union-stats penalty halves from m = 10 to m = 50 and recall's ceiling
   rises 0.85 → 0.93 on SciFact. This is a per-mount row cap already
   modelled by `_route_fanout(row_cap=…)`; it changes from `limit` to
   `limit·depth` for glean only, and the rerank trims back to `limit`.

Two things the lean does *not* need: per-mount score normalisation (the
mounts' exposed scores can be dropped from the merge entirely — they are
useful only for the mount's own ordering and for the `score` column's
provenance), and any form of cross-mount RRF.

### Recommendation and forks

**In-mount fusion (gap 7).** Convex combination of min-max-normalised leg
scores, α = 0.5 default, with the harness (below) tuning α per golden
corpus. RRF with a small per-leg k stays as the floor for a leg that
yields ranks without scores. Static priors enter as bounded
multiplicative factors on the fused score (`× ∏(1 + β_s·p_s)`, β_s ≤ 0.5
default, p_s a reindex-time min-max-normalised column); an absent signal
is factor 1. Never as an extra RRF list (Part A.4: -0.20 nDCG from an
uninformative one).

- *Fork A1*: α as a mount-config value (default 0.5) vs α learned at
  reindex from a stored query set. Recommend config; learning is a later
  producer that writes the same field.
- *Fork A2*: min-max over the candidate union vs the theoretical range.
  Recommend theoretical for cosine (`(cos+1)/2`, no window function
  needed) and union min-max for BM25 (unbounded above); Bruch shows the
  choice is absorbed by α.

**Cross-mount merge (R3 / question 10).** The router (a) fans out
`glean(query, limit·depth)` to every mount in scope, (b) unions the rows
(deduplicating on `content_hash`), (c) reranks the union with one BM25
over the returned chunk text using corpus-wide statistics where mounts
supplied them and union statistics otherwise, (d) aggregates chunks to
entries (the aggregation study's choice), (e) returns the top-`limit`
with a warning-severity record when the union was truncated by any
mount's cap or when statistics were union-only. A single mount in scope
skips (c) entirely — the mount's own fused order stands.

- *Fork B1*: rerank in Python vs in the Rust engine (`crates/vfs-core`).
  The union is ≤ a few hundred short texts; Python is fine for the first
  landing, and the tokenisation must match the lexical index's (the
  same folding/stemming as the preview's bolding, gap 12).
- *Fork B2*: whether the router re-fuses the mounts' vector cosine into
  the rerank (vi-b). Recommend **no** by default — it needs per-mount
  normalisation and lost to plain BM25 with static embedders — but keep
  the cosine on the row so a reranker stage can use it (see the seam).
- *Fork B3*: `depth` as a hidden constant (3) vs a `glean` parameter. ADR
  007 forbids strategy selectors; a fetch-depth is a budget, not a
  strategy, but recommend a constant first and a spec-051-style budget
  knob if latency demands it.

**Evaluation harness (gap 8).** Keep in-tree, under `tests/ranking/`
(or `benchmarks/`), the following, all deterministic and offline:

- *Golden corpora*: a small hand-labelled vfs-native set (≈ 200 files
  drawn from `docs/` + `context/` with ≈ 40 queries and graded qrels in
  TREC format, labelled by hand and checked in) **and** a downloaded BEIR
  pair (SciFact, NFCorpus) fetched by a `uv run` script into a cache
  outside the repo and skipped when absent. SciFact exercises
  precision@1, NFCorpus exercises recall under truncation; the vfs-native
  set exercises path globs, code tokens and the entry/chunk aggregation
  no BEIR set has.
- *Embedders*: the offline provider (model2vec potion-base-8M, 256-d,
  MIT, ~30 MB, no network at test time) as the deterministic default;
  the hashing embedder as the zero-dependency floor. Both are pinned by
  content hash of the produced vectors for one fixed sentence.
- *Metrics*: ranx `evaluate` with `ndcg@10`, `mrr@10`, `recall@10`,
  `recall@50`; `optimize_fusion` for α/β/k sweeps; `compare` for
  significance when a change claims a gain. ranx is a dev-only
  dependency (numba), never imported by `src/`.
- *Determinism pins*: for every golden query, the conformance suite pins
  the top-10 *ordered* path list per backend — identical across SQLite,
  Postgres, MariaDB, MySQL, SQL Server, Oracle — which forces the fused
  statement to carry an explicit total order (`ORDER BY score DESC,
  entry_id ASC, chunk_index ASC`) and the router's rerank to break ties
  on `(score, path)`. Floating-point drift across engines is handled by
  rounding the fused score to a fixed number of decimals *before* the
  order-by (OpenSearch quantises RRF scores to 10 decimals for the same
  reason).
- *Regression gate*: nDCG@10 on each golden corpus may not drop by more
  than 0.005 without an ADR note; the merge simulation's strategies (i)
  and (ii) are kept as named baselines so the gate has a floor to
  compare against.

**Rerank seam (gap 13).** One stage, one shape:

```
class Reranker(Protocol):
    async def rerank(self, query: str, candidates: Sequence[Candidate], *, limit: int) -> Sequence[Candidate]
```

where `Candidate` carries `(entry_id, path, chunk text, line bounds,
mount, native score, per-leg raw scores, prior columns, term stats if
supplied)` — everything the router already has in hand, so no stage
re-fetches. The router composes stages in order: the BM25 union rerank
(ships first), then optional stages — a cross-encoder (LanceDB's
`CrossEncoderReranker` shape: score every `(query, text)` pair, sort),
an LLM listwise reranker (score or permute the top-*k*), a diversity
stage (MMR over the cosine column). Every stage is a pure function of the
candidates; every stage is bounded by the fan-out budget (spec 051) and
answers with a warning record if it was skipped for time. The seam
lives in Storage-adjacent router code, not on the verb — ADR 007's "no
strategy selector" holds because the stages are configured on the VFS
instance, not chosen per call.

- *Fork C1*: stage configuration on the `VFS` constructor vs on mount
  config. Recommend the `VFS` (a cross-mount stage cannot belong to one
  mount).
- *Fork C2*: whether a stage may see more than `limit·depth` candidates.
  No — the union is the contract; stages reorder, they do not retrieve.

### Open items for the memo

- The lexical-index study decides whether `df/N/avgdl` per query term is
  cheap on every dialect (it is one aggregate over the term table); if
  not, the union-stats penalty (0.01–0.03 nDCG) is the accepted cost.
- The aggregation study decides whether the router reranks chunks and
  aggregates after (MaxP over reranked chunks) or aggregates first.
- Re-run `sim_merge.py` with a dense embedder at BM25 parity (fastembed
  BGE-small is Apache-2.0) before the ADR fixes fork B2 — the one result
  here that is embedder-conditional.

---

## Sources

Papers:

- Cormack, Clarke & Büttcher, "Reciprocal rank fusion outperforms
  Condorcet and individual rank learning methods", SIGIR 2009 —
  https://doi.org/10.1145/1571941.1572114 ; PDF
  https://cormack.uwaterloo.ca/cormacksigir09-rrf.pdf
- Bruch, Gai & Ingber, "An Analysis of Fusion Functions for Hybrid
  Retrieval", ACM TOIS 42(1) art. 20, 2023 —
  https://doi.org/10.1145/3596512 ; arXiv https://arxiv.org/abs/2210.11934
- Si & Callan, "A semisupervised learning method to merge search engine
  results", ACM TOIS 21(4):457–491, 2003 —
  https://doi.org/10.1145/944012.944017 ; PDF
  https://www.cs.cmu.edu/~callan/Papers/tois03-lsi.pdf
- Shokouhi & Si, "Federated Search", Foundations and Trends in IR
  5(1):1–102, 2011 — https://doi.org/10.1561/1500000010 ; PDF
  https://www.microsoft.com/en-us/research/wp-content/uploads/2011/01/now.pdf
- Shokouhi & Zobel, "Robust result merging using sample-based score
  estimates", ACM TOIS 27(3), 2009 —
  https://doi.org/10.1145/1508850.1508852
- Si & Callan, "Relevant document distribution estimation method for
  resource selection" (ReDDE), SIGIR 2003 (as summarised in the survey
  §3.2).
- Craswell, Hawking & Thistlewaite, "Merging results from isolated search
  engines", ADC 1999 (as summarised in the survey §4.6).
- Callan, "Distributed information retrieval", in *Advances in
  Information Retrieval*, 2000 (CORI merging; survey Eq. 4.1–4.2).
- Mazzeschi, "Distribution-Based Score Fusion (DBSF)", 2023 —
  https://medium.com/plain-simple-software/distribution-based-score-fusion-dbsf-a-new-approach-to-vector-search-ranking-f87c37488b18
- "Balancing the Blend: An Experimental Analysis of Trade-offs in Hybrid
  Search", 2025 — https://arxiv.org/abs/2508.01405

Product docs:

- OpenSearch, "Introducing reciprocal rank fusion for hybrid search"
  (2.19) — https://opensearch.org/blog/introducing-reciprocal-rank-fusion-hybrid-search/
- Elasticsearch, RRF retriever reference (`rank_constant` 60,
  `rank_window_size`, no weights) —
  https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion
- ranx — https://github.com/AmenRa/ranx (Bassani, ECIR 2022 "ranx"; ECIR
  2023 "ranx.fuse")

Data and tools used by the simulation:

- BEIR SciFact and NFCorpus via `ir_datasets` (`beir/scifact/test`,
  `beir/nfcorpus/test`) — https://ir-datasets.com/beir.html
- model2vec potion-base-8M / 4M (MIT) —
  https://huggingface.co/minishlab/potion-base-8M
- bm25s (MIT) — https://github.com/xhluca/bm25s
