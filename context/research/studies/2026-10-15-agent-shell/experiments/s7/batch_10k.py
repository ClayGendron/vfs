"""S7 experiment 4: a 10,000-file write in ONE call through a Session.

Grounds the background-job question: is a long batch something the
caller waits on (one Result, all rows) or something that needs a job
handle? Reports row counts and elapsed wall-clock -- a memo number,
never a test assertion.
"""

from __future__ import annotations

import asyncio
import time

from vfs.authority import Authority, Principal
from vfs.base import VirtualFileSystem
from vfs.models import Entry
from vfs.paths import Path
from vfs.storage.backends.memory import InMemoryStorage

ALICE = Authority.of(Principal("alice"))
N = 10_000


async def main() -> None:
    fs = VirtualFileSystem(storage=InMemoryStorage())
    s = fs.session(ALICE)
    entries = [Entry(path=Path(f"/corpus/d{i % 100}/f{i}.md"), content=f"doc {i} alpha beta") for i in range(N)]
    t0 = time.perf_counter()
    result = await s.write(entries, parents=True)
    t1 = time.perf_counter()
    print(f"write {N} entries in one call: success={result.success} rows={len(result.observations)} "
          f"errors={len(result.errors)} elapsed={t1 - t0:.2f}s")
    t0 = time.perf_counter()
    hits = await s.grep("alpha", paths=("/corpus",), max_count=5, allow_scan=True)
    t1 = time.perf_counter()
    print(f"grep over the corpus, max_count=5: rows={len(hits.observations)} elapsed={t1 - t0:.2f}s")
    t0 = time.perf_counter()
    found = await s.glob("**/*.md", paths=("/corpus",))
    t1 = time.perf_counter()
    print(f"glob **/*.md: rows={len(found.observations)} elapsed={t1 - t0:.2f}s")
    await fs.close()


if __name__ == "__main__":
    asyncio.run(main())
