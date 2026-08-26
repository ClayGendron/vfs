# Filesystem hierarchy edges in glean's centrality prior: a graph-ranking review

- **Study for**: the glean *signals* memo
  (`context/research/2026-08-26-glean-ranking-signals-and-ranker-api.md`,
  §2.3 "no directory-adjacency fallback graph") and the signals ADR it
  feeds. Adversarial second opinion on one question only: whether the
  materialised `edge_type='fs'` parent→child rows (ADR 018) should join
  the graph that produces glean's query-independent centrality prior.
  Traversal verbs are out of scope. Constrained by ADR 007 (nothing on
  the verb) and by the fusion memo §4 (a prior enters as a bounded
  multiplicative factor `f × ∏(1 + β_s p_s)`, `β_s ≤ 0.5`).
- **Date**: 2026-08-26
- **Sources**:
  - Papers, each verified by web lookup on 2026-08-26 and listed with
    venue and URL/DOI under *Sources* at the end; two read in full from
    the PDF (Bianchini, Gori & Scarselli 2005 — Lemma 2.1, Theorems
    4.1–4.2, §2.3; McMillan et al. 2011 — §§2.1–4.6, Table 1).
  - vfs live tree: `src/vfs/models/rows.py:443–454` (`edges`:
    `source_id, target_id, edge_type, weight, distance`; both directions
    indexed), `context/decisions/018-edge-authoring-verbs-and-materialized-fs-edges.md`
    (pins 5–7: exactly one `fs` in-edge per live non-root entry, source
    is a directory, `parent_id` authoritative),
    `context/decisions/007-fused-glean-search-surface.md`,
    the signals memo and its study
    (`studies/2026-08-26-glean/centrality-and-read-signals.md` §A.4),
    the fusion memo §4.
  - Reference checkouts under `~/Git/Repos`, read-only, used as *data*
    (their import graphs and package trees), nothing copied:
    `sqlalchemy/lib/sqlalchemy`, `networkx/networkx`, `python-sdk/src/mcp`.
  - Executed: two throwaway numpy scripts in the session scratchpad
    (kernels reproduced in Appendix A): the Markdown link graph over this
    repo's `context/` + `docs/` plus its directory tree; the Python import
    graph plus package tree of `src/vfs` and the three checkouts above; a
    synthetic hub-in-a-directory graph. Raw outputs are condensed in §6.

## Question

The project owner holds that filesystem containment edges (directory →
child, one row per entry) should participate in the graph behind glean's
static centrality prior, at a lower weight than extracted reference edges
(imports, links, symbol uses). The memo holds that the tree is a
partition, not a citation structure: PageRank over a tree rewards depth
and fan-out, sibling adjacency makes in-degree equal directory size, and
the honest structural prior is a separate `path_shape` column. Who is
right, and what is the principled way to model a heterogeneous graph of
{containment, reference} edges so that a query-independent importance
score helps search ranking?

---

## 0. Verdict

Both are half right, and the half each has wrong is the same half:
**"weight."**

- The owner is right that the tree carries information about importance.
  On four of five corpora measured here (§6.2) the leave-one-out mean of
  a file's *siblings'* log in-degree predicts the file's own log
  in-degree (Spearman 0.18–0.77, permutation z = 2.3–13.9), and 28–63 %
  of the variance of log in-degree is *between* directories. A prior
  that ignores that leaves 51 % of this repo's documents (233 of 459)
  and 49 % of networkx's modules (287 of 583) at the floor when their
  directory already says where they sit. The literature agrees: the two
  hierarchy-aware rankers that were actually evaluated against PageRank
  on TREC .GOV — Kraaij's URL-form prior (SIGIR 2002) and Xue et al.'s
  Hierarchical Rank (SIGIR 2005), which "aggregates pages by directory,
  host or domain, ranks the aggregate, and distributes importance back
  down" — both beat it, the latter "even when the space is sparse and
  contains new pages," which is the vfs situation.
- The memo is right that containment is not citation and must not sit
  in the same random walk as references *under the same normaliser*.
  But its stated failure modes are the wrong ones, and its remedy (drop
  the tree) throws away a measured signal. PageRank over a bare
  parent→child tree is a depth prior of at most 1.8× spread — and on this
  corpus it is *wrong-signed* (ρ = −0.76 with depth; the referenced hubs
  are shallow). Sibling edges do not exist in vfs's edge table at all.
  The real failure is §2's normalisation lemma: **a per-node
  out-normalised walk makes the edge weight irrelevant for every node
  whose out-edges are all of one type.** In this repo's link graph 43 %
  of files (198 of 459) have no reference out-edge, so 100 % of their
  walk goes up the tree whatever weight `fs` rows carry. Measured: with
  `fs` weight `c` = 0.1, 0.5, 1.0 the file ordering's Spearman against
  reference-only PageRank is 0.746, 0.743, 0.738 — the knob does
  nothing — and 36–45 % of the stationary mass sits on directories,
  which are not glean candidates. In the synthetic hub test the hub's
  18× advantage over its siblings collapses to 3–5× and the siblings
  out-rank the 20 files that actually cite the hub by 2.6–5.8×.
