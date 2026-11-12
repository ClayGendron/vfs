"""Render the study's Markdown tables from the results JSON files beside this script.

Usage: uv run python tables.py [results_*.json ...]  -> writes tables.md beside this file and prints it.
"""

from __future__ import annotations

import glob
import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def med(values):
    return statistics.median(values) if values else 0.0


def fmt_s(x: float) -> str:
    return f"{x:.3f}" if x < 10 else f"{x:.1f}"


def fmt_i(x) -> str:
    return f"{int(x):,}"


def mb(x) -> str:
    return f"{x / 1_000_000:.1f}"


def by_name(calls):
    out: dict[str, list[dict]] = {}
    for c in calls:
        out.setdefault(c["name"], []).append(c)
    return out


def phase(calls, name, key):
    return [c["phases"].get(name, {}).get(key, 0) for c in calls]


def truncs(calls) -> str:
    seen: dict[str, int] = {}
    for c in calls:
        for r in c["records"]:
            if "truncated" in r["kind"]:
                label = r["message"].split("at the ", 1)[-1].split(";")[0]
                if r.get("data"):
                    label += " " + json.dumps(r["data"], separators=(",", ":"))
                seen[label] = seen.get(label, 0) + 1
    return "; ".join(f"{k} ({v}/{len(calls)})" for k, v in seen.items()) or "none"


