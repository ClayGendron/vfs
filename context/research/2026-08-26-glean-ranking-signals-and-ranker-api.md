# glean ranking signals: index-time centrality, read-derived popularity, and the ranker API

- **Status**: research memo — design input for the glean *signals* ADR
  (a `signals` table, a reindex phase, an opt-in read log, and a
  `Ranker` configuration on the Storage). One of five memos from the
  2026-08-26 glean research leg
  (brief: [2026-08-26-glean-brief.md](2026-08-26-glean-brief.md)).
  Companions: [fusion and cross-mount merge](2026-08-26-glean-fusion-and-cross-mount-merge.md)
  (how a prior enters the fused score),
  [glean in the engine](2026-08-26-glean-in-the-engine.md),
  [the embedding seam](2026-08-26-glean-embedding-seam.md),
  [previews and the result shape](2026-08-26-glean-previews-and-result-shape.md).
  Commits us to nothing.
- **Date**: 2026-08-26
- **Owner**: Clay Gendron
- **Question**: Clay asked that glean be designed so PageRank, Katz, or
  other centrality computed in the reindex pipeline can join the fusion,
  that reads ("clicks") be tracked so they can inform the ranker, and
  that the whole thing be a customisable API. What is a static,
  query-independent signal actually worth; how is each captured,
  stored, refreshed and folded in; and what API lets a deployment
  register signals, weights, a fusion function and a rerank stage
  without the verb growing a strategy selector (ADR 007: a parameter may
  select *what* to answer, never *how*)?
- **Evidence gathered**: the centrality-and-read-signals study
  ([studies/2026-08-26-glean/centrality-and-read-signals.md](studies/2026-08-26-glean/centrality-and-read-signals.md)):
  the web-search and ULTR literature, zoekt's commit history, HippoRAG /
  graphify / LightRAG / graphrag / cognee source, the OpenSearch / Vespa
  / Elasticsearch / LanceDB / haystack configuration surfaces, and two
  executed experiments — four centrality measures on two real graphs
  from this repository, and PageRank/Katz scaling on synthetic 10⁴–10⁶
  node graphs across networkx, rustworkx, numpy, pure Python and
  iterative SQL; the fusion study's prior-injection experiment
  ([fusion-and-merge.md §A.4](studies/2026-08-26-glean/fusion-and-merge.md));
  the landscape study's read-signal survey
  ([landscape.md §5](studies/2026-08-26-glean/landscape.md)); and, added
  after Clay's 2026-08-26 review, three studies on whether the
  filesystem hierarchy should participate in the centrality graph —
  an academic lens with the mass-flow derivations
  ([hierarchy-edges-academic.md](studies/2026-08-26-glean/hierarchy-edges-academic.md)),
  a prior-art survey of fourteen systems
  ([hierarchy-edges-prior-art.md](studies/2026-08-26-glean/hierarchy-edges-prior-art.md)),
  and an executed experiment on this repository's tree plus extracted
  edges ([hierarchy-edges-experiment.md](studies/2026-08-26-glean/hierarchy-edges-experiment.md)).
- **Headline**: On a real link graph in-degree, Katz and PageRank rank
  the same entries (Spearman 0.97–0.98) and HITS does not (0.65–0.74);
  the web record agrees (Craswell 2005: in-degree's tuned weight went to
  zero *beside* PageRank — they are substitutes), and the largest
  code-search practitioner's arc is a warning — zoekt fused file rank by
  RRF, replaced it with a weighted sum ("much easier to debug and
  tune"), then deleted document ranks outright in October 2024. **Ship
  `centrality` = in-degree over live `edges`** (one `GROUP BY`,
  dialect-free) as the default link signal, keep PageRank/Katz as
  declared alternatives on the same numpy kernel (0.76 s at 10⁶ nodes,
  no new dependency), and let a zero-edge mount have *no* signal rows so
  the leg is absent, not zero-weighted. **The filesystem hierarchy is
  not an edge type in that graph — it is a smoothing layer over it**:
  `fs` edges at any weight were measured to change nothing in the
  materialised direction (the weight cancels under per-node
  normalisation) and to become a depth or directory-size prior in the
  others, while siblings' reference counts predict a file's own at
  ρ = 0.40–0.77 across five corpora — so a file's score is blended with
  its directory's mean (`γ ≈ 0.2`, Xue et al. SIGIR 2005's
  aggregate-and-distribute), computed in the reindex phase and stored;
  **nothing in the prior path is computed at query time** — the fused
  statement reads one stored float. **Reads**: deferred by Clay on
  2026-08-26; the design below is recorded for when it is picked up —
  at vfs traffic the unbiased-learning-to-rank premises fail (Joachims
  2017 needs ~10⁴+ clicks and repeated impressions; an agent's "click"
  *is* rank), so the defensible design is an opt-in popularity prior —
  `read` only, host-buffered events flushed in a separate short writer
  transaction *after* the read-only op, rolled up at reindex as
  `log1p(Σ 2^(−age/30 d))`. **API**: a frozen `Ranker` config on the
  Storage (signals with transform and weight, a `Fusion`, an aggregate,
  an optional `Reranker`), compiled to SQL where the engine can and run
  client-side where it cannot; nothing on the verb.

