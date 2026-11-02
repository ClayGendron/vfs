"""Render the measurement JSON files as Markdown tables (stdout). Pure formatting; no measurement here."""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    p = os.path.join(HERE, name)
    return json.load(open(p)) if os.path.exists(p) else None


def table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def phases(r):
    p = r.get("phases_s", {})
    return (p.get("chunk_dirty", 0), round(p.get("build_epoch", 0) - p.get("build_lexical_epoch (inside build_epoch)", 0), 2),
            p.get("build_lexical_epoch (inside build_epoch)", 0), round(p.get("publish_epoch", 0) + p.get("reclaim_epochs", 0), 2))


def errs(e):
    return "; ".join(f"{x['kind'].split('.')[-1]}: {x['message']}" + (f" {x['data']}" if x.get("data") else "") for x in e) or "-"


def section_A(results):
    rows = []
    for d in results:
        for key, label in (("A_cold", "cold build"), ("A_noop", "no-op (nothing dirty)")):
            r = d[key]
            c, g, l, pr = phases(r)
            rows.append([d["n"], label, r["wall_s"], c, g, l, pr, r["statements"], r["executemany_rows"], r["posting_list"], r["posting_mb"],
                         r["lex_postings"], r["lex_posting_mb"], r["lex_docs"], r["chunks"], r.get("db_main_mb"), r.get("wal_mb"), r["rss_after_mb"]])
    return table(["files", "step", "wall s", "chunk s", "gram build s", "lexical build s", "publish+reclaim s", "SQL stmts", "executemany rows",
                  "posting rows", "posting MB", "lex_postings rows", "lex blob MB", "lex_docs rows", "chunk rows", "db MB", "WAL MB", "peak RSS MB"], rows)


def section_B(results):
    rows = []
    for d in results:
        cold = d["A_cold"]["wall_s"]
        cold_build = d["A_cold"]["phases_s"]["build_epoch"]
        for key, label in (("A_cold", "cold (all dirty)"), ("B_new2000", "2,000 new entries dirty"), ("B_5pct", "5% rewritten + 1,501 new"), ("B_1pct", "1% rewritten")):
            r = d[key]
            c, g, l, pr = phases(r)
            rows.append([d["n"], label, r["not_encoded"] if key != "A_cold" else d["n"], r["entry"], r["wall_s"], f"{r['wall_s'] / cold:.2f}", c,
                         r["phases_s"]["build_epoch"], f"{r['phases_s']['build_epoch'] / cold_build:.2f}", r["statements"], r["executemany_rows"], r["posting_list"], r["lex_postings"], r["epoch"]])
    return table(["files", "step", "dirty before", "entry rows", "wall s", "wall / cold", "chunk s", "build_epoch s (gram+lex)", "build / cold build",
                  "SQL stmts", "executemany rows", "posting rows", "lex_postings rows", "epoch"], rows)


def section_C(results):
    out = []
    for d in results:
        states = []
        for r in d["grep"]:
            if r["state"] not in states:
                states.append(r["state"])
        names = [r["name"] for r in d["grep"] if r["state"] == states[0]]
        headers = ["pattern"] + [f"{s} wall s / stmts / files" for s in states]
        rows = []
        for name in names:
            row = [name]
            for s in states:
                r = next(x for x in d["grep"] if x["state"] == s and x["name"] == name)
                flag = " T" if r["errors"] else ""
                row.append(f"{r['wall_s']} / {r['statements']} / {r['files']}{flag}")
            rows.append(row)
        totals = ["TOTAL wall s"] + [f"{sum(x['wall_s'] for x in d['grep'] if x['state'] == s):.2f}" for s in states]
        rows.append(totals)
        out.append(f"\n{d['n']} files (T = a truncation record was returned):\n\n" + table(headers, rows))
        trunc = {(r["state"], r["name"]): errs(r["errors"]) for r in d["grep"] if r["errors"]}
        if trunc:
            out.append("\nTruncation records:\n\n" + table(["state", "pattern", "record"], [[s, n, e] for (s, n), e in trunc.items()]))
    return "\n".join(out)


