"""Probe 3: a posture change's relabel — transactions and UPDATE statements against ceil(rows / relabel_rows),
and what a read issued between two chunks answers against the pointwise oracle.

usage: probe_relabel.py DATA_DIR ROWS RELABEL_ROWS [deeper]
  deeper: also plant that many deeper posture rows (one per subfolder) under /big before the change.
Counts only.
"""

from __future__ import annotations

import asyncio
import math
import os
import sys
from dataclasses import replace

from world import DATA, SYSTEM, Recorder, who

from tests.support.oracles.grants import GrantWorld, set_rank
from vfs.models import Entry
from vfs.paths import Path
from vfs.storage.backends.database import DatabaseStorage, seams
from vfs.storage.backends.database import engine as engine_module
from vfs.storage.backends.database.dialects import SQLITE
from vfs.storage.backends.database.rights import resolve_authority
from vfs.storage.grants import LEVEL_RANK, GrantRow

HERE = DATA


async def main() -> None:
    rows, cap = int(sys.argv[2]), int(sys.argv[3])
    deeper = int(sys.argv[4]) if len(sys.argv) > 4 else 0
    profile = replace(SQLITE, relabel_rows=cap)
    engine_module.profile_for = lambda name: profile  # the suite's monkeypatch idiom, by hand
    path = os.path.join(HERE, f"relabel-{rows}-{deeper}.sqlite")
    fresh = not os.path.exists(path)
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{path}", posture="read")
    try:
        width = max(1, deeper)
        if fresh:
            files = [Entry(path=Path(f"/big/d{i % width:05}/f{i:06}.md"), content="x") for i in range(rows)]
            for k in range(0, len(files), 10_000):
                assert (await storage.write(entries=files[k : k + 10_000], parents=True, authority=SYSTEM)).success
            for i in range(deeper):
                assert (await storage.posture(path=Path(f"/big/d{i:05}"), posture="read", authority=SYSTEM)).success
            granted = await storage.grant(path=Path("/big/d00000"), principal="bob", level="read", authority=SYSTEM)
            assert granted.success
        rec = Recorder(storage)
        seen: list[dict] = []
        world_rows = [GrantRow("*", "/", "read"), GrantRow("bob", "/big/d00000", "read")]
        world_rows += [GrantRow("*", f"/big/d{i:05}", "read") for i in range(deeper)]
        target = "none"
        after = GrantWorld([*world_rows, GrantRow("*", "/big", target)])

        async def midway() -> None:
            rec.armed = False
            for name in ("ann", "bob"):
                listed = await storage.glob(patterns=("/big/**",), authority=who(name))
                names = {str(o.path) for o in listed.observations}
                host = storage._host
                async with host.session_factory() as session:
                    res = await resolve_authority(
                        session, host.tables, host.profile, host.membership_budget, who(name), None
                    )
                rights = res.at("list")
                expected = {
                    p for p in names | set(all_paths) if set_rank(after, (name,), p) >= LEVEL_RANK["list"]
                }
                seen.append(
                    {
                        "caller": name,
                        "named": len(names),
                        "oracle": len(expected),
                        "agree": names == expected,
                        "holes": len(rights.holes),
                        "hole_pieces": len(rights.ranges().holes.points) + len(rights.ranges().holes.opens),
                    }
                )
            rec.armed = True

        all_paths = [f"/big/d{i % width:05}/f{i:06}.md" for i in range(rows)]
        all_paths += [f"/big/d{i:05}" for i in range(width)] + ["/big"]
        with seams.installed("relabel:after-chunk", midway):
            result, stmts = await rec.run(storage.posture(path=Path("/big"), posture=target, authority=SYSTEM))
        assert result.success, result.errors
        relabel = (result.model_extra or {}).get("relabel")
        begins = sum(1 for s, _, _ in stmts if s.strip().upper().startswith("BEGIN"))
        updates = [(s, b) for s, b, _ in stmts if s.lstrip().upper().startswith("UPDATE VFS_ENTRIES")]
        print(f"rows={rows} relabel_rows={cap} deeper={deeper}")
        print(f"  verb relabel record: {relabel}")
        print(f"  ceil(rows/relabel_rows) = {math.ceil(rows / cap)}; ceil((rows+dirs)/relabel_rows) = "
              f"{math.ceil((rows + width + 1) / cap)}")
        print(f"  BEGIN statements={begins} entry UPDATE statements={len(updates)} max update binds="
              f"{max((b for _, b in updates), default=0)} all statements={len(stmts)}")
        print(f"  midway reads: {len(seen)} checks, all agree={all(s['agree'] for s in seen)}")
        for s in seen[:4]:
            print(f"    {s}")
        print(f"    ... max hole pieces seen midway: {max((s['hole_pieces'] for s in seen), default=0)}")
    finally:
        await storage.close()


asyncio.run(main())
