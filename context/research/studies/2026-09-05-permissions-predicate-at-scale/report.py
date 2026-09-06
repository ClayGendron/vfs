"""Assemble `results.md` from `runs/*.md` and print the memo's cross-engine tables.

    uv run --no-sync python report.py

Runs made before the bind-count fix reported the chunk *cap* as the
join-back bind count in the subject-set table; the JSON carries enough
to recompute the actual count, and this script patches those cells.
"""

from __future__ import annotations

import glob
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ORDER = ["sqlite", "postgres", "mariadb", "mssql", "oracle"]


def runs() -> list[tuple[str, int, dict, str]]:
    out = []
    for path in glob.glob(os.path.join(HERE, "runs", "*.json")):
        with open(path) as f:
            j = json.load(f)
        with open(path[:-5] + ".md") as f:
            md = f.read()
        out.append((j["engine"], j["rows"], j, md))
    return sorted(out, key=lambda r: (r[1] > 500_000, ORDER.index(r[0])))


def fix_binds(j: dict, md: str) -> str:
    res = j["results"]
    for n in (2, 5, 20):
        row_re = re.compile(rf"(\| n={n} join-back K=1000 \|)(.*)")
        m = row_re.search(md)
        if not m:
            continue
        cells = m.group(2).split("|")[:-1]
        labels = [f"set_and_exists[n={n}]", f"set_having[n={n}]", None]
        new = []
        for cell, label in zip(cells, labels):
            key = next(k for k in res if k.startswith(f"set/{n}/back1000/") and (label is None and "set_app" in k or label is not None and k.endswith(label)))
            r = res[key]
            copies = 3 if "having" in key else 1
            cap = r["chunk"]
            actual = r["binds"] - copies * (cap - min(cap, 1000))
            new.append(re.sub(r"(\d+)b\s*$", f"{actual}b ", cell))
        md = md[: m.start(2)] + "|".join(new) + "|" + md[m.end(2):]
    return md


def ms(r: dict, key: str) -> str:
    x = r["results"].get(key)
    if x is None:
        return "—"
    s = f"{x['median_ms']:.0f}" if x["median_ms"] >= 10 else f"{x['median_ms']:.1f}"
    if x.get("statements", 1) != 1:
        s += f" ({x['statements']}s)"
    if x.get("note", "").startswith("capped"):
        s += " †"
    return s


def main() -> None:
    all_runs = runs()
    parts = [
        "# Results: the row-grant predicate at scale\n",
        "Raw per-engine tables from `probe.py` (see `README.md`). Times are medians over warm runs in ms; `· Nr` is rows fetched; `· Nb` is binds per statement; `(2 stmts)` means the batch was chunked; `†`/`capped` means only one run was taken because it exceeded the 60 s cap. SQL Server and Oracle run under Rosetta emulation: read ratios, not absolute times.\n",
    ]
    for eng, rows, j, md in all_runs:
        parts.append(fix_binds(j, md))
        parts.append("\n")
    with open(os.path.join(HERE, "results.md"), "w") as f:
        f.write("\n".join(parts))
    print(f"results.md: {len(all_runs)} runs")

    def hdr(runs_):
        return "| shape | " + " | ".join(f"{e} {r // 1000}k" for e, r, _, _ in runs_) + " |\n|---|" + "---|" * len(runs_)

    print("\n#### Read predicate (typical principal), ms\n")
    print(hdr(all_runs))
    for f in ("list", "glob", "grep"):
        for p in ("none", "exists", "literal_like", "literal_range", "materialised"):
            print(f"| {f} · {p} | " + " | ".join(ms(j, f"read/{f}/{p}") for _, _, j, _ in all_runs) + " |")
    for f in ("list", "grep"):
        for p in ("none", "exists", "materialised"):
            print(f"| heavy {f} · {p} | " + " | ".join(ms(j, f"heavy/{f}/{p}") for _, _, j, _ in all_runs) + " |")

    print("\n#### Ranked join-back, ms\n")
    print(hdr(all_runs))
    for k in (256, 1000, 3000):
        for form in ("in", "values"):
            for p in ("none", "exists", "literal_like", "materialised"):
                print(f"| K={k} {form.upper()} · {p} | " + " | ".join(ms(j, f"back/{k}/{form}/{p}") for _, _, j, _ in all_runs) + " |")

    print("\n#### Write point check\n")
    print(hdr(all_runs))
    print("| one path, ms | " + " | ".join(f"{j['results']['write']['single_median_ms']:.2f}" for _, _, j, _ in all_runs) + " |")
    print("| 10k paths chunked IN, ms (stmts) | " + " | ".join(f"{j['results']['write']['batch']['median_ms']:.0f} ({j['results']['write']['batch']['statements']})" for _, _, j, _ in all_runs) + " |")
    print("| grants once + app, ms | " + " | ".join(f"{j['results']['write']['grants_once']['median_ms']:.1f} + {j['results']['write']['app_resolve_ms']:.0f}" for _, _, j, _ in all_runs) + " |")

    print("\n#### Materialised\n")
    print(hdr(all_runs))
    for k, lab in (("exhaustive_rows", "exhaustive rows"), ("direct_only_rows", "direct grants only")):
        print(f"| {lab} | " + " | ".join(f"{j['results']['materialised'][k]:,}" for _, _, j, _ in all_runs) + " |")
    print("| wide grant, one principal, ms (rows) | " + " | ".join(f"{j['results']['materialised']['maintenance']['wide grant /t000, one principal'][0]:.0f} ({j['results']['materialised']['maintenance']['wide grant /t000, one principal'][1]:,})" for _, _, j, _ in all_runs) + " |")

    print("\n#### Groups, ms\n")
    print(hdr(all_runs))
    for f in ("glob", "grep", "back1000"):
        for p in ("flat expanded (exists over grantgx)", "membership subquery", "groups literal"):
            print(f"| {f} · {p} | " + " | ".join(ms(j, f"groups/{f}/{p}") for _, _, j, _ in all_runs) + " |")

    print("\n#### Subject set, ms\n")
    print(hdr(all_runs))
    for n in (2, 5, 20):
        for f in ("glob", "grep", "back1000"):
            for lab in ("set_and_exists", "set_having", "set_app_prefixes"):
                vals = []
                for _, _, j, _ in all_runs:
                    key = next((k for k in j["results"] if k.startswith(f"set/{n}/{f}/{lab}")), None)
                    vals.append(ms(j, key) if key else "—")
                print(f"| n={n} {f} · {lab} | " + " | ".join(vals) + " |")


if __name__ == "__main__":
    main()
