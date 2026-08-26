# Hierarchy edges in the centrality prior: an executed experiment on this repository

- **Study for**: `context/research/2026-08-26-glean-ranking-signals-and-ranker-api.md`
  §2.3 — the memo's rule "no directory-adjacency fallback graph" against the
  owner's hypothesis that fs edges (`edge_type = 'fs'`, ADR 018) added to the
  reference graph *at a lower weight* would improve the static prior.
- **Date**: 2026-08-26
- **Method**: executed, single script, read-only over this repository.
  `hierarchy-edges-experiment/hierarchy_edges.py` walks `src/`, `docs/`,
  `context/`, `tests/`, `crates/`, `scripts/` (build artefacts skipped),
  extracts reference edges with the same idea as
  `centrality-and-read-signals/graph_signals.py` (markdown relative links and
  backticked `.md` paths over `context/` + `docs/`; `from vfs… import` /
  `import vfs…` over `src/vfs`), materialises fs edges the way ADR 018 does
  (one `parent → child` per non-root entry), and computes weighted PageRank
  (α = 0.85, `networkx.pagerank`, tol 1e-10), weighted in-degree, and Katz
  (α = 0.9/λ_max, exact solve via `katz_centrality_numpy`; λ_max from a dense
  eigendecomposition) on 19 configurations. `tables.py` renders
  `tables.md` from the raw `hierarchy_edges.json` (which also carries every
  node's score under every configuration and the per-node depth / fan-out
  attributes). Throwaway venv: Python 3.13, networkx 3.6.1, scipy 1.18.1,
  numpy 2.5.2, bm25s 0.3.11; the project's lockfile was not touched. Nothing
  copied from reference repos.

## Question

If the fs hierarchy edges vfs already stores are added to the reference graph
(markdown links + Python imports) at a reduced weight, does the centrality
prior glean would use get better, or does it turn into the memo's "depth
prior in disguise"? Concretely: how far does H(w) = R ∪ w·T drift from R,
what climbs, what drives the new scores (depth? parent fan-out? directory
size?), how much of the "coverage" gain is real, and does any of it move a
BM25 ranking on real queries.

## Setup

| | |
|---|---|
| nodes | 977 — 779 files, 198 directories (the root `.` included, as vfs has a root entry) |
| fs edges (T) | 976, one `parent → child` per non-root node; tried **down** (as materialised), **up** (`child → parent`), **both** |
| reference edges (R) | 864 — 691 markdown link edges, 173 import edges — incident to 394 nodes (all files) |
| tree shape | max depth 7, max fan-out 113 (`context/specs/archive`); `src` and `crates` are one-child chains |
| H(w) | R at weight 1.0 ∪ T at w ∈ {0.05, 0.1, 0.25, 0.5, 1.0}; parallel edges sum |
| Katz α | 0.9/λ_max: λ_max = 5.93 for R (set by the markdown link cycles) → α = 0.152; a pure tree is nilpotent (λ_max = 0), so T alone uses α = 0.9; λ_max climbs to 11.4 for H(1.0)[both] |
| excluded | `__pycache__`, `crates/vfs-core/target`, `.pytest_cache`, `.ruff_cache`, `.DS_Store`, and this study's own directory (its script quotes the sanity-check queries and had ranked first for four of them) |

Two honesty notes on the corpus. The "~1,500 files" figure in the brief
counts the Rust `target/` build tree; the tree a vfs mount of this repo would
honestly hold is the 977 nodes above. And the walk includes today's
untracked glean research outputs, so the markdown graph is larger than the
440-file graph the memo measured (691 vs 615 link edges).

"Any reference edge" below means a node incident to at least one R edge, in
or out (394 nodes). "At floor" means a score equal to the configuration's
minimum: for in-degree that is zero; for PageRank and Katz it is the value
every node with no in-edges shares.

## Results

Full tables, including every w row, are in
`hierarchy-edges-experiment/tables.md`; rows that are identical across w are
collapsed here.

### 1. Agreement with R (Spearman / Kendall)

Rank correlation of each configuration with R for the same measure, over
the 394 reference-incident nodes, all 977 nodes, and the 779 files; and with
T (same direction) over all nodes.

