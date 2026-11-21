"""Render the study's result files as the Markdown tables the memo quotes.

    uv run python scripts/report.py > results/tables.md

Every table names the result file it was read from, so each figure in the memo traces to a script and a run.
"""

from __future__ import annotations

import json
import statistics
from typing import Any

from harness import RESULTS_DIR

VERB_ORDER = ("read", "grep", "write", "batch")
MODE_ORDER = ("none", "sync", "leaned")


def load(name: str) -> dict[str, Any] | None:
    path = RESULTS_DIR / name
    return json.loads(path.read_text()) if path.exists() else None


def statements_table(engine: str, data: dict[str, Any]) -> list[str]:
    cells = {(c["verb"], c["sessions"], c["mode"]): c for c in data["cells"]}
    out = [
        f"#### Statements per call, {engine} (`results/calls-{engine}.json`)",
        "",
        "| call | storage statements | added, none | added, sync | added, leaned | failures (none / sync / leaned) |",
        "|---|---|---|---|---|---|",
    ]
    for verb in VERB_ORDER:
        for sessions in (1, 32):
            row = [cells.get((verb, sessions, m)) for m in MODE_ORDER]
            if not all(row):
                continue
            storage = _values(row[0]["storage_statements"])
            added = [_values(c["log_statements"]) for c in row]
            failures = " / ".join(str(c["failures"]) for c in row)
            out.append(
                f"| {_call(verb)} × {sessions} | {storage} | {added[0]} | {added[1]} | {added[2]} | {failures} |"
            )
    return [*out, ""]


def time_table(engine: str, data: dict[str, Any]) -> list[str]:
    cells = {(c["verb"], c["sessions"], c["mode"]): c for c in data["cells"]}
    out = [
        f"#### Wall time per call, {engine} (`results/calls-{engine}.json`)",
        "",
        "Median of the repeats' medians, the spread between the repeats' medians, and the median of their 95th "
        "percentiles, in milliseconds. The change is the mode's median less the no-log median.",
        "",
        "| call | none: median (spread) p95 | sync: median (spread) p95 | leaned: median (spread) p95 "
        "| sync change | leaned change |",
        "|---|---|---|---|---|---|",
    ]
    for verb in VERB_ORDER:
        for sessions in (1, 32):
            row = [cells.get((verb, sessions, m)) for m in MODE_ORDER]
            if not all(row):
                continue
            shown = [f"{_ms(c['median_ms'])} ({_ms(c['median_spread_ms'])}) {_ms(c['p95_ms'])}" for c in row]
            base = row[0]["median_ms"]
            changes = [_signed(c["median_ms"] - base) for c in row[1:]]
            out.append(f"| {_call(verb)} × {sessions} | {' | '.join(shown)} | {' | '.join(changes)} |")
    return [*out, ""]


