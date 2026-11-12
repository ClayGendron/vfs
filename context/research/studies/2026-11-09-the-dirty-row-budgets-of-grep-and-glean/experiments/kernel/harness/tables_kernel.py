"""Render study 03's tables from results_kernel_sqlite_100000.json beside study 02's results_sqlite_100000.json.

Usage: python tables_kernel.py <results_kernel.json> <study02 results_sqlite_100000.json>
"""

from __future__ import annotations

import json
import statistics
import sys


def med(values):
    return statistics.median(values) if values else float("nan")


def by_query(rows):
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["name"], []).append(r)
    return out


def phase(rows, name, key="wall_s"):
    return med([r["phases"].get(name, {}).get(key, 0.0) for r in rows])


def level_table(level, rows_key, label):
    n = level["n"]
    print(f"\n### N = {n:,} dirty rows (+ sentinel): {label}\n")
    print("| query | wall s | nominees | nominee s | surrogate s | bodies MB | body fetch s | tokenize-and-count s | overlay s | stmts | hits | lexical hits | tokenize us/row | overlay us/row | call us/row |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for name, rows in by_query(level[rows_key]).items():
        wall = med([r["wall_s"] for r in rows])
        tok = phase(rows, "glean.tokenize")
        ov = phase(rows, "glean.overlay")
        nominees = int(phase(rows, "glean.nominees", "rows"))
        print(
            f"| {name} | {wall:.3f} | {nominees:,} | {phase(rows, 'glean.nominees'):.3f} | {phase(rows, 'glean.surrogate_ids'):.3f} | "
            f"{phase(rows, 'glean.bodies', 'bytes') / 1e6:.1f} | {phase(rows, 'glean.bodies'):.3f} | {tok:.3f} | {ov:.3f} | "
            f"{int(med([r['statements'] for r in rows]))} | {int(med([r['hits'] for r in rows]))} | {int(med([r['lexical_hits'] or 0 for r in rows]))} | "
            f"{tok / n * 1e6:.1f} | {ov / n * 1e6:.1f} | {wall / n * 1e6:.1f} |"
        )


def main() -> None:
    kernel = json.load(open(sys.argv[1]))
    s02 = json.load(open(sys.argv[2]))
    s02_levels = {lv["n"]: lv for lv in s02["results"]}
    print(f"# Study 03 tables: kernel run started {kernel['started']}, finished {kernel.get('finished')}; base counts {kernel['base_counts']}")
    for level in kernel["results"]:
        n = level["n"]
        print(f"\n## Level N = {n:,}: copy {level['copy_s']} s, dirty {level['dirty']['wall_s']} s, not_encoded {level['dirty']['not_encoded_after']}, level total {level['level_total_s']} s, rss {level['rss_mb']} MB")
        if n in s02_levels:
            level_table(s02_levels[n], "glean_lifted", "study 02, Python overlay, median of 3 (its own session)")
        level_table(level, "glean_lifted_python", "this session, Python overlay, 1 pass")
        level_table(level, "glean_lifted_kernel", "this session, kernel overlay, median of 3")
        print("\nParity (Python against kernel, lifted budget, limit 10):")
        for p in level["parity"]:
            print(f"- {p['name']}: same paths {p['same_paths']}, max score delta {p['max_score_delta']}")
        rk = level["recall_kernel"]
        print(f"\nSentinel recall through the kernel at budget {rk['overlay_budget']}: found {rk['sentinel_found']}; records {[(r['data']) for r in rk['records']]}")
        recs = {json.dumps(r["data"], sort_keys=True) for row in level["glean_lifted_kernel"] for r in row["records"]}
        print(f"Truncation records on the kernel runs: {sorted(recs)}")

    # Slopes between consecutive levels, whole call and tokenize phase, per implementation.
    print("\n## Slopes between consecutive levels (median over the five queries), us per dirty row")
    print("| from N | to N | implementation | call slope | tokenize slope | overlay slope |")
    print("|---|---|---|---|---|---|")
    levels = kernel["results"]
    for a, b in zip(levels, levels[1:], strict=False):
        for key, label in (("glean_lifted_python", "Python overlay (1 pass)"), ("glean_lifted_kernel", "kernel overlay")):
            qa, qb = by_query(a[key]), by_query(b[key])
            dn = b["n"] - a["n"]
            call = med([(med([r["wall_s"] for r in qb[q]]) - med([r["wall_s"] for r in qa[q]])) / dn * 1e6 for q in qa])
            tok = med([(phase(qb[q], "glean.tokenize") - phase(qa[q], "glean.tokenize")) / dn * 1e6 for q in qa])
            ov = med([(phase(qb[q], "glean.overlay") - phase(qa[q], "glean.overlay")) / dn * 1e6 for q in qa])
            print(f"| {a['n']:,} | {b['n']:,} | {label} | {call:.1f} | {tok:.1f} | {ov:.1f} |")


if __name__ == "__main__":
    main()