| config | in-deg ref | in-deg all | in-deg files | PR ref | PR all | PR files | Katz ref | Katz all | Katz files | PR vs T | Katz vs T |
|---|---|---|---|---|---|---|---|---|---|---|---|
| T[down] | const | 0.02/0.02 | const | −0.41/−0.30 | −0.19/−0.14 | −0.30/−0.23 | −0.28/−0.22 | −0.20/−0.17 | −0.28/−0.24 | 1 | 1 |
| T[up] | const | −0.30/−0.28 | const | const | −0.30/−0.27 | const | const | −0.30/−0.27 | const | 1 | 1 |
| T[both] | const | −0.30/−0.28 | const | −0.47/−0.34 | −0.45/−0.35 | −0.35/−0.27 | 0.07/0.05 | 0.04/0.04 | 0.27/0.21 | 1 | 1 |
| H(w)[down], **any w** | 1.00/1.00 | 1.00/1.00 | 1.00/1.00 | 0.85/0.75 | 0.72/0.62 | 0.75/0.65 | 0.99/0.97 | 0.80/0.74 | 0.86/0.81 | 0.44/0.47 | 0.34/0.36 |
| H(0.05)[up] | 1.00/1.00 | 0.84/0.80 | 1.00/1.00 | 1.00/0.99 | 0.65/0.63 | 1.00/1.00 | 1.00/1.00 | 0.84/0.81 | 1.00/1.00 | 0.49/0.45 | 0.25/0.26 |
| H(0.1)[up] | 1.00/1.00 | 0.83/0.79 | 1.00/1.00 | 1.00/0.99 | 0.65/0.63 | 1.00/1.00 | 1.00/1.00 | 0.83/0.80 | 1.00/1.00 | 0.50/0.45 | 0.26/0.27 |
| H(0.25)[up] | 1.00/1.00 | 0.79/0.76 | 1.00/1.00 | 1.00/0.98 | 0.63/0.61 | 1.00/0.99 | 1.00/1.00 | 0.81/0.77 | 1.00/1.00 | 0.52/0.47 | 0.30/0.30 |
| H(0.5)[up] | 1.00/1.00 | 0.74/0.71 | 1.00/1.00 | 1.00/0.96 | 0.61/0.59 | 1.00/0.98 | 1.00/1.00 | 0.77/0.73 | 1.00/1.00 | 0.55/0.50 | 0.36/0.34 |
| H(1.0)[up] | 1.00/1.00 | 0.65/0.63 | 1.00/1.00 | 0.99/0.93 | 0.56/0.54 | 1.00/0.97 | 1.00/1.00 | 0.72/0.69 | 1.00/1.00 | 0.60/0.54 | 0.43/0.40 |
| H(0.05)[both] | 1.00/1.00 | 0.84/0.80 | 1.00/1.00 | 0.89/0.74 | 0.38/0.31 | 0.55/0.44 | 0.98/0.94 | 0.78/0.68 | 0.85/0.76 | −0.06/−0.06 | 0.39/0.29 |
| H(0.1)[both] | 1.00/1.00 | 0.83/0.79 | 1.00/1.00 | 0.89/0.74 | 0.38/0.31 | 0.56/0.45 | 0.98/0.92 | 0.77/0.67 | 0.85/0.75 | −0.07/−0.06 | 0.41/0.31 |
| H(0.25)[both] | 1.00/1.00 | 0.79/0.76 | 1.00/1.00 | 0.88/0.73 | 0.38/0.31 | 0.56/0.46 | 0.93/0.82 | 0.70/0.59 | 0.82/0.70 | −0.07/−0.06 | 0.53/0.40 |
| H(0.5)[both] | 1.00/1.00 | 0.74/0.71 | 1.00/1.00 | 0.88/0.72 | 0.37/0.30 | 0.57/0.46 | 0.84/0.70 | 0.59/0.49 | 0.78/0.65 | −0.06/−0.06 | 0.69/0.55 |
| H(1.0)[both] | 1.00/1.00 | 0.65/0.63 | 1.00/1.00 | 0.87/0.70 | 0.36/0.29 | 0.58/0.46 | 0.74/0.58 | 0.48/0.39 | 0.73/0.59 | −0.02/−0.03 | 0.83/0.68 |

