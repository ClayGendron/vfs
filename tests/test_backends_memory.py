"""The in-memory storage's capability pin and single-connection
concurrency contract.

One ``StaticPool`` connection serves the whole storage, so the engine
host serializes sessions: overlapping callers queue, never collide,
and the database survives a cold-start storm intact.
"""

from __future__ import annotations

import asyncio

from vfs.models import Entry
from vfs.paths import Path
from vfs.storage.backends.memory import InMemoryStorage


def test_capabilities_pin_the_landed_set() -> None:
    # A drift alarm in both directions: when grep or mkedge land, this
    # pin must move together with the backend's declaration.
    assert InMemoryStorage().capabilities() == frozenset(
        {"read", "stat", "ls", "tree", "glob", "write", "edit", "mkdir", "delete", "restore", "sweep", "move", "copy"}
    )


class TestInMemoryConcurrency:
    async def test_overlapping_writes_on_a_warm_storage_both_succeed(self) -> None:
        storage = InMemoryStorage()
        assert (await storage.write(entries=[Entry(path=Path("/warm.txt"), content="x")])).success
        first, second = await asyncio.gather(
            storage.write(entries=[Entry(path=Path("/a.txt"), content="x")]),
            storage.write(entries=[Entry(path=Path("/b.txt"), content="x")]),
        )
        assert first.success, first.errors
        assert second.success, second.errors
        await storage.close()

    async def test_cold_start_write_storm_all_succeed_and_data_survives(self) -> None:
        # The review's storm: 30 concurrent writes on a fresh instance
        # hung the loop or wiped the database before serialization.
        storage = InMemoryStorage()
        results = await asyncio.gather(
            *(storage.write(entries=[Entry(path=Path(f"/f{i:02}.txt"), content="x")]) for i in range(30))
        )
        assert all(result.success for result in results)
        listing = await storage.ls(path=Path("/"))
        assert listing.success
        assert len(listing.observations) == 30
        await storage.close()

    async def test_reads_overlap_writes_cleanly(self) -> None:
        storage = InMemoryStorage()
        assert (await storage.write(entries=[Entry(path=Path("/r.txt"), content="body")])).success
        read, write = await asyncio.gather(
            storage.read(path=Path("/r.txt")),
            storage.write(entries=[Entry(path=Path("/w.txt"), content="x")]),
        )
        assert read.success and write.success
        assert read.observations[0].content == "body"
        await storage.close()
