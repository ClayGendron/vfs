"""Centrality measures on two real graphs from the vfs repo (read-only).

Graph A: markdown link graph across context/ and docs/ — an edge u->v when
u contains a relative link or a backticked path that resolves to v.
Graph B: the import graph of src/vfs — an edge u->v when module u imports
module v (regex over `from vfs... import` / `import vfs...`).

For each: PageRank, Katz, HITS (authority + hub), in-degree; Spearman and
Kendall rank correlations between the measures; wall time per measure.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import networkx as nx
import numpy as np
from scipy.stats import kendalltau, spearmanr

ROOT = Path(sys.argv[1]).resolve()
OUT = Path(__file__).resolve().parent


def md_link_graph() -> nx.DiGraph:
    files = [p for d in ("context", "docs") for p in (ROOT / d).rglob("*.md")]
    known = {p.resolve(): p.resolve() for p in files}
    by_name: dict[str, list[Path]] = {}
    for p in known:
        by_name.setdefault(p.name, []).append(p)
    g = nx.DiGraph()
    for p in known:
        g.add_node(str(p.relative_to(ROOT)))
    link_re = re.compile(r"\]\(([^)#\s]+\.md)(?:#[^)]*)?\)")
    tick_re = re.compile(r"`([^`\s]+\.md)`")
    for p in known:
        text = p.read_text(errors="replace")
        src = str(p.relative_to(ROOT))
        targets = set(link_re.findall(text)) | set(tick_re.findall(text))
        for t in targets:
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
            dst = str(cand.relative_to(ROOT))
            if dst != src:
                g.add_edge(src, dst)
    return g


def import_graph() -> nx.DiGraph:
    src = ROOT / "src" / "vfs"
    mods = {}
    for p in src.rglob("*.py"):
        rel = p.relative_to(ROOT / "src").with_suffix("")
        parts = list(rel.parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        mods[".".join(parts)] = p
    g = nx.DiGraph()
    g.add_nodes_from(mods)
    imp_re = re.compile(r"^\s*(?:from\s+(vfs[\w.]*)\s+import\s+([^\n]+)|import\s+(vfs[\w.]*))", re.M)
    for name, p in mods.items():
        text = p.read_text(errors="replace")
        for m in imp_re.finditer(text):
            base = m.group(1) or m.group(3)
            targets = []
            if m.group(1) and m.group(2):
                # `from vfs.x import a, b` — a/b may be submodules.
                for item in re.split(r"[,\s()]+", m.group(2)):
                    item = item.split(" as ")[0].strip()
                    if item and f"{base}.{item}" in mods:
                        targets.append(f"{base}.{item}")
            if base in mods:
                targets.append(base)
            for t in targets:
                if t != name:
                    g.add_edge(name, t)
    return g


def measures(g: nx.DiGraph) -> tuple[dict[str, dict[str, float]], dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    timings: dict[str, float] = {}
    t = time.perf_counter(); out["in_degree"] = dict(g.in_degree()); timings["in_degree"] = time.perf_counter() - t
    t = time.perf_counter(); out["pagerank"] = nx.pagerank(g, alpha=0.85); timings["pagerank"] = time.perf_counter() - t
    # Katz needs alpha < 1/lambda_max for convergence.
    A = nx.to_scipy_sparse_array(g, dtype=float)
    lam = float(np.max(np.abs(np.linalg.eigvals(A.toarray())))) if g.number_of_nodes() <= 2000 else 10.0
    alpha = 0.9 / lam if lam > 0 else 0.1
    t = time.perf_counter(); out["katz"] = nx.katz_centrality(g, alpha=alpha, beta=1.0, max_iter=5000, tol=1e-8); timings["katz"] = time.perf_counter() - t
    t = time.perf_counter(); hubs, auth = nx.hits(g, max_iter=1000, tol=1e-8); timings["hits"] = time.perf_counter() - t
    out["hits_authority"] = auth; out["hits_hub"] = hubs
    timings["_katz_alpha"] = alpha; timings["_lambda_max"] = lam
    return out, timings


def correlations(meas: dict[str, dict[str, float]], nodes: list[str]) -> dict[str, dict[str, float]]:
    names = ["in_degree", "pagerank", "katz", "hits_authority"]
    vec = {n: np.array([meas[n][x] for x in nodes]) for n in names}
    res = {}
    for a in names:
        for b in names:
            if a < b:
                s = spearmanr(vec[a], vec[b]).statistic
                k = kendalltau(vec[a], vec[b]).statistic
                res[f"{a} vs {b}"] = {"spearman": round(float(s), 3), "kendall": round(float(k), 3)}
    return res


def top(meas: dict[str, float], k: int = 8) -> list[tuple[str, float]]:
    return [(n, round(v, 4)) for n, v in sorted(meas.items(), key=lambda kv: -kv[1])[:k]]


def report(label: str, g: nx.DiGraph) -> dict:
    nodes = list(g.nodes)
    meas, timings = measures(g)
    zero_in = sum(1 for n in nodes if meas["in_degree"][n] == 0)
    out = {
        "label": label,
        "nodes": g.number_of_nodes(),
        "edges": g.number_of_edges(),
        "isolated_nodes": nx.number_of_isolates(g),
        "zero_in_degree": zero_in,
        "timings_s": {k: (round(v, 5) if not k.startswith("_") else v) for k, v in timings.items()},
        "correlations": correlations(meas, nodes),
        "top": {k: top(meas[k]) for k in ("in_degree", "pagerank", "katz", "hits_authority", "hits_hub")},
    }
    return out


if __name__ == "__main__":
    results = [report("markdown links (context/ + docs/)", md_link_graph()), report("import graph (src/vfs)", import_graph())]
    (OUT / "graph_signals.json").write_text(json.dumps(results, indent=2))
    for r in results:
        print(f"== {r['label']}: {r['nodes']} nodes, {r['edges']} edges, {r['isolated_nodes']} isolated, {r['zero_in_degree']} zero in-degree")
        print("timings:", r["timings_s"])
        for k, v in r["correlations"].items():
            print(f"  {k}: spearman={v['spearman']} kendall={v['kendall']}")
        for k, v in r["top"].items():
            print(f"  top {k}: {v}")