**Does w matter?** H(0.05) vs H(1.0), same direction:

| direction | in-deg all / files | PR all / files | Katz all / files |
|---|---|---|---|
| down | 1.00 / 1.00 | **1.00 / 1.00** | 1.00 / 1.00 |
| up | 0.95 / 1.00 | 0.99 / 1.00 | 0.97 / 1.00 |
| both | 0.95 / 1.00 | 0.94 / 0.95 | 0.77 / 0.79 |

### 2. What climbs — top-25 profile

Directories in the top-25 / mean depth / mean parent fan-out / overlap with
R's top-25 for the same measure.

| config | in-degree | PageRank | Katz |
|---|---|---|---|
| R | 0 / 3.1 / 58.6 / 25 | 0 / 3.3 / 69.4 / 25 | 0 / 3.5 / 74.8 / 25 |
| T[down] | 2 / 2.8 / 45.8 / 0 | 3 / 4.7 / **1.0** / 0 | 1 / **6.5** / 11.1 / 0 |
| T[up] | 25 / 3.2 / 14.4 / 0 | 25 / 2.8 / 18.0 / 0 | 25 / 2.7 / 18.1 / 0 |
| T[both] | 25 / 3.2 / 14.4 / 0 | 25 / 3.3 / 18.6 / 0 | 25 / 3.6 / **91.7** / 0 |
| H(w)[down], any w | 0 / 3.1 / 58.6 / 25 | 0 / 3.2 / 68.9 / 23 | 0 / 3.5 / 74.8 / 25 |
| H(0.05)[up] | 0 / 3.1 / 58.6 / 25 | **19** / 2.5 / 29.5 / 6 | 0 / 3.5 / 74.8 / 25 |
| H(0.1)[up] | 2 / 3.1 / 58.2 / 23 | **20** / 2.4 / 29.6 / 5 | 1 / 3.4 / 74.9 / 24 |
| H(0.5)[up] | 9 / 3.1 / 46.6 / 16 | **24** / 2.6 / 14.0 / 1 | 4 / 3.1 / 70.1 / 21 |
| H(1.0)[up] | 17 / 3.0 / 30.2 / 8 | **24** / 2.6 / 14.0 / 1 | 6 / 3.1 / 70.4 / 19 |
| H(0.1)[both] | 2 / 3.1 / 58.2 / 23 | **18** / 2.9 / 26.2 / 7 | 1 / 3.4 / 74.9 / 24 |
| H(0.5)[both] | 9 / 3.1 / 46.6 / 16 | **22** / 3.0 / 18.3 / 3 | 2 / 3.2 / **86.1** / 20 |
| H(1.0)[both] | 17 / 3.0 / 30.2 / 8 | **24** / 3.0 / 15.1 / 1 | 5 / 2.8 / **90.2** / 17 |

Selected top-10 lists (the full lists are in `tables.md`):

- **T[down], PageRank**: `context/research/studies/2026-08-12-posting-path-rust-kernel/vfs_postings_rs/src/lib.rs` (depth 7),
  `context/research/studies/2026-08-17-verify-authority-spike/rust/src/main.rs` (7),
  `crates/vfs-core` (dir), `src/vfs` (dir), `context/product/home-doc-section-1-arc.md`,
  then five `context/specs/active/*/spec.md` files — every one the sole (or
  near-sole) child of a chain of one-child directories.
- **T[down], Katz**: the ten deepest files in the tree, all depth 7 — the
  `lexical-leg/results/*.json` logs of another study.
- **T[up], PageRank**: `.`, `context`, `context/specs/archive`, `context/research`,
  `context/specs`, `context/research/studies`, … — directories by size, all 25.
- **H(0.1)[down], PageRank**: `context/open-questions.md`,
  `…/2026-08-25-set-based-scattered-delete.md`, `…/mysql-family-batch-update-shapes.md`,
  `docs/reference/glob-patterns.md`, … — R's top-10 with one swap.
