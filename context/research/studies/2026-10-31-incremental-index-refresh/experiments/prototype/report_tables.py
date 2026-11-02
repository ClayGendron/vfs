"""Render the experiment JSON files as Markdown tables (stdout)."""

from __future__ import annotations

import json
import os
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    with open(os.path.join(HERE, name)) as fh:
        return json.load(fh)


def table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def ms(x):
    return f"{x * 1e3:.2f}"


def main():
    print("### Table 1. Build cost (N = 100,000 base; deltas half re-posts, half new ids)\n")
    r1 = load("exp1_results.json")
    rows = []
    for r in r1:
        rows.append([
            r["set"], r["docs"], f"{r['doc_bytes'] / 1e6:.1f}", f"{r['fold_s']:.3f}", f"{r['feed_s']:.3f}", f"{r['drain_s']:.3f}",
            f"{r['insert_s']:.3f}", f"{r['index_s']:.3f}", f"{r['index_s'] / r['docs'] * 1e6:.0f}", r["rows"], f"{r['bytes'] / 1e6:.1f}",
            f"{r['gen_s']:.1f}",
        ])
    print(table(["set", "docs", "doc MB", "fold s", "feed s", "drain s", "insert s", "index s (sum)", "us/doc", "rows", "posting MB", "(gen s, excluded)"], rows))
    print(f"\nPeak RSS during the base build: {r1[0]['maxrss_mb']:.0f} MB.\n")

    print("### Table 2. Read amplification vs K (per query, live set = base + K deltas of 500 docs)\n")
    r2 = load("exp2_results.json")
    ks = sorted({r["K"] for r in r2})
    # Aggregate per K across the 20 queries.
    rows = []
    for K in ks:
        rs = [r for r in r2 if r["K"] == K]
        rows.append([
            K, len(rs),
            f"{statistics.mean(r['rows'] for r in rs):.0f}", f"{statistics.mean(r['bytes'] for r in rs) / 1e3:.0f}",
            ms(statistics.mean(r["meta_s"] for r in rs)), ms(statistics.mean(r["fetch_s"] for r in rs)),
            ms(statistics.mean(r["kernel_groups_s"] for r in rs)), ms(max(r["kernel_groups_s"] for r in rs)),
            ms(statistics.mean(r["merge_py_s"] for r in rs)), ms(statistics.mean(r["kernel_merged_s"] for r in rs)),
            f"{statistics.mean(r['candidates'] for r in rs):.0f}",
        ])
    print(table(["K", "queries", "rows/query", "KB/query", "meta ms", "fetch ms", "kernel(groups) ms mean", "kernel(groups) ms max", "py-union ms (strategy a)", "kernel after union ms", "candidates mean"], rows))
    print()
    print("### Table 3. Per-query detail at K = 0, 12, 48 (strategy b: per-segment kernel groups)\n")
    rows = []
    for r in r2:
        if r["K"] in (0, 12, 48):
            ver = r["verified"] or 1
            rows.append([
                r["K"], r["query"], r["groups"], r["grams_wanted"], r["rows"], f"{r['bytes'] / 1e3:.1f}", ms(r["fetch_s"]), ms(r["kernel_groups_s"]), ms(r["merge_py_s"]),
                r["candidates"], r["phantoms"], r["verified"], f"{r['ghosts'] / ver * 100:.1f}%", f"{r['fp'] / ver * 100:.1f}%",
            ])
    print(table(["K", "query", "AND groups", "grams", "rows", "KB", "fetch ms", "kernel ms", "py-union ms", "candidates", "phantoms (a only)", "verified (sample)", "ghost %", "other fp %"], rows))
    print()

    print("### Table 4. Merging segments (Python union + re-encode; exp2 store)\n")
    r3 = load("exp3_results.json")
    rows = []
    for m in r3["merges"]:
        rows.append([
            f"{len(m['sources'])} segs -> {m['target']}", m["tombstones"], m["rows_in"], f"{m['bytes_in'] / 1e6:.1f}", m["rows_out"], f"{m['bytes_out'] / 1e6:.1f}",
            m["pairs_dropped"], f"{m['decode_s']:.2f}", f"{m['union_s']:.2f}", f"{m['encode_s']:.2f}", f"{m['insert_s']:.2f}", f"{m['total_s']:.2f}",
        ])
    print(table(["merge", "tombstoned docs", "rows in", "MB in", "rows out", "MB out", "(gram,doc) pairs dropped", "decode s", "union s", "encode s", "insert s", "total s"], rows))
    print(f"\nTiered layout build (3x60min + 1x30min merges): {r3['tier_build_s']:.1f} s. Live segments after tiering: {len(r3['tier_segments'])} + base.\n")

    print("### Table 5. Read amplification: 48 flat deltas vs the tiered layout (same 24,000 delta docs)\n")
    flat = [r for r in r2 if r["K"] == 48]
    tier = r3["tier_queries"]
    rows = []
    for name in ("mean over 20 queries",):
        for label, rs in (("K=48 flat", flat), (f"K={tier[0]['K']} tiered", tier), ("K=0 (base only, for reference)", [r for r in r2 if r["K"] == 0])):
            rows.append([
                label, f"{statistics.mean(r['rows'] for r in rs):.0f}", f"{statistics.mean(r['bytes'] for r in rs) / 1e3:.0f}", ms(statistics.mean(r["meta_s"] for r in rs)),
                ms(statistics.mean(r["fetch_s"] for r in rs)), ms(statistics.mean(r["kernel_groups_s"] for r in rs)), ms(statistics.mean(r["merge_py_s"] for r in rs)),
                f"{statistics.mean(r['candidates'] for r in rs):.0f}",
            ])
    print(table(["layout", "rows/query", "KB/query", "meta ms", "fetch ms", "kernel(groups) ms", "py-union ms", "candidates"], rows))
    print()

    print("### Table 6. BM25 idf drift with 5% of docs re-posted (deltas' df ignored vs summed vs true)\n")
    r4 = load("exp4_results.json")
    rows = []
    for r in r4["rows"]:
        rows.append([
            r["term"], r["df_base"], r["df_delta"], r["df_true"], f"{r['idf_base_only']:.4f}", f"{r['idf_summed']:.4f}", f"{r['idf_true']:.4f}",
            "n/a" if r["err_base_only_pct"] is None else f"{r['err_base_only_pct']:+.1f}%", "n/a" if r["err_summed_pct"] is None else f"{r['err_summed_pct']:+.1f}%",
        ])
    print(table(["term", "df base", "df delta", "df true", "idf base-only", "idf summed", "idf true", "err base-only", "err summed"], rows))
    e = r4["idf_abs_rel_err_base_only"]
    print(
        f"\nOver all {r4['terms_true']} terms of the current corpus, |idf(base-only) - idf(true)| / idf(true): "
        f"median {e['median'] * 100:.2f}%, p90 {e['p90'] * 100:.2f}%, p99 {e['p99'] * 100:.2f}%, max {e['max'] * 100:.0f}% "
        f"({r4['terms_only_in_delta']} terms exist only in the deltas). avg_dl base {r4['avg_dl_base']:.1f} vs true {r4['avg_dl_true']:.1f}. "
        f"Lexical builder: base {r4['lexical_build_base_s']:.1f} s for {r4['N']} docs, delta {r4['lexical_build_delta_s']:.2f} s for {r4['reposted']} docs.\n"
    )


if __name__ == "__main__":
    main()