---

## 1. What the tree has to work with

- **Edges are user-minted only.** `edges(source_id, target_id,
  edge_type, weight, distance)`, both directions indexed
  (`src/vfs/models/rows.py:443`); no extractor mints references from
  content. The `graph` verb walks them; ADR 007 says analytics are
  "index-time data feeding glean's graph signal, not queries".
- **Reads leave no trace.** No column, counter or event table records
  that an entry was read. `DatabaseStorage.read` runs through
  `_execute(op, fn)` in a read-only session under one committed snapshot
  (`backend.py:594–620`, `reads.py:108` — "only executes SELECTs; none
  begins or commits").
- **Reindex is phased and leased**: claim → `chunk_dirty` (offloaded
  split) → `build_epoch` → `publish_epoch` (flag flips + CAS pointer) →
  reclaim, each in its own writer transaction, the lease heartbeat
  between phases, CPU hops through `call_offloaded` (`indexing.py`,
  `offload.py`).

## 2. Centrality as a static prior

### 2.1 What the record says it is worth

**Web search.** Kraaij, Westerveld & Hiemstra (SIGIR 2002) found the
*cheapest* structural feature — URL form — beat in-links for entry-page
search. Upstill, Craswell & Hawking (TOIS 2003) found all
query-independent evidence beats random over content-only, but only
URL-type still helped over anchor text, and PageRank and in-degree were
strongly correlated with "limited added value" for PageRank. Craswell,
Robertson, Zaragoza & Taylor (SIGIR 2005) reranked BM25 top-1000 with
`final = BM25 + f(S)`:

| transform of static S | test MAP (baseline 0.430) |
|---|---|
| linear `w·S` | 0.439 |
| log `w·log S` | 0.508 |
| saturation `w·S/(k+S)` | 0.515 |
| sigmoid `w·Sᵃ/(kᵃ+Sᵃ)` | **0.523** |
| in-degree, sigmoid | 0.489 |
| PageRank + URL length | 0.532 |

Three findings bind: a linear weight on a power-law feature is useless
— it must pass through log or a saturating transform; **after PageRank
was added, in-degree's tuned weight went to zero** — link measures are
redundant with one another, so ship one; and they list "aggregate
clickthrough, visit frequency or dwell time" as static features to be
transformed the same way — the read prior of §3 belongs in the same
slot.

**Code search.** Sourcegraph's file rank ("inbound references from any
other file in the available code graph … inspired by PageRank",
computed from SCIP) was consumed by zoekt — and the zoekt checkout
tells the rest: before #523 ranks fused by RRF ("k = 60 is arbitrary
but reportedly works well"); #523 (2023-01) replaced it with a weighted
sum — "much easier to debug and tune compared to RRF. We're in full
control of the ranking signals, and can make sure they're bounded +
meaningful" — as `9000 × min(1, log₂count/32)`, and removed index
sorting by rank ("didn't really make a difference"); #853 (2024-10)
removed document ranks: "an experimental feature … we have already
removed the code in Sourcegraph". What survives at `a9206004` as static
priors is recency, file category, and name/size shape. The lesson is
not "centrality is worthless" — their corpus was monorepo code; a wiki
or note graph is different — but that a static prior must be cheap,
bounded, log-scaled, additive, and easy to turn off, and that the
evidence for link rank in code search was thin enough that the largest
practitioner deleted it.

**Graph RAG.** The field converges on degree as the cheap structural
measure: LightRAG stamps node degree as `rank` for prompt ordering;
graphrag stores `degree`/`combined_degree` as rank columns; cognee's
PageRank is a *report*, with a fallback to degree; graphify v8's "god
nodes" are plain degree and its p99-degree hub *penalty* in traversal
is the only ranking idea in its codebase. HippoRAG runs *personalized*
PageRank at **query time**, seeded by the query's matched facts, damping
0.5 — a query-dependent diffusion over an extracted phrase/passage graph
vfs does not have; it is a retrieval strategy, not a prior, and it is
out of glean's scope under the no-selector rule. Its one transferable
trick is dividing a hub's seed weight by its chunk count — degree as a
*dampened* input. Nobody in the study set folds an index-time PageRank
into hybrid retrieval fusion.