- **H(0.1)[up], PageRank**: `.`, `context`, `context/research`, `context/specs/archive`,
  `context/specs`, `context/research/studies`, `docs`, `…/2026-08-26-glean` (dir),
  `tests`, then `context/open-questions.md` as the first file.
- **H(0.5)[both], Katz**: `context/research` (dir) first, then nine of R's Katz top-10, lightly reordered.

### 3. Structure: Spearman of score with depth (files), parent fan-out (files), own fan-out (directories)

| config | in-degree | PageRank | Katz |
|---|---|---|---|
| R | −0.30 / +0.32 / n/a | −0.30 / +0.30 / n/a | −0.28 / +0.32 / n/a |
| T[down] | const / const / −0.09 | +0.45 / **−0.99** / +0.39 | **+1.00** / −0.46 / −0.25 |
| T[up] | const / const / **+1.00** | const / const / +0.95 | const / const / +0.95 |
| T[both] | const / const / +1.00 | +0.52 / −0.83 / +0.96 | −0.31 / +0.45 / +0.07 |
| H(w)[down], any w | −0.30 / +0.32 / −0.09 | −0.08 / −0.27 / +0.39 | +0.17 / +0.16 / −0.25 |
| H(w)[up], any w | −0.30 / +0.32 / +1.00 | −0.30 / +0.31 / +0.81…0.85 | −0.28 / +0.32 / +0.98 |
| H(0.1)[both] | −0.30 / +0.32 / +1.00 | −0.30 / +0.35 / +0.79 | −0.39 / **+0.68** / +0.90 |
| H(0.5)[both] | −0.30 / +0.32 / +1.00 | −0.35 / +0.40 / +0.81 | −0.40 / **+0.67** / +0.39 |
| H(1.0)[both] | −0.30 / +0.32 / +1.00 | −0.36 / +0.41 / +0.83 | −0.41 / +0.56 / +0.13 |

Restricted to the **506 files R leaves at the floor** (65 % of files) —
the nodes whose order H(w) newly decides:

| config, measure | vs T[down] | vs depth | vs parent fan-out | distinct score values |
|---|---|---|---|---|
| H(0.1)[down], PageRank | **1.00** | +0.27 | **−0.995** | 50 |
| H(0.1)[down], Katz | **1.00** | **+1.00** | −0.29 | 4 |
| H(0.1)[both], PageRank | −0.25 | −0.03 | +0.29 | 80 |
| H(0.1)[both], Katz | −0.28 | −0.28 | **+0.985** | 58 |
| H(0.1)[up], either | const | const | const | 1 |

Under H(0.1)[down] PageRank, none of those 506 files scores above the
median of the 273 referenced files; the fs edges permute the floor, they do
not lift anything into the referenced band. Among the referenced files
themselves, H[down] PageRank still agrees with R at ρ = 0.97 (H[up] 0.97,
H[both] 0.88).

### 4. Coverage — fraction of nodes at the score floor (all nodes / files)

| config | in-degree | PageRank | Katz |
|---|---|---|---|
| R | 0.721 / 0.650 | 0.721 / 0.650 | 0.721 / 0.650 |
| T[down] | 0.001 / 1.000 | 0.001 / 0.141 | 0.001 / 0.051 |
| T[up] | 0.799 / 1.000 | 0.799 / 1.000 | 0.799 / 1.000 |
| H(w)[down], any w | 0.001 / 0.650 | 0.001 / 0.031 | 0.001 / 0.040 |
| H(w)[up], any w | 0.520 / 0.650 | 0.520 / 0.650 | 0.520 / 0.650 |
| H(w ≤ 0.25)[both] | 0.520 / 0.650 | 0.031 / 0.039 | 0.001 / 0.001 |
| H(w ≥ 0.5)[both] | 0.520 / 0.650 | 0.001 / 0.001 | 0.001 / 0.001 |

The memo's "53 % zero in-degree" was over the 440 markdown files alone; over
the whole tree R leaves 65 % of files and 72 % of nodes at the floor. Down
edges take that to ~3 % (PageRank) — table 3 says what fills the gap.

### 5. Sanity check — BM25 alone vs BM25 × (1 + β · prior)

