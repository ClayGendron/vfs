"""Print the study's markdown table rows from the report JSON files.

    uv run python context/research/studies/2026-08-26-glean/lexical-leg/summarize.py results/report-linux-*.json
"""

from __future__ import annotations

import json
import sys


def main(paths: list[str]) -> None:
    for path in paths:
        r = json.load(open(path))
        c, i, inc, t = r["corpus"], r["index"], r["incremental"], r["timings_ms"]
        tb = i["table_bytes"]
        per_1k = (c["split_seconds"] + i["tokenize_seconds"] + i["insert_seconds"]) / c["files"] * 1000
        print(f"### {r['label']}")
        print(
            f"| {r['label']} | {c['files']:,} | {c['bytes'] / 1e6:.1f} | {i['n_chunks']:,} | {i['n_terms_rows']:,} | "
            f"{i['n_terms_rows'] / i['n_chunks']:.0f} | {i['n_vocab']:,} | {c['split_seconds']:.2f} | {i['tokenize_seconds']:.2f} | "
            f"{i['insert_seconds']:.2f} | {per_1k:.1f} | {tb['lex_terms'] / 1e6:.1f} (norm {tb['lex_terms_norm'] / 1e6:.1f}) | "
            f"{i['db_bytes'] / 1e6:.1f} | {i['db_bytes'] / c['bytes']:.1f} |"
        )
        print(f"secondary index: {inc['secondary_index_seconds']} s, db {inc['db_bytes_with_index'] / 1e6:.1f} MB; "
              f"reinsert 1000 entries: {inc['reinsert_1000_entries_seconds']} s; allow sizes {t['_allow_sizes']}")
        d = inc["scope_driven_timings_ms"]
        for a in ("1", "3", "6"):
            x = t[a]
            print(
                f"| {i['n_chunks']:,} (gpu) | {a} | {x['precomputed']['median_ms']:.3f} | {x['runtime']['median_ms']:.3f} | "
                f"{x['entry_maxp']['median_ms']:.3f} | {x['scope_ids_small']['median_ms']:.3f} | {x['scope_ids_half']['median_ms']:.3f} | "
                f"{x['scope_segment']['median_ms']:.3f} | {d[a]['scope_driven_small']['median_ms']:.3f} / {d[a]['scope_driven_half']['median_ms']:.3f} |"
            )
        for n, o in r["overlay_scan"].items():
            print(f"| {r['label']} | {o['dirty_entries']} | {o['chunks']:,} | {o['seconds']:.2f} |")
        print("max_ms:", {a: {k: v["max_ms"] for k, v in t[a].items()} for a in ("1", "3", "6")})
        print("queries 3:", r["queries"]["3"][:3], "6:", r["queries"]["6"][:2])
        print()


if __name__ == "__main__":
    main(sys.argv[1:])
