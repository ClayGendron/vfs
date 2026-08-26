# Index-time centrality and read-derived signals as ranking inputs, and the customizable ranker API

- **Study for**: `context/research/2026-08-26-glean-brief.md` — questions 7
  (centrality in the reindex pipeline), 8 (read-derived signals), 9 (the
  customizable ranker API); gaps 5 (read metrics as writes) and 6
  (centrality needs a graph). Constrained by ADR 007
  (`context/decisions/007-fused-glean-search-surface.md`): a parameter
  may select *what* to answer, never *how*.
- **Date**: 2026-08-26
- **Sources** (reference checkouts under `~/Git/Repos`, read-only, cited
  and described — no code copied):
  - zoekt @ `a9206004` (2026-08-26) — `index/score.go`,
    `index/contentprovider.go`, `index/builder.go`, `api.go`, and the
    history commits `f6d0aa00` (#523, 2023-01-27) and `c7f1e697`
    (#853, 2024-10-31).
  - HippoRAG @ `2f52a86` — `src/hipporag/HippoRAG.py` (`run_ppr`,
    `graph_search_with_fact_entities`).
  - graphify `v8` @ `43d54ac` — `graphify/analyze.py`, `graphify/cluster.py`.
  - LightRAG @ `812f2d5d` (`lightrag/operate.py`), graphrag @ `f40e9a2`
    (`data_model/schemas.py`, `index/workflows/prune_graph.py`), cognee @
    `690c0ec02` (`modules/retrieval/graph_report_retriever.py`).
  - rustworkx @ `e02dc7ce` (0.18.0; `rustworkx/rustworkx.pyi`,
    `src/link_analysis.rs`, `src/centrality.rs`, `pyproject.toml`,
    `Cargo.toml`), networkx @ `cfc6b79`.
  - neural-search @ `972d698` (OpenSearch hybrid processors:
    `processor/normalization/*`, `processor/combination/*`).
  - Papers and docs by URL in *Sources* at the end.
  - vfs live tree: `src/vfs/models/rows.py` (`edges`, `chunks`, `meta`),
    `src/vfs/storage/backends/database/{indexing,offload,reads,backend}.py`,
    `src/vfs/storage/protocol.py` (`SupportsGlean`).
- **Executed**: `centrality-and-read-signals/graph_signals.py` (two real
  graphs from this repo) and `centrality-and-read-signals/scaling.py`
  (synthetic 10⁴/10⁵/10⁶-node graphs) in a throwaway venv
  (networkx 3.6.1, scipy 1.18.1, rustworkx 0.18.1, numpy); outputs beside
  them as `*.out.txt` / `*.json`. The project's lockfile was not touched.

## Question

When `glean` fuses a vector leg and a lexical leg inside the engine, what
is a *static, query-independent* signal worth — graph centrality computed
at reindex over the `edges` table, and a popularity prior rolled up from
reads — how is each captured, stored, refreshed, and folded into the
fusion, and what API lets a deployment register signals, weights, a
fusion function, and a rerank stage without the verb growing a strategy
selector?

---

## Part A — centrality as a static document prior

### A.1 The web-search record

**PageRank as a prior.** Brin & Page (1998) combine PageRank with the
text score but do not say how; Craswell et al. (SIGIR 2005) point out that
the original paper "did not describe how PageRank should be combined with
a query dependent baseline", and that combination is hard because
PageRank is power-law distributed (on TREC .GOV the mean is 1, the top
value 4,522, the median 0.21 — a linear sum "would lead to most pages
getting almost no score and a few getting a very large score").

**Priors in the language-modelling frame** — Kraaij, Westerveld &
Hiemstra (SIGIR 2002): three non-content features for entry-page search
— page length, number of incoming links, and URL form (root/subroot/
path/file). In-degree was binned on a log scale with one prior per bin
and combined multiplicatively with the LM probability. URL form was the
strongest: over 70% of entry pages at rank 1 and up to 89% in the top 10.
The lesson that transfers: the *cheapest* structural feature (a path
shape) beat the link feature for the navigational task.

**What PageRank actually adds** — Upstill, Craswell & Hawking (TOIS 2003):
across five query sets and three corpora, all query-independent methods
(in-degree, URL-type, two PageRank variants) beat random on a
content-only baseline, but only URL-type still helped over an anchor-text
baseline. Their ADCS 2003 companion ("Predicting fame and fortune:
PageRank or indegree?") found PageRank and in-degree strongly correlated
on company home pages and spam pages, with limited added value for
PageRank over the raw in-link count.

**How to fold a static feature in** — Craswell, Robertson, Zaragoza &
Taylor (SIGIR 2005, FLOE). Reranking the BM25 top 1000 with
`final = BM25 + f(S)`:

| transform of static S | tuned parameters | test MAP (baseline 0.430) |
|---|---|---|
| linear `w·S` | w = 0.005 | 0.439 |
| log `w·log S` | w = 0.20 | 0.508 |
| saturation `w·S/(k+S)` | w = 1.34, k = 1.36 | 0.515 |
| sigmoid `w·Sᵃ/(kᵃ+Sᵃ)` | w = 1.8, k = 1, a = 0.6 | **0.523** |
| in-degree, sigmoid | w = 3.6, k = 5, a = 0.2 | 0.489 |
| URL length, sigmoid (decreasing) | w = 4.5, k = 4, a = 0.5 | 0.477 |
| PageRank + URL length | — | 0.532 |

Three findings bind design: (1) a linear weight on a power-law feature
is useless — it must pass through log or a saturating sigmoid on log(S);
(2) the ordering of usefulness was PageRank > in-degree > URL length >
click distance, but **after PageRank was added, the tuned weight of
in-degree went to zero** — link measures are redundant with one another,
so ship one; (3) they list "aggregate clickthrough, visit frequency or
dwell time statistics" as static features that "may also prove useful",
to be transformed the same way — the popularity prior of Part B belongs
in the same slot as centrality. They also contrast rank-based combination
("cannot fall foul of PageRank's power law", but throws away score
information) with score-based combination after a transform (preferred
when you control the signal); zoekt's history below reached the same
verdict independently.

**The measures.** PageRank is the stationary distribution of a damped
random walk (α = 0.85 conventionally). Katz (1953) is the attenuated path
count `x = Σₖ αᵏ (Aᵀ)ᵏ·1` — with α small it is in-degree plus a decayed
two-hop term, a "reference count with decay"; it converges only for
α < 1/λ_max, which must be estimated per graph (our experiment computed
λ_max and set α = 0.9/λ_max). HITS (Kleinberg 1999) yields authority and
hub scores by mutual reinforcement; it was designed as a *query-time*
measure over a root set, and as a global index-time score it is captured
by the largest tightly-knit cluster — visibly so in our data (A.4).
In-degree is one `GROUP BY`.

### A.2 Code-search practice: Sourcegraph and zoekt

Sourcegraph's indexed-ranking doc (the page now 403s to fetchers; the
search-engine snippet is quoted in *Sources*) describes file rank as
"the number of inbound references from any other file in the available
code graph ... inspired by PageRank", computed from SCIP, with zoekt
consuming it "as an important file signal" and laying shards out so
important files are searched first.

The zoekt checkout tells the rest of the story, and it is the most
instructive prior art in this study:

- **Before #523** (the `FileMatch.Ranks` / `UseDocumentRanks` era, e.g.
  #466): ranks were fused with match scores by reciprocal rank fusion —
  the removed code reads "k = 60 is arbitrary but reportedly works well
  (RRF; Cormack et al., 2009)".
- **#523 (2023-01-27, "simplify score combination strategy")** replaced
  RRF with a weighted sum: "In my experience, this is much easier to
  debug and tune compared to RRF. We're in full control of the ranking
  signals, and can make sure they're bounded + meaningful, so using a sum
  seems totally fine." The file rank entered as
  `scoreFileRankFactor (9000) × min(1, log₂count/32)` — a log-scaled,
  clamped reference count. The same commit **removed index sorting by
  file rank**: "From my testing, it didn't really make a difference to
  improving result quality."
- **#853 (2024-10-31, "removing document ranks")**: "Document ranks was
  an experimental feature of Sourcegraph. We have already removed the
  code in Sourcegraph in the last release." The `ranks` TOC section is
  now `unusedSimple`.

What zoekt ships today at `a9206004` as its static priors: index-time
document order by a rank vector (`index/builder.go` `rank()`): skipped
last, then not-generated, not-vendored, not-test, shorter name, more
symbols, shorter content, present on more branches, original order; and
at query time (`index/score.go` `scoreFile`)
`Score = 10⁷·trunc(matchScore) + 100·repoRank + 10·docOrderScore`, where
`repoRank ∈ [0, 65535]` is `monthsSince1970(latestCommitDate)` — or, when
a `priority` is configured, `priority/(5000+priority)·65535`, a
saturation transform of exactly Craswell's `S/(k+S)` shape — and
`docOrderScore = 1 − doc/len(boundaries)`. In BM25 mode, "low priority"
categories (test, vendored, generated, binary) have term frequencies
divided by 5. So the static priors that survived at Sourcegraph are
**recency, file category, and name/size shape** — not link centrality.
The lesson for vfs is not "centrality is worthless" (their corpus was
monorepo code with a reference graph; ours may be a wiki) but that a
static prior must be cheap, bounded, log-scaled, additive, and easy to
turn off — and that the evidence for link rank in code search was thin
enough that the largest practitioner deleted it.

### A.3 Graph-RAG practice

- **HippoRAG** (`HippoRAG.py:2003–2210`) runs *personalized* PageRank at
  **query time**: reset probabilities are the query's matched phrase
  nodes (weighted by fact-query similarity, top-k) plus passage nodes
  weighted by min-max-normalized dense scores × 0.05; damping 0.5;
  undirected projection; igraph's `prpack`. The output ranks passages.
  This is a query-dependent diffusion over a KG, the opposite of an
  index-time global prior — and it presupposes an extracted
  phrase/passage graph vfs does not have. Not comparable to question 7;
  relevant only as the future "extracted references" producer's consumer.
- **LightRAG** (`operate.py:5908–5931`): node degree fetched in batch and
  stored as `"rank": d` on each retrieved entity; it orders context
  building, not a fused result list.
- **graphrag**: `NODE_DEGREE = "degree"` is a stored node column; used by
  `prune_graph` (`min_node_degree`, `max_node_degree_std`) and community
  report ranking (`community_context.py:242` sorts by rank attributes).
- **cognee** (`graph_report_retriever.py:49–66`): `nx.pagerank` for "hub
  nodes" in an insight *report*, with an explicit fallback to degree when
  scipy is missing ("never build a dense N×N matrix"). A report, not a
  ranker.
- **graphify v8** (`analyze.py`): "god nodes" = plain degree (`G.degree()`
  sorted, with exclusions for builtins); "surprising connections" =
  cross-community edges (Leiden via graspologic, networkx Louvain as
  fallback, `cluster.py`) scored with a peripheral-to-hub bonus, or edge
  betweenness when no communities exist; `suggest_questions` uses
  sampled betweenness. Nothing in graphify ranks search results by these
  metrics — they feed the human-facing report.

The field's convergence: degree/in-degree everywhere as the cheap
structural measure; PageRank appears either in reports or as query-time
PPR; nobody in the study set folds an index-time PageRank into hybrid
retrieval fusion.

### A.4 What graph does vfs have?

Two structures: the **`edges` table** (`rows.py:443` —
`(source_id, target_id, edge_type, weight, distance)`, both directions
indexed, user-minted, no extractor) and the **directory tree**. Measured
on this repository as a stand-in for a note/wiki corpus (Markdown
relative links plus backticked `.md` paths across `context/` and
`docs/`, 440 files):

- 615 edges; **111 files isolated; 233 of 440 (53%) have zero
  in-degree**. Half the corpus has no prior even on a link-rich corpus.
- Spearman ρ between measures: in-degree/PageRank 0.977, in-degree/Katz
  0.975, Katz/PageRank 0.966; HITS authority vs the others 0.65–0.74.
- The top lists show the character of each: in-degree and Katz agree on
  the hub research memos and `open-questions.md`; PageRank promotes two
  2026-08-25 memos with few but well-linked citers; HITS hubs are the
  spec-072 pipeline documents (a dense cluster).

On the `src/vfs` import graph (49 modules, 173 edges) the measures
diverge more (in-degree/PageRank ρ = 0.58) because the graph is tiny and
PageRank's flow through `vfs` (the package root) and `vfs.native`
inflates them; HITS authority vs PageRank ρ = 0.09 — HITS is the wrong
global measure.

**Worth on a link-rich corpus**: a real navigational prior — the same
hub-page effect Kraaij and Craswell measured — with in-degree capturing
almost all of it at one `GROUP BY`. **Worth on a bare tree**: none; zero
edges means the signal does not exist.

**How a zero-edge mount must degrade.** Absent, not zero. In score
fusion, imputing 0 for every entry and then min-max normalizing divides
by zero or yields a constant column; in RRF, an all-tied list adds the
same constant to every candidate — harmless, but the deployment now
believes it has a graph signal it does not have. The rule: the signal
leg joins the fusion only when the signals table holds rows for that
signal in the current generation; otherwise the compiled statement omits
the leg and the envelope reports it (a warning-severity record in the
spirit of grep's truncation record, gap 9). On a *sparse* graph (53%
zero here), the signal stays present and the transform maps 0 to the
floor (`log1p(0) = 0`, `S/(k+S) = 0`): unlinked entries get no boost,
which is the honest semantics.

**Directory adjacency as a fallback graph — no.** Same-parent edges make
every file's in-degree its sibling count, so centrality becomes
"directory size", rewarding exactly the large flat directories zoekt
demotes (tests, vendored, generated). Parent→child edges make PageRank a
function of depth and fan-out only — a depth prior in disguise, and one
that PageRank computes expensively. The tree is a partition, not a
citation structure; an edge should mean "this refers to that". If a
structural prior is wanted where no links exist, declare the real thing:
a **path-shape prior** (segment count, name length — Kraaij's URL form,
Craswell's URL length, zoekt's `squashRange(len(name))`), which is a
column expression, not a graph. It is the one non-link feature that still
helped after PageRank in SIGIR 2005 (MAP 0.523 → 0.532).

---

## Part B — read-derived signals

### B.1 What a "click" is when the reader is an agent

A web click is a human choice among visible alternatives; the click
models exist because that choice is filtered by examination. An agent
over MCP receives the whole `glean` result list and typically reads the
top entries in order, so its reads are close to a deterministic function
of rank — the **cascade model** (examine top-down, stop when satisfied;
Craswell et al. 2008) with examination probability near 1 at the top
ranks and a hard cut where the agent's context budget ends. Position
bias is therefore not a perturbation to correct but the dominant term.
Two further confounders: reads reach `read` from `ls`/`tree`/`glob`
navigation as often as from `glean`, and vfs has no session or
impression record linking a read to the result list that produced it.

### B.2 The unbiased / counterfactual learning-to-rank record

- **Joachims, Swaminathan & Schnabel (WSDM 2017)**: position-based
  propensity model `P(click) = P(examine | rank) · P(click | rel,
  examined)`; the inverse-propensity-scored empirical risk
  `Σ rank(y)/Q(o=1|x,ȳ,r)` over clicked results is unbiased if every
  relevant result has a positive propensity; Propensity SVM-Rank; and
  propensities estimated by a swap intervention (swap rank k with rank r
  for a small slice of traffic). Their synthetic curve (Fig. 1, Yahoo
  LTR data, η = 1 bias) crosses the production ranker only around
  ~10⁴ training clicks and keeps improving to ~10⁶; below that the naive
  and propensity-weighted learners are both worse than the baseline.
- **Oosterhuis (arXiv 2206.12204, 2022)**: counterfactual estimation
  "can only produce unbiased methods for click behavior based on affine
  transformations" — the guarantees rest on the click model being of a
  narrow form, and neither click-modelling nor pairwise approaches can
  be unbiased for all plausible behaviours.
- **Click models** (Chuklin, Markov & de Rijke 2015, *Click Models for
  Web Search*): PBM (examination depends on position only), cascade
  (top-down, stop at first click), DBN (satisfaction vs attractiveness,
  Chapelle & Zhang 2009). All are fitted from repeated impressions of the
  same query — which "is unrealistic in many retrieval settings (e.g.,
  personal collection search)", as Joachims et al. note explicitly; vfs
  mounts are exactly that setting.

**Verdict at vfs scale.** A mount sees tens to thousands of reads a day
with no impression log, no repeated-query volume, and a reader whose
clicks are rank. A learned or de-biased model is starved and its
unbiasedness premises fail. What is defensible is what Craswell 2005
named among static features — **a popularity prior**: a time-decayed
read count, log-scaled, saturating, with a small weight, entering the
fusion in the same slot as centrality. Its known pathology is the
rich-get-richer loop (reads follow rank, rank follows reads); the
mitigations are the log/saturation transform (a 100× read gap becomes a
~2× signal gap), exponential decay (a half-life bounds how long a hub
stays a hub), a low weight, and opt-in default-off. The impression-log
fork (record which glean result list a read came from, so a propensity
correction becomes possible later) is named in *Bearing on vfs* and not
recommended now.

### B.3 How production systems store it

Two shapes: **an in-row counter** (`UPDATE entries SET reads = reads + 1`)
or **an append-only event log rolled up periodically**. The counter is
what search engines avoid: every read becomes a write on a hot row; on
Postgres each increment is a new tuple version and a row lock that
serializes concurrent readers of the same popular file; on SQLite it is
the single writer; on read replicas it is impossible. vfs's read path
makes the cost concrete: `DatabaseStorage.read` runs through
`_execute(op, fn)` (`backend.py:594–620`) — one session per op with
`op_execution_options(profile, writer=False)` so every chunked statement
observes one committed snapshot, under `with_retry`; `read_rows`
(`reads.py:108`) "only executes SELECTs; none begins or commits". A
counter update would turn every read into `_execute_write`'s writer
transaction (`BEGIN IMMEDIATE` on SQLite, the write lock held from the
first read) and defeat the read-only pin. Vespa and Elasticsearch both
model the popularity feature as an *attribute/field the application
updates on its own cadence* (Vespa `attribute(popularity)` in the
first-phase example; Elasticsearch `rank_feature`/`field_value_factor`
over a `popularity` field), not as something the query path writes.

### B.4 Recommended capture design

- **Which verbs count**: `read` only. `stat`, `ls`, `tree`, `glob`,
  `grep`, `glean` are navigation and search, not consumption; counting
  them measures the agent's loop, not the entry's value. A `read` of a
  batch of paths counts once per entry.
- **Opt-in**: a mount-level setting (`read_signal=ReadSignal(half_life_days=30)`
  or `None`, default `None`). Off means no event table writes and no
  `reads` signal rows, so the leg is absent (Part A.4 rule).
- **Batched append, never inside the read transaction**: the read op
  returns from its read-only session first; the host buffers
  `(entry_id, user_id, read_at)` events in memory and flushes them as one
  chunked bulk `INSERT` (bounded by `chunked(..., parameter_budget)`) on
  a size/time threshold (e.g. 256 events or 5 s) and on `close()`,
  through a short writer transaction of its own. A lost buffer on crash
  loses at most one flush window of popularity — advisory data, no
  correctness claim. The event row is narrow: `read_events(id, entry_id,
  user_id NULL, read_at)`.
- **Roll-up at reindex** (Part C): `reads` signal value per entry =
  `log1p(Σ_events 2^(−(now − read_at)/half_life))`; events older than
  ~5 half-lives are deleted after roll-up (the residual weight is < 4%),
  which bounds the table. Between reindexes the signal is stale, like
  every derived structure — the freshness posture of gap 1 applies
  uniformly.
- **Half-life**: 30 days default; a knob on `ReadSignal`. The transform
  and half-life are part of the signal's options hash so a change forces
  a recompute.
- **Privacy / multi-tenant**: every read signature already carries
  `user_id: str | None` and the row model has no ACL columns (`rows.py`)
  — vfs has no per-user visibility today, so a *global* popularity prior
  leaks nothing that a `glean` result list does not already reveal. But
  the event table is an access log: it must be opt-in, its retention
  horizon declared (the 5-half-life sweep), and `user_id` stored only if
  the deployment asks (a `record_users` flag). Per-user popularity ("what
  *this* user reads") is a personalization feature, not a static prior —
  it needs the user in the query path and a per-(user, entry) signal —
  and is a named fork, not part of the reference design.

---

## Part C — storing and refreshing signals in the reindex pipeline

### C.1 A `signals` table vs columns on `entries`

| | `signals(entry_id, signal, value, computed_at)` PK `(entry_id, signal)` | columns on `entries` |
|---|---|---|
| adding a signal | insert rows | `ALTER TABLE` per signal, per dialect |
| absence | no row → leg absent (Part A.4) | `NULL` vs 0 ambiguity; a column always "exists" |
| read cost | one `LEFT JOIN` per signal leg on the entry PK | free |
| rename | keyed by entry identity like `chunks`/`edges` — zero rows touched | same |
| refresh | delete+insert or upsert, chunked | chunked `UPDATE` |
| unknown dialects | plain table, no engine feature | `ALTER` under `GENERIC` |

Recommend the table. It is sparse by construction (a zero-edge mount
holds no `centrality` rows, an opted-out mount no `reads` rows), it is
schema-stable as signals are added by configuration, and the join is on
the same `ULIDKey` the `chunks`→`entries` join already pays. Keep a
`generation` (or `computed_at`) column so a partially refreshed signal is
detectable, and a per-signal `options_hash` in `meta`-style bookkeeping
(the gram index's `format_version`/`options_hash` fingerprint is the
model) so a transform or half-life change invalidates the signal.

### C.2 Refresh under the reindex discipline

`indexing.py`'s docstring fixes the phase structure: claim the lease →
Phase A `chunk_dirty` (offloaded split) → Phase B `build_epoch` (postings
under a fresh epoch, invisible until published) → Phase C `publish_epoch`
(version-guarded `encoded` flips plus the CAS epoch-pointer flip in one
transaction) → reclaim. Signals slot in as a phase between A and B (or
after C — they are independent of the gram epoch):

1. **Extract** the graph (`SELECT source_id, target_id FROM edges` joined
   to live entries, keyset-paginated so no statement grows with the
   graph) and the event roll-up (`SELECT entry_id, read_at FROM
   read_events`), into arrays.
2. **Compute** off the event loop through `call_offloaded` (the same hop
   chunk splitting and posting builds take; the pool follows the host's
   close, so a close mid-compute serves it inline, verb-sized, as
   documented in `offload.py`). Heartbeat the lease between extract,
   compute, and write.
3. **Write** with the current-generation stamp, chunked by the parameter
   budget, then delete rows of the previous generation for that signal.
   Because a signal is advisory, it need not ride the epoch pointer:
   in-place generation replacement in one writer transaction per signal
   (or per chunk, with the query reading `MAX(generation)`) is enough — a
   torn read between chunks yields a slightly stale prior, never a wrong
   result. The epoch-scoped double-generation-plus-pointer machinery
   exists for the gram index because a torn posting set loses matches;
   priors do not have that failure mode.

The freshness posture follows gap 1: a new entry has no signal until the
next reindex (no boost — the floor), a deleted entry's rows go with the
generation sweep.

### C.3 Computing PageRank/Katz on 10⁵–10⁶ nodes: measured

Synthetic directed preferential-attachment graphs (~4–5 edges per node),
Apple Silicon laptop, single process (`scaling.py`):

| nodes / edges | networkx pagerank (scipy) | networkx Katz | rustworkx pagerank | rustworkx Katz | rustworkx HITS | numpy power iteration, 20 it | pure Python, 20 it | SQLite iterative SQL, 20 it (per it) |
|---|---|---|---|---|---|---|---|---|
| 10⁴ / 33 k | 0.09 s | 0.03 s | 0.007 s | 0.001 s | 0.005 s | 0.004 s | 0.047 s | 0.43 s (0.02 s) |
| 10⁵ / 416 k | 0.27 s | 1.03 s | 0.038 s | 0.014 s | 0.089 s | 0.041 s | 0.65 s | 6.7 s (0.32 s) |
| 10⁶ / 4.8 M | 4.37 s | 23.5 s | 0.74 s | 0.28 s | 1.55 s | 0.76 s | 15.6 s | 94 s (4.5 s) |

Graph construction is not free either: building the networkx `DiGraph`
at 10⁵ cost 0.55 s (rustworkx 0.22 s), i.e. more than the algorithm.

Reading the table against CLAUDE.md's dependency rule:

- **networkx** is pure Python but `nx.pagerank` *requires scipy* (the
  import fails without it — cognee's fallback-to-degree exists for this
  reason). That is the heaviest dependency of the four for the least
  speed.
- **rustworkx** is the fastest (Rust, abi3-py310 wheels, numpy the only
  dependency — `pyproject.toml`, `Cargo.toml` `abi3-py310`). It has no
  pure-Python fallback: an environment without a wheel has no
  `rustworkx`. vfs's own rule for native code is a Rust kernel behind
  the `vfs.native` seam with a byte-identical pure fallback; rustworkx
  would be a second, un-seamed native dependency.
- **A numpy power iteration** (`np.bincount(tgt, weights=rank[src]/outdeg[src])`
  per iteration) matches rustworkx within noise at 10⁵ and needs nothing
  vfs does not already ship (`numpy>=2.4.2` is in `pyproject.toml`).
  PageRank and Katz are the *same* loop with a different affine step
  (`x ← α·Aᵀ·D⁻¹·x + (1−α)/n` vs `x ← α·Aᵀ·x + β`), and in-degree is its
  zeroth iteration. Thirty lines, offloaded, deterministic, testable
  against the pure reference the same way the engines are.
- **Pure Python** is 15× slower than numpy but still sub-second at 10⁵;
  it is the natural byte-identical fallback for the native seam if the
  kernel ever moves to `crates/vfs-core`.
- **Iterative SQL** (power iteration as `INSERT ... SELECT ... GROUP BY`
  joins over an `edges` table, 20 iterations) is portable to every
  dialect and needs no memory beyond the engine's, but costs
  0.32 s/iteration at 10⁵ and 4.5 s/iteration at 10⁶ on SQLite in
  memory — 10–100× the in-memory kernels, and every iteration is a
  full-table churn on a production engine under the reindex lease. It is
  the honest *out-of-core* direction if a corpus ever exceeds what one
  reindex process can hold, not the reference path. Memory profile of
  the in-memory kernel at 10⁶ nodes × 5 edges: two int64 edge arrays
  (80 MB) plus three float64 vectors (24 MB) — acknowledged in the
  docstring, per the no-declared-cap rule, with the SQL path named as
  the future direction.

The **in-degree signal needs none of this**: `SELECT target_id, COUNT(*)
FROM edges JOIN entries ... GROUP BY target_id` is one statement on every
engine, incremental, and — per A.1 and A.4 — carries almost all of the
ranking information of PageRank and Katz on link graphs (ρ ≈ 0.97 here;
Craswell's in-degree weight went to zero only *after* PageRank was
present, i.e. they are substitutes).

---

## Part D — the ranker API: prior-art shapes

The constraint: ADR 007 fixes `glean(query, limit, paths, ...)`; a
deployment may configure *how* ranking works, but the verb must not
grow a strategy or profile parameter. So every knob lives on the
Storage (mount configuration), and the verb reads it.

### D.1 Where prior art puts the knobs

| system | where configured | signals | fusion | rerank | per-query selector? |
|---|---|---|---|---|---|
| **OpenSearch search pipelines** (`neural-search` @ 972d698) | server-side pipeline object, referenced by name via `search_pipeline` param or set as the index default | sub-queries of the `hybrid` query | `normalization-processor`: normalization `min_max`/`l2`/`z_score`, combination `arithmetic_mean`/`geometric_mean`/`harmonic_mean` with `weights`; `score-ranker-processor`: `rrf` with `rank_constant` (default 60, range 1–10,000) | rerank processors | a pipeline *name*, defaultable to none |
| **Elasticsearch/OpenSearch `rank_feature`** | mapping (`rank_feature` field, `positive_score_impact`) + query clause | numeric static features (`pagerank`, `url_length`) | `bool.should` addition of `saturation S/(S+pivot)` (default; pivot defaults to the field's geometric mean), `log(scaling_factor+S)`, `sigmoid Sᵉ/(Sᵉ+pivotᵉ)`, `linear` | — | the query author writes the clause (server-side templates hide it) |
| **Elasticsearch `function_score`** | query | `field_value_factor(field, factor, modifier ∈ {log1p, sqrt, …}, missing)`, decay functions, `weight` | `score_mode` (multiply/sum/avg/max/min) × `boost_mode` (multiply/replace/sum/avg/max/min), `max_boost`, `min_score` | — | same |
| **Vespa rank profiles** | schema (`rank-profile` in `.sd`/`.profile`, application package) | `attribute(popularity)`, `bm25(field)`, `closeness`, `nativeRank`, `query(tensor)` inputs | `first-phase` expression (e.g. `0.7·bm25(text) + 0.3·attribute(popularity)`) | `second-phase` with `rerank-count`, `global-phase` | `ranking.profile=name` selects a *server-defined* profile; `default` if absent |
| **zoekt** @ a9206004 | Go constants (`scoreFactorAtomMatch 400`, `scoreRepoRankFactor 100`, `scoreFileOrderFactor 10`, `ScoreOffset 10⁷`) | repo recency/priority, doc order, file category | truncated weighted sum with tie-breakers | — | `UseBM25Scoring` flag, self-described "EXPERIMENTAL"; `DebugScore` |
| **LanceDB rerankers** | per query: `.search(q).rerank(reranker)` | vector, FTS | `RRFReranker`, `LinearCombinationReranker` (normalize + blend), `MRRReranker` (weighted RRF) | `CrossEncoderReranker`, `ColbertReranker`, `CohereReranker`, … via a `Reranker` base class with `rerank_hybrid/vector/fts`; `return_score="relevance"|"all"` | yes — the caller picks the strategy per call (the shape ADR 007 rejects) |
| **Haystack `DocumentJoiner`** | pipeline graph, at build time | any retriever branch | `join_mode ∈ {concatenate, merge, reciprocal_rank_fusion, distribution_based_rank_fusion}`, `weights`, `top_k`, `sort_by_score` | a ranker component downstream | no — the pipeline is the configuration |

Two families: *the search request carries the ranking program*
(Elasticsearch query DSL, LanceDB) vs *the deployment declares it and the
request names nothing or only a profile* (OpenSearch pipelines, Vespa,
Haystack, zoekt). vfs is in the second family by ADR 007. Vespa's shape
is the most complete precedent — declared features, a first-phase
expression over them, a bounded second phase — and its profile
*selection* is the one thing vfs must not copy onto the verb.

### D.2 Three candidate shapes for vfs

All three: declared on the Storage at construction (mount config),
serializable and hashable (the hash feeds the signals' options
fingerprint and the epoch fingerprint where relevant), inspected by the
verb, never a verb parameter. The signals a ranker names must exist as
`signals` rows in the current generation or the leg is dropped with a
warning-severity record.

**Shape 1 — a declarative `Ranker` config, compiled to SQL.**

```python
DatabaseStorage(
    url=...,
    ranker=Ranker(
        legs=(VectorLeg(), LexicalLeg()),            # retrieval legs, always both when available
        signals=(
            Signal("centrality", transform=Saturation(pivot=4.0), weight=0.15),
            Signal("reads",      transform=Log1p(),            weight=0.10),
        ),
        fusion=RRF(k=60),                             # or Convex(weights={"vector": .5, "lexical": .5}, normalize="min_max")
        aggregate=MaxP(),                              # chunk → entry
    ),
)
```

Becomes SQL as: one ranked CTE per leg (scope allow-list joined inside
each, `LIMIT` per leg), an RRF or normalized-sum expression across them,
and each static signal either as a further ranked list (RRF semantics: a
`signals` CTE ordered by value) or as an additive boost term
`weight · transform(value)` `LEFT JOIN`ed on `entry_id` (convex/sum
semantics), then per-entry aggregation and the outer `LIMIT n`. Engines
without a server-side distance (MySQL community, `GENERIC`) get the same
object compiled to the client-side path. The transform vocabulary is
Craswell's/Elasticsearch's: `Saturation(pivot)`, `Log1p(scale)`,
`Sigmoid(pivot, exponent)`, `Linear()` — each a one-line SQL expression
(`v/(v+pivot)`, `LN(1+v)`), which is why this compiles.

**Shape 2 — named rank profiles on the Storage (Vespa-shaped).**

```python
DatabaseStorage(
    url=...,
    rank_profiles={"default": Ranker(...), "recency": Ranker(...)},
    active_profile="default",
)
```

Same compilation as Shape 1; the registry lets a deployment keep
several rankers and swap the active one by configuration or by an
evaluation harness (gap 8), and lets the conformance suite pin two
profiles' determinism. The profile is selected on the mount, *never* by
`glean` — a per-query `profile=` would be exactly LightRAG's `mode`.
Worth having only once the harness exists; before that it is speculative
generality over Shape 1.

**Shape 3 — protocol seams for fusion and rerank, with a SQL fast path.**

```python
class Fusion(Protocol):
    def to_sql(self, legs: Sequence[RankedLeg], signals: Sequence[SignalLeg]) -> Select | None: ...
    def fuse(self, legs: Sequence[RankedList], signals: Mapping[str, Mapping[EntryId, float]]) -> RankedList: ...

class Reranker(Protocol):
    async def rerank(self, query: str, candidates: Sequence[Candidate]) -> Sequence[Candidate]: ...

DatabaseStorage(url=..., ranker=Ranker(..., fusion=RRF(k=60), rerank=BM25Rerank(top=50)))
```

`fuse` is the client-side floor every engine can run over the per-leg
top-K it fetched; `to_sql` returns the in-engine statement where the
fusion is expressible (RRF and convex on every dialect, since both are
arithmetic over ranks/scores). `Reranker` is a bounded second phase
(Vespa `second-phase` + `rerank-count`): an in-process BM25 over the
fused top-50's content — Clay's R3 lean lands here for the *single-mount*
case — or a cross-encoder later. A protocol seam is what lets a
deployment plug a fusion or reranker vfs did not ship without touching
the verb.

**Recommendation: Shape 1 for the data, Shape 3 for the seams.** The
`Ranker` is a frozen dataclass a deployment writes and vfs can hash and
inspect; `Fusion` and `Reranker` are protocols the built-ins (`RRF`,
`Convex`, `BM25Rerank`) implement, so the reference design ships
declaratively and extension is by implementing a protocol, not by
subclassing the backend. Shape 2 becomes trivial on top (a dict of
Shape 1 objects) once the evaluation harness gives a reason to hold two.
The verb's signature does not change in any shape. Result honesty (gap
9): the envelope names which signal legs were present and which fusion
compiled in-engine vs client-side.

---

## Executed experiment

Scripts and outputs in `centrality-and-read-signals/`:

- `graph_signals.py` → `graph_signals.out.txt`, `graph_signals.json`.
  Two real graphs from this repository, read-only: (A) Markdown link
  graph over `context/` + `docs/` (edge = relative link or backticked
  `.md` path resolving to a known file), (B) `src/vfs` import graph (edge
  = `from vfs… import` / `import vfs…`). PageRank (α = 0.85), Katz
  (α = 0.9/λ_max, computed exactly), HITS, in-degree via networkx;
  Spearman/Kendall via scipy.
- `scaling.py` → `scaling.out.txt`, `scaling.json`. Synthetic
  preferential-attachment digraphs at 10⁴/10⁵/10⁶ nodes; networkx,
  rustworkx, numpy power iteration, pure-Python power iteration, and an
  all-SQL power iteration on in-memory SQLite (20 fixed iterations for
  the last three).

Findings:

1. **Link graph (440 nodes, 615 edges)**: 111 isolated, 233 with zero
   in-degree. In-degree vs PageRank ρ = 0.977 (τ = 0.906); in-degree vs
   Katz ρ = 0.975; Katz vs PageRank ρ = 0.966; HITS authority vs
   in-degree 0.737, vs PageRank 0.652. Timings are microseconds to tens
   of milliseconds (Katz 44 ms is the λ_max eigen-solve).
2. **Import graph (49 nodes, 173 edges)**: in-degree vs PageRank
   ρ = 0.58 — on a tiny dense graph PageRank's flow matters more; HITS
   authority vs PageRank ρ = 0.09. HITS is not a usable global prior.
3. **Scaling**: at 10⁵ nodes, PageRank costs 0.27 s (networkx + scipy),
   0.038 s (rustworkx), 0.041 s (numpy, 20 iterations), 0.65 s (pure
   Python), 6.7 s (SQL, 20 iterations at 0.32 s each). At 10⁶ nodes:
   4.8 M edges — networkx 4.4 s (plus 8.3 s to build its `DiGraph`), rustworkx 0.74 s (build 3.1 s), numpy 0.76 s, pure Python 15.6 s, SQL 94 s (4.5 s per iteration, 4.2 s to load). Extrapolation is linear in edges for the in-memory
   kernels (one pass over the edge arrays per iteration); the SQL path
   grows with join and re-materialization cost per iteration.

Caveats: the link graph is one small documentation corpus, not a wiki
at scale; the synthetic graphs are preferential-attachment with a fixed
out-degree, which is friendlier to convergence than a real corpus with
long chains; SQLite in memory is the *best* case for the SQL path (a
production engine adds WAL, network, and lock cost per iteration).

---

## Bearing on vfs

**Recommendation.**

1. **Ship one link signal, `centrality`, computed as in-degree over live
   `edges`** (`GROUP BY target_id`, one statement, incremental,
   dialect-free), log-scaled/saturated at fusion time. The record (Upstill
   2003; Craswell 2005's in-degree weight collapsing to zero beside
   PageRank; ρ ≈ 0.97 here) says PageRank and Katz are substitutes for it
   on link graphs, and zoekt's arc (RRF → weighted sum → deleted) says the
   marginal value of the fancier measure did not survive contact with
   users. Keep the numpy power-iteration kernel (PageRank/Katz share one
   loop; ~40 ms at 10⁵, offloaded) as the second signal *if* a corpus
   demonstrates the difference on the evaluation harness — not before.
   HITS is out.
2. **Zero-edge mounts have no `centrality` rows, and the leg is
   absent** — the statement omits it, the envelope says so. No directory
   fallback graph; if a structural prior is wanted, add a declared
   `path_shape` signal (segment count / name length) as a column
   expression.
3. **Reads become an opt-in popularity prior**: `read` only; the host
   buffers events and flushes them in a separate short writer transaction
   after the read-only op returns (never inside it); reindex rolls them up
   into a `reads` signal with a 30-day half-life and `log1p`, sweeping
   events past five half-lives. No learned or de-biased model: at vfs
   traffic the ULTR premises (repeated impressions, ≥10⁴ clicks, an
   examination model that is not simply "rank") do not hold.
4. **A `signals(entry_id, signal, value, generation)` table**, refreshed
   as a reindex phase (extract → offloaded compute → chunked write with a
   generation stamp), advisory and therefore not on the epoch pointer.
5. **Ranker API = Shape 1 data + Shape 3 seams**: a frozen `Ranker`
   config on the Storage naming signals with transform and weight, a
   `Fusion` (`RRF(k)` / `Convex(weights, normalize)`) with a SQL
   compilation and a client-side floor, and an optional `Reranker` second
   phase; nothing on the verb.

**Named forks** for the memo/ADR:

- **F1 — which link measure ships first**: in-degree (recommended) vs
  Katz/PageRank via the numpy kernel vs rustworkx. Decide on the
  harness; the dependency rule and the correlation data favour
  in-degree now.
- **F2 — how a static prior enters the fusion**: as an extra ranked list
  under RRF (distribution-free, but the prior's magnitude is discarded)
  vs an additive transformed boost (`weight · saturation(v)`; Craswell's
  finding and zoekt's #523 preference; needs a tuned weight). Gap 7's
  harness decides; the `Ranker` object must express both.
- **F3 — read capture default**: opt-in default-off (recommended) vs
  on-by-default with a short half-life. Privacy and the access-log
  nature of the event table argue for off.
- **F4 — popularity scope**: global (recommended) vs per-user
  personalization (requires the user in the query path and per-(user,
  entry) signals; a later capability, not a static prior).
- **F5 — impression log**: record which `glean` result list a read came
  from (enables propensity correction later, costs a write per glean and a
  session notion vfs lacks) vs not (recommended now).
- **F6 — signal publish discipline**: in-place generation replacement
  (recommended; advisory data) vs riding the gram epoch's CAS pointer
  (one machinery, but couples an optional feature to the index's
  freshness).
- **F7 — profiles**: a single `Ranker` (recommended) vs a named-profile
  registry selected on the mount (Shape 2) once the evaluation harness
  exists.

## Sources

Papers:

- Brin & Page, "The Anatomy of a Large-Scale Hypertextual Web Search
  Engine", 1998 — http://infolab.stanford.edu/~backrub/google.html
- Kraaij, Westerveld & Hiemstra, "The Importance of Prior Probabilities
  for Entry Page Search", SIGIR 2002 — https://dl.acm.org/doi/10.1145/564376.564383
  (abstract via https://research.utwente.nl/en/publications/the-importance-of-prior-probabilities-for-entry-page-search/)
- Upstill, Craswell & Hawking, "Query-independent evidence in home page
  finding", ACM TOIS 21(3), 2003 — https://dl.acm.org/doi/10.1145/858476.858479
  (PDF: http://david-hawking.net/pubs/upstill_tois03.pdf)
- Upstill, Craswell & Hawking, "Predicting fame and fortune: PageRank or
  indegree?", ADCS 2003 — https://david-hawking.net/pubs/upstill_adcs03.pdf
- Craswell, Robertson, Zaragoza & Taylor, "Relevance Weighting for Query
  Independent Evidence", SIGIR 2005 —
  https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/craswell_sigir05.pdf
  (read in full; Table 1 values quoted above)
- Katz, "A New Status Index Derived from Sociometric Analysis",
  Psychometrika 18(1), 1953 — https://doi.org/10.1007/BF02289026
- Kleinberg, "Authoritative Sources in a Hyperlinked Environment", JACM
  46(5), 1999 — https://doi.org/10.1145/324133.324140
- Joachims, Swaminathan & Schnabel, "Unbiased Learning-to-Rank with
  Biased Feedback", WSDM 2017 — https://arxiv.org/abs/1608.04468
  (PDF read in full: https://www.cs.cornell.edu/people/tj/publications/joachims_etal_17a.pdf)
- Oosterhuis, "Reaching the End of Unbiasedness: Uncovering Implicit
  Limitations of Click-Based Learning to Rank", ICTIR 2022 —
  https://arxiv.org/abs/2206.12204
- Chuklin, Markov & de Rijke, *Click Models for Web Search*, Morgan &
  Claypool 2015 — https://www.semanticscholar.org/paper/0b19b37da5e438e6355418c726469f6a00473dc3
  ; SIGIR 2015 tutorial https://irlab.science.uva.nl/wp-content/papercite-data/pdf/chuklin-introduction-2015.pdf
- Craswell, Zoeter, Taylor & Ramsey, "An experimental comparison of
  click position-bias models", WSDM 2008 (cascade model) —
  https://doi.org/10.1145/1341531.1341545
- Chapelle & Zhang, "A dynamic bayesian network click model for web
  search ranking", WWW 2009 (DBN) — https://doi.org/10.1145/1526709.1526711

Docs and code:

- Sourcegraph, "Indexed ranking" —
  https://docs.sourcegraph.com/dev/background-information/architecture/indexed-ranking
  (fetch returns 403; the search-engine snippet reads: "A file's rank is
  based on the number of inbound references from any other file in the
  available code graph, representing how widely-used and important the
  file is to the codebase, inspired by PageRank in web search" and "If
  code intel ranks are being calculated from SCIP data, then Zoekt
  incorporates these as an important file signal"); blog
  https://sourcegraph.com/blog/ranking-in-a-week (403 to fetchers).
- zoekt @ a9206004: `index/score.go:300–356` (`scoreFile`),
  `index/contentprovider.go:599–609` (score factors), `index/builder.go:
  878–975` (`rank`, `sortDocuments`), `api.go:678–700` (`Rank` from
  `LatestCommitDate`/`priority`), `index/toc.go:103,193` (`ranks`
  unused); commits `f6d0aa00` (#523) and `c7f1e697` (#853).
- OpenSearch hybrid search / search pipelines —
  https://docs.opensearch.org/latest/vector-search/ai-search/hybrid-search/index/
  and https://docs.opensearch.org/latest/search-plugins/search-pipelines/normalization-processor/ ;
  technique names and `rank_constant` bounds from `neural-search` @ 972d698
  (`RRFNormalizationTechnique.java:44–48`, `ScoreCombinationUtil.java:27`).
- Elasticsearch `rank_feature` field and query —
  https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/rank-feature ,
  https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-rank-feature-query ;
  `function_score` —
  https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-function-score-query
- Vespa ranking — https://docs.vespa.ai/en/ranking.html
- LanceDB reranking — https://docs.lancedb.com/reranking
- Haystack `DocumentJoiner` — https://docs.haystack.deepset.ai/docs/documentjoiner
- rustworkx 0.18 — `rustworkx/rustworkx.pyi:635–653` (`hits`, `pagerank`
  with `personalization`), `rustworkx/__init__.py:1524` (`katz_centrality`
  dispatching to `src/centrality.rs:895,1024`), `src/link_analysis.rs:90`;
  https://www.rustworkx.org/apiref/rustworkx.pagerank.html
- networkx — https://networkx.org/documentation/stable/reference/algorithms/link_analysis.html
- HippoRAG @ 2f52a86 — `src/hipporag/HippoRAG.py:2003–2210`.
- graphify v8 @ 43d54ac — `graphify/analyze.py:109–131` (`god_nodes`),
  `:340–425` (`_cross_community_surprises`), `:428–470`
  (`suggest_questions`), `graphify/cluster.py:48–74`.
- LightRAG @ 812f2d5d `lightrag/operate.py:5908–5931`; graphrag @ f40e9a2
  `graphrag/data_model/schemas.py:13`, `graphrag/index/workflows/prune_graph.py:61`,
  `graphrag/query/context_builder/community_context.py:242`; cognee @
  690c0ec02 `cognee/modules/retrieval/graph_report_retriever.py:49–66`.
- vfs: `src/vfs/models/rows.py:424–480`, `src/vfs/storage/backends/database/indexing.py:1–120,196–460`,
  `offload.py:1–90`, `reads.py:1–130`, `backend.py:85–110,141–160,594–660`,
  `src/vfs/storage/protocol.py:286–303`.