Ten queries about this repo, 1–3 relevant files each **hand-labelled by me**
(see `QUERIES` in the script); 780 UTF-8 files as candidates, bm25s with
its default English tokeniser over file text plus the path; the prior is
the configuration's score over the 780 candidate files, log-scaled
(`log1p(v / min positive v)`) then min-max normalised to [0, 1]. BM25
alone puts the first labelled file at rank 1, 1, 1, 2, 4, 5, 13, 13, 35 and
124 across the ten queries — the baseline is weak and one query's
reciprocal rank moves MRR by up to 0.1. **This is a sanity check, not an
evaluation.**

| prior | β | MRR | nDCG@5 |
|---|---|---|---|
| none (BM25 only) | — | 0.414 | 0.270 |
| in-degree, R | 0.15 / 0.5 | 0.412 / **0.431** | 0.279 / 0.284 |
| PageRank, R | 0.15 / 0.5 | 0.403 / 0.403 | 0.246 / 0.249 |
| in-degree, T[down] | either | 0.414 | 0.270 (constant prior — no-op) |
| PageRank, T[down] | 0.15 / 0.5 | 0.267 / **0.205** | 0.188 / 0.123 |
| in-degree or PageRank, T[up] | either | 0.414 | 0.270 (constant over files — no-op) |
| in-degree, H(0.1)[down] | 0.15 / 0.5 | 0.426 / **0.435** | **0.312** / **0.312** |
| in-degree, H(0.5)[down] | 0.15 / 0.5 | 0.412 / 0.431 | 0.279 / 0.284 (= R) |
| PageRank, H(0.1)[down] = H(0.5)[down] | 0.15 / 0.5 | 0.401 / 0.380 | 0.243 / 0.255 |
| in-degree, H(0.1)[up] | 0.15 / 0.5 | 0.412 / 0.431 | 0.279 / 0.284 (= R) |
| PageRank, H(0.1)[up] | 0.15 / 0.5 | 0.403 / 0.403 | 0.252 / 0.249 |
| in-degree, H(0.1)[both] | 0.15 / 0.5 | 0.426 / 0.435 | 0.312 / 0.312 |
| PageRank, H(0.1)[both] | 0.15 / 0.5 | 0.385 / 0.375 | 0.237 / 0.231 |

The one cell that beats R — in-degree under H(0.1)[down] — has **exactly
R's ranking** (ρ = 1.00, table 1); every file's in-degree is R's plus 0.1,
and the `log1p(v / min)` transform with min = 0.1 bends into a different
curve than with min = 1 (R) or 0.5 (H(0.5)[down], which lands exactly on
R's numbers). The gain is the transform's shape, obtainable by choosing the
transform's constant, not information from the tree.

### 6. Timings (single process, Apple Silicon; 977 nodes)

| config | edges | in-degree | PageRank | λ_max (dense eig) | Katz (solve) |
|---|---|---|---|---|---|
| R | 864 | 0.0003 s | 0.007 s | 0.010 s | 0.013 s |
| T[down] / T[up] | 976 | 0.0003 s | 0.002 s | 0.003–0.006 s | 0.011 s |
| H(w)[down] / [up] | 1,840 | 0.0003 s | 0.002–0.004 s | 0.010–0.012 s | 0.011 s |
| T[both], H(w)[both] | 1,952–2,816 | 0.0004 s | 0.003 s | 0.16–0.17 s | 0.011 s |

Extraction (walk + link and import parsing): 0.17 s. BM25 index + 10
queries: 1.8 s. The whole script runs in ~4 s; at this size nothing here is
a cost argument either way — the scaling numbers in the memo's §2.4 stand.

## Readings

**1. "At a lower weight" is not a knob in the direction vfs materialises.**
For down edges every w from 0.05 to 1.0 gives the same ranking for all
three measures (ρ = 1.00, Kendall 1.00). The reason is structural, not a
coincidence of this tree: PageRank normalises out-weights per source node,
and no node emits both kinds of edge — directories emit only fs edges,
files only reference edges — so the fs weight cancels exactly; in-degree
adds the same +w to every non-root node, a constant shift; and a file's
Katz term from its parent is monotone in the parent's depth for any w. The
fs weight only bites where a node mixes edge types, i.e. when files also
point *up* at their parent (the up and both directions), where it sets how
much reference-sourced mass leaks into directories. An ADR that promised
"fs edges at weight 0.1" for the graph as vfs stores it would be promising
a dial that does nothing.

**2. Down edges are a tree-shape prior with the reference prior laid on
top.** H[down] keeps R's referenced files in nearly their R order (ρ = 0.97
among referenced files, 0.85 over reference-incident nodes) but reorders
the whole population (0.72 all nodes, 0.75 files) because it hands the 65 %
of files R left at the floor a score. That score is T[down]'s score
exactly (ρ = 1.00 on those 506 files), and T[down] is: for **Katz, depth
itself** (ρ = +1.00 on T; the top-10 are the ten deepest files; only four
distinct values among the 506); for **PageRank, narrowness of ancestry**
(ρ = −0.995 with parent fan-out; the top files are the ones at the end of
one-child directory chains — a study's `rust/src/main.rs`, `crates/vfs-core`
and `src/vfs` as directories — because a directory splits its mass among
its children and a chain never splits). None of the 506 rises above the
referenced-file median, so the lift is a permutation of the floor. The
memo's "depth prior computed expensively" is exactly right for Katz and
half-right for PageRank: PageRank over a down-tree is an *inverse fan-out*
prior, which penalises the children of wide directories — the opposite sign
of "degree = directory size", but no less a fact about the tree and no more
a fact about relevance.