def closing_table(engine: str, data: dict[str, Any]) -> list[str]:
    out = [
        f"#### The log after each run, {engine} (`results/calls-{engine}.json`)",
        "",
        "| run | mode | calls | rows logged | flushes | largest flush, parameters | slowest flush, s "
        "| buffer high water | log writes failed |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for c in data["closing"]:
        if c["mode"] == "none":
            continue
        out.append(
            f"| {c['kind']} r{c['repeat']} | {c['mode']} | {c['expected_rows']} | {c['logged_rows']} | {c['flushes']} "
            f"| {c['flush_max_parameters']} | {c['flush_max_seconds']} | {c['buffer_high_water']} "
            f"| {c['log_failures']} |"
        )
    return [*out, ""]


def waits_table(engine: str, data: dict[str, Any]) -> list[str]:
    out = [
        f"#### Reads and writes while a 10,000-entry write runs, {engine} (`results/waits-{engine}.json`)",
        "",
        f"{data['readers']} reader sessions back to back and one one-file writer, in a quiet window and then while "
        "one more session writes 10,000 entries. Milliseconds; each cell is the median over the repeats.",
        "",
        "| mode | batch, s | read median quiet → during | read p95 quiet → during | read max during "
        "| reads failed | one-file write median during | write max during | writes failed "
        "| log writes failed | flushes failed / run | slowest flush, s | buffer high water |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    modes: dict[str, list[dict[str, Any]]] = {}
    for c in data["cells"]:
        modes.setdefault(c["mode"], []).append(c)
    for mode, cells in modes.items():
        quiet = [c["baseline"]["reads"] for c in cells]
        busy = [c["during_batch"]["reads"] for c in cells]
        writes = [c["during_batch"]["writes"] for c in cells]
        flushes = [c["during_batch"]["flushes"] for c in cells]
        logfail = [c["during_batch"]["log_failures"]["count"] for c in cells]
        out.append(
            f"| {mode} | {_med(c['during_batch']['batch']['seconds'] for c in cells):.1f} "
            f"| {_ms(_med(q['median_ms'] for q in quiet))} → {_ms(_med(b['median_ms'] for b in busy))} "
            f"| {_ms(_med(q['p95_ms'] for q in quiet))} → {_ms(_med(b['p95_ms'] for b in busy))} "
            f"| {_ms(max(b['max_ms'] for b in busy))} | {sum(b['failures'] for b in busy)} "
            f"| {_ms(_med(w.get('median_ms', 0) for w in writes))} | {_ms(max(w.get('max_ms', 0) for w in writes))} "
            f"| {sum(w.get('failures', 0) for w in writes)} | {sum(logfail)} "
            f"| {sum(f['failed'] for f in flushes)} / {sum(f['count'] for f in flushes)} "
            f"| {max(f['max_seconds'] for f in flushes)} "
            f"| {max(c['during_batch']['buffer_high_water'] for c in cells)} |"
        )
    return [*out, ""]


def growth_table(engine: str, data: dict[str, Any]) -> list[str]:
    sizes = data["sizes"]
    out = [
        f"#### Growth and reclaim, {engine} (`results/growth-{engine}.json`)",
        "",
        "| point | rows | heap MB | index MB | bytes per row | file or relation MB | free MB |",
        "|---|---|---|---|---|---|---|",
    ]
    for point, s in sizes.items():
        whole = s.get("file_bytes", s.get("total_relation_bytes", 0))
        free = s.get("freelist_bytes")
        out.append(
            f"| {point.replace('_', ' ')} | {s['rows']:,} | {s['heap_bytes'] / 2**20:.1f} "
            f"| {s['index_bytes'] / 2**20:.1f} "
            f"| {s['bytes_per_row']} | {whole / 2**20:.1f} | {'' if free is None else f'{free / 2**20:.1f}'} |"
        )
    r = data["reclaim"]
    out += [
        "",
        f"Reclaiming one day: {r['rows_deleted']:,} rows in {r['chunks']} chunks of {r['chunk_rows']:,}, "
        f"{r['statements']} statements, {r['seconds']} s; a chunk's median {r['chunk_seconds']['median_ms']} ms, "
        f"p95 {r['chunk_seconds']['p95_ms']} ms, max {r['chunk_seconds']['max_ms']} ms.",
        "",
        "| probe | quiet: median, p95, max ms | during the delete: median, p95, max ms | failed during |",
        "|---|---|---|---|",
    ]
    for probe in ("read", "write", "log_row"):
        q, d = r["probes_baseline"][probe], r["probes_during_delete"][probe]
        out.append(f"| {probe} | {_trio(q)} | {_trio(d)} | {d.get('failures', 0)} |")
    return [*out, ""]


def pool_table(engine: str, data: dict[str, Any]) -> list[str]:
    out = [
        f"#### The pool under 32 sessions, no log, {engine} (`results/pool-{engine}.json`)",
        "",
        "| pool | verb | median ms per repeat | calls a second per repeat |",
        "|---|---|---|---|",
    ]
    for pool in ("default", "32"):
        for verb in ("read", "grep"):
            cells = [c for c in data["cells"] if c["pool"] == pool and c["verb"] == verb]
            medians = ", ".join(_ms(c["median_ms"]) for c in cells)
            rates = ", ".join(str(c["calls_per_second"]) for c in cells)
            out.append(f"| {pool} | {verb} | {medians} | {rates} |")
    return [*out, ""]


def environment_lines() -> list[str]:
    out = ["#### Where every figure was measured", ""]
    seen = set()
    for name in sorted(RESULTS_DIR.glob("*.json")):
        env = json.loads(name.read_text())["environment"]
        key = (env["commit"], env.get("postgres"))
        if key in seen:
            continue
        seen.add(key)
        out.append(
            f"- `{name.name}`: commit `{env['commit']}` (src dirty: {env['src_dirty']}), {env['date']}, "
            f"Python {env['python']}, SQLite {env['sqlite']}, {env['cpu']}, {env['cores']} cores, "
            f"{env['memory_gb']} GB" + (f"; {env['postgres']}" if env.get("postgres") else "")
        )
    return [*out, ""]


def main() -> None:
    lines = ["# The study's tables", "", "Generated by `scripts/report.py` from the files in `results/`.", ""]
    lines += environment_lines()
    for engine in ("sqlite", "postgres"):
        lines += [f"## {engine}", ""]
        if calls := load(f"calls-{engine}.json"):
            lines += statements_table(engine, calls) + time_table(engine, calls) + closing_table(engine, calls)
        if waits := load(f"waits-{engine}.json"):
            lines += waits_table(engine, waits)
        if growth := load(f"growth-{engine}.json"):
            lines += growth_table(engine, growth)
        if pool := load(f"pool-{engine}.json"):
            lines += pool_table(engine, pool)
    print("\n".join(lines))


def _call(verb: str) -> str:
    return "10,000-entry `write`" if verb == "batch" else f"`{verb}`"


def _values(distribution: dict[str, int]) -> str:
    return ", ".join(distribution) if len(distribution) > 1 else next(iter(distribution))


def _ms(value: float) -> str:
    return f"{value:,.0f}" if abs(value) >= 100 else f"{value:.1f}"


def _signed(value: float) -> str:
    return f"+{_ms(value)}" if value >= 0 else f"−{_ms(-value)}"


def _med(values: Any) -> float:
    return statistics.median(list(values))


def _trio(w: dict[str, Any]) -> str:
    if not w.get("n"):
        return "none"
    return f"{_ms(w['median_ms'])}, {_ms(w['p95_ms'])}, {_ms(w['max_ms'])}"


if __name__ == "__main__":
    main()