- The principled model is the one XRank (SIGMOD 2003) and ObjectRank
  (VLDB 2004) built twenty years ago for exactly this heterogeneous
  case: **a transfer rate per edge type, each type normalised by its own
  out-degree**, so containment's share of the walk is a designer's
  constant (5 % up, 5 % down) rather than an artefact of how many
  references a file happens to emit. Under that model the reference
  ordering survives (Spearman 0.93–1.00 across five corpora at 5 %/5 %),
  a hub's spillover onto a sibling is second-order and diluted by
  directory size (`a_up · a_down · m / n` — 0.05 % of the hub's mass per
  sibling at n = 10), and a 500-child directory dilutes rather than
  concentrates. To first order that walk *is* hierarchical shrinkage —
  `p(f) = (1−γ)·c(f) + γ·p(parent)` with directory means built bottom-up
  — which is two O(N) passes, no eigenvector, no damping, no dangling
  nodes, exactly Ogilvie & Callan's INEX shrinkage and Xue's
  distribute-down step. **Recommend that** (§7): reference in-degree (or
  PageRank) as the citation layer, the tree as a smoothing layer with
  γ ≤ 0.3 (default 0.2, harness-gated, γ = 0 is the memo's design),
  never a shared normaliser, directories never candidates, `path_shape`
  kept as a *separate* signal whose sign must be learned (it is negative
  on this corpus: ρ = −0.38 between name length and in-degree, the
  opposite of zoekt's squash).

---

## 1. What the graph actually is

Three facts about vfs's edge table shape the whole question, and the
memo's §2.3 argument treats a different graph than the one ADR 018
materialises.

1. **The `fs` layer is a rooted out-tree, one in-edge per entry.** ADR 018
   pins 5–6: "exactly one fs in-edge per live non-root entry," source is
   a directory, `parent_id` authoritative, N−1 rows. There are **no
   sibling edges**. The memo's "same-parent edges make every file's
   in-degree its sibling count" describes a graph vfs does not have; on
   the graph it does have, in-degree over `fs` rows is the constant 1
   for every file and the child count for every directory. (Practical
   corollary for the memo's own default: `centrality = in-degree over
   live edges` must filter `edge_type <> 'fs'`, or it adds a constant
   +1 to every file and ranks directories by fan-out.)
2. **Directories are nodes but never glean candidates.** Glean ranks
   chunk-bearing entries. A directory's centrality matters only for
   what it re-emits to files. That is what makes the "concentrate vs
   dilute" question answerable in closed form (§3).
3. **The reference layer, when the extractor lands, is sparse and
   dangling-heavy.** Measured on this repo's Markdown link graph
   (2026-08-26 tree, 459 files, 691 edges): 233 files with zero
   in-degree (51 %), 198 with zero out-degree (43 %). networkx's import
   graph: 287 of 583 modules with zero in-degree (49 %). Sparse in-degree
   is what Xue et al. designed Hierarchical Rank for; dangling-heavy
   out-degree is what makes the naive mixed walk fail (§2).

## 2. The normalisation lemma: why "lower weight" is not a knob

Take any random-walk centrality with per-node out-normalisation —
PageRank, weighted PageRank in Xing & Ghorbani's sense, random walk with
restart — over the union graph where a file `f` has `r` reference
out-edges of weight 1 and one `fs` up-edge of weight `c`. The transition
probability of the up-edge is

    P(f → parent) = c / (r + c).

For `r = 0` this is **1 for every c > 0**. The weight cancels. The share
of `f`'s walk that leaks into the tree is therefore not chosen by the
designer; it is decided per node by how many references that node
happens to emit, and for the 43 % of files with `r = 0` it is total.
Lowering `c` only changes behaviour at nodes that have *both* kinds of
out-edge, which are the minority and, in a citation graph, the least
important ones to protect (a hub with many out-references is already
protected; a leaf with none is not).

The same lemma holds in the other direction. A directory has `k` child
down-edges and one up-edge, all `fs`; its split is `k/(k+1)` down and
`1/(k+1)` up regardless of `c`. So under per-node normalisation the tree
forms a closed reservoir: mass enters from every dangling-in-references
file, pools at directories, and is re-emitted down roughly uniformly.
The effect on the reference layer is that of **raising the teleport
probability by an amount the designer did not set** — Boldi, Santini &
Vigna (WWW 2005) showed PageRank's *ordering* is a function of the
damping factor; here the effective damping is a function of the
zero-out-degree share. Measured (§6.1): Spearman vs reference-only
0.746 / 0.743 / 0.738 at `c` = 0.1 / 0.5 / 1.0; on the four code corpora
0.86 / 0.96 / 0.91 / 0.71 at `c` = 0.1, barely different at 0.5.

This is also why the `edges.weight` column is the wrong place for the
containment weight: a per-edge weight enters the walk only through this
per-node normalisation. The knob that works is a **per-type transfer
rate with per-type normalisation** — §4.2's XRank/ObjectRank shape,
§7's model.

## 3. Mass flow on a tree, derived

Notation: `N` nodes, uniform teleport, damping `α` (0.85), dangling mass
redistributed uniformly (Langville & Meyer 2004 §5; Bianchini et al.
2005 Eq. 13 — the two treatments give the same ordering, their
Proposition 2.2). Let `b` be the per-node base inflow (teleport plus the
dangling share); every node receives at least `b`.

**(a) Parent→child only, per-node normalisation.** A directory with `k`
children sends `α·r(dir)/k` to each. The root has in-degree 0, so
`r(root) = b`; a node at depth `d` in a uniform `k`-ary tree gets

    r_d = b · Σ_{i=0}^{d} (α/k)^i  <  b / (1 − α/k).

Bounds: `k = 2` → 1.74·b; `k = 10` → 1.093·b; `k = 500` → 1.0017·b. So
(i) the tree-only prior is a *depth* prior, as the memo says, but
**deeper nodes get more, not less** — a child of a small directory
inherits a share of its parent's inflow; (ii) its total spread is at
most 1.8× — measured max/median 1.8 on this repo's tree; (iii) **a
500-child directory dilutes**: each child gains `α/500 = 0.0017` of the
directory's mass. Measured ρ with depth = −0.76 to −0.78 (§6.1, tree-only
rows), while reference in-degree's ρ with depth is +0.33 on the same
corpus — the tree-only walk is wrong-signed here, not merely weak.

**(b) Child→parent only.** Every non-root node has out-degree 1 and
sends `α·r` up; leaves receive only `b`. So

    r(dir) = b · (1 + α·n₁ + α²·n₂ + …),   n_i = descendants at depth i below,

a discounted subtree size, and the root — dangling, in-degree N₁ —
approaches Bianchini et al.'s star bound `1 + (N−1)·d` (their §1.2,
Theorem 5.1). **Files are all equal**: measured 79 % of the mass on
directories and a constant file vector. Child→parent edges alone
compute a *directory* score and no file prior at all.

**(c) Both directions, type-normalised transfer rates `a_up`, `a_down`,
remainder teleport.** For a file `f` in a directory `D` of `n` files,
with no reference edges:

    r(f) = b′ + (a_down/n)·r(D)
    r(D) = b′ + a_up · Σ_{c∈D} r(c) + (a_down/k)·r(parent(D))

Substituting and solving for `r(f)`:

    r(f)·(1 − a_up·a_down) = b′·(1 + a_down/n) + a_down²·r(parent(D))/(n·k)
    ⇒  r(f) ≈ b′·(1 + a_down/n + a_up·a_down + …)

The `a_up·a_down` term is the round trip `f → D → f` and is
**independent of n**; the `n`-dependent term is `a_down/n`. At 5 %/5 %
the spread between a file in a 1-file directory and one in a 500-file
directory is `(1.05)/(1.0001) ≈ 1.05` — five per cent. The tree-only
type-normalised walk is nearly flat over files (measured max/median 1.1).

Now put a hub `h` in `D` with reference in-mass `m ≫ b′`. Under type
normalisation the hub's *reference* share `a_ref·m` stays in the
reference layer (or teleports if the hub has no reference out-edges — a
missing type teleports, it does not leak); only `a_up·m` goes up. `D`
re-emits `a_down` of its mass split `n` ways, so each sibling gains

    Δr(sibling) = a_up · a_down · m / n.

At `a_up = a_down = 0.05`, `n = 10`: `0.00025·m` — 0.025 % of the hub's
mass per sibling. At 0.1/0.1, `n = 5`: `0.002·m`. Measured synthetic
(§6.3): hub/sibling 17.3 at n = 5 (the sibling gains 4 %), 18.0 at
n = 50, 18.1 at n = 500, against 18.0 with no tree. **Spillover is
second order in the transfer rates and first order diluted by directory
size. The tree cannot dominate.** Compare the naive model (§2) on the
same synthetic: hub/sibling 2.96 / 4.76 / 5.43, siblings out-ranking the
hub's actual referrers 5.8× / 3.0× / 2.6×, 45–47 % of all mass on three
directory nodes. One hub becomes one hot directory.

So, to the brief's question — *does a directory with 500 children
dilute or concentrate mass?* — both, in different directions, and the
asymmetry is the design lever: **down-flow dilutes by 1/n, up-flow
concentrates by n, and because directories are not candidates the only
thing that reaches a file is the product, which is n-independent for
the file's own round trip and 1/n for a sibling's spillover.**

**(d) Up-only is a no-op for file ranking — proved and measured.** With
`a_down = 0`, file inflows are `b″ + a_ref·Σ_{u→f} x_u/outdeg_ref(u)`:
mass that goes up returns only through uniform teleport. The fixed point
is the reference-only fixed point up to the scalar `b″`, and PageRank is
linear in its teleport vector, so the file ordering is identical.
Measured Spearman 1.000 (§6.1, `T(ref=0.85, up=0.10, down=0)`). A
child→parent-only containment layer is a directory-scoring device;
anyone proposing "child→parent only, so files aren't affected" is
proposing nothing. **Down-flow is what carries the prior to files;
up-flow is what makes the prior informed rather than uniform.** Both are
needed, and (c) shows both can be small.

**(e) Dangling nodes.** In the reference layer 43 % of files are
dangling. Bianchini et al. Lemma 2.1: the walk's total energy is
`N − d/(1−d)·Σ_{dangling} x_i`, i.e. dangling pages lose energy to the
uniform redistribution. Adding `fs` up-edges under a shared normaliser
makes *no file* dangling any more — the whole dangling correction
disappears and the mass that used to spread uniformly now spreads by
directory size, a second uncontrolled global change. Under per-type
normalisation each layer keeps its own dangling semantics: a file with
no reference out-edge still teleports its reference share.

**(f) Katz on containment** converges for every `α` (a tree's adjacency
is nilpotent, so `Σ αᵏ Aᵏ` is a finite sum, no `λ_max` estimate needed)
and equals: child→parent, the discounted descendant count of (b);
parent→child, the depth series of (a). Both are column expressions
(depth, subtree size) — here the memo is exactly right that the honest
name for "Katz over the tree" is `path_shape`, and the numpy kernel is
wasted on it.

## 4. What the literature says

### 4.1 Weighted PageRank, typed walks, and learned edge weights

- Xing & Ghorbani, *Weighted PageRank Algorithm* (CNSR 2004) weight each
  link by the in- and out-link popularity of its target rather than
  splitting rank equally; it is still a per-node normalisation, so §2's
  lemma applies to it unchanged. Random walk with restart (Tong,
  Faloutsos & Pan, ICDM 2006) is the query-seeded form (HippoRAG's
  personalised PageRank in the memo's §2.1) — same normaliser, out of
  glean's scope by ADR 007.
- The multilayer/multiplex literature is the formal home of "one
  transfer rate per layer": De Domenico et al., *Ranking in
  interconnected multilayer networks reveals versatile nodes* (Nature
  Communications 2015) define PageRank on a supra-adjacency tensor where
  inter-layer switching is a separate parameter from intra-layer
  transition — precisely the `a_ref / a_up / a_down` split of §3(c).
- Where the weight should come from: Agarwal, Chakrabarti & Aggarwal,
  *Learning to rank networked entities* (KDD 2006) learn per-edge-type
  conductances of a Markov walk from pairwise preferences; Backstrom &
  Leskovec, *Supervised random walks* (WSDM 2011) learn the transition
  weights as a function of edge features, with containment-like edge
  types as features. The principled way to set the containment weight
  is to learn it against a relevance target, which is §8's experiment;
  the principled *default* before that is a small constant.

### 4.2 Heterogeneous information networks: what "contains" does in a walk

- **XRank** (Guo, Shao, Botev & Shanmugasundaram, SIGMOD 2003) is the
  closest precedent and settles the modelling question. ElemRank
  propagates over three edge types — hyperlinks, *forward containment*
  (parent→child) and *reverse containment* (child→parent) — with three
  separate navigation probabilities `d₁, d₂, d₃`, and, decisively, the
  containment edges are normalised by the number of elements in the
  containing document (`N_de(v)`) while hyperlinks are normalised by the
  document's hyperlink out-degree (`N_h(u)`). That is exactly the
  per-type normalisation §2 asks for, chosen by people ranking *nested
  elements* of a tree, twenty-three years ago. They needed both
  directions for the same reason as §3(d): reverse containment lets an
  element's importance inform its ancestors; forward containment lets
  the document's importance reach its elements.
- **ObjectRank** (Balmin, Hristidis & Papakonstantinou, VLDB 2004)
  generalises it to a schema graph: every relationship type carries an
  *authority transfer rate* in each direction (paper→citing-paper high,
  paper→author lower, author→paper lower still), each normalised by the
  type's out-degree, with the leftover probability going to the base
  set. **PopRank** (Nie, Zhang, Wen & Ma, WWW 2005) learns those
  "popularity propagation factors" per relation type from partial
  ground-truth rankings — the transfer-rate design plus §4.1's learning.
- Sun & Han's HIN line — **RankClus** (Sun, Han, Zhao, Yin, Cheng & Wu,
  EDBT 2009: authority propagates across types with per-type rates),
  **PathSim** (Sun, Han, Yan, Yu & Wu, PVLDB 2011) and **HeteSim** (Shi,
  Kong, Huang, Yu & Wu, TKDE 2014) — gives the vocabulary for what a
  containment relation *means* in a walk. A meta-path `File–Dir–File`
  (siblings) is a *similarity* relation, not an *authority* one, and
  PathSim's whole point is that the raw path count along such a
  meta-path is biased toward high-degree objects — a big directory makes
  every pair of its files "similar" — so PathSim normalises by the
  self-path counts `(2·paths(x,y)) / (paths(x,x) + paths(y,y))`. The
  memo's "sibling in-degree = directory size" objection is this known
  bias, and normalisation is its known fix. What a `contains` relation
  does inside a random walk, in HIN terms, is act as a **two-hop
  smoothing operator over the partition**: `F→D→F` averages the files of
  a directory. That is a feature when importance clusters by directory
  (§6.2 says it does) and a bug only when the operator is unnormalised
  or over-weighted.

### 4.3 Hierarchy-aware ranking in web search

- **Kraaij, Westerveld & Hiemstra** (SIGIR 2002) — a prior `P(entry page
  | URL form ∈ {root, subroot, path, file})`, combined multiplicatively
  with the language-model score; the strongest of three non-content
  priors. This is a *partition-derived* prior with no link in it. The
  memo cites it for `path_shape`; it is equally the precedent that the
  hierarchy is where a document prior comes from.
- **Upstill, Craswell & Hawking** (TOIS 21(3), 2003) — URL-type was the
  only query-independent feature still useful over anchor text;
  PageRank and in-degree strongly correlated (their ADCS 2003 companion).
- **BlockRank** (Kamvar, Haveliwala, Manning & Golub, Stanford TR 2003)
  — the web graph is nested-block by host and domain; compute local
  PageRanks per block, weight blocks by a block-level PageRank, use the
  product as the starting vector. The hierarchy is used as *structure
  for computation and aggregation*, never as citation edges.
- **HostRank / dangling** (Eiron, McCurley & Tomlin, WWW 2004) — a
  host-level PageRank is more robust to link manipulation than page-level;
  the "web frontier" of dangling nodes is large enough that its
  treatment materially changes rankings. **SiteRank** (Wu & Aberer, AH
  2004) — PageRank at site granularity decomposes the global computation.
- **Hierarchical Rank** (Xue, Yang, Zeng, Yu & Chen, SIGIR 2005) — the
  one that matters most here. Pages are aggregated by directory, host or
  domain; link analysis runs on the aggregated graph; each node's
  importance is then *distributed to its member pages by the hierarchy*.
  On TREC 2003/2004 .GOV it "consistently outperforms PageRank,
  BlockRank and LayerRank," and the abstract's rationale is verbatim the
  vfs case: it "allows the importance of linked Web pages to be
  distributed in the Web page space even when the space is sparse and
  contains new pages." Aggregate-then-distribute is the two-pass
  smoothing of §7 with the reference graph collapsed to the directory
  level for the first pass.
- **Hierarchical language-model shrinkage** (Ogilvie & Callan, INEX
  2004) — an XML element's model is smoothed with its parent's, "bottom
  to top and then ranking by passing the model from the root down," the
  method they name shrinkage. The same estimator, on the content side
  instead of the link side, at the same conference series XRank targets.
- In-degree vs PageRank: Litvak, Scheinhardt & Volkovich (Internet
  Mathematics 4(2–3), 2007) prove the two have power-law tails differing
  only by a multiplicative constant — the theoretical reason the memo's
  ρ ≈ 0.97 is expected, and the reason §7 lets the citation layer be
  either.

### 4.4 PageRank on software graphs, and whether it was ever evaluated as a search prior

- **Component Rank / SPARS-J** (Inoue, Yokomori, Yamamoto, Matsushita &
  Kusumoto, TSE 31(3), 2005) — a PageRank variant over class use
  relations; frequently used classes rank higher, and the retrieval
  system "gives a higher rank to components that are used more
  frequently, so software engineers … have a better chance of finding it
  quickly." Evaluated as a retrieval aid, not against a text baseline
  with relevance judgments.
- **CodeRank** (Neate, Irwin & Churcher, ASWEC 2006) — PageRank over
  class/method dependency graphs as a *metric family*, not a ranker.
- **Sourcerer** (Linstead, Bajracharya, Ngo, Rigor, Lopes & Baldi, DMKD
  18(2), 2009) — the clearest positive evaluation: combining text with
  structural "Code Rank" raised retrieval AUC to 0.92, "roughly 10–30 %
  better than previous approaches based on text alone."
- **Portfolio** (McMillan, Grechanik, Poshyvanyk, Xie & Fu, ICSE 2011;
  read in full) — call-graph PageRank plus spreading activation plus
  VSM, combined as `S = λ_PR‖π‖_PR + λ_SAN‖π‖_SAN`. 49 professional C/C++
  programmers, 15 tasks, top-10 judged on a 4-point confidence scale:
  mean confidence 2.86 vs Google Code Search 1.97 and Koders 2.45;
  precision 0.65 vs 0.35 and 0.49 (p ≤ 3·10⁻⁸, Table 1). Caveat the
  authors do not resolve: PageRank's contribution is not ablated from
  SAN's.
- **Zaidman & Demeyer** (JSME 20(6), 2008) — webmining (HITS) over
  dynamic coupling recovers 90 % of maintainer-nominated key classes at
  ~50 % precision; a comprehension aid.
- **Bhattacharya, Iliofotou, Neamtiu & Faloutsos** (ICSE 2012) — graph
  metrics over call and collaboration graphs predict bug severity and
  maintenance effort; not search.
- **Sourcegraph** ("Ranking in a week", 2022; SCIP references → file
  graph → Spark PageRank → zoekt) — *undirected* edges, because directed
  ones "rank auto-generated files with tons of definitions very highly"
  and main-like files low; hand-vetted, no metric; later deleted (the
  memo's zoekt arc). Note that the pathology they hit — a generated file
  with many definitions — is the in-degree analogue of a big directory,
  and their fix was a normalisation choice, not a graph exclusion.

**What none of these evaluated**: a containment layer. Every software
study ranks over use/call/import edges only; every hierarchy-aware web
study aggregates by URL rather than adding tree edges. The specific
question — does adding the tree as a smoothing layer to a sparse
reference graph improve *search* nDCG — is open in the literature, and
the only honest answer is §8's experiment. What the literature does
settle is *how* to add it if it is added (per-type transfer rates or
aggregate-then-distribute) and *how not to* (a shared normaliser).

### 4.5 Tree- and DAG-specific measures

Hierarchy measures such as global reaching centrality (Mones, Vicsek &
Vicsek, PLoS ONE 2012) quantify how hierarchical a *graph* is, not a
node prior; depth-normalised degree and Katz on a DAG (§3(f)) reduce to
depth and subtree size. None of these adds anything a `path_shape`
column expression does not, and the memo is right to keep them out of
the kernel. The one tree-specific estimator that *is* a node prior is
the shrinkage of §4.3 (Ogilvie & Callan; Efron & Morris, JASA 1975, for
the empirical-Bayes justification: a group mean is a better prior for a
member than the grand mean whenever between-group variance is
non-trivial — which §6.2 measures).

## 5. The information test: does the directory know anything?

Before arguing about how to fold the tree in, ask whether it carries
information about the quantity the reference layer measures. The test:
for every file with at least one sibling, correlate its own
`log1p(in-degree)` with the leave-one-out mean of its siblings'
`log1p(in-degree)`; compare against a permutation null that shuffles
files across directories (LOO means are negatively biased under the
null, so the null mean is below zero); and report `η²`, the
between-directory share of the variance.

| corpus (read-only) | nodes | ref edges | zero-in | ρ(own, LOO sibling mean) | null mean ± sd | z | η² between-dir | zero-in files lifted by siblings |
|---|---|---|---|---|---|---|---|---|
| this repo, Markdown links (`context/`+`docs/`) | 459 files / 151 dirs | 691 | 233 (51 %) | **0.40** | −0.115 ± 0.076 | 6.8 | **0.49** | 108 of 142 |
| networkx (import graph) | 583 / 51 | 1 289 | 287 (49 %) | **0.77** | −0.041 ± 0.059 | 13.9 | **0.63** | 38 of 285 |
| sqlalchemy (`lib/sqlalchemy`) | 257 / 23 | 2 827 | 20 (8 %) | **0.49** | −0.077 ± 0.088 | 6.5 | **0.40** | 20 of 20 |
| python-sdk (`src/mcp`) | 123 / 21 | 389 | 16 (13 %) | 0.18 | −0.112 ± 0.132 | 2.3 | 0.28 | 12 of 16 |
| this repo, `src/vfs` imports | 49 / 8 | 173 | 2 (4 %) | −0.11 | −0.194 ± 0.210 | 0.4 | 0.11 | 2 of 2 |

Reading: on every corpus large enough to test, the directory a file sits
in predicts its reference in-degree well above chance; 28–63 % of the
variance of importance is between directories. The last column is the
practical stake — the number of the memo's "floor" files whose siblings
are referenced and who would therefore receive a non-zero prior under
smoothing. On networkx that is only 38 of 285: most zero-in-degree
modules sit in directories *of* zero-in-degree modules (leaf
algorithms), and smoothing correctly leaves them at the floor — the
prior is informed, not inflationary.

Two comparators on the Markdown corpus: depth predicts in-degree at
ρ = 0.37 (shallower = more referenced), and **name length at ρ = −0.38
in the direction opposite to zoekt's and Kraaij's priors** — the long
dated research-memo names are the hubs here. A hand-signed `path_shape`
prior would have pointed the wrong way on this corpus; the sibling prior
has no sign to get wrong.

## 6. Executed experiment

Kernels in Appendix A. Teleport is uniform over all nodes including
directories in every model (a production kernel would teleport to files
only; this only rescales directory mass). Dangling mass is redistributed
uniformly, per type in the type-normalised models.

### 6.1 Model comparison on this repo's link graph + tree

Files only (459); "ref" is the memo's position (reference edges,
α = 0.85). `W(c)` is the owner's naive model (`fs` edges both ways at
weight `c`, one normaliser). `T(a_ref, a_up, a_down)` is the
type-normalised walk. `S(γ)` is hierarchical shrinkage of
`log1p(in-degree)`.

| model | mass on dirs | ρ vs `ref` | ρ vs in-degree | distinct values among the 233 zero-in files | ρ vs −depth | max/median |
|---|---|---|---|---|---|---|
| `ref` | 0.11 | 1.000 | 0.974 | 1 | +0.33 | 53.4 |
| `W(c=0.1)` | 0.36 | 0.746 | 0.723 | 45 | +0.39 | 31.9 |
| `W(c=0.5)` | 0.41 | 0.743 | 0.723 | 45 | +0.42 | 23.2 |
| `W(c=1.0)` | 0.45 | 0.738 | 0.721 | 45 | +0.44 | 18.1 |
| `T(0.85, 0.05, 0.05)` | 0.16 | **0.935** | 0.910 | 27 | +0.12 | 52.1 |
| `T(0.75, 0.10, 0.10)` | 0.22 | 0.933 | 0.911 | 27 | +0.13 | 38.8 |
| `T(0.60, 0.20, 0.20)` | 0.33 | 0.892 | 0.866 | 27 | +0.11 | 25.9 |
| `T(0.85, up 0, down 0.10)` | 0.11 | 0.935 | 0.910 | 20 | +0.11 | 50.5 |
| `T(0.85, up 0.10, down 0)` | 0.20 | **1.000** | 0.974 | 1 | +0.33 | 53.4 |
| tree only, `T(·, 0.1, 0.1)` | 0.32 | −0.43 | −0.46 | 20 | **−0.76** | 1.1 |
| tree only, parent→child, `c=1` | 0.21 | −0.44 | −0.47 | 20 | **−0.78** | 1.8 |
| tree only, child→parent, `c=1` | 0.79 | const. | const. | 1 | const. | 1.0 |
| `S(γ=0.2)` | — | 0.908 | **0.932** | 20 | +0.55 | 15.2 |
| `S(γ=0.5)` | — | 0.892 | 0.920 | 20 | +0.60 | 4.4 |

Top-5 files are identical for `ref` and `T(0.85, 0.05, 0.05)`
(`open-questions.md`, two 2026-08-25 research memos,
`docs/reference/glob-patterns.md`, spec 031's design); `W(c ≥ 0.5)`
replaces three of them with `docs/internals/fs.md` and the three
2026-07-13 database-storage memos — files whose directories are large,
not files that are cited.

Five-corpus check of the two live candidates (Spearman of file ordering
vs `ref`): `T(0.85, 0.05, 0.05)` = 0.935 / 0.939 / 1.000 / 0.998 / 0.999
(docs / networkx / sqlalchemy / mcp / vfs); `W(0.5)` = 0.743 / 0.885 /
0.945 / 0.697 / 0.858, with 13–45 % of mass on directories.

### 6.2 Information test

§5's table.

### 6.3 Synthetic hub-in-a-directory

20 referrer files in directory B each cite one hub file in directory A;
A also holds `n` unreferenced siblings. Ratios of stationary mass:

| n siblings | `ref` hub/sibling | `T(0.85,0.1,0.1)` hub/sibling | `T` sibling/referrer | `W(0.5)` hub/sibling | `W(0.5)` sibling/referrer | `W(0.5)` mass on the 3 dirs |
|---|---|---|---|---|---|---|
| 5 | 18.0 | 17.3 | 1.04 | **2.96** | **5.79** | 0.47 |
| 50 | 18.0 | 18.0 | 1.00 | 4.76 | 3.01 | 0.45 |
| 500 | 18.0 | 18.1 | 0.99 | 5.43 | 2.56 | 0.46 |

The `T` column is §3(c)'s closed form to two decimals
(`Δ = a_up·a_down·m/n`); the `W` column is §2's lemma — the hub has no
reference out-edge, so its entire walk enters the tree at any weight.

## 7. Recommendation

### 7.1 The model

**Two layers, two normalisers, one score.**

- **Citation layer**: reference edges (`edge_type <> 'fs'`; imports,
  links, symbol uses, user-minted edges), scored by in-degree or
  PageRank exactly as the memo proposes — Litvak et al. and the memo's
  ρ ≈ 0.97 say the choice is second-order. Call the per-file value
  `c(f) = log1p(in-degree)` (or `log(PageRank)`; the log is Craswell's
  finding and also what keeps a hub from flooding its siblings in the
  next step).
- **Smoothing layer**: the `fs` tree, used to shrink `c(f)` toward its
  neighbourhood:

      m(D)  = mean over children x of D of m(x)        (bottom-up; m(f) = c(f))
      p(root) = m(root)
      p(x)  = (1 − γ)·m(x) + γ·p(parent(x))            (top-down)

  and the stored signal is `p(f)` for files, min-max normalised per
  generation, entering the fusion as `(1 + β·p)` per the fusion memo.
  Directories get `p(D)` computed but never stored as candidates.
- **Equivalent single-kernel form**, if one power iteration is preferred
  over two passes: the type-normalised walk
  `x ← a_ref·P_refᵀx + a_down·P_downᵀx + a_up·P_upᵀx + (1 − Σa + leaked)·u`
  with per-type out-degree normalisation and per-type dangling teleport
  (Appendix A), `a_ref = 0.85`, `a_up = a_down = 0.05`. §3(c) shows it is
  the shrinkage estimator to first order; §6.1 shows they rank alike
  (both 0.89–0.94 against `ref`, `S` closer to in-degree, `T` closer to
  PageRank). Prefer the two-pass form: no damping constant, no
  convergence tolerance, no dangling handling, O(N) instead of
  O(iterations × E), and incrementally recomputable per dirty subtree.

**Direction**: both. Child→parent alone changes nothing for files (§3(d),
proved); parent→child alone gives a uniform depth prior (§3(a)).
Information goes up, the prior comes down.

**Keeping the tree from dominating**, four mechanisms, all bounded:

1. `γ ≤ 0.3` (or `a_up + a_down ≤ 0.10`), default **γ = 0.2**. At
   γ = 0.2 the file ordering keeps ρ = 0.93 with in-degree and the
   hub-to-sibling spillover is `γ·(1−γ)/n` of the *log* value — a hub
   with in-degree 100 in a 10-file directory raises an unreferenced
   sibling from 0 to `0.16·log(101)/10 ≈ 0.07` — a tenth of what one
   citation is worth (`log 2 = 0.69`). γ = 0 is byte-for-byte the
   memo's design.
2. Smooth the **log** of in-degree, never the raw count: the mean of a
   directory holding one 100-cited file and nine uncited ones is 0.46
   in log space, 10 in count space.
3. Directories are never candidates; they are intermediaries.
4. `path_shape` (depth, name length) stays a *separate* declared signal,
   harness-gated, with its sign learned per deployment (§5: negative on
   this corpus).

**Options hash**: `γ` (or the transfer triple) and the citation measure
are part of the `centrality` signal's `options_hash`, so changing them
invalidates the generation exactly as the memo's transform change does.
This is a *measure option* on the existing `centrality` signal
(`Centrality(measure=InDegree(), smoothing=Hierarchical(gamma=0.2))`),
not a new signal and not a verb parameter — ADR 007 is untouched.

### 7.2 Computing it at index time (SQL-backed store, offloaded numpy)

Fits the memo's extract → offloaded compute → chunked write phase with
one more array and two more passes.

1. **Extract** (keyset-paginated, no statement grows with the graph):
   - `SELECT target_id, COUNT(*) FROM edges JOIN entries … WHERE
     edge_type <> 'fs' GROUP BY target_id` → `c` (the memo's one
     statement, with the `fs` filter §1 requires), or the reference
     `(source_id, target_id)` pairs if PageRank is the measure.
   - `SELECT id, parent_id FROM entries WHERE live …` → the tree, from
     the authoritative column (ADR 018 pin 7). The `fs` edge rows are
     the same information and may be used instead if the graph phase
     already streams them; either way it is N−1 pairs.
2. **Compute** through `call_offloaded`:
   - Map ids → dense indices (`np.unique` + `searchsorted`); `parent`
     as an `int64` array; `depth` by iterating `depth[v] = depth[parent[v]] + 1`
     level by level (≤ max depth iterations, each a vectorised gather).
   - Bottom-up: for level `L = max_depth … 1`, `sum = np.bincount(parent[at L],
     weights=m[at L])`, `cnt = np.bincount(parent[at L])`, `m[dir] = sum/cnt`.
   - Top-down: for level `1 … max_depth`, `p[at L] = (1−γ)·m[at L] + γ·p[parent[at L]]`.
   - Min-max normalise `p` over files; heartbeat the lease between
     extract, compute and write as the memo already does.
   Cost is O(N + E) with ~3 vectorised passes — well under the memo's
   0.76 s numpy PageRank at 10⁶ nodes; memory is three float64 vectors
   and one int64 parent vector (32 MB at 10⁶). For the single-kernel
   form, the memo's `np.bincount(tgt, weights=rank[src]/outdeg[src])`
   loop runs once per layer per iteration (three bincounts instead of
   one; ~2.3 s extrapolated at 10⁶ nodes / 4.8 M edges).
3. **Write** `signals(entry_id, 'centrality', p, generation)` for files
   only, chunked by the parameter budget; delete the prior generation.
   Absent rows (no reference edges *and* no referenced sibling anywhere
   up the tree) mean the memo's "absent, not zero" rule still holds for
   a bare tree: with `c ≡ 0` every `p ≡ 0`, and the phase writes no
   rows.

**Incrementality** if it is ever needed: a changed file alters `m` only
on its ancestor chain and `p` only within the subtrees hanging off that
chain; recompute per dirty subtree. Not needed at the sizes the memo
measured.

### 7.3 Where this disagrees with the memo, explicitly

1. **"No directory fallback graph … the tree is a partition, not a
   citation structure."** Agree on the premise, reject the conclusion.
   A partition is exactly what document priors are built from (Kraaij
   2002, Xue 2005, BlockRank, Ogilvie & Callan), and §5 measures that
   the partition carries 28–63 % of the variance of importance. The
   tree should not be a citation layer; it should be a smoothing layer.
2. **"Parent→child edges make PageRank a depth prior computed
   expensively."** Right in kind, wrong in sign and magnitude: deeper
   nodes gain, the spread is ≤ 1.8×, and the sign is opposite to the
   reference structure on this corpus. More importantly, this is the
   *tree-only* case; in the *mixed* case the failure is §2's leak, which
   the memo does not name and which a "lower weight" cannot fix.
3. **"Same-parent edges make every file's in-degree its sibling
   count."** True of a graph vfs does not have. vfs's `fs` layer has no
   sibling edges; in-degree over it is the constant 1 for files. If a
   sibling meta-path were ever used, PathSim normalisation is the
   standard fix, not exclusion.
4. **`path_shape` as *the* structural prior.** Its sign flips by corpus
   (ρ = −0.38 here versus zoekt's and Kraaij's assumption). Keep it, but
   as a second, harness-gated signal; the neighbourhood prior has no
   sign to assume.
5. **The default `centrality = in-degree over live edges`** needs
   `edge_type <> 'fs'` or it counts the mirror.

And where the owner is wrong: "lower weight on `fs` edges in the same
graph" is not a knob (§2, §6.1, §6.3), and `edges.weight` is not where
the containment weight lives. The weight must be a per-type transfer
rate or a shrinkage coefficient — a `Ranker` configuration constant, not
a column.

## 8. The experiment that settles γ

§5 settles *whether* the tree carries information (it does, on four of
five corpora). It cannot settle whether that information improves
*retrieval*, because in-degree is itself only a proxy for relevance. The
harness the fusion memo already calls for decides γ; the design:

1. **Corpora**: this repo's `context/`+`docs/` (wiki-shaped), and two
   code trees with an extractor-grade import graph (sqlalchemy,
   networkx — both already measured structurally above; read-only).
2. **Queries and judgments without human labels** (the navigational
   task Kraaij and Upstill used, adapted): hold out 20 % of reference
   edges — *temporally* where git history gives it (the references added
   in the most recent commits), else at random — and for each held-out
   edge `(u → v)` form the query from `u`'s anchor text or the imported
   name, with `v` as the single relevant entry. This tests exactly the
   thing a prior is for: promoting the entry that a new reference is
   about to cite. Report MRR and nDCG@10; add the fusion memo's noise
   prior as the control that must not regress.
3. **Grid**: `β ∈ {0, 0.25, 0.5}` × `γ ∈ {0, 0.1, 0.2, 0.3, 0.5}` for the
   two-pass form, and `(a_up, a_down) ∈ {0, 0.05, 0.1}²` for the walk
   form, over in-degree and PageRank citation layers. `γ = 0` is the
   memo's design and the baseline that must be beaten.
4. **Decision rule**: adopt the smallest γ within 0.01 nDCG@10 of the
   best, provided the held-out-edge MRR improves over γ = 0 by ≥ 0.01 on
   at least two of three corpora and the noise-prior control does not
   move by more than the fusion memo's −0.05 bound. Otherwise ship
   γ = 0 with the smoothing option present but off.
5. **Second-order checks** the harness should print: the share of
   zero-in-degree entries that receive `p > 0` (§5's last column), the
   Spearman of `p` with `c` (must stay ≥ 0.9 at the adopted γ), and
   the top-20 by `p` minus the top-20 by `c` — the files the tree
   promoted — inspected by hand once, the way Sourcegraph vetted theirs.
6. **When reads exist** (the memo's opt-in popularity prior), rerun with
   the time-decayed read count as the target instead of held-out edges;
   agreement between the two targets on γ is the strongest evidence
   available without human judgments.

---

## Appendix A — kernels used (numpy, throwaway; original code)

```python
def pagerank_typed(n, layers, iters=300, tol=1e-12):
    """x <- sum_t a_t * P_t^T x + (1 - sum_t a_t + leaked) * u.
    layers: [(src, tgt, a_t)]; each type normalised by its own out-degree;
    a node with no out-edge of type t teleports that type's share."""
    u = np.full(n, 1.0 / n); x = u.copy(); total = sum(a for *_, a in layers)
    outs = [np.bincount(src, minlength=n).astype(float) for src, _, _ in layers]
    for _ in range(iters):
        nx = (1.0 - total) * u.copy()
        for (src, tgt, a), od in zip(layers, outs):
            has = od > 0; flow = np.zeros(n); flow[has] = x[has] / od[has]
            nx += a * np.bincount(tgt, weights=flow[src], minlength=n)
            nx += a * x[~has].sum() * u
        if np.abs(nx - x).sum() < tol: return nx / nx.sum()
        x = nx
    return x / x.sum()

def pagerank_weighted(n, src, tgt, w, alpha=0.85, iters=300, tol=1e-12):
    """Classic weighted PageRank: one normaliser over ALL out-edges (the W(c) model)."""
    u = np.full(n, 1.0 / n); x = u.copy(); wout = np.bincount(src, weights=w, minlength=n)
    for _ in range(iters):
        has = wout > 0; share = np.zeros(n); share[has] = x[has] / wout[has]
        nx = (1 - alpha) * u + alpha * np.bincount(tgt, weights=share[src] * w, minlength=n)
        nx += alpha * x[~has].sum() * u
        if np.abs(nx - x).sum() < tol: return nx / nx.sum()
        x = nx
    return x / x.sum()

def shrink(c, parent, children, order, gamma):
    """Hierarchical shrinkage: bottom-up directory means, top-down blend.
    order = nodes in pre-order (root first); files have m = c."""
    m = c.copy()
    for i in reversed(order):
        if children[i]: m[i] = np.mean([m[k] for k in children[i]])
    p = np.zeros_like(m)
    for i in order:
        p[i] = m[i] if parent[i] < 0 else (1 - gamma) * m[i] + gamma * p[parent[i]]
    return p
```

Reference-edge extraction: Markdown relative links and backticked `.md`
paths resolving to a known file (the earlier study's rule); Python
`import pkg.a` / `from pkg.a import b` / `from .a import b` resolved
against the package's own module set, targets collapsed to the nearest
existing module. Spearman computed on average ranks (no scipy in the
project environment). Permutation null: 500 shuffles (300 for the code
corpora) of files across directories, seed 0.

## Sources

Papers (verified 2026-08-26):

- Xing & Ghorbani, "Weighted PageRank Algorithm," *CNSR 2004*, 305–314 —
  https://www.semanticscholar.org/paper/322293bb0bbd47349c5fd605dce5c63f03efb6a8
- Tong, Faloutsos & Pan, "Fast Random Walk with Restart and Its
  Applications," *ICDM 2006*, 613–622 — DOI 10.1109/ICDM.2006.70
- Backstrom & Leskovec, "Supervised Random Walks: Predicting and
  Recommending Links in Social Networks," *WSDM 2011*, 635–644 —
  https://ir.webis.de/anthology/2011.wsdm_conference-2011.71/
- Agarwal, Chakrabarti & Aggarwal, "Learning to Rank Networked
  Entities," *KDD 2006*, 14–23 — DOI 10.1145/1150402.1150409
- De Domenico, Solé-Ribalta, Omodei, Gómez & Arenas, "Ranking in
  interconnected multilayer networks reveals versatile nodes," *Nature
  Communications* 6:6868, 2015 — DOI 10.1038/ncomms7868
- Guo, Shao, Botev & Shanmugasundaram, "XRANK: Ranked Keyword Search
  over XML Documents," *SIGMOD 2003* — DOI 10.1145/872757.872762
  (ElemRank: `d₁, d₂, d₃` for hyperlink / forward containment / reverse
  containment; containment normalised by `N_de(v)`, hyperlinks by
  `N_h(u)`)
- Balmin, Hristidis & Papakonstantinou, "ObjectRank: Authority-Based
  Keyword Search in Databases," *VLDB 2004*, 564–575 —
  https://www.researchgate.net/publication/2949568
- Nie, Zhang, Wen & Ma, "Object-Level Ranking: Bringing Order to Web
  Objects," *WWW 2005*, 567–574 — DOI 10.1145/1060745.1060828
- Sun, Han, Zhao, Yin, Cheng & Wu, "RankClus: Integrating Clustering
  with Ranking for Heterogeneous Information Network Analysis," *EDBT
  2009*, 565–576 — https://web.cs.ucla.edu/~yzsun/papers/edbt09_rankclus.pdf
- Sun, Han, Yan, Yu & Wu, "PathSim: Meta Path-Based Top-K Similarity
  Search in Heterogeneous Information Networks," *PVLDB* 4(11), 2011,
  992–1003 — DOI 10.14778/3402707.3402736
- Shi, Kong, Huang, Yu & Wu, "HeteSim: A General Framework for
  Relevance Measure in Heterogeneous Networks," *IEEE TKDE* 26(10),
  2014, 2479–2492
- Kraaij, Westerveld & Hiemstra, "The Importance of Prior Probabilities
  for Entry Page Search," *SIGIR 2002* — DOI 10.1145/564376.564383
- Upstill, Craswell & Hawking, "Query-independent evidence in home page
  finding," *ACM TOIS* 21(3), 2003 — DOI 10.1145/858476.858479;
  "Predicting fame and fortune: PageRank or indegree?," *ADCS 2003* —
  https://david-hawking.net/pubs/upstill_adcs03.pdf
- Kamvar, Haveliwala, Manning & Golub, "Exploiting the Block Structure
  of the Web for Computing PageRank," Stanford TR, 2003 —
  https://nlp.stanford.edu/pubs/blockrank.pdf
- Eiron, McCurley & Tomlin, "Ranking the Web Frontier," *WWW 2004* —
  DOI 10.1145/988672.988714
- Wu & Aberer, "Using SiteRank for Decentralized Computation of Web
  Document Ranking," *AH 2004*, LNCS 3137 — DOI 10.1007/978-3-540-27780-4_30
- Xue, Yang, Zeng, Yu & Chen, "Exploiting the Hierarchical Structure
  for Link Analysis," *SIGIR 2005*, 186–193 — DOI 10.1145/1076034.1076068
- Ogilvie & Callan, "Hierarchical Language Models for XML Component
  Retrieval," *INEX 2004*, LNCS 3493 — DOI 10.1007/11424550_18
- Litvak, Scheinhardt & Volkovich, "In-Degree and PageRank: Why Do They
  Follow Similar Power Laws?," *Internet Mathematics* 4(2–3), 2007,
  175–198 — DOI 10.1080/15427951.2007.10129293
- Bianchini, Gori & Scarselli, "Inside PageRank," *ACM TOIT* 5(1),
  2005, 92–128 — DOI 10.1145/1052934.1052938 (read in full: Lemma 2.1,
  Prop. 2.2, §2.3 essential/inessential nodes, Theorems 4.1–4.2, the
  star bound `1 + (N−1)d`)
- Langville & Meyer, "Deeper Inside PageRank," *Internet Mathematics*
  1(3), 2004, 335–380 — DOI 10.1080/15427951.2004.10129091
- Boldi, Santini & Vigna, "PageRank as a Function of the Damping
  Factor," *WWW 2005*, 557–566 — http://www2005.org/cdrom/docs/p557.pdf
- Craswell, Robertson, Zaragoza & Taylor, "Relevance Weighting for
  Query Independent Evidence," *SIGIR 2005* —
  https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/craswell_sigir05.pdf
- Inoue, Yokomori, Yamamoto, Matsushita & Kusumoto, "Ranking
  Significance of Software Components Based on Use Relations," *IEEE
  TSE* 31(3), 2005 — https://ieeexplore.ieee.org/document/1423993/
- Neate, Irwin & Churcher, "CodeRank: A New Family of Software
  Metrics," *ASWEC 2006*, 369–378 — DOI 10.1109/ASWEC.2006.21
- Zaidman & Demeyer, "Automatic identification of key classes in a
  software system using webmining techniques," *J. Software Maintenance
  and Evolution* 20(6), 2008, 387–417 — DOI 10.1002/smr.370
- Linstead, Bajracharya, Ngo, Rigor, Lopes & Baldi, "Sourcerer: mining
  and searching internet-scale software repositories," *Data Mining and
  Knowledge Discovery* 18(2), 2009, 300–336 — DOI 10.1007/s10618-008-0118-x
- McMillan, Grechanik, Poshyvanyk, Xie & Fu, "Portfolio: Finding
  Relevant Functions and Their Usages," *ICSE 2011* —
  https://www.cs.wm.edu/~denys/pubs/ICSE11-Portfolio.pdf (read in full)
- Bhattacharya, Iliofotou, Neamtiu & Faloutsos, "Graph-Based Analysis
  and Prediction for Software Evolution," *ICSE 2012*, 419–429 — DOI
  10.1109/ICSE.2012.6227173
- Mones, Vicsek & Vicsek, "Hierarchy Measure for Complex Networks,"
  *PLoS ONE* 7(3):e33799, 2012 — DOI 10.1371/journal.pone.0033799
- Efron & Morris, "Data Analysis Using Stein's Estimator and its
  Generalizations," *JASA* 70(350), 1975, 311–319 — DOI
  10.1080/01621459.1975.10479864

Practice:

- Sourcegraph, "Ranking in a week" (2022) —
  https://sourcegraph.com/blog/ranking-in-a-week (403 to fetchers; read
  via the author's mirror https://www.eric-fritz.com/articles/ranking-in-a-week):
  SCIP references → undirected file graph → Spark PageRank → zoekt
  document order; directed edges rejected because they ranked generated
  definition-heavy files highest.
- zoekt history (#523, #853) and Sourcegraph's later removal: as cited
  in the signals memo §2.1.

vfs: `src/vfs/models/rows.py:443–454`; ADR 018 pins 5–7; ADR 007; the
signals memo §2.3 and §2.4; the fusion memo §4; the centrality study
§A.4 and its `graph_signals.py` extraction rule.