**3. Up edges do not touch the file ranking at all; they score directories
by size.** Files gain no in-edges, so among files every measure agrees with
R at ρ = 1.00 for every w, and coverage over files is unchanged at 65 % at
the floor. What changes is that directories absorb the mass: in-degree
becomes child count exactly (ρ = 1.00), PageRank tracks own fan-out at
0.81–0.85, and 19–24 of the top-25 PageRank nodes are directories, headed by
the root. This is the memo's "degree = directory size", realised on the
directories rather than the files. Since glean's candidates are files
(chunks belong to entries with content), an up-edge prior is a
directory-size column that happens to be computed by a graph — and if the
prior were normalised over *all* entries, the root and `context/` would own
the top of the range and every file would be squeezed into its bottom
decile. A prior must be normalised over the retrievable population.

**4. Both directions is the worst of the two.** Among files, PageRank
agreement with R falls to 0.55–0.58; 18–24 of the top-25 are directories at
every w; and the reference-incident nodes' Katz drifts from R (0.98 → 0.74 as
w rises) toward T (0.39 → 0.83). Here the memo's sibling claim lands on
files directly: with children pointing up and the parent pointing back
down, a file's Katz correlates with its parent's fan-out at +0.67 to +0.70
(+0.985 among the unreferenced files), and the mean parent fan-out of the
Katz top-25 climbs to 86–92 — wide directories' children dominate. This is
the only direction in which w is a real dial, and the dial interpolates
between "reference prior" and "sibling-count prior".

