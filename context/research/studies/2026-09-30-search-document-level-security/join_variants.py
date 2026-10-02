"""Follow-up to ``filter_shapes.py``: the join without a temp table, and why the arms are slow.

Three questions, same corpus:

- Does an inline ``VALUES`` table of ranges (no temp table, portable where a
  temp table is awkward) plan like the temp-table join?
- Are the OR'd arms slow because of the predicate or because of the plan?
  ``range, entry-first`` forces SQLite to drive from ``entry`` (CROSS JOIN
  fixes the loop order), so the OR can use the path index.
- With the ranges disjoint, per-statement aggregates add up exactly, so a
  budget split needs no row fetch and no dedupe. ``values, split`` runs one
  aggregate per slice of ``SLICE`` ranges and sums them.

    uv run --no-sync python join_variants.py --folders 100 --files 50
"""

from __future__ import annotations

import argparse
import sqlite3

from filter_shapes import build, callers, corpus_by_join, range_arms, ranges, timed

SLICE = 500


def corpus_by_values(db: sqlite3.Connection, prefixes: list[str], slice_size: int = 100_000) -> tuple[int, int]:
    spans = ranges(prefixes)
    count = total = 0
    for i in range(0, len(spans), slice_size):
        part = spans[i : i + slice_size]
        rows = ", ".join("(?, ?)" for _ in part)
        n, dl = db.execute(
            f"WITH r(lo, hi) AS (VALUES {rows}) SELECT count(*), coalesce(sum(d.dl),0) FROM r "
            "JOIN entry e ON e.path >= r.lo AND e.path < r.hi "
            "JOIN lex_docs d ON d.epoch = 1 AND d.entry_id = e.entry_id",
            [b for span in part for b in span],
        ).fetchone()
        count, total = count + n, total + dl
    return count, total


def corpus_by_range_entry_first(db: sqlite3.Connection, prefixes: list[str]) -> tuple[int, int]:
    seen = 0, 0
    for i in range(0, len(prefixes), 400):
        where, binds = range_arms(prefixes[i : i + 400])
        n, dl = db.execute(
            "SELECT count(*), coalesce(sum(d.dl),0) FROM entry e CROSS JOIN lex_docs d "
            f"ON d.epoch = 1 AND d.entry_id = e.entry_id WHERE {where}",
            binds,
        ).fetchone()
        seen = seen[0] + n, seen[1] + dl  # prefixes here never overlap, so slices add up
    return seen


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--folders", type=int, default=100)
    parser.add_argument("--files", type=int, default=50)
    args = parser.parse_args()
    db = build(args.folders, args.files)
    print("| caller | temp join | values join | values, split every 500 ranges | range arms, entry-first |")
    print("|---|---|---|---|---|")
    for label, prefixes in callers(args.folders, args.files).items():
        t_join, a = timed(corpus_by_join, db, prefixes)
        t_values, b = timed(corpus_by_values, db, prefixes)
        t_split, c = timed(corpus_by_values, db, prefixes, SLICE)
        t_first, d = timed(corpus_by_range_entry_first, db, prefixes)
        assert tuple(a) == tuple(b) == tuple(c) == tuple(d), (label, a, b, c, d)
        print(f"| {label} | {t_join:.1f} | {t_values:.1f} | {t_split:.1f} | {t_first:.1f} |")
    prefixes = callers(args.folders, args.files)["100 grants (10%)"]
    where, binds = range_arms(prefixes)
    plan = db.execute(
        "EXPLAIN QUERY PLAN SELECT count(*) FROM entry e CROSS JOIN lex_docs d "
        f"ON d.epoch = 1 AND d.entry_id = e.entry_id WHERE {where}",
        binds,
    ).fetchall()
    print("\nentry-first plan (100 grants): " + "; ".join(row[3] for row in plan[:4]) + " ...")


if __name__ == "__main__":
    main()
