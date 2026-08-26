"""Do filesystem-hierarchy edges help or hurt a centrality prior? (vfs repo, read-only)

Three graphs over the same node set (every file and directory under src/,
docs/, context/, tests/, crates/, scripts/, plus the root; build artefacts
and this study's own directory are skipped):

  R     reference edges only — markdown relative links / backticked .md paths
        (context/ + docs/) and `from vfs… import` / `import vfs…` edges
        (src/vfs); weight 1.0.
  T     hierarchy edges only — the fs edges vfs materialises (dir -> child);
        also tried child -> parent ("up") and both.
  H(w)  R ∪ T with fs edges at weight w in {0.05, 0.1, 0.25, 0.5, 1.0}.

Per graph: weighted PageRank (alpha 0.85), weighted in-degree, Katz
(alpha = 0.9 / lambda_max; alpha = 0.9 when the graph is acyclic and
lambda_max = 0). Then rank agreement with R and with T, what the top-25
looks like, depth / fan-out correlations, coverage, and a BM25 x prior
sanity check on ten hand-labelled queries.

Usage: python hierarchy_edges.py <repo root>
"""
from __future__ import annotations

import json
import math
import re
import sys
import time
from pathlib import Path

import bm25s
import networkx as nx
import numpy as np
from scipy.stats import kendalltau, spearmanr

ROOT = Path(sys.argv[1]).resolve()
OUT = Path(__file__).resolve().parent
TOP_DIRS = ("src", "docs", "context", "tests", "crates", "scripts")
SKIP_DIRS = {"__pycache__", "target", ".pytest_cache", ".ruff_cache", ".venv", "node_modules"}
SKIP_FILES = {".DS_Store"}
WEIGHTS = (0.05, 0.1, 0.25, 0.5, 1.0)
DIRECTIONS = ("down", "up", "both")
MEASURES = ("in_degree", "pagerank", "katz")


# ---------------------------------------------------------------------------
# Tree walk and reference-edge extraction
# ---------------------------------------------------------------------------

def walk_tree() -> tuple[dict[str, dict], list[tuple[str, str]]]:
    """Nodes (path -> attrs) and fs edges (parent -> child) for the repo tree."""
    nodes: dict[str, dict] = {".": {"kind": "dir", "depth": 0, "parent": None}}
    fs_edges: list[tuple[str, str]] = []

    def visit(d: Path, rel: str, depth: int) -> None:
        for child in sorted(d.iterdir()):
            if child.is_symlink():
                continue
            if child.is_dir() and (child.name in SKIP_DIRS or child.resolve() == OUT):
                continue
            if child.is_file() and child.name in SKIP_FILES:
                continue
            crel = child.name if rel == "." else f"{rel}/{child.name}"
            nodes[crel] = {"kind": "dir" if child.is_dir() else "file", "depth": depth + 1, "parent": rel}
            fs_edges.append((rel, crel))
            if child.is_dir():
                visit(child, crel, depth + 1)

    for top in TOP_DIRS:
        p = ROOT / top
        nodes[top] = {"kind": "dir", "depth": 1, "parent": "."}
        fs_edges.append((".", top))
        visit(p, top, 1)
    fanout: dict[str, int] = {}
    for parent, _ in fs_edges:
        fanout[parent] = fanout.get(parent, 0) + 1
    for n, a in nodes.items():
        a["fanout"] = fanout.get(n, 0)
        a["parent_fanout"] = fanout.get(a["parent"], 0) if a["parent"] is not None else 0
    return nodes, fs_edges


def markdown_edges(nodes: dict[str, dict]) -> list[tuple[str, str]]:
    md = [n for n in nodes if n.endswith(".md") and (n.startswith("context/") or n.startswith("docs/"))]
    known = {(ROOT / n).resolve(): n for n in md}
    by_name: dict[str, list[Path]] = {}
    for p in known:
        by_name.setdefault(p.name, []).append(p)
    link_re = re.compile(r"\]\(([^)#\s]+\.md)(?:#[^)]*)?\)")
    tick_re = re.compile(r"`([^`\s]+\.md)`")
    edges: set[tuple[str, str]] = set()
    for p, src in known.items():
        text = p.read_text(errors="replace")
        for t in set(link_re.findall(text)) | set(tick_re.findall(text)):
            cand = (p.parent / t).resolve()
            if cand not in known:
                cand2 = (ROOT / t).resolve()
                if cand2 in known:
                    cand = cand2
                else:
                    hits = by_name.get(Path(t).name, [])
                    if len(hits) != 1:
                        continue
                    cand = hits[0]
            dst = known[cand]
            if dst != src:
                edges.add((src, dst))
    return sorted(edges)