### 2.2 Measured on this repository

Markdown link graph over `context/` + `docs/` (440 files, 615 edges,
111 isolated, **233 of 440 with zero in-degree**): Spearman ρ
in-degree/PageRank 0.977, in-degree/Katz 0.975, Katz/PageRank 0.966;
HITS authority vs the others 0.65–0.74 (captured by the densest
cluster). On the tiny `src/vfs` import graph (49 nodes) the measures
diverge more (ρ = 0.58) and HITS vs PageRank is 0.09 — HITS is not a
usable global prior anywhere.

### 2.3 Which graph, and how a mount without one degrades

- **Reference edges only: `edges WHERE edge_type <> 'fs'`.** Declared
  edges today; extracted references (imports, markdown links, symbol
  uses) once the extractor exists — a small producer spec of its own,
  raised by Clay on 2026-08-26 as the way edges stop being user-minted
  only. On a link-rich corpus in-degree is a real navigational prior —
  the hub effect Kraaij and Craswell measured — at one `GROUP BY`. On a
  bare code tree with no extractor there are no edges and the signal
  does not exist. The materialised hierarchy (`edge_type='fs'`, ADR
  018) is excluded from this graph — §2.5 says why, with measurements —
  and enters as smoothing instead.
- **Absent, not zero.** Imputing 0 for every entry and min-max
  normalising divides by zero or yields a constant column; under RRF an
  all-tied list adds a constant. Rule: the signal leg joins the fusion
  only when `signals` holds rows for that signal in the current
  generation; otherwise the compiled statement omits it and the
  envelope says so (a warning-severity record). On a *sparse* graph (53 %
  zero here) the signal stays present and the transform maps 0 to the
  floor — unlinked entries get no boost, which is the honest semantics.
- **No hierarchy edges in the walk, at any weight or direction.**
  Measured on this repository (977 nodes; 864 reference edges, 976 `fs`
  edges; hierarchy-edges-experiment): with directory → child edges as
  vfs materialises them, every weight from 0.05 to 1.0 produced
  *identical* rankings (ρ = 1.00 on PageRank, in-degree and Katz) —
  PageRank normalises out-weights per source and a directory has only
  `fs` out-edges, so the weight cancels; what the tree edges rank is
  depth (Katz-down ρ = 1.00 with depth) and inverse parent fan-out
  (PageRank-down ρ = −0.995). Reversed, file ordering is untouched and
  directories score by child count; bidirectional, file agreement with
  the reference graph falls to 0.55 and Katz tracks parent fan-out at
  +0.67. The academic study derives the same result — under per-node
  normalisation a file with no reference out-edge sends all its mass
  up its `fs` edge whatever the weight (43 % of this repo's docs) — and
  corrects an earlier sign: parent → child PageRank favours *deeper*
  nodes, bounded by ≤ 1.8×. The prior-art survey found no system that
  folds containment into a search prior; the tree appears as a scalar
  feature (SharePoint `UrlDepth`/`ClickDistance`), an aggregation
  level (Eiron 2004 HostRank/DirRank; Xue 2005), or a teleport set.
  "Lower-weight `fs` edges" is therefore not a knob; §2.5 is the
  replacement. A **path-shape** signal (depth, name length) remains a
  legitimate *separate* declared input — a column expression, weighted
  on its own; note the academic study measured name length with the
  *opposite* sign to Kraaij's and zoekt's prior on this repo, so its
  sign is learned, not assumed.
- **Extracted references** (imports, links, symbol uses) are a *future
  edge producer*, not a glean concern; when they exist they are just
  more `edges` rows and the signal reads them unchanged.

### 2.4 Computing it, measured

Synthetic preferential-attachment digraphs (~4–5 edges/node), single
process, Apple Silicon:

| nodes / edges | networkx (scipy) | rustworkx | numpy power iteration, 20 it | pure Python, 20 it | iterative SQL (SQLite in-memory), 20 it |
|---|---|---|---|---|---|
| 10⁵ / 416 k | 0.27 s (+0.55 s build) | 0.038 s | **0.041 s** | 0.65 s | 6.7 s (0.32 s/it) |
| 10⁶ / 4.8 M | 4.4 s (+8.3 s build) | 0.74 s | **0.76 s** | 15.6 s | 94 s (4.5 s/it) |

networkx's `pagerank` *requires scipy* (cognee's degree fallback exists
for this reason); rustworkx is fastest but would be a second, un-seamed
native dependency with no pure fallback; the **numpy power iteration**
(`np.bincount(tgt, weights=rank[src]/outdeg[src])` per iteration)
matches rustworkx within noise using nothing vfs does not already ship,
and PageRank and Katz are the same loop with a different affine step —
in-degree is its zeroth iteration. Pure Python is the natural
byte-identical fallback if the kernel ever moves to `crates/vfs-core`.
Iterative SQL is portable and out-of-core but 10–100× slower and churns
the whole table per iteration under the reindex lease — the honest
future direction if a graph ever exceeds one process's memory (10⁶
nodes × 5 edges ≈ 104 MB of arrays; acknowledged in a docstring, never a
declared cap).

