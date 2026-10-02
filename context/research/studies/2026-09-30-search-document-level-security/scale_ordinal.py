"""Does the join or the ordinal seek stay flat as the corpus grows ten-fold?

Runs only the two shapes that survived ``filter_shapes.py`` (the range join
and the ordinal seeks) on SQLite at 50,000 and 500,000 chunks, for callers
whose grant count is fixed while the rows they see grow with the corpus.

    uv run --no-sync python scale_ordinal.py

Study code only: nothing here is imported by vfs.
"""

from __future__ import annotations

from filter_shapes import build, corpus_by_join, corpus_by_ordinal, timed


def main() -> None:
    print("| chunks | caller | visible | join (ms) | ordinal (ms) |")
    print("|---|---|---|---|---|")
    for folders in (100, 1000):
        db = build(folders, 50)
        every_folder = [f"/t{t:02d}/f{f:03d}" for t in range(10) for f in range(folders)]
        spread = every_folder[:: len(every_folder) // 100]
        for label, prefixes in (("1 grant (10%)", ["/t03"]), ("100 grants", spread)):
            t_join, a = timed(corpus_by_join, db, prefixes)
            t_ord, b = timed(corpus_by_ordinal, db, prefixes)
            assert tuple(a) == tuple(b), (label, a, b)
            print(f"| {folders * 500:,} | {label} | {a[0]:,} | {t_join:.1f} | {t_ord:.2f} |")
        db.close()


if __name__ == "__main__":
    main()