def import_edges(nodes: dict[str, dict]) -> list[tuple[str, str]]:
    mods: dict[str, str] = {}
    for n in nodes:
        if n.startswith("src/vfs/") and n.endswith(".py"):
            parts = list(Path(n).with_suffix("").parts[1:])
            if parts[-1] == "__init__":
                parts = parts[:-1]
            mods[".".join(parts)] = n
    imp_re = re.compile(r"^\s*(?:from\s+(vfs[\w.]*)\s+import\s+([^\n]+)|import\s+(vfs[\w.]*))", re.M)
    edges: set[tuple[str, str]] = set()
    for name, path in mods.items():
        text = (ROOT / path).read_text(errors="replace")
        for m in imp_re.finditer(text):
            base = m.group(1) or m.group(3)
            targets = []
            if m.group(1) and m.group(2):
                for item in re.split(r"[,\s()]+", m.group(2)):
                    item = item.split(" as ")[0].strip()
                    if item and f"{base}.{item}" in mods:
                        targets.append(f"{base}.{item}")
            if base in mods:
                targets.append(base)
            for t in targets:
                if mods[t] != path:
                    edges.add((path, mods[t]))
    return sorted(edges)


# ---------------------------------------------------------------------------
# Graph construction and measures
# ---------------------------------------------------------------------------

def build(nodes: dict[str, dict], ref: list[tuple[str, str]], fs: list[tuple[str, str]],
          w_fs: float, direction: str, with_ref: bool) -> nx.DiGraph:
    g = nx.DiGraph()
    g.add_nodes_from(nodes)
    if with_ref:
        for u, v in ref:
            g.add_edge(u, v, weight=g.edges[u, v]["weight"] + 1.0 if g.has_edge(u, v) else 1.0)
    if w_fs > 0:
        for parent, child in fs:
            pairs = []
            if direction in ("down", "both"):
                pairs.append((parent, child))
            if direction in ("up", "both"):
                pairs.append((child, parent))
            for u, v in pairs:
                g.add_edge(u, v, weight=g.edges[u, v]["weight"] + w_fs if g.has_edge(u, v) else w_fs)
    return g


def lambda_max(g: nx.DiGraph) -> float:
    A = nx.to_scipy_sparse_array(g, weight="weight", dtype=float).toarray()
    return float(np.max(np.abs(np.linalg.eigvals(A))))