**In-degree needs none of this**: `SELECT target_id, COUNT(*) FROM edges
JOIN entries … WHERE edge_type <> 'fs' GROUP BY target_id` — one
statement, incremental, identical on every engine.

### 2.5 The tree as a smoothing layer, computed at reindex

The hierarchy carries importance information even though it must not
be a citation edge: across five corpora read read-only (this repo's
docs, networkx, sqlalchemy, mcp and one more), the leave-one-out mean
of a file's *siblings'* in-degree predicts its own `log` in-degree at
ρ = 0.40–0.77 (z = 2.3–13.9), and 28–63 % of the variance in reference
counts is between directories (hierarchy-edges-academic §5). The
principled use of that fact is Xue et al. (SIGIR 2005) — aggregate by
directory, rank, distribute down — which beat PageRank and BlockRank
on .GOV "even when the space is sparse"; XRank (SIGMOD 2003) and
ObjectRank (VLDB 2004) are the per-type-normalised precedents, and
Ogilvie & Callan's shrinkage is the same estimator. The model:

```
m(f)    = log1p(reference in-degree of f)                -- or the configured measure
mean(d) = bottom-up mean of m over d's files and subdirectory means
p(root) = mean(root)
p(d)    = (1 − γ)·mean(d) + γ·p(parent(d))               -- top-down
p(f)    = (1 − γ)·m(f)    + γ·p(parent(f))               -- γ = 0.2 default, ≤ 0.3
```

A file with no references inherits a fraction of its directory's
importance (coverage for the honest reason — 53–65 % of files have no
reference under R alone); a file deep in a 500-file directory gets
nothing for being there. γ is a real knob with a real effect, unlike
the edge weight. Computation, all inside the reindex phase of §4.2:
(1) the raw measure — the in-degree `GROUP BY`, or the numpy kernel —
into an array over entries; (2) one bottom-up pass over the tree from
`parent_id` (the only place the hierarchy is read); (3) one top-down
pass; (4) min-max normalisation over *retrievable* entries (files;
directories are never candidates and never normalised against); (5)
chunked writes to `signals` under a new generation. Two O(N) numpy
passes — milliseconds at 10⁵ entries, about a second at 10⁶ — through
the same `call_offloaded` hop. **Rule for the spec: `signals` is read,
never computed, on the query path.** The fused statement `LEFT JOIN`s
the stored float and multiplies by `(1 + β·value)`; no graph, no
aggregate and no smoothing runs at query time; a missing row is factor
1. Recompute is whole-corpus at every reindex (O(N + E), no incremental
path); γ, β, the measure and the transform live in the signal's
`options_hash`, so a change forces a recompute.

## 3. Read-derived signals

> **Deferred** (Clay, 2026-08-26): read capture is not part of the
> first glean landing. The design below is the record for when it is
> picked up; nothing in §4–§6 depends on it.

### 3.1 What a click is when the reader is an agent

A web click is a human choice among visible alternatives, filtered by
examination — the reason click models exist. An agent over MCP receives
the whole glean list and reads the top entries in order: its reads are
close to a deterministic function of rank (the cascade model with
examination ≈ 1 at the top and a hard cut at its context budget).
Position bias is not a perturbation to correct but the dominant term.
Two more confounders: reads arrive from `ls`/`tree`/`glob` navigation as
often as from `glean`, and vfs has no impression record linking a read
to the result list that produced it.

### 3.2 The ULTR record, and the verdict at vfs scale

Joachims, Swaminathan & Schnabel (WSDM 2017) give the inverse-propensity
estimator and Propensity SVM-Rank; their curve crosses the production
ranker only around ~10⁴ training clicks and keeps improving to ~10⁶.
Oosterhuis (2022) shows counterfactual estimation is unbiased only for
click behaviour that is an affine transform of relevance. Click models
(PBM, cascade, DBN) are fitted from *repeated impressions of the same
query* — which Joachims et al. themselves call "unrealistic … (e.g.,
personal collection search)". A vfs mount sees tens to thousands of
reads a day with no impression log, no repeated-query volume, and a
reader whose clicks are rank: a learned or de-biased model is starved
and its premises fail.