def section_D(results):
    out = []
    for d in results:
        states = []
        for r in d["glean"]:
            if r["state"] not in states:
                states.append(r["state"])
        qs = [r["query"] for r in d["glean"] if r["state"] == states[0]]
        headers = ["query"] + [f"{s} wall s / stmts" for s in states]
        rows = []
        for q in qs:
            row = [q]
            for s in states:
                r = next(x for x in d["glean"] if x["state"] == s and x["query"] == q)
                row.append(f"{r['wall_s']} / {r['statements']}" + (" T" if r["errors"] else ""))
            rows.append(row)
        rows.append(["TOTAL wall s"] + [f"{sum(x['wall_s'] for x in d['glean'] if x['state'] == s):.2f}" for s in states])
        out.append(f"\n{d['n']} files (T = an overlay-budget record was returned):\n\n" + table(headers, rows))
        recs = {r["state"]: errs(r["errors"]) for r in d["glean"] if r["errors"]}
        if recs:
            out.append("\nOverlay-budget records (one example per state):\n\n" + table(["state", "record"], [[s, e] for s, e in recs.items()]))
        out.append(f"\nFreshness of a never-reindexed file at the last path ({d['n']} files):\n\n" + table(
            ["state", "dirty files", "grep finds it", "grep wall s", "glean ranks it", "glean wall s", "glean record"],
            [[f["state"], f["not_encoded"], f["grep_found"], f["grep_wall_s"], f["glean_found"], f["glean_wall_s"], errs(f["glean_errors"])] for f in d["freshness"]]))
    return "\n".join(out)


def section_E(results):
    rows = []
    for d in results:
        for key in ("E_clean", "E_dirty"):
            for r in d[key]:
                rows.append([d["n"], r["state"], r["rep"], r["wall_s"], r["statements"]])
    return table(["files", "store state", "rep", "write(500) wall s", "SQL stmts"], rows)


def section_F(b):
    rows = [[r["docs"], r["content_mb"], r["chunks"], r["chunk_split_s"], r["gram_total_s"], r["gram_rows"], r["gram_blob_mb"], r["lex_total_s"], r["lex_df_rows"], r["lex_block_rows"], r["lex_blob_mb"],
             round(r["chunk_split_s"] + r["gram_total_s"] + r["lex_total_s"], 2)] for r in b]
    return table(["docs", "content MB", "chunks", "chunk split s", "gram build+drain s", "gram rows", "gram blob MB", "lexical build+drain s", "lex_df rows", "lex block rows", "lex blob MB", "total CPU s"], rows)


def section_drift(d, n):
    rows = []
    for r in d["rounds"]:
        c, g, l, pr = phases(r)
        rows.append([r["label"], r["wall_s"], c, g, l, pr, r["entry"], r["lex_postings"], r.get("db_main_mb"), r.get("wal_mb"), r["epoch"]])
    return f"VACUUM + WAL truncate took {d['vacuum_s']} s.\n\n" + table(["step", "wall s", "chunk s", "gram build s", "lexical build s", "publish+reclaim s", "entry rows", "lex_postings rows", "db MB", "WAL MB", "epoch"], rows)


if __name__ == "__main__":
    sizes = [int(a) for a in sys.argv[1:]] or [10000, 50000]
    results = [r for r in (load(f"results_{n}.json") for n in sizes) if r]
    print("## A. Full reindex\n\n" + section_A(results))
    print("\n## B. Dirty rebuild vs cold\n\n" + section_B(results))
    print("\n## C. grep under staleness\n" + section_C(results))
    print("\n## D. glean under staleness\n" + section_D(results))
    print("\n## E. Write latency\n\n" + section_E(results))
    b = load("results_builders.json")
    if b:
        print("\n## F. Builder-only cost\n\n" + section_F(b))
    for n in sizes:
        dr = load(f"results_drift_{n}.json")
        if dr:
            print(f"\n## Epoch drift ({n} files)\n\n" + section_drift(dr, n))
