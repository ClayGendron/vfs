"""Spec 102 Q1/Q4 baseline: profile the current scattered-delete arm.

For each engine in the environment and each batch size, write the corpus
in one batch, then delete every scattered target in one call while a
rival handle issues a topology verb (a move) 0.5 s later — the rival's
elapsed is the lock-hold measurement. Per-statement-shape timing comes
off the cursor events.

    uv run python context/research/studies/2026-08-25-set-based-topology-statements/profile_scattered_delete.py 1000 10000
"""

from __future__ import annotations

import asyncio
import os
import sys
import time

from common import ENGINE_ENV, StatementProfile, minted, save, scattered_corpus, sibling

from vfs.models import Observation
from vfs.paths import Path
from vfs.storage import ResolvedPair


async def run(engine: str, url: str, size: int, dirs: int) -> dict:
    async with minted(url) as storage:
        entries, targets = scattered_corpus(size, dirs_with_children=dirs)
        t0 = time.perf_counter()
        written = await storage.write(entries=entries, parents=True)
        assert written.success, written.errors[:3]
        write_s = time.perf_counter() - t0
        profile = StatementProfile(storage)
        rival = sibling(url, storage)
        try:
            profile.enabled = True
            t0 = time.perf_counter()
            delete = asyncio.ensure_future(storage.delete(observations=[Observation(path=t) for t in targets]))
            await asyncio.sleep(0.5)
            t_rival = time.perf_counter()
            moved = await rival.move(operations=[ResolvedPair(src=Path("/rival"), dest=Path("/rival2"))])
            rival_s = time.perf_counter() - t_rival
            result = await delete
            delete_s = time.perf_counter() - t0
            profile.enabled = False
        finally:
            await rival.close()
        assert result.success, result.errors[:3]
        assert moved.success, moved.errors[:3]
        payload = {
            "engine": engine,
            "profile": storage._host.profile.name,
            "size": size,
            "directory_targets": dirs,
            "write_seconds": round(write_s, 3),
            "delete_seconds": round(delete_s, 3),
            "rival_move_blocked_seconds": round(rival_s, 3),
            "observations": len(result.observations),
            "statements": profile.report(),
            "statement_total": sum(v["count"] for v in profile.shapes.values()),
        }
        save(f"baseline-{engine}-{size}", payload)
        print(f"{engine} {size}: delete {delete_s:.2f}s, rival blocked {rival_s:.2f}s, statements {payload['statement_total']}")
        return payload


async def main() -> None:
    sizes = [int(a) for a in sys.argv[1:]] or [1000, 10000]
    for engine, env in ENGINE_ENV.items():
        url = os.environ.get(env)
        if not url:
            continue
        for size in sizes:
            await run(engine, url, size, dirs=size // 100)


if __name__ == "__main__":
    asyncio.run(main())