What is defensible is what Craswell 2005 named among static features:
**a popularity prior** — a time-decayed read count, log-scaled,
saturating, small weight, in the same slot as centrality. Its known
pathology is the rich-get-richer loop (reads follow rank, rank follows
reads); the mitigations are the transform (a 100× read gap becomes a
~2× signal gap), exponential decay (a half-life bounds how long a hub
stays a hub), a low weight, and opt-in default-off. graphify's authors
reached the same reading independently — their `reflect` verdicts are
"deliberately deferred" from ranking because it "needs propensity
correction + exploration to avoid a self-reinforcing feedback loop"
(CHANGELOG 0.9.3) — and cognee ships `feedback_influence = 0.0`.

### 3.3 The field stores it outside the read path — or not at all

None of the open-source agent-memory codebases ranks on reads: letta's
`files_agents.last_accessed_at`, cognee's `last_accessed`, MemOS's
`usage` list (writer now disabled) and gbrain's `last_retrieved_at` are
all written and never ranked; memori's `num_times` is a *write-side*
re-extraction counter. The one published read-signal design is mem0's
**closed platform** "Memory Decay": per-project opt-in, a fire-and-forget
reinforcement on every returned memory (history capped at 20 touches),
a **0.3×–1.5× multiplicative factor** over a pool widened to
`max(3·top_k, 50)`, and a fallback to modification time when there is no
history. Vespa and Elasticsearch both model popularity as an
attribute/field the *application* updates on its own cadence
(`attribute(popularity)`, `rank_feature`), never something the query
path writes.

The in-row counter (`UPDATE entries SET reads = reads + 1`) is what
search engines avoid: every read becomes a write on a hot row — a new
tuple version and a row lock on Postgres, the single writer on SQLite,
impossible on a read replica — and in vfs it would turn every `read`
into `_execute_write`'s writer transaction (`BEGIN IMMEDIATE` on SQLite)
and defeat the read-only pin.

### 3.4 Recommended capture design

- **Which verbs count**: `read` only. `stat`, `ls`, `tree`, `glob`,
  `grep`, `glean` are navigation and search; counting them measures the
  agent's loop, not the entry's value. A batch read counts once per
  entry.
