"""Render the markdown tables for the study from hierarchy_edges.json."""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
R = json.loads((HERE / "hierarchy_edges.json").read_text())
C = R["configs"]
MEAS = ("in_degree", "pagerank", "katz")
ORDER = ["R"] + [f"T[{d}]" for d in ("down", "up", "both")] + [f"H({w})[{d}]" for d in ("down", "up", "both") for w in (0.05, 0.1, 0.25, 0.5, 1.0)]
SHORT = {"in_degree": "in-deg", "pagerank": "PR", "katz": "Katz"}


def f(x) -> str:
    if x is None:
        return "—"
    if isinstance(x, dict):
        return f"{x['spearman']:.2f}/{x['kendall']:.2f}" if x["spearman"] == x["spearman"] else "n/a (const)"
    return f"{x}"


lines: list[str] = []
S = R["summary"]
lines.append(f"Setup: {S['nodes']} nodes ({S['files']} files, {S['dirs']} directories incl. root), {S['fs_edges']} fs edges, "
             f"{S['ref_edges']} reference edges ({S['md_edges']} markdown, {S['import_edges']} import) touching {S['ref_incident_nodes']} nodes; "
             f"max depth {S['max_depth']}, max fan-out {S['max_fanout']}; extraction {S['extraction_s']} s.\n")

lines.append("### Agreement with R (Spearman/Kendall)\n")
lines.append("| config | in-deg ref | in-deg all | in-deg files | PR ref | PR all | PR files | Katz ref | Katz all | Katz files | PR vs T all | Katz vs T all |")
lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
for c in ORDER:
    m = C[c]["measures"]
    cells = [c]
    for k in MEAS:
        cells += [f(m[k]["vs_R_ref_nodes"]), f(m[k]["vs_R_all_nodes"]), f(m[k]["vs_R_files"])]
    cells += [f(m["pagerank"]["vs_T_all_nodes"]), f(m["katz"]["vs_T_all_nodes"])]
    lines.append("| " + " | ".join(cells) + " |")

lines.append("\n### Top-25 profile (directories in top-25 / mean depth / mean parent fan-out / overlap with R's top-25)\n")
lines.append("| config | in-deg | PR | Katz |")
lines.append("|---|---|---|---|")
for c in ORDER:
    m = C[c]["measures"]
    cells = [c] + [f"{m[k]['top25']['n_dirs']} / {m[k]['top25']['mean_depth']} / {m[k]['top25']['mean_parent_fanout']} / {m[k]['top25']['overlap_with_R_top25']}" for k in MEAS]
    lines.append("| " + " | ".join(cells) + " |")

lines.append("\n### Structure correlations (Spearman of score with depth over files, parent fan-out over files, own fan-out over directories)\n")
lines.append("| config | in-deg depth/pfan/dirfan | PR depth/pfan/dirfan | Katz depth/pfan/dirfan |")
lines.append("|---|---|---|---|")
for c in ORDER:
    m = C[c]["measures"]
    def st(k):
        s = m[k]["structure"]
        return " / ".join("n/a" if v != v else f"{v:+.2f}" for v in (s["depth_files"], s["parent_fanout_files"], s["own_fanout_dirs"]))
    lines.append("| " + " | ".join([c] + [st(k) for k in MEAS]) + " |")

lines.append("\n### Coverage: fraction of nodes at the score floor (all nodes / files only)\n")
lines.append("| config | in-deg | PR | Katz |")
lines.append("|---|---|---|---|")
for c in ORDER:
    m = C[c]["measures"]
    lines.append("| " + " | ".join([c] + [f"{m[k]['at_floor_all']:.3f} / {m[k]['at_floor_files']:.3f}" for k in MEAS]) + " |")

lines.append("\n### Does w matter? H(0.05) vs H(1.0), same direction (Spearman/Kendall)\n")
lines.append("| direction | in-deg all / files | PR all / files | Katz all / files |")
lines.append("|---|---|---|---|")
for d in ("down", "up", "both"):
    cells = [d] + [f"{f(R['w_invariance'][f'{d}/{k}']['all_nodes'])} / {f(R['w_invariance'][f'{d}/{k}']['files'])}" for k in MEAS]
    lines.append("| " + " | ".join(cells) + " |")

lines.append("\n### Top-10 under selected configurations\n")
for c, k in (("R", "pagerank"), ("R", "in_degree"), ("T[down]", "pagerank"), ("T[down]", "katz"), ("T[up]", "pagerank"),
             ("H(0.1)[down]", "pagerank"), ("H(0.1)[down]", "katz"), ("H(0.1)[up]", "pagerank"), ("H(0.5)[up]", "in_degree"), ("H(0.1)[both]", "pagerank"), ("H(0.5)[both]", "katz")):
    top = C[c]["measures"][k]["top25"]["top"][:10]
    lines.append(f"- **{c}, {SHORT[k]}**: " + "; ".join(f"`{n}`{' (dir)' if kind == 'dir' else ''} d{depth}" for n, kind, depth, pf, v in top))

lines.append("\n### Sanity check: BM25 alone vs BM25 x (1 + beta * prior), 10 queries, 780 text files\n")
lines.append("| prior | beta | MRR | nDCG@5 |")
lines.append("|---|---|---|---|")
for name, v in R["sanity"]["configs"].items():
    if name == "bm25 only":
        lines.append(f"| (none) | — | {v['MRR']:.3f} | {v['nDCG@5']:.3f} |")
    else:
        inner = name[len("bm25 x (1 + "):-1]
        beta, rest = inner.split(" * ", 1)
        lines.append(f"| {rest} | {beta} | {v['MRR']:.3f} | {v['nDCG@5']:.3f} |")

lines.append("\n### Timings (seconds, single process, Apple Silicon)\n")
lines.append("| config | edges | in-deg | PageRank | lambda_max (dense eig) | Katz (solve) | total |")
lines.append("|---|---|---|---|---|---|---|")
for c in ORDER:
    t = C[c]["timings_s"]
    lines.append(f"| {c} | {t['edges']} | {t['in_degree']:.4f} | {t['pagerank']:.4f} | {t['lambda_max']:.3f} | {t['katz']:.4f} | {t['total']:.3f} |")

(HERE / "tables.md").write_text("\n".join(lines) + "\n")
print("\n".join(lines))
