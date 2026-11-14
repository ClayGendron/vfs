"""Probe 1: what an ordinary caller's compile and visibility statements cost at N users, for N in argv.

usage: probe_compile.py DATA_DIR N [N ...]   (builds world-N.sqlite in DATA_DIR when it is absent)

Counts only. Prints, per N and caller: the compile's spans, pieces, owner
pieces, holes; per verb: statements, the widest bind count, the biggest
bound bytes, and a fingerprint of the statement texts; then whether the
texts are identical across the N values given.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys

from world import DATA, SYSTEM, Recorder, biggest_bound, build, who

from vfs.models import Entry
from vfs.paths import Path
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database.rights import resolve_authority

HERE = DATA
CALLERS = ("ann", "heavy", "granted", "admin", "system", "anonymous")


async def compile_facts(storage: DatabaseStorage, name: str) -> dict:
    host = storage._host
    async with host.session_factory() as session:
        res = await resolve_authority(session, host.tables, host.profile, host.membership_budget, who(name), None)
    out = {}
    for rung in ("list", "read", "read_write"):
        rights = res.at(rung)
        if rights.whole:
            out[rung] = "whole"
            continue
        r = rights.ranges()
        owner_points = sum(len(p.points) for _, p in r.owners)
        owner_opens = sum(len(p.opens) for _, p in r.owners)
        arms_json = len(json.dumps(list(r.arms.points))) + len(json.dumps([list(o) for o in r.arms.opens]))
        owner_json = sum(len(json.dumps(list(p.points))) + len(json.dumps([list(o) for o in p.opens])) for _, p in r.owners)
        out[rung] = {
            "spans": len(rights.spans),
            "roots": len(rights.roots),
            "points": len(r.arms.points),
            "opens": len(r.arms.opens),
            "owner_arms": len(r.owners),
            "owner_points": owner_points,
            "owner_opens": owner_opens,
            "holes": len(rights.holes),
            "json_bytes": arms_json + owner_json,
        }
    return out


def verbs(name: str):
    a = who(name)
    home = "ann" if name in ("system", "anonymous", "admin") else name
    return {
        "ls /": lambda s: s.ls(path=Path("/"), authority=a),
        "ls /home": lambda s: s.ls(path=Path("/home"), authority=a),
        "ls /shared": lambda s: s.ls(path=Path("/shared"), authority=a),
        "glob /shared/**": lambda s: s.glob(patterns=("/shared/**",), authority=a),
        "tree /": lambda s: s.tree(path=Path("/"), authority=a),
        "tree /home": lambda s: s.tree(path=Path("/home"), authority=a),
        "tree /shared": lambda s: s.tree(path=Path("/shared"), authority=a),
        "glob /home/**": lambda s: s.glob(patterns=("/home/**",), authority=a),
        "grep needle": lambda s: s.grep(pattern="needle", authority=a),
        "search needle": lambda s: s.search(query="needle", authority=a),
        "read own": lambda s: s.read(path=Path(f"/home/{home}/f0.md"), authority=a),
        "stat share": lambda s: s.stat(path=Path("/shared/s000/f0.md"), authority=a),
        "write own": lambda s: s.write(entries=[Entry(path=Path(f"/home/{home}/new.md"), content="x")], authority=a),
    }


async def measure(n: int) -> dict:
    path = os.path.join(HERE, f"world-{n}.sqlite")
    url = f"sqlite+aiosqlite:///{path}"
    if os.path.exists(path):
        storage = DatabaseStorage(url=url, posture="read")
    else:
        storage = await build(url, n)
    rec = Recorder(storage)
    report: dict = {}
    try:
        for name in CALLERS:
            facts = await compile_facts(storage, name) if name != "system" else "everything"
            per: dict = {"compile": facts}
            for verb, call in verbs(name).items():
                await call(storage)  # warm the cache: count the hit path, as a steady caller pays
                result, rows = await rec.run(call(storage))
                texts = [t for t, _, _ in rows]
                per[verb] = {
                    "ok": result.success,
                    "rows": len(result.observations),
                    "statements": len(rows),
                    "max_binds": max((b for _, b, _ in rows), default=0),
                    "max_bound_bytes": biggest_bound(rows),
                    "text_hash": hashlib.sha256("\n--\n".join(texts).encode()).hexdigest()[:12],
                    "_texts": texts,
                }
            report[name] = per
    finally:
        await storage.close()
    return report


async def main() -> None:
    sizes = [int(a) for a in sys.argv[2:]] or [1000, 10000]
    reports = {n: await measure(n) for n in sizes}
    for n, rep in reports.items():
        print(f"===== N={n}")
        for name, per in rep.items():
            print(f"--- {name}: compile {json.dumps(per['compile'])}")
            for verb, m in per.items():
                if verb == "compile":
                    continue
                shown = {k: v for k, v in m.items() if not k.startswith("_")}
                print(f"    {verb:18} {shown}")
    if len(sizes) >= 2:
        print("===== text identity across sizes")
        first = reports[sizes[0]]
        for name in CALLERS:
            for verb in first[name]:
                if verb == "compile":
                    continue
                hashes = [reports[n][name][verb]["text_hash"] for n in sizes]
                counts = [reports[n][name][verb]["statements"] for n in sizes]
                same = len(set(hashes)) == 1
                if not same:
                    a, b = reports[sizes[0]][name][verb]["_texts"], reports[sizes[-1]][name][verb]["_texts"]
                    diff = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
                    print(f"  DIFF {name:9} {verb:18} counts={counts} first-diff-index={diff[:3]} lens={len(a)},{len(b)}")
                else:
                    print(f"  same {name:9} {verb:18} counts={counts}")


if __name__ == "__main__":
    asyncio.run(main())