def measures(g: nx.DiGraph) -> tuple[dict[str, dict[str, float]], dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    tm: dict[str, float] = {}
    t = time.perf_counter()
    out["in_degree"] = {n: float(d) for n, d in g.in_degree(weight="weight")}
    tm["in_degree"] = time.perf_counter() - t
    t = time.perf_counter()
    out["pagerank"] = nx.pagerank(g, alpha=0.85, weight="weight", tol=1e-10, max_iter=1000)
    tm["pagerank"] = time.perf_counter() - t
    t = time.perf_counter()
    lam = lambda_max(g)
    tm["lambda_max"] = time.perf_counter() - t
    alpha = 0.9 / lam if lam > 1e-9 else 0.9
    t = time.perf_counter()
    out["katz"] = nx.katz_centrality_numpy(g, alpha=alpha, beta=1.0, weight="weight")
    tm["katz"] = time.perf_counter() - t
    tm["_lambda_max"] = lam
    tm["_katz_alpha"] = alpha
    return out, tm


def rank_corr(a: dict[str, float], b: dict[str, float], nodes: list[str]) -> dict[str, float]:
    x = np.array([a[n] for n in nodes]); y = np.array([b[n] for n in nodes])
    if np.ptp(x) == 0 or np.ptp(y) == 0:
        return {"spearman": float("nan"), "kendall": float("nan")}
    return {"spearman": round(float(spearmanr(x, y).statistic), 3),
            "kendall": round(float(kendalltau(x, y).statistic), 3)}


def at_floor(scores: dict[str, float]) -> float:
    vals = np.array(list(scores.values()))
    lo = vals.min()
    return float(np.mean(np.abs(vals - lo) <= 1e-12 * max(1.0, abs(lo))))


def top_profile(scores: dict[str, float], nodes: dict[str, dict], ref_top: set[str] | None, k: int = 25) -> dict:
    ranked = sorted(scores, key=lambda n: (-scores[n], n))[:k]
    dirs = [n for n in ranked if nodes[n]["kind"] == "dir"]
    return {
        "top": [(n, nodes[n]["kind"], nodes[n]["depth"], nodes[n]["parent_fanout"], round(scores[n], 6)) for n in ranked],
        "n_dirs": len(dirs),
        "mean_depth": round(float(np.mean([nodes[n]["depth"] for n in ranked])), 2),
        "mean_parent_fanout": round(float(np.mean([nodes[n]["parent_fanout"] for n in ranked])), 1),
        "overlap_with_R_top25": (len(set(ranked) & ref_top) if ref_top is not None else None),
    }


def structure_corr(scores: dict[str, float], nodes: dict[str, dict]) -> dict[str, float]:
    allnodes = list(nodes)
    files = [n for n in allnodes if nodes[n]["kind"] == "file"]
    dirs = [n for n in allnodes if nodes[n]["kind"] == "dir"]
    def sp(ns: list[str], attr: str) -> float:
        x = np.array([scores[n] for n in ns]); y = np.array([nodes[n][attr] for n in ns], dtype=float)
        if np.ptp(x) == 0 or np.ptp(y) == 0:
            return float("nan")
        return round(float(spearmanr(x, y).statistic), 3)
    return {
        "depth_all": sp(allnodes, "depth"),
        "depth_files": sp(files, "depth"),
        "parent_fanout_all": sp(allnodes, "parent_fanout"),
        "parent_fanout_files": sp(files, "parent_fanout"),
        "own_fanout_dirs": sp(dirs, "fanout"),
        "depth_dirs": sp(dirs, "depth"),
    }


# ---------------------------------------------------------------------------
# BM25 sanity check
# ---------------------------------------------------------------------------

QUERIES: list[tuple[str, list[str]]] = [
    ("how does grep push down glob scope to the database",
     ["src/vfs/storage/backends/database/grep.py", "src/vfs/storage/backends/database/pathterms.py",
      "context/decisions/040-path-segment-index-and-glob-pushdown.md"]),
    ("where are dialect budgets declared in list budget bind parameters",
     ["src/vfs/storage/backends/database/dialects.py", "context/decisions/024-byte-denominated-path-limits-mysql-profile.md"]),
    ("what does the reindex lease do",
     ["src/vfs/storage/backends/database/indexing.py", "context/decisions/033-indexed-grep-tier-refusal-gate-and-epoch-lifecycle.md"]),
    ("how are fs edges materialised in the edges table",
     ["context/decisions/018-edge-authoring-verbs-and-materialized-fs-edges.md", "src/vfs/models/rows.py", "src/vfs/models/edge.py"]),
    ("how does the rust engine fall back to pure python",
     ["src/vfs/native.py", "context/decisions/039-grep-rust-core-and-verify-authority.md"]),
    ("self-describing trash names and the restore contract",
     ["context/decisions/026-self-describing-trash-names-and-restore-contract.md", "src/vfs/storage/backends/database/topology.py"]),
    ("semantic chunking splitter for embeddings",
     ["src/vfs/models/chunking.py", "context/decisions/048-semantic-chunking-placement-and-rust-engine.md", "crates/vfs-core/src/chunk.rs"]),
    ("result envelope refusal classification error channel",
     ["src/vfs/results/envelope.py", "context/decisions/010-result-envelope-contract.md", "context/decisions/008-result-only-error-channel.md"]),
    ("run the ci matrix lint format types coverage",
     ["scripts/ci.sh", "docs/contributing.md"]),
    ("glob pattern language segment semantics",
     ["docs/explanation/glob-language.md", "src/vfs/pattern_matching/glob.py",
      "context/decisions/032-glob-segment-semantics-and-pushdown-doctrine.md"]),
]


def read_text_files(nodes: dict[str, dict]) -> list[str]:
    docs = []
    for n, a in nodes.items():
        if a["kind"] != "file":
            continue
        try:
            (ROOT / n).read_text(encoding="utf-8")
            docs.append(n)
        except (UnicodeDecodeError, OSError):
            continue
    return docs


def log_minmax(scores: dict[str, float], docs: list[str]) -> np.ndarray:
    v = np.array([scores[d] for d in docs], dtype=float)
    v = np.log1p(v / max(v[v > 0].min(), 1e-300)) if (v > 0).any() else v
    return (v - v.min()) / (v.max() - v.min()) if np.ptp(v) > 0 else np.zeros_like(v)


def eval_ranking(score_rows: np.ndarray, docs: list[str]) -> dict[str, float]:
    mrr, ndcg = [], []
    for qi, (_, rel) in enumerate(QUERIES):
        order = np.argsort(-score_rows[qi], kind="stable")
        ranked = [docs[i] for i in order]
        rr = 0.0
        for r, d in enumerate(ranked, 1):
            if d in rel:
                rr = 1.0 / r
                break
        mrr.append(rr)
        dcg = sum(1.0 / math.log2(r + 1) for r, d in enumerate(ranked[:5], 1) if d in rel)
        idcg = sum(1.0 / math.log2(r + 1) for r in range(1, min(len(rel), 5) + 1))
        ndcg.append(dcg / idcg)
    return {"MRR": round(float(np.mean(mrr)), 3), "nDCG@5": round(float(np.mean(ndcg)), 3)}


def sanity_check(nodes: dict[str, dict], graph_scores: dict[str, dict[str, dict[str, float]]]) -> dict:
    docs = read_text_files(nodes)
    for q, rel in QUERIES:
        for r in rel:
            assert r in docs, f"label {r} not a text file in the walk"
    t = time.perf_counter()
    texts = [(ROOT / d).read_text(encoding="utf-8") + " " + d.replace("/", " ").replace("_", " ").replace("-", " ") for d in docs]
    tokens = bm25s.tokenize(texts, stopwords="en", show_progress=False)
    retriever = bm25s.BM25()
    retriever.index(tokens, show_progress=False)
    qtok = bm25s.tokenize([q for q, _ in QUERIES], stopwords="en", return_ids=False, show_progress=False)
    base = np.vstack([retriever.get_scores(qt) for qt in qtok])
    tm_bm25 = time.perf_counter() - t
    results = {"n_docs": len(docs), "bm25_index_and_score_s": round(tm_bm25, 3), "configs": {}}
    results["configs"]["bm25 only"] = eval_ranking(base, docs)
    for gname, meas in graph_scores.items():
        for m in ("pagerank", "in_degree"):
            prior = log_minmax(meas[m], docs)
            for beta in (0.15, 0.5):
                fused = base * (1.0 + beta * prior)[None, :]
                results["configs"][f"bm25 x (1 + {beta} * {m} [{gname}])"] = eval_ranking(fused, docs)
    # Per-query baseline ranks of the labelled files, so the reader can see how noisy this is.
    per_q = []
    for qi, (q, rel) in enumerate(QUERIES):
        order = np.argsort(-base[qi], kind="stable")
        pos = {d: int(np.where(order == docs.index(d))[0][0]) + 1 for d in rel}
        per_q.append({"query": q, "labelled": pos, "bm25_top3": [docs[i] for i in order[:3]]})
    results["per_query_bm25"] = per_q
    return results


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def main() -> None:
    t0 = time.perf_counter()
    nodes, fs = walk_tree()
    md = markdown_edges(nodes)
    py = import_edges(nodes)
    ref = sorted(set(md) | set(py))
    ref_nodes = sorted({u for u, _ in ref} | {v for _, v in ref})
    all_nodes = list(nodes)
    files = [n for n in all_nodes if nodes[n]["kind"] == "file"]
    summary = {
        "nodes": len(all_nodes), "files": len(files), "dirs": len(all_nodes) - len(files),
        "fs_edges": len(fs), "md_edges": len(md), "import_edges": len(py), "ref_edges": len(ref),
        "ref_incident_nodes": len(ref_nodes),
        "max_depth": max(a["depth"] for a in nodes.values()),
        "max_fanout": max(a["fanout"] for a in nodes.values()),
        "extraction_s": round(time.perf_counter() - t0, 3),
    }

    configs: list[tuple[str, float, str, bool]] = [("R", 0.0, "down", True)]
    for d in DIRECTIONS:
        configs.append((f"T[{d}]", 1.0, d, False))
        for w in WEIGHTS:
            configs.append((f"H({w})[{d}]", w, d, True))

    scores: dict[str, dict[str, dict[str, float]]] = {}
    timings: dict[str, dict[str, float]] = {}
    for name, w, d, with_ref in configs:
        g = build(nodes, ref, fs, w, d, with_ref)
        t = time.perf_counter()
        scores[name], timings[name] = measures(g)
        timings[name]["total"] = time.perf_counter() - t
        timings[name]["edges"] = g.number_of_edges()

    ref_top = {m: set(sorted(scores["R"][m], key=lambda n: (-scores["R"][m][n], n))[:25]) for m in MEASURES}
    report: dict = {"summary": summary, "configs": {}}
    for name, w, d, with_ref in configs:
        entry: dict = {"w_fs": w, "direction": d, "with_ref": with_ref,
                       "timings_s": {k: (round(v, 5) if not k.startswith("_") else v) for k, v in timings[name].items()},
                       "measures": {}}
        for m in MEASURES:
            s = scores[name][m]
            me: dict = {
                "vs_R_ref_nodes": rank_corr(s, scores["R"][m], ref_nodes),
                "vs_R_all_nodes": rank_corr(s, scores["R"][m], all_nodes),
                "vs_R_files": rank_corr(s, scores["R"][m], files),
                "vs_T_all_nodes": rank_corr(s, scores[f"T[{d}]"][m], all_nodes) if name != "R" else None,
                "vs_T_ref_nodes": rank_corr(s, scores[f"T[{d}]"][m], ref_nodes) if name != "R" else None,
                "at_floor_all": round(at_floor(s), 3),
                "at_floor_files": round(at_floor({n: s[n] for n in files}), 3),
                "zero_in_degree_all": round(float(np.mean([scores[name]["in_degree"][n] == 0 for n in all_nodes])), 3),
                "structure": structure_corr(s, nodes),
                "top25": top_profile(s, nodes, ref_top[m]),
                "top25_files_only": top_profile({n: s[n] for n in files}, nodes, ref_top[m] & set(files), k=25),
            }
            entry["measures"][m] = me
        report["configs"][name] = entry

    # Does the fs weight matter at all? Agreement between the lightest and heaviest w, same direction.
    report["w_invariance"] = {}
    for d in DIRECTIONS:
        for m in MEASURES:
            lo, hi = scores[f"H(0.05)[{d}]"][m], scores[f"H(1.0)[{d}]"][m]
            report["w_invariance"][f"{d}/{m}"] = {"all_nodes": rank_corr(lo, hi, all_nodes), "files": rank_corr(lo, hi, files)}
    report["scores"] = scores
    sanity_graphs = {g: scores[g] for g in ("R", "T[down]", "T[up]", "H(0.1)[down]", "H(0.5)[down]", "H(0.1)[up]", "H(0.1)[both]")}
    report["sanity"] = sanity_check(nodes, sanity_graphs)
    report["node_attrs"] = nodes
    (OUT / "hierarchy_edges.json").write_text(json.dumps(report, indent=1, default=str))

    print("summary:", json.dumps(summary))
    for name in scores:
        e = report["configs"][name]
        print(f"\n== {name}  edges={e['timings_s']['edges']}  lambda_max={e['timings_s']['_lambda_max']:.3f}  katz_alpha={e['timings_s']['_katz_alpha']:.3f}  "
              f"t(in={e['timings_s']['in_degree']:.4f}s pr={e['timings_s']['pagerank']:.4f}s katz={e['timings_s']['katz']:.4f}s eig={e['timings_s']['lambda_max']:.3f}s)")
        for m in MEASURES:
            me = e["measures"][m]
            print(f"  {m:10s} vsR(ref)={me['vs_R_ref_nodes']} vsR(all)={me['vs_R_all_nodes']} vsT(all)={me['vs_T_all_nodes']} "
                  f"floor(all/files)={me['at_floor_all']}/{me['at_floor_files']} struct={me['structure']} "
                  f"top25: dirs={me['top25']['n_dirs']} depth={me['top25']['mean_depth']} pfan={me['top25']['mean_parent_fanout']} ovl={me['top25']['overlap_with_R_top25']}")
            print(f"             top10: {[t[0] for t in me['top25']['top'][:10]]}")
    print("\n== w invariance (H(0.05) vs H(1.0), same direction)")
    print(json.dumps(report["w_invariance"]))
    print("\n== sanity")
    print(json.dumps(report["sanity"], indent=1))


if __name__ == "__main__":
    main()