**5. The sanity check says the same, at its own low resolution.** BM25 alone
sits at MRR 0.414; R's in-degree at β = 0.5 nudges it to 0.431 (one query's
first hit moving up a place or two); R's PageRank does nothing; T[down]
PageRank is the one prior that clearly hurts (0.205 at β = 0.5 — the narrow-
ancestry prior promotes study logs and Rust spike files over the labelled
answers); T[up] is a no-op on files. The single H cell that beats R,
in-degree under H(0.1)[down] at nDCG@5 0.312, is R's ranking to the last
tie — the difference is the log transform reacting to a +0.1 offset, and
H(0.5)[down] reproduces R's numbers exactly. Read with the labels' noise
(one query's reciprocal rank is worth up to 0.1 MRR), the check shows no
configuration where hierarchy edges add information that the reference
graph plus a transform constant does not already give.

**6. On the hypothesis and the counter-claim.** The hypothesis "hierarchy
edges at lower weight help" fails on both halves: the weight is inert in
the materialised direction, and the edges' contribution — in every
direction — is a function of tree shape (depth, ancestry narrowness, child
count, sibling count) that is uncorrelated or negatively correlated with
the reference prior (T vs R: −0.19 to −0.47 for PageRank) and does not
improve retrieval on this repo. The counter-claim holds, with a sharper
statement of *which* shape each measure and direction rewards: Katz-down is
depth; PageRank-down is inverse parent fan-out; anything-up is directory
child count; both-Katz is sibling count. The coverage argument ("R leaves
65 % of files unscored") is real but is not answered by fs edges — they fill
the floor with a permutation by tree shape, which a path-shape column
states in one expression and lets the ranker weight on purpose.

## Bearing on vfs

- **Recommendation: do not add `fs` edges to the centrality graph — in any
  direction, at any weight.** The centrality signal reads
  `edges WHERE edge_type <> 'fs'` (declared and future extracted edges
  only). This confirms memo §2.3 with measurements rather than argument.
- **Do not offer a per-edge-type weight as the mechanism.** For the graph as
  vfs stores it (files never point at their parent), a weight on fs edges is
  provably inert under PageRank and a constant shift under in-degree. If a
  future edge family does need a weight (one where nodes mix edge types),
  that is a separate decision with its own evidence; nothing here supports
  it.
- **If a structural prior is wanted where links are sparse, declare it as a
  path-shape column, not a graph**: depth (segment count) and name length
  are exactly what Katz-down and PageRank-down compute — Katz-down *is*
  depth to ρ = 1.00 — at graph cost and with the sign fixed by the
  algorithm rather than by the ranker. As a column the deployment chooses
  the sign (zoekt penalises depth; a wiki might reward it) and the
  transform. Directory size, if anyone wants it, is
  `COUNT(*) GROUP BY parent_id`, and it is a fact about directories, which
  glean does not return.
- **Normalise the prior over the retrievable population** (entries with
  chunks), never over all entries. The up-direction result shows how a graph
  that scores directories would otherwise crush every file into the bottom
  of the range.
- **In-degree over reference edges remains the prior to ship**, log- or
  saturation-transformed, as the memo already recommends (memo §2.1, §2.4:
  one `GROUP BY`, incremental, engine-identical). The sanity check's only
  gains over BM25 came from it; PageRank over the same edges gave none on
  this corpus, consistent with SIGIR 2005's "in-degree and PageRank are
  redundant — ship one".
- **The "coverage" objection should be answered in the transform, not the
  graph.** Nodes with no reference in-edges are absent-but-present: they map
  to the transform's floor, and the transform's constant (the `k` in a
  saturation, the offset in a log) is the legitimate place to decide how
  far above the floor the first link lifts a node — which is precisely what
  the H(0.1)[down] in-degree cell demonstrated by accident.

## Limits

- **One small repository** (977 nodes) with a particular shape: `context/`
  is 60 % of the tree, `context/specs/archive` has 113 children, `src` and
  `crates` are one-child chains. The *signs* of the structural correlations
  (Katz-down = depth, PageRank-down = inverse fan-out, up = child count) are
  algebraic and will hold on any tree; the *magnitudes* of agreement with R
  are this repo's.
- **The reference graph is two extractors** (markdown links, Python
  imports); declared user edges, symbol references, and test → module
  imports are absent. A denser reference graph would leave fewer nodes at
  the floor and make the fs contribution smaller still, which cuts against
  the hypothesis, not for it.
- **Hand labels by me**, 1–3 files per query, ten queries, a weak default
  BM25 tokeniser over whole files: the sanity check separates "clearly
  hurts" (T[down] PageRank) from "does nothing" and cannot resolve ±0.02.
- **The w-invariance proof for down edges assumes files never point at
  directories.** A future extracted edge type whose target is a directory
  (a link to a folder README resolved to the folder, say) would give
  directories reference in-edges and files mixed out-edges, and the weight
  would then matter; the direction-and-shape findings would still apply.
- Katz's α follows λ_max per graph, as specified; a fixed α would change
  the both-direction Katz numbers (its λ_max nearly doubles at w = 1.0) but
  not the down/up ones, whose λ_max is R's.