def grep_table(d) -> str:
    lines = [
        "| N dirty | pattern | median wall s | SQL stmts | index rows | scan rows | scan bytes MB | body bytes fetched MB | nominee s | body fetch s | verify s | files hit | records |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for level in d["results"]:
        n = level["n"]
        for name, calls in by_name(level["grep"]).items():
            lines.append(
                f"| {fmt_i(n)} | {name} | {fmt_s(med([c['wall_s'] for c in calls]))} | {fmt_i(med([c['statements'] for c in calls]))} | "
                f"{fmt_i(med(phase(calls, 'grep.index_rows', 'rows')))} | {fmt_i(med(phase(calls, 'grep.nominees', 'rows')))} | "
                f"{mb(med(phase(calls, 'grep.nominees', 'bytes')))} | {mb(med(phase(calls, 'grep.bodies', 'bytes')))} | "
                f"{fmt_s(med(phase(calls, 'grep.nominees', 'wall_s')))} | {fmt_s(med(phase(calls, 'grep.bodies', 'wall_s')))} | "
                f"{fmt_s(med(phase(calls, 'grep.verify', 'wall_s')))} | {fmt_i(med([c['files'] for c in calls]))} | {truncs(calls)} |"
            )
    return "\n".join(lines)


def glean_table(d, key: str) -> str:
    lines = [
        "| N dirty | budget | query | median wall s | SQL stmts | nominees | bodies | body MB | nominee s | body fetch s | tokenize s | score s | overlay s | overlay hits | hits | records |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for level in d["results"]:
        n = level["n"]
        for name, calls in by_name(level[key]).items():
            lines.append(
                f"| {fmt_i(n)} | {fmt_i(calls[0]['overlay_budget'])} | {name} | {fmt_s(med([c['wall_s'] for c in calls]))} | "
                f"{fmt_i(med([c['statements'] for c in calls]))} | {fmt_i(med(phase(calls, 'glean.nominees', 'rows')))} | "
                f"{fmt_i(med(phase(calls, 'glean.bodies', 'rows')))} | {mb(med(phase(calls, 'glean.bodies', 'bytes')))} | "
                f"{fmt_s(med(phase(calls, 'glean.nominees', 'wall_s')))} | {fmt_s(med(phase(calls, 'glean.bodies', 'wall_s')))} | "
                f"{fmt_s(med(phase(calls, 'glean.tokenize', 'wall_s')))} | {fmt_s(med(phase(calls, 'glean.score', 'wall_s')))} | "
                f"{fmt_s(med(phase(calls, 'glean.overlay', 'wall_s')))} | {fmt_i(med(phase(calls, 'glean.overlay', 'rows')))} | "
                f"{fmt_i(med([c['hits'] for c in calls]))} | {truncs(calls)} |"
            )
    return "\n".join(lines)


def suite_table(d) -> str:
    """Per level: the suite medians summed over the five patterns/queries, the per-call maximum median, bytes."""
    lines = [
        "| N dirty | grep: sum of 5 medians s | grep: slowest median s | grep scan bytes MB | glean@500: sum s | glean@500 slowest s | glean@25000: sum s | glean@25000 slowest s | glean@25000 body MB | glean@25000 tokenize s (median query) |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for level in d["results"]:
        g = by_name(level["grep"])
        gm = [med([c["wall_s"] for c in calls]) for calls in g.values()]
        gd = by_name(level["glean_default"])
        gdm = [med([c["wall_s"] for c in calls]) for calls in gd.values()]
        gl = by_name(level["glean_lifted"])
        glm = [med([c["wall_s"] for c in calls]) for calls in gl.values()]
        scan_bytes = med([med(phase(calls, "grep.nominees", "bytes")) for calls in g.values()])
        body_mb = med([med(phase(calls, "glean.bodies", "bytes")) for calls in gl.values()])
        tok = med([med(phase(calls, "glean.tokenize", "wall_s")) for calls in gl.values()])
        lines.append(
            f"| {fmt_i(level['n'])} | {fmt_s(sum(gm))} | {fmt_s(max(gm))} | {mb(scan_bytes)} | {fmt_s(sum(gdm))} | {fmt_s(max(gdm))} | "
            f"{fmt_s(sum(glm))} | {fmt_s(max(glm))} | {mb(body_mb)} | {fmt_s(tok)} |"
        )
    return "\n".join(lines)


def slope_table(d) -> str:
    """Per-dirty-entry cost from the slope between consecutive levels (suite medians averaged over the five calls)."""
    lines = [
        "| from N | to N | grep: s per dirty entry per call | grep: bytes per dirty entry | glean@25000: s per dirty entry per call | glean@25000: bytes per dirty entry | glean tokenize s per entry |",
        "|---|---|---|---|---|---|---|",
    ]
    prev = None
    for level in d["results"]:
        g = by_name(level["grep"])
        gl = by_name(level["glean_lifted"])
        cur = {
            "n": level["n"],
            "grep_s": statistics.mean(med([c["wall_s"] for c in calls]) for calls in g.values()),
            "grep_b": statistics.mean(med(phase(calls, "grep.nominees", "bytes")) for calls in g.values()),
            "glean_s": statistics.mean(med([c["wall_s"] for c in calls]) for calls in gl.values()),
            "glean_b": statistics.mean(med(phase(calls, "glean.bodies", "bytes")) for calls in gl.values()),
            "tok_s": statistics.mean(med(phase(calls, "glean.tokenize", "wall_s")) for calls in gl.values()),
        }
        if prev is not None and cur["n"] > prev["n"]:
            dn = cur["n"] - prev["n"]
            lines.append(
                f"| {fmt_i(prev['n'])} | {fmt_i(cur['n'])} | {(cur['grep_s'] - prev['grep_s']) / dn * 1e6:.0f} µs | "
                f"{(cur['grep_b'] - prev['grep_b']) / dn:,.0f} | {(cur['glean_s'] - prev['glean_s']) / dn * 1e6:.0f} µs | "
                f"{(cur['glean_b'] - prev['glean_b']) / dn:,.0f} | {(cur['tok_s'] - prev['tok_s']) / dn * 1e6:.0f} µs |"
            )
        prev = cur
    return "\n".join(lines)


def recall_table(d) -> str:
    lines = [
        "| N dirty | not encoded after dirtying | grep finds sentinel | grep wall s | glean@500 finds sentinel | glean@500 record | glean@25000 finds sentinel | glean@25000 record |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for level in d["results"]:
        r = level["recall"]
        lines.append(
            f"| {fmt_i(level['n'])} | {fmt_i(level['dirty']['not_encoded_after'])} | {r['grep']['sentinel_found']} | {fmt_s(r['grep']['wall_s'])} | "
            f"{r['glean_default']['sentinel_found']} | {truncs([r['glean_default']])} | {r['glean_lifted']['sentinel_found']} | {truncs([r['glean_lifted']])} |"
        )
    return "\n".join(lines)


def default_wall_table(d) -> str:
    lines = [
        "| N dirty | verb | call | wall s | SQL stmts | hits | records |",
        "|---|---|---|---|---|---|---|",
    ]
    for level in d["results"]:
        for c in level["default_wall"]["grep"]:
            lines.append(
                f"| {fmt_i(level['n'])} | grep | {c['name']} | {fmt_s(c['wall_s'])} | {c['statements']} | {c['files']} | {truncs([c])} |"
            )
        for c in level["default_wall"]["glean_lifted"]:
            lines.append(
                f"| {fmt_i(level['n'])} | glean@25000 | {c['name']} | {fmt_s(c['wall_s'])} | {c['statements']} | {c['hits']} | {truncs([c])} |"
            )
    return "\n".join(lines)


def build_table(d) -> str:
    b = d["base"]
    if b.get("reused"):
        return f"Base store reused: {b['counts']}."
    rows = [
        "| step | wall s | SQL stmts | files | chunks | posting rows | lex posting rows | not encoded | epoch |",
        "|---|---|---|---|---|---|---|---|---|",
        f"| write ({d['files']} files, 10,000 per call) | {b['write']['wall_s']} | - | - | - | - | - | - | - |",
    ]
    for r in b["reindex"]:
        rows.append(
            f"| reindex #{r['attempt']} | {r['wall_s']} | {r['statements']} | {fmt_i(r['files'])} | {fmt_i(r['chunks'])} | "
            f"{fmt_i(r['posting_list'])} | {fmt_i(r['lex_postings'])} | {fmt_i(r['not_encoded'])} | {r['epoch']} |"
        )
    extra = f"\nStore size {b.get('db_mb', '-')} MB; peak RSS {b.get('rss_mb')} MB; base build total {b.get('total_s')} s."
    return "\n".join(rows) + extra


def render(path: str) -> str:
    d = json.load(open(path))
    title = f"## {d['engine']} {fmt_i(d['files'])} files ({os.path.basename(path)})"
    parts = [
        title,
        f"Started {d['started']}, finished {d.get('finished', 'running')}; {d['machine']}; Python {d['python']}; levels {d['levels']}.",
        "### Build",
        build_table(d),
        "### Suite summary per level",
        suite_table(d),
        "### Per-dirty-entry slopes",
        slope_table(d),
        "### grep per pattern",
        grep_table(d),
        "### glean at the default overlay budget (500)",
        glean_table(d, "glean_default"),
        "### glean at the lifted overlay budget (25,000)",
        glean_table(d, "glean_lifted"),
        "### Sentinel recall",
        recall_table(d),
        "### One pass under the default 10 s wall",
        default_wall_table(d),
        "### Level walls",
        "\n".join(
            [
                "| N | fresh-store copy s | dirty write s | level total s | peak RSS MB |",
                "|---|---|---|---|---|",
                *(
                    f"| {fmt_i(l['n'])} | {l['copy_s']} | {l['dirty']['wall_s']} | {l['level_total_s']} | {l['rss_mb']} |"
                    for l in d["results"]
                ),
            ]
        ),
    ]
    return "\n\n".join(parts)


def main() -> None:
    paths = sys.argv[1:] or sorted(glob.glob(os.path.join(HERE, "results_*.json")))
    text = "\n\n".join(render(p) for p in paths)
    with open(os.path.join(HERE, "tables.md"), "w") as f:
        f.write(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
