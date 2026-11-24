"""Render the JSON a probe printed as the tables kept in ``output.md``.

    uv run python agents/2026-11-22-the-kernel-keeps-records-of-its-own/probes/report.py waits <file.json>
    uv run python agents/2026-11-22-the-kernel-keeps-records-of-its-own/probes/report.py pool <file.json>

``waits`` reads what ``probe_waits.py`` printed and ``pool`` what ``probe_postgres_pool.py`` printed. A
figure over several repeats is the median of the repeats' figures; a count is the sum over the repeats.
"""

from __future__ import annotations

import json
import statistics
import sys
from typing import Any


def med(values: list[float]) -> str:
    values = [v for v in values if v is not None]
    if not values:
        return "—"
    value = statistics.median(values)
    return f"{value:,.0f}" if value >= 100 else f"{value:,.1f}"


def total(values: list[int]) -> int:
    return sum(v for v in values if v is not None)


def pick(cells: list[dict[str, Any]], *path: str) -> list[Any]:
    out = []
    for cell in cells:
        value: Any = cell
        for key in path:
            value = value.get(key) if isinstance(value, dict) else None
        out.append(value)
    return out


def waits(payload: dict[str, Any]) -> None:
    arguments = payload["arguments"]
    print(f"Arguments: `{json.dumps(arguments)}`; SQLite {payload.get('sqlite')}; {payload['seconds']} s in all.\n")
    for kind in ("quiet", "batch", "held", "sweep"):
        rows = []
        notes = []
        for cell in payload["cells"]:
            ws = [w for w in cell["windows"] if w["window"] == kind]
            if not ws:
                continue
            flushes = pick(ws, "flushes")
            has_store = any(f is not None for f in flushes)
            for w in ws:
                if w.get("batch_record"):
                    notes.append(
                        f"- `{cell['place']}` repeat {w['repeat']}: the batch took {w['batch_seconds']} s; its record of "
                        f"{w['batch_record']['rows']:,} rows waited {w['batch_record']['waited_to_begin_s']} s to begin "
                        f"and held the writer {w['batch_record']['held_the_writer_s']} s; failed: {w['batch_record']['failed']}."
                    )
                if w.get("sweep"):
                    notes.append(
                        f"- `{cell['place']}`: the pass removed {sum(w['sweep_chunks_removed']):,} rows in "
                        f"{w['sweep']['chunks']} commits, {w['sweep']['failed']} failed; a commit's median "
                        f"{w['sweep']['whole']['median_ms']} ms and longest {w['sweep']['whole']['max_ms']} ms; "
                        f"its longest wait to begin {w['sweep']['begin_wait']['max_ms']} ms."
                    )
            rows.append(
                [
                    cell["place"],
                    med(pick(ws, "seconds")),
                    f"{total(pick(ws, 'reads', 'n')):,}",
                    med(pick(ws, "reads_a_second")),
                    med(pick(ws, "reads", "median_ms")),
                    med(pick(ws, "reads", "p95_ms")),
                    f"{max(v for v in pick(ws, 'reads', 'max_ms') if v is not None):,.0f}",
                    total(pick(ws, "reads", "failed")),
                    total(pick(ws, "writes_verb", "n")),
                    med(pick(ws, "writes_verb", "median_ms")),
                    med(pick(ws, "writes_verb_and_record", "median_ms")),
                    total(pick(ws, "writes_verb", "refused")),
                    total(pick(ws, "records", "failed")) if has_store else "—",
                    f"{total(pick(ws, 'flushes', 'failed'))} / {total(pick(ws, 'flushes', 'count'))}" if has_store else "—",
                    total(pick(ws, "flushes", "needed_more_than_one_try")) if has_store else "—",
                    f"{max(v for v in pick(ws, 'flushes', 'slowest_s') if v is not None):.2f}" if has_store else "—",
                    med(pick(ws, "store_commit_begin_wait", "median_ms")) if has_store else "—",
                    f"{max(v for v in pick(ws, 'store_commit_begin_wait', 'max_ms') if v is not None):,.0f}" if has_store else "—",
                    max(v for v in pick(ws, "buffer_high_water") if v is not None) if has_store else "—",
                    total(pick(ws, "rows_dropped")) if has_store else "—",
                ]
            )
        if not rows:
            continue
        print(f"#### Window `{kind}`\n")
        head = [
            "place", "window s", "reads", "reads a second", "read median ms", "read p95 ms", "read max ms", "reads failed",
            "one-file writes", "write median ms, verb", "write median ms, verb and record", "writes refused",
            "record writes failed", "flushes failed / all", "flushes that needed a second try", "slowest flush s",
            "store commit waited to begin, median ms", "the longest such wait ms", "buffer high water", "rows dropped",
        ]
        table(head, rows)
        if notes:
            print("\n".join(notes) + "\n")
    rows = []
    for cell in payload["cells"]:
        ms = cell["many_writers"]
        if not ms:
            continue
        has_store = any(m.get("records") for m in ms)
        rows.append(
            [
                cell["place"],
                len(ms),
                total(pick(ms, "writes_verb", "n")),
                med(pick(ms, "writes_verb", "median_ms")),
                med(pick(ms, "writes_verb", "p95_ms")),
                med(pick(ms, "writes_verb_and_record", "median_ms")),
                med(pick(ms, "writes_verb_and_record", "p95_ms")),
                f"{max(v for v in pick(ms, 'writes_verb_and_record', 'max_ms') if v is not None):,.0f}",
                total(pick(ms, "refused")),
                total(pick(ms, "records", "failed")) if has_store else "—",
                total(pick(ms, "records", "needed_more_than_one_try")) if has_store else "—",
                med(pick(ms, "records", "begin_wait", "median_ms")) if has_store else "—",
                f"{max(v for v in pick(ms, 'records', 'begin_wait', 'max_ms') if v is not None):,.0f}" if has_store else "—",
            ]
        )
    if rows:
        print(f"#### {arguments['sessions']} writing sessions, no reader and no batch\n")
        head = [
            "place", "repeats", "writes counted", "verb median ms", "verb p95 ms", "verb and record median ms",
            "verb and record p95 ms", "slowest ms", "writes refused", "record writes failed",
            "records that needed a second try", "record waited to begin, median ms", "the longest such wait ms",
        ]
        table(head, rows)
    for cell in payload["cells"]:
        print(f"- `{cell['place']}` at close: {json.dumps(cell['at_close'])}")
    print()


