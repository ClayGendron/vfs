"""What today's code answers in the cases the etag spec's tables leave out, on each engine.

A list of corners. Each prints what the code answers today, so
the spec can state the answer it wants under a required etag or the mark:

1. a ``write`` that expects a version at a path a deleted directory holds;
2. a create-only ``write`` at a path a deleted directory holds;
3. a ``write`` that expects a version beneath a parent that is a file;
4. one ``delete`` without cascade that names a child and then its directory;
5. one ``move`` whose second pair's source is the first pair's destination;
6. one ``edit`` whose observations name one file twice;
7. one batch ``write`` that names one path twice and expects a version there;
8. the row a parent kernel lists for a mount point, and what a ``stat`` of it
   returns: which storage's version the row carries;
9. two rows of one path merged when their versions agree and when they differ;
10. a rename of a file onto itself, and the version it reports.

    VFS_TEST_POSTGRES_URL=postgresql+asyncpg://vfs:vfs@localhost:54320/vfs \
        uv run python agents/2026-11-22-a-row-carries-an-etag-and-a-change-can-require-it/probes/p08_cases_the_spec_does_not_state.py
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from harness import engines, run, storage_on
from vfs.authority import Authority
from vfs.base import AsyncVirtualFileSystem
from vfs.models import Entry, Observation
from vfs.paths import Path
from vfs.results import Result
from vfs.storage.backends.memory import InMemoryStorage

if TYPE_CHECKING:
    from vfs.storage.backends.database import DatabaseStorage

SYSTEM = Authority.system()


def said(result: Result) -> str:
    if result.success:
        return f"ok {[(str(o.path), o.status, o.version) for o in result.observations]}"
    return f"refused {[(str(e.kind), str(e.path), e.data) for e in result.errors]}"


async def one_engine(storage: DatabaseStorage) -> None:
    fs = AsyncVirtualFileSystem(storage=storage)
    await fs.mkdir("/gone", authority=SYSTEM)
    await fs.delete("/gone", authority=SYSTEM)
    print(f"1. write(if_version=1) where a deleted directory is:   {said(await fs.write(path='/gone', content='x', if_version=1, authority=SYSTEM))}")
    print(f"2. write(if_absent=True) where a deleted directory is: {said(await fs.write(path='/gone', content='x', if_absent=True, authority=SYSTEM))}")
    await fs.write(path="/file", content="a file", authority=SYSTEM)
    print(f"3. write(if_version=1) beneath a file:                 {said(await fs.write(path='/file/child', content='x', if_version=1, authority=SYSTEM))}")

    await fs.mkdir("/d", authority=SYSTEM)
    await fs.write(path="/d/a", content="1", authority=SYSTEM)
    rows = [Observation(path=Path("/d/a")), Observation(path=Path("/d"))]
    print(f"4. delete([/d/a, /d], cascade=False):                  {said(await fs.delete(observations=rows, cascade=False, authority=SYSTEM))}")

    await fs.write(path="/m1", content="1", authority=SYSTEM)
    print(f"5. move([(/m1, /m2), (/m2, /m3)]):                     {said(await fs.move(moves=[('/m1', '/m2'), ('/m2', '/m3')], authority=SYSTEM))}")

    await fs.write(path="/twice", content="aaa", authority=SYSTEM)
    twice = [Observation(path=Path("/twice")), Observation(path=Path("/twice"))]
    print(f"6. edit of one file named twice (a -> b, once each):   {said(await fs.edit(old='a', new='b', observations=twice, authority=SYSTEM))}")

    await fs.write(path="/dup", content="one", authority=SYSTEM)
    entries = [Entry(path=Path("/dup"), content="two"), Entry(path=Path("/dup"), content="three")]
    print(f"7. write of one path twice, if_versions at 1:          {said(await fs.write(entries, if_versions={'/dup': 1}, authority=SYSTEM))}")
    print(f"   the same call again, still expecting 1:             {said(await fs.write(entries, if_versions={'/dup': 1}, authority=SYSTEM))}")

    inner = InMemoryStorage()
    await fs.add_mount(inner, "/mnt")
    await fs.write(path="/mnt/f", content="in the mount", authority=SYSTEM)
    listed = [o for o in (await fs.ls("/", authority=SYSTEM)).observations if str(o.path) == "/mnt"]
    stat = (await fs.stat("/mnt", authority=SYSTEM)).observations
    own_root = (await inner.stat(path=Path("/"))).observations
    print(f"8. ls / shows the mount point as:   {[(str(o.path), o.kind, o.version, sorted(o.populated)) for o in listed]}")
    print(f"   stat /mnt returns:               {[(str(o.path), o.kind, o.version) for o in stat]}")
    print(f"   the mounted storage's own root:  {[(str(o.path), o.kind, o.version) for o in own_root]}")

    def row(version: int) -> Result:
        return Result(ops=("stat",), observations=[Observation(path=Path("/p"), kind="file", version=version)])

    same = row(3) | row(3)
    differ = row(3) | row(4)
    print(f"9. merged, versions agree:  version={same.observations[0].version} masked={'version' in same.observations[0].populated}")
    print(f"   merged, versions differ: version={differ.observations[0].version} masked={'version' in differ.observations[0].populated}")

    await fs.write(path="/self", content="1", authority=SYSTEM)
    print(f"10. move(/self, /self):                                {said(await fs.move('/self', '/self', authority=SYSTEM))}")


async def main() -> None:
    for engine in engines():
        print(f"== {engine}")
        async with storage_on(engine) as (storage, _):
            await one_engine(storage)


if __name__ == "__main__":
    run(main)
