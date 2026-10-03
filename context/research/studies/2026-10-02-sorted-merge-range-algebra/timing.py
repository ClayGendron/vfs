"""Timing: the shipped resolver and pieces against the sorted-merge algebra.

Three shapes, each at 1k, 10k and 100k:

- ``holes``: an open root with H private homes (one everyone arm with H
  holes) — the shipped ``_subtract`` is O(H²).
- ``postures``: a private root with H shared homes, each holding a
  private sub-folder — H qualifying everyone arms, so the shipped
  ``_everyone_arms`` and ``_already`` scan pairwise.
- ``grants``: G grants to one group, with 1, 2 and 5 members in it — the
  shipped ``meet`` is a cross product, and the owner floor's trim is G×G.

A shipped run is skipped when the previous size projects it past 60 s
(quadratic projection), and the table says so.

Run from the repo root:

    uv run --no-sync python context/research/studies/2026-10-02-sorted-merge-range-algebra/timing.py
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

from algebra import Row, resolve_rights  # noqa: E402
from vfs.storage.grants import GrantRow, resolve  # noqa: E402

LIMIT = 60.0
SIZES = (1_000, 10_000, 100_000)


def holes_rows(h: int) -> list[GrantRow]:
    return [GrantRow("*", "/", "read_write"), *(GrantRow("*", f"/home/u{i}", "none") for i in range(h))]


def postures_rows(h: int) -> list[GrantRow]:
    rows = [GrantRow("*", "/", "none")]
    for i in range(h):
        rows.append(GrantRow("*", f"/home/u{i}", "read"))
        rows.append(GrantRow("*", f"/home/u{i}/secret", "none"))
    return rows


def grants_rows(g: int) -> list[GrantRow]:
    return [GrantRow("*", "/", "none"), *(GrantRow("group:eng", f"/p/{i}", "read") for i in range(g))]


def time_shipped(closures, rows) -> tuple[float, float, int]:
    t0 = time.perf_counter()
    rights = resolve(closures, rows, "read")
    t1 = time.perf_counter()
    found = rights.ranges()
    t2 = time.perf_counter()
    n = len(found.arms.points) + len(found.arms.opens)
    return t1 - t0, t2 - t1, n


def time_new(closures, rows) -> tuple[float, float, int]:
    new_rows = [Row(*r) for r in rows]
    t0 = time.perf_counter()
    rights = resolve_rights(closures, new_rows, "read")
    t1 = time.perf_counter()
    found = rights.pieces()
    t2 = time.perf_counter()
    return t1 - t0, t2 - t1, len(found.points) + len(found.opens)


def fmt(t: float | None, note: str = "") -> str:
    if t is None:
        return note
    return f"{t * 1000:.0f} ms" if t < 1 else f"{t:.1f} s"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "runs" / "timing.md"))
    ap.add_argument("--sizes", type=int, nargs="*", default=list(SIZES))
    args = ap.parse_args()
    lines = ["# Timing run", "", "resolve = the resolver; pieces = `Rights.ranges()` (shipped) / `RangeRights.pieces()` (new). Total = both.", ""]

    shapes = [
        ("holes (open root, H private homes), 1 member", holes_rows, {"ann": frozenset()}),
        ("postures (private root, H shared homes each with a private sub), 1 member", postures_rows, {"ann": frozenset()}),
    ]
    for members in (1, 2, 5):
        closures = {f"u{k}": frozenset({"group:eng"}) for k in range(members)}
        shapes.append((f"grants (G grants to one group), {members} member{'s' if members > 1 else ''}", grants_rows, closures))

    for title, builder, closures in shapes:
        lines += [f"## {title}", "", "| n | shipped resolve | shipped pieces | shipped total | new resolve | new pieces | new total | pieces (shipped / new) |", "|---|---|---|---|---|---|---|---|"]
        prev: tuple[int, float] | None = None
        for n in args.sizes:
            rows = builder(n)
            note = ""
            shipped: tuple[float, float, int] | None = None
            if prev is not None and prev[1] * (n / prev[0]) ** 2 > LIMIT:
                note = f"skipped: projected ~{prev[1] * (n / prev[0]) ** 2:.0f} s"
            else:
                shipped = time_shipped(closures, rows)
                prev = (n, shipped[0] + shipped[1])
            new = time_new(closures, rows)
            if shipped is None:
                row = f"| {n:,} | {note} | | | {fmt(new[0])} | {fmt(new[1])} | {fmt(new[0] + new[1])} | – / {new[2]:,} |"
            else:
                row = f"| {n:,} | {fmt(shipped[0])} | {fmt(shipped[1])} | {fmt(shipped[0] + shipped[1])} | {fmt(new[0])} | {fmt(new[1])} | {fmt(new[0] + new[1])} | {shipped[2]:,} / {new[2]:,} |"
            lines.append(row)
            print(row, flush=True)
        lines.append("")

    # A meet whose answer is not one of its inputs: u1 holds /p/i, u2 holds /p/i/sub.
    lines += ["## grants, 2 members with different prefixes (u1: /p/i, u2: /p/i/sub) — the meet keeps the deeper one", "", "| n | shipped total | new total | pieces (shipped / new) |", "|---|---|---|---|"]
    prev = None
    for n in args.sizes:
        rows = [GrantRow("*", "/", "none")]
        rows += [GrantRow("u1", f"/p/{i}", "read") for i in range(n)]
        rows += [GrantRow("u2", f"/p/{i}/sub", "read") for i in range(n)]
        closures = {"u1": frozenset(), "u2": frozenset()}
        shipped = None
        note = ""
        if prev is not None and prev[1] * (n / prev[0]) ** 2 > LIMIT:
            note = f"skipped: projected ~{prev[1] * (n / prev[0]) ** 2:.0f} s"
        else:
            shipped = time_shipped(closures, rows)
            prev = (n, shipped[0] + shipped[1])
        new = time_new(closures, rows)
        row = f"| {n:,} | {note if shipped is None else fmt(shipped[0] + shipped[1])} | {fmt(new[0] + new[1])} | {'–' if shipped is None else f'{shipped[2]:,}'} / {new[2]:,} |"
        lines.append(row)
        print(row, flush=True)
    lines.append("")
    Path(args.out).write_text("\n".join(lines))
    print("wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
