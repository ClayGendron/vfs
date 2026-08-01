"""Property check: glob-pattern residuation across a mount table is exact.

The law under test (the seam contract candidate for namespace-coordinate
glob patterns):

    For every (pattern, mount table, row placement):
        rows matched by the full pattern over the unified namespace
        ==  union over mounts of rows matched entry-locally by that
            mount's residual patterns.

where ``residuals(pattern, mount_path)`` is the segment-wise derivative
of the pattern's components by the mount's segments: a literal/wildcard
component consumes a matching segment, ``**`` both survives consumption
and may match zero components, and an empty result set means the mount
is unreachable (dead residual -> the router skips the dispatch).

Exactness is the claim — soundness (no dropped rows) AND tightness (no
spurious rows) — unlike the 073 LIKE spike, which proves superset only.
The empty residual (pattern exhausted exactly at the bind point) denotes
the mount-point row, which belongs to the parent storage and is dropped
from the child's dispatch; the property run covers this because bind
points are modeled as ordinary rows of the parent.

Re-pointed 2026-08-01 (the 091 slice-1 landing): ``residuals`` and the
authoritative compile now import from the LANDED ``vfs.glob_patterns``,
so every run re-proves the shipped functions. Landed-run record: 5,590
cases, zero failures; 5,766 dead-mount skips; 261 multi-residual
dispatches; max residual-set size 2 — identical to the pre-landing
reference run, as required.

Run:  uv run python context/research/studies/2026-07-31-glob-residuation/verify_residuation.py
Exit 0 iff every case agrees; prints routing/fan-out statistics either way.
"""

from __future__ import annotations

import itertools
import sys

from vfs.glob_patterns import compile_glob, residuals
from vfs.paths import Path

# ---------------------------------------------------------------------------
# Rendering (router-side inline when 091 slice 2 lands)
# ---------------------------------------------------------------------------


def residual_pattern(comps: tuple[str, ...]) -> str:
    """Render a residual back to an entry-local anchored pattern."""
    return "/" + "/".join(comps)


# ---------------------------------------------------------------------------
# Corpus: mount tables, row placements, patterns
# ---------------------------------------------------------------------------

MOUNT_TABLES: list[list[str]] = [
    ["/"],
    ["/", "/data"],
    ["/", "/data", "/data/api"],
    ["/", "/data", "/docs"],
    ["/", "/deep", "/deep/data", "/deep/data/api"],
]

# Entry-local rows per mount (mount-point rows of children are added by
# the model builder). Names deliberately collide with mount segments.
ROW_SHAPES: list[str] = [
    "/a.txt",
    "/x.py",
    "/data/a.txt",
    "/api/c.txt",
    "/deep/nested/b.txt",
    "/.hidden/h.txt",
    "/data.txt",
]

PATTERN_COMPONENTS: list[str] = ["data", "api", "deep", "*", "**", "*.txt", "?.py", "[dD]ata", "d*", "a.txt"]

EXTRA_PATTERNS: list[str] = [
    "*/x.py",
    "**/*.txt",
    "src/*.py",
    "/data",
    "/d*",
    "/data/**",
    "/**/api/*.txt",
    "/data/**/api/*.txt",
]


def build_namespace(table: list[str]) -> dict[str, list[str]]:
    """Rows per mount: shapes minus shadowed placements, plus bind points."""
    rows: dict[str, list[str]] = {m: [] for m in table}
    deeper = {m: [d for d in table if d != m and d.startswith(m.rstrip("/") + "/")] for m in table}
    for mount in table:
        for shape in ROW_SHAPES:
            full = shape if mount == "/" else mount + shape
            if any(full == d or full.startswith(d + "/") for d in deeper[mount]):
                continue
            rows[mount].append(shape)
    for mount in table:
        if mount == "/":
            continue
        parents = [m for m in table if m != mount and (m == "/" or mount.startswith(m + "/"))]
        parent = max(parents, key=len)
        rows[parent].append(mount if parent == "/" else mount[len(parent) :])
    return rows


def full_paths(rows: dict[str, list[str]]) -> dict[str, str]:
    """full path -> owning mount, for the unified oracle view."""
    out: dict[str, str] = {}
    for mount, locals_ in rows.items():
        for local in locals_:
            out["/".join([mount.rstrip("/"), local.lstrip("/")]) if mount != "/" else local] = mount
    return out


# ---------------------------------------------------------------------------
# The property run
# ---------------------------------------------------------------------------


def check(pattern: str, table: list[str]) -> tuple[bool, dict[str, int]]:
    rows = build_namespace(table)
    unified = full_paths(rows)
    oracle = compile_glob(pattern)
    want = {p for p in unified if oracle.match(p)}

    got: set[str] = set()
    stats = {"dead": 0, "multi": 0, "max_set": 0}
    for mount in table:
        res = residuals(pattern, Path(mount))
        live = [r for r in res if r]
        stats["max_set"] = max(stats["max_set"], len(live))
        if not res:
            stats["dead"] += 1
            continue
        if len(live) > 1:
            stats["multi"] += 1
        matchers = [compile_glob(residual_pattern(r)) for r in live]
        for local in rows[mount]:
            if any(m.match(local) for m in matchers):
                got.add("/".join([mount.rstrip("/"), local.lstrip("/")]) if mount != "/" else local)
    return want == got, stats


def main() -> int:
    patterns = ["/" + "/".join(c) for n in (1, 2, 3) for c in itertools.product(PATTERN_COMPONENTS, repeat=n)]
    patterns += EXTRA_PATTERNS
    failures = 0
    totals = {"cases": 0, "dead": 0, "multi": 0, "max_set": 0}
    for table in MOUNT_TABLES:
        for pattern in patterns:
            ok, stats = check(pattern, table)
            totals["cases"] += 1
            totals["dead"] += stats["dead"]
            totals["multi"] += stats["multi"]
            totals["max_set"] = max(totals["max_set"], stats["max_set"])
            if not ok:
                failures += 1
                if failures <= 10:
                    print(f"MISMATCH  table={table}  pattern={pattern!r}")
    print(
        f"\ncases={totals['cases']}  failures={failures}  "
        f"dead-mount skips={totals['dead']}  multi-residual dispatches={totals['multi']}  "
        f"max residual-set size={totals['max_set']}"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