- **Opt-in** at mount level (`read_signal=ReadSignal(half_life_days=30)`
  or `None`, default `None`). Off means no event writes and no `reads`
  rows — the leg is absent (§2.3's rule).
- **Batched append, never inside the read transaction**: the read op
  returns from its read-only session first; the host buffers
  `(entry_id, user_id?, read_at)` in memory and flushes as one chunked
  bulk `INSERT` (under `chunked(…, parameter_budget)`) on a size/time
  threshold (e.g. 256 events or 5 s) and on `close()`, in a short
  writer transaction of its own. A crash loses at most one flush window
  of advisory data. Row: `read_events(id, entry_id, user_id NULL,
  read_at)`.
- **Roll-up at reindex**: `reads` value per entry =
  `log1p(Σ_events 2^(−(now − read_at)/half_life))`; events older than
  ~5 half-lives are deleted after roll-up (residual weight < 4 %), which
  bounds the table. Between reindexes the signal is stale, like every
  derived structure.
- **Privacy / multi-tenant**: the event table is an access log. Opt-in,
  retention declared (the 5-half-life sweep), `user_id` stored only
  when a `record_users` flag asks. vfs has no per-user visibility today,
  so a *global* prior leaks nothing a glean list does not already
  reveal; per-user popularity is personalisation (the user in the query
  path, per-`(user, entry)` signals) — a later capability, not a static
  prior.

## 4. Storing and refreshing signals

### 4.1 A `signals` table, not columns on `entries`

`signals(entry_id, signal, value, generation)`, PK `(entry_id, signal)`:
sparse by construction (a zero-edge mount holds no `centrality` rows, an
opted-out mount no `reads` rows), schema-stable as signals are added by
configuration (no `ALTER TABLE` per signal per dialect), rename-proof
(keyed by entry identity like `chunks` and `edges`), one `LEFT JOIN` per
signal leg on the same `ULIDKey` the `chunks → entries` join already
pays, and a plain table on `GENERIC`. A `generation` column makes a
partially refreshed signal detectable; a per-signal `options_hash` (the
gram index's `format_version`/`options_hash` fingerprint is the model)
invalidates the signal when its transform, measure or half-life changes.

### 4.2 Refresh as a reindex phase

Signals slot in as a phase after `chunk_dirty` — independent of the gram
epoch — in three steps: **extract** (the graph as
`SELECT source_id, target_id FROM edges` joined to live entries,
keyset-paginated so no statement grows with the graph; the read roll-up
from `read_events`) → **compute** off the event loop through
`call_offloaded` (the same hop chunk splitting takes; the pool follows
the host's close) with the lease heartbeat between steps → **write**
with the current-generation stamp, chunked by the parameter budget, then
delete the previous generation for that signal. Because a signal is
advisory it need not ride the epoch pointer: in-place generation
replacement per signal is enough — a torn read between chunks yields a
slightly stale prior, never a wrong result. The epoch-and-CAS machinery
exists because a torn posting set loses matches; priors have no such
failure mode. Freshness follows gap 1: a new entry has no signal until
the next reindex (no boost — the floor); a deleted entry's rows go with
the generation sweep.

## 5. How a signal enters the fusion

Settled by the fusion memo with numbers: a **bounded multiplicative
factor** on the fused score, `f × ∏(1 + β_s · p_s)`, `β_s ≤ 0.5`
default, `p_s` the signal's stored value already transformed
(`log1p`, saturation `v/(v + pivot)`, sigmoid) and min-max normalised at
reindex so it is a column read, not a query-time computation; an absent
signal is a missing row → factor 1. Never an extra RRF list: an
uninformative prior injected that way cost −0.20 nDCG; as a bounded
factor ≤ −0.05, while a real prior gained +0.16 either way. Each
transform is a one-line SQL expression (`LN(1 + v)`, `v/(v + :pivot)`),
which is what makes the ranker configuration compile.

## 6. The ranker API

### 6.1 Where prior art puts the knobs

Two families. *The request carries the ranking program*: Elasticsearch
query DSL (`rank_feature` with `saturation`/`log`/`sigmoid`,
`function_score` with `field_value_factor` and `boost_mode`), LanceDB
(`.search(q).rerank(reranker)` — the caller picks the strategy per call,
the shape ADR 007 rejects). *The deployment declares it and the request
names nothing*: OpenSearch search pipelines (`normalization-processor`
with `min_max`/`l2`/`z_score` and weighted `arithmetic_mean`;
`score-ranker-processor` with `rank_constant` 1–10,000), Vespa rank
profiles (declared features, a `first-phase` expression such as
`0.7·bm25(text) + 0.3·attribute(popularity)`, a bounded `second-phase`
with `rerank-count`), haystack pipelines (the graph is the
configuration), zoekt (Go constants plus an "EXPERIMENTAL" BM25 flag).
vfs is in the second family. Vespa is the most complete precedent —
declared features, a first-phase expression, a bounded second phase —
and its per-query *profile selection* is the one thing vfs must not copy
onto the verb.

### 6.2 The recommended shape: declarative data plus protocol seams

Declared on the Storage at construction, frozen, hashable (the hash
feeds the signals' options fingerprint), inspected by the verb, never a
verb parameter:

```python
DatabaseStorage(
    url=...,
    embedder=...,
    ranker=Ranker(
        signals=(
            Signal("centrality", measure=InDegree(), transform=Saturation(pivot=4.0), weight=0.15),
            Signal("reads", transform=Log1p(), weight=0.10),          # rows exist only when ReadSignal is on
        ),
        fusion=Convex(weights={"vector": 0.5, "lexical": 0.5}),     # or RRF(k=10) for a rank-only leg
        aggregate=MaxP(chunks_per_entry=3),
    ),
)
```

with two protocol seams the built-ins implement and a deployment may
replace:

```python
class Fusion(Protocol):
    def to_sql(self, legs: Sequence[RankedLeg], signals: Sequence[SignalLeg]) -> Select | None: ...   # in-engine where expressible
    def fuse(self, legs: Sequence[RankedList], signals: Mapping[str, Mapping[EntryId, float]]) -> RankedList: ...  # the client-side floor

class Reranker(Protocol):
    async def rerank(self, query: str, candidates: Sequence[Candidate], *, limit: int) -> Sequence[Candidate]: ...
```

`to_sql` compiles the configuration into the fused statement — one
ranked CTE per leg with the scope allow-list inside, the fusion
expression (`Convex` and `RRF` are both arithmetic over ranks/scores),
each signal `LEFT JOIN`ed on `entry_id` as `weight · transform(value)`,
per-entry aggregation, the outer `LIMIT n` — and `fuse` runs the same
arithmetic over per-leg top-K lists on engines with no server-side
distance (MySQL community, `GENERIC`) and for the router's cross-mount
merge. `Centrality(measure=InDegree() | PageRank(damping=0.85) |
Katz(alpha=…))` selects which value the reindex phase computes — the
in-degree `GROUP BY` or the numpy kernel — so Clay's ask (PageRank/Katz
"could be calculated in the reindex pipeline and used in the fusion")
is a configuration choice, while the reference default stays the one
the evidence supports. A signal the ranker names that has no rows in
the current generation is dropped from the statement with a
warning-severity record. The `Reranker` seam is where Clay's cross-mount
BM25 rerank lives (on the `VFS`, since a cross-mount stage cannot belong
to one mount — fusion memo §7) and where a single-mount second phase
(a cross-encoder over the fused top-50) would attach later.

**Explain surface** (gap 9): per-leg ranks and raw scores, the signal
factors applied, which legs were present, and whether fusion compiled
in-engine or ran client-side ride the envelope — letta's
`relevance: {rrf_score, vector_rank, fts_rank}` and gbrain's
`degraded[]` trail are the field's two versions of the same honesty.

Named profiles (`rank_profiles={"default": …, "recency": …}` selected
on the mount) are trivial on top of this once the evaluation harness
gives a reason to hold two; before that they are speculative
generality.

## 7. Recommendation for the ADR

1. **One link signal, `centrality`, default measure in-degree** over
   `edges WHERE edge_type <> 'fs'` (extracted references once the
   extractor exists; declared edges today), log-transformed; PageRank
   and Katz as declared alternative measures on a ~30-line numpy
   power-iteration kernel behind the offload hop, adopted as default
   only if the harness shows a difference on a real corpus (the
   import-graph ρ = 0.58 says it may, on code). HITS is out.
2. **The hierarchy is a smoothing layer, not an edge type** (§2.5):
   `p(f) = (1−γ)·m(f) + γ·p(parent)`, γ = 0.2, bottom-up directory
   means, computed and stored at reindex; `fs` edges are never in the
   walk. Zero-edge mounts have no `centrality` rows and the leg is
   absent. A declared `path_shape` signal (depth, name length, learned
   sign) is the separate structural input if wanted.
3. **Everything in the prior path is computed at reindex and read at
   query time** — one `LEFT JOIN` on `signals`, one multiplication;
   never a graph walk, aggregate or smoothing pass per query. Reads
   are deferred (Clay, 2026-08-26); the opt-in popularity prior of §3
   is the recorded design for later.
4. **A `signals(entry_id, signal, value, generation)` table** refreshed
   as a reindex phase (extract → offloaded compute → chunked write),
   advisory and off the epoch pointer.
5. **Ranker API = frozen `Ranker` data + `Fusion`/`Reranker` protocols**,
   configured on the Storage, compiled to SQL where the engine can and
   run client-side where it cannot; nothing on the verb; the envelope
   explains what applied.

## 8. Forks the ADR must close

- **F1** — first link measure: in-degree (recommended) vs PageRank/Katz
  via the numpy kernel vs rustworkx (rejected: un-seamed native dep).
- **F2** — how a prior enters: bounded multiplicative/additive term
  (recommended; measured) vs an extra RRF list (rejected; measured).
- **F3** — read capture default: opt-in off (recommended) vs on with a
  short half-life. Privacy and the access-log nature argue for off.
- **F4** — popularity scope: global (recommended) vs per-user
  personalisation (later capability).
- **F5** — impression log (which glean list a read came from; enables
  propensity correction later; costs a write per glean and a session
  notion vfs lacks): not now.
- **F6** — signal publish discipline: in-place generation replacement
  (recommended) vs riding the gram epoch's CAS pointer.
- **F7** — a single `Ranker` (recommended) vs a named-profile registry
  once the harness exists.
- **F8** — an identity tier (a query that names a path lands at rank 1
  without consulting the fusion — gbrain's exact-lookup tier, zoekt's
  basename 7000, GitHub's complete-over-partial): the lexical index's
  path field (engine memo) covers most of it; whether a hard tier is
  also wanted is a harness question.
- **F9** — the smoothing weight γ: 0.2 default (recommended, ≤ 0.3) vs
  0 (no hierarchy influence) vs a type-normalised random walk at
  0.85/0.05/0.05 (the equivalent XRank/ObjectRank form). Settled by the
  held-out-edges experiment in §9; adopt γ > 0 only on ≥ +0.01 nDCG on
  two of three corpora with the fusion memo's noise-prior control
  unmoved.
- **F10** — reference context as a lexical field ("anchor text": the
  importing line, the link text, the call site, indexed on the
  *target* entry as a BM25F field beside the path field — engine memo
  E8). Upstill/Craswell/Hawking found anchor text made PageRank nearly
  redundant on the web; the extractor produces the referring line for
  free. The accuracy study's strongest arm; a lexical-index fork, named
  here because it competes with every prior in this memo.

## 9. What to measure: the accuracy study for 1d

No study has measured centrality's contribution to search accuracy on
a file corpus; the web numbers (Craswell 2005, +0.09 MAP) are the
closest evidence. The settling study, to run as the next research leg
on the evaluation harness (fusion memo §6):

- **Corpora with labels and edges**: SWE-bench Verified (500 issues
  over 12 Python repos — query = issue text, relevant = files the gold
  patch touched, graph = extracted imports + tree; the standard
  file-localisation task, so numbers are comparable to the agent
  literature); a Wikipedia slice from BEIR (NQ / HotpotQA) with the
  hyperlink graph recovered from the dump — the enterprise-wiki
  analogue and PageRank's home ground; the vfs-native hand-labelled set
  over `context/` + `docs/` as the regression gate.
- **Arms**: the hybrid baseline (convex BM25 + cosine); × each prior —
  in-degree, PageRank, Katz, HITS-authority — through log, saturation
  and sigmoid transforms with β swept by `ranx.optimize_fusion`; × γ ∈
  {0, 0.1, 0.2, 0.3}; the academic study's held-out *temporal*
  reference edges as navigational queries (a later link to a file is a
  query whose answer is the file); and the anchor-text field (F10) as
  its own arm and in combination.
- **Metrics**: nDCG@10, recall@20 (the agent's real question), MRR;
  `ranx.compare` for significance; the fusion memo's uninformative-prior
  injection as the control that no arm may worsen.
- **Decision rule**: the default measure, γ, and whether the anchor
  field ships are set by this table, not by taste.

## Sources

Studies (this repo): `studies/2026-08-26-glean/centrality-and-read-signals.md`
with `centrality-and-read-signals/graph_signals.py`, `scaling.py` and
their `*.out.txt`/`*.json`; `hierarchy-edges-academic.md` (mass-flow
derivations, five-corpus information test, XRank/ObjectRank/Xue 2005
model); `hierarchy-edges-prior-art.md` (fourteen systems plus Neo4j
GDS, SharePoint, Eiron 2004); `hierarchy-edges-experiment.md` with
`hierarchy-edges-experiment/hierarchy_edges.py`, `tables.py`,
`hierarchy_edges.json`; `fusion-and-merge.md` §A.4; `landscape.md` §1,
§2, §5.

Hierarchy papers (cited in full in the academic study): Xue, Zeng,
Chen, Ma, Zhang & Lu, "Exploiting the hierarchical structure for link
analysis", SIGIR 2005; Guo, Shao, Botev & Shanmugasundaram, "XRANK",
SIGMOD 2003; Balmin, Hristidis & Papakonstantinou, "ObjectRank", VLDB
2004; Eiron, McCurley & Tomlin, "Ranking the web frontier", WWW 2004
(HostRank/DirRank); Kamvar, Haveliwala, Manning & Golub, "Exploiting
the block structure of the web", 2003; Ogilvie & Callan on hierarchical
shrinkage.

Papers: Brin & Page 1998; Kraaij, Westerveld & Hiemstra, SIGIR 2002;
Upstill, Craswell & Hawking, TOIS 21(3) 2003 and ADCS 2003; Craswell,
Robertson, Zaragoza & Taylor, SIGIR 2005
(https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/craswell_sigir05.pdf);
Katz 1953; Kleinberg 1999; Joachims, Swaminathan & Schnabel, WSDM 2017
(https://arxiv.org/abs/1608.04468); Oosterhuis, ICTIR 2022
(https://arxiv.org/abs/2206.12204); Chuklin, Markov & de Rijke, *Click
Models for Web Search*, 2015; Craswell et al., WSDM 2008 (cascade);
Chapelle & Zhang, WWW 2009 (DBN).

Code and docs (refreshed 2026-08-26, read-only): zoekt @ a9206004
(`index/score.go`, `index/builder.go`, `api.go`; commits `f6d0aa00`
#523 and `c7f1e697` #853); HippoRAG @ 2f52a86 (`HippoRAG.py:2003–2210`);
graphify v8 @ 43d54ac (`analyze.py`, `cluster.py`, `reflect.py`,
CHANGELOG 0.9.3); LightRAG @ 812f2d5d; graphrag @ f40e9a2; cognee @
690c0ec02; rustworkx @ e02dc7ce; networkx @ cfc6b79; neural-search @
972d698; Sourcegraph indexed-ranking doc (403 to fetchers; cited via
search snippet and the zoekt source); OpenSearch search pipelines
(https://docs.opensearch.org/latest/search-plugins/search-pipelines/normalization-processor/);
Elasticsearch `rank_feature` and `function_score`; Vespa ranking
(https://docs.vespa.ai/en/ranking.html); LanceDB reranking
(https://docs.lancedb.com/reranking); haystack `DocumentJoiner`; mem0
platform Memory Decay (`docs/platform/features/memory-decay.mdx` @
39bc023).