def pool(payload: dict[str, Any]) -> None:
    arguments = payload["arguments"]
    print(f"Arguments: `{json.dumps(arguments)}`; {payload['seconds']} s in all.\n")
    ways: list[str] = []
    for cell in payload["cells"]:
        if cell["way"] not in ways:
            ways.append(cell["way"])
    order = [w for w in ("none", "mount-pool", "own-15", "own-32") if w in ways]
    rows = []
    for way in order:
        cs = [c for c in payload["cells"] if c["way"] == way]
        has_store = way != "none"
        row = [
            way,
            len(cs),
            total(pick(cs, "write_verb_and_record", "n")),
            med(pick(cs, "write_verb_and_record", "median_ms")),
            " ".join(f"{v:,.0f}" for v in pick(cs, "write_verb_and_record", "median_ms") if v is not None),
            med(pick(cs, "write_verb_and_record", "p95_ms")),
            med(pick(cs, "write_verb_alone", "median_ms")),
            med(pick(cs, "record", "median_ms")) if has_store else "—",
            med(pick(cs, "record", "p95_ms")) if has_store else "—",
            total(pick(cs, "writes_refused")),
            total(pick(cs, "record", "failed")) if has_store else "—",
            max(pick(cs, "connections_open_at_the_peak")),
            max(pick(cs, "mount_pool", "most_out")),
            max(pick(cs, "mount_pool", "most_callers_waiting")),
            max(v for v in pick(cs, "store_pool", "most_out") if v is not None) if way.startswith("own") else "—",
            max(v for v in pick(cs, "store_pool", "most_callers_waiting") if v is not None) if way.startswith("own") else "—",
            total(pick(cs, "record_checkouts_that_found_the_pool_exhausted")) if has_store else "—",
        ]
        if arguments.get("batches"):
            row += [
                med(pick(cs, "reads", "median_ms")),
                med(pick(cs, "reads", "p95_ms")),
                f"{total(pick(cs, 'flushes', 'failed'))} / {total(pick(cs, 'flushes', 'count'))}" if has_store else "—",
                med(pick(cs, "flushes", "whole", "median_ms")) if has_store else "—",
                f"{max((v for v in pick(cs, 'flushes', 'whole', 'max_ms') if v is not None), default=0):,.0f}" if has_store else "—",
                max((v for v in pick(cs, "flushes", "buffer_high_water") if v is not None), default=0) if has_store else "—",
                f"{total(pick(cs, 'batches', 'served'))} / {total(pick(cs, 'batches', 'refused'))} / {total(pick(cs, 'batches', 'cancelled_at_the_window'))}",
            ]
        rows.append(row)
    head = [
        "way", "repeats", "writes counted", "verb and record median ms", "each repeat's median", "verb and record p95 ms",
        "verb alone median ms", "record median ms", "record p95 ms", "writes refused", "record writes failed",
        "connections open at the peak", "mount pool: most out", "mount pool: most callers waiting",
        "store pool: most out", "store pool: most callers waiting", "record writes that found their pool exhausted",
    ]
    if arguments.get("batches"):
        head += ["read median ms", "read p95 ms", "flushes failed / all", "flush median ms", "slowest flush ms",
                 "buffer high water", "batches served / refused / cancelled at the window"]
    table(head, rows)
    kinds = sorted({k for c in payload["cells"] for k in c.get("refusal_kinds", [])})
    errors = sorted({e for c in payload["cells"] for e in (c.get("record") or {}).get("errors", [])})
    flush_errors = sorted({e for c in payload["cells"] for e in (c.get("flushes") or {}).get("errors", [])})
    batch_kinds = sorted({k for c in payload["cells"] for k in (c.get("batches") or {}).get("refusal_kinds", [])})
    print(f"- write refusal kinds: {kinds or 'none'}")
    print(f"- record errors: {errors or 'none'}")
    print(f"- flush errors: {flush_errors or 'none'}")
    if arguments.get("batches"):
        print(f"- batch refusal kinds: {batch_kinds or 'none'}")
    print()


def table(head: list[str], rows: list[list[Any]]) -> None:
    """One row a measure and one column a place, since the measures are many and the places few."""
    print("| measure | " + " | ".join(str(r[0]) for r in rows) + " |")
    print("|---|" + "---|" * len(rows))
    for i, name in enumerate(head[1:], start=1):
        print(f"| {name} | " + " | ".join(str(r[i]) for r in rows) + " |")
    print()


if __name__ == "__main__":
    with open(sys.argv[2]) as handle:
        loaded = json.load(handle)
    {"waits": waits, "pool": pool}[sys.argv[1]](loaded)
