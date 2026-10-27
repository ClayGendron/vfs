"""Object constructions per read/stat/ls on the hot path (study 05, Q2).

Counts, never times: wraps the constructors of the envelope's models
(Observation, Result, ResultError, Entry, Path) and the pydantic copy
and validate doors, then runs one read, one stat and listings of 1, 100
and 10,000 rows. Also reports ``sys.getallocatedblocks`` deltas and the
tracemalloc block count for each call. Monkeypatching happens in this
script only; nothing in src/ changes.

Run: uv run python context/research/studies/2026-10-23-filesystem-shaped-api/experiments/s05/allocations.py
"""

from __future__ import annotations

import asyncio
import gc
import sys
import tracemalloc
from collections import Counter
from pathlib import Path as FsPath

from pydantic import BaseModel

from vfs.authority import Authority
from vfs.base import VirtualFileSystem
from vfs.models import Entry, Observation
from vfs.paths import Path
from vfs.results import Result, ResultError
from vfs.storage.backends.memory import InMemoryStorage

OUT = FsPath(__file__).with_suffix(".out")
COUNTS: Counter[str] = Counter()


def count_init(cls: type, label: str) -> None:
    original = cls.__init__

    def wrapped(self, *args, **kwargs):  # noqa: ANN001, ANN202
        COUNTS[label] += 1
        return original(self, *args, **kwargs)

    cls.__init__ = wrapped  # type: ignore[method-assign]


def count_new(cls: type, label: str) -> None:
    original = cls.__new__

    def wrapped(klass, *args, **kwargs):  # noqa: ANN001, ANN202
        COUNTS[label] += 1
        return original(klass, *args, **kwargs)

    cls.__new__ = staticmethod(wrapped)  # type: ignore[method-assign]


def count_method(cls: type, name: str, label: str) -> None:
    original = getattr(cls, name)

    def wrapped(self, *args, **kwargs):  # noqa: ANN001, ANN202
        COUNTS[label] += 1
        return original(self, *args, **kwargs)

    setattr(cls, name, wrapped)


count_init(Observation, "Observation()")
count_init(Result, "Result()")
count_init(ResultError, "ResultError()")
count_init(Entry, "Entry()")
count_new(Path, "Path()")
count_method(BaseModel, "model_copy", "model_copy")

_orig_validate = BaseModel.model_validate.__func__  # type: ignore[attr-defined]


def _validate(cls, *args, **kwargs):  # noqa: ANN001, ANN202
    COUNTS[f"{cls.__name__}.model_validate"] += 1
    return _orig_validate(cls, *args, **kwargs)


BaseModel.model_validate = classmethod(_validate)  # type: ignore[method-assign]


async def main() -> None:
    storage = InMemoryStorage()
    fs = VirtualFileSystem(storage=storage)
    system = Authority.system()
    await storage.first_touch()
    body = ("x" * 63 + "\n") * 16  # 1 KiB text body
    await fs.write(path="/one/f.md", content=body, parents=True, authority=system)
    await fs.write([Entry(path=f"/hundred/f{i:03}.md", content="b") for i in range(100)], parents=True, authority=system)
    await fs.write([Entry(path=f"/big/f{i:05}.md", content="b") for i in range(10_000)], parents=True, authority=system)

    lines: list[str] = []

    async def measure(label: str, make) -> None:  # noqa: ANN001
        await make()  # warm: caches, codegen, first-call effects
        gc.collect()
        COUNTS.clear()
        blocks_before = sys.getallocatedblocks()
        tracemalloc.start()
        result = await make()
        snapshot = tracemalloc.take_snapshot()
        tracemalloc.stop()
        blocks_after = sys.getallocatedblocks()
        traced_blocks = sum(stat.count for stat in snapshot.statistics("filename"))
        rows = len(result.observations)
        lines.append(
            f"{label}: rows={rows} getallocatedblocks delta={blocks_after - blocks_before} "
            f"tracemalloc live blocks at return={traced_blocks}"
        )
        for name, n in sorted(COUNTS.items()):
            per_row = f" ({n / rows:.2f}/row)" if rows else ""
            lines.append(f"    {n:6d}  {name}{per_row}")
        del result

    await measure("read(/one/f.md)", lambda: fs.read("/one/f.md", authority=system))
    await measure("stat(/one/f.md)", lambda: fs.stat("/one/f.md", authority=system))
    await measure("ls(/one)  [1 row]", lambda: fs.ls("/one", authority=system))
    await measure("ls(/hundred)  [100 rows]", lambda: fs.ls("/hundred", authority=system))
    await measure("ls(/big)  [10,000 rows]", lambda: fs.ls("/big", authority=system))
    await measure("stat(/one/f.md) through a session", lambda: fs.session(system).stat("/one/f.md"))
    await measure("read(/one/f.md).to_payload()", lambda: _payload(fs, system))

    await fs.close()
    OUT.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


async def _payload(fs: VirtualFileSystem, who: Authority) -> Result:
    result = await fs.read("/one/f.md", authority=who)
    result.to_payload()
    return result


if __name__ == "__main__":
    asyncio.run(main())
