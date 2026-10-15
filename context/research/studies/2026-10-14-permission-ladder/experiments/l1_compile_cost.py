"""How much a third and fourth Rights compile would weigh — measured on the live resolver (two levels today)."""
from __future__ import annotations
import time
from vfs.storage.grants import GrantRow, resolve
from vfs.storage.backends.database.rights import _size

def world(n: int) -> list[GrantRow]:
    rows = [GrantRow("ann", f"/p{i:05d}", "read" if i % 2 else "read_write") for i in range(n)]
    rows += [GrantRow("group:g", f"/q{i:05d}", "read") for i in range(n)]
    return rows

closures = {"ann": frozenset({"group:g"}), "bob": frozenset()}
for n in (10, 200, 2000):
    rows = world(n)
    t0 = time.perf_counter()
    per_level = {}
    for level in ("read", "read_write"):
        r = resolve(closures, rows, level)
        per_level[level] = _size((r.spans, r.roots, r.holes, tuple((a.owner, a.prefixes) for a in r.owner_arms), r.ranges()))
    dt = time.perf_counter() - t0
    # The same rows resolved at a level no row carries exactly: a stand-in for `list` (every row >= list) and
    # `contribute` (only read_write rows >= contribute) — what the two extra compiles would produce today.
    as_list = resolve(closures, rows, "read")        # rows with rank >= list == rows with rank >= read today
    as_contribute = resolve(closures, rows, "read_write")
    same_list = as_list == resolve(closures, rows, "read")
    print(f"n={n:5d} rows={len(rows):5d}  weight read={per_level['read']:8d} B  read_write={per_level['read_write']:8d} B  "
          f"two compiles {dt*1000:.1f} ms; list==read when no list row: {same_list}; contribute==read_write when no contribute row: {as_contribute == resolve(closures, rows, 'read_write')}")
