"""Namespace-coordinate glob over real storages — the placement-invariance law.

The dispatch tests prove which mounts receive which patterns with
doubles; these rows prove the *results* over real entries: the same
logical tree returns the same rows for the same call whether a subtree
is plain directories or a mount. Row sets are compared sorted — row
*order* is the fan-out merge order (entries in table order), a
pre-existing contract placement does change.
"""

from __future__ import annotations

import pytest

from tests.support.base_doubles import RecorderStorage
from vfs.base import VirtualFileSystem
from vfs.results import VFSErrorKind
from vfs.storage.backends.memory import InMemoryStorage

# The demo tree: /notes.txt at the root, a.txt and deep/b.txt under /data.
TREE = (("/notes.txt", "root"), ("/data/a.txt", "a"), ("/data/deep/b.txt", "b"))

INVARIANCE_BATTERY = (
    "*.txt",  # name arm
    "b.txt",  # name arm, mount-interior row
    "/data/*.txt",  # anchored, direct children
    "/data/**/*.txt",  # ** spanning the seam
    "**/*.txt",  # explicit any-depth
    "*/a.txt",  # depth pin across the seam
    "**/**/*.txt",  # adjacent ** canonicalizes; the derivative stays exact
    "/docs/*.md",  # dead prefix: nothing anywhere
    "/d*",  # the bind-point / plain-directory row itself
)


async def _plain_world() -> VirtualFileSystem:
    fs = VirtualFileSystem()
    for path, content in TREE:
        await fs.write(path=path, content=content, parents=True)
    return fs


async def _mounted_world() -> VirtualFileSystem:
    fs = VirtualFileSystem()
    await fs.write(path="/notes.txt", content="root")
    await fs.add_mount(InMemoryStorage(), "/data")
    await fs.write(path="/data/a.txt", content="a")
    await fs.write(path="/data/deep/b.txt", content="b", parents=True)
    return fs


async def test_the_headline_repro_flips() -> None:
    # The motivating bug: these two calls returned empty success while
    # the rows sat in the /data mount.
    fs = await _mounted_world()
    both = await fs.glob("/data/**/*.txt")
    assert sorted(both.paths) == ["/data/a.txt", "/data/deep/b.txt"]
    direct = await fs.glob("/data/*.txt")
    assert direct.paths == ("/data/a.txt",)


@pytest.mark.parametrize("pattern", INVARIANCE_BATTERY)
async def test_mount_placement_is_invisible_to_patterns(pattern: str) -> None:
    plain = await (await _plain_world()).glob(pattern)
    mounted = await (await _mounted_world()).glob(pattern)
    assert plain.success is True and mounted.success is True
    assert sorted(plain.paths) == sorted(mounted.paths)


async def test_scoped_patterns_read_root_relative() -> None:
    # Three spellings of the same question — including the deliberate
    # contract change: a leading slash anchors at the scope root.
    fs = await _mounted_world()
    absolute = await fs.glob("/data/deep/*.txt")
    scoped = await fs.glob("deep/*.txt", paths=("/data",))
    anchored = await fs.glob("/deep/*.txt", paths=("/data",))
    assert absolute.paths == scoped.paths == anchored.paths == ("/data/deep/b.txt",)


async def test_double_star_spans_a_nested_mount_boundary() -> None:
    fs = await _mounted_world()
    await fs.add_mount(InMemoryStorage(), "/data/api")
    await fs.write(path="/data/api/y.txt", content="y")
    spanning = await fs.glob("/data/**/*.txt")
    assert sorted(spanning.paths) == ["/data/a.txt", "/data/api/y.txt", "/data/deep/b.txt"]


async def test_multi_residual_rows_arrive_exactly_once() -> None:
    # ** either spans the nested bind segment or stops before it: two
    # dispatches to /data/api whose overlap must merge to one row.
    fs = await _mounted_world()
    await fs.add_mount(InMemoryStorage(), "/data/api")
    await fs.write(path="/data/api/y.txt", content="y")
    result = await fs.glob("/data/**/api/*.txt")
    assert result.paths == ("/data/api/y.txt",)


async def test_bind_point_row_is_served_by_the_parent() -> None:
    # /d* exhausts at the bind point: the match is the parent's stored
    # mount-point directory, and the mount itself is never dispatched.
    fs = VirtualFileSystem()
    recorder = RecorderStorage()
    await fs.add_mount(recorder, "/data")
    result = await fs.glob("/d*")
    assert result.paths == ("/data",)
    assert recorder.calls == []


async def test_multiple_anchors_into_one_entry_all_dispatch() -> None:
    # Every scope root must reach its dispatch: a regression that drops
    # anchors after the first per entry loses rows, not duplicates them.
    plain = await (await _plain_world()).glob("**/*.txt", paths=("/data", "/data/deep"))
    mounted = await (await _mounted_world()).glob("**/*.txt", paths=("/data", "/data/deep"))
    assert sorted(plain.paths) == sorted(mounted.paths) == ["/data/a.txt", "/data/deep/b.txt"]
    assert len(mounted.paths) == len(set(mounted.paths))


async def test_max_count_returns_a_merge_order_prefix_of_the_set() -> None:
    # The invariance law binds the match *set*; a cap keeps merge order,
    # which mount layout can reorder — pinned as prefix-of-set semantics.
    for world in (await _plain_world(), await _mounted_world()):
        full = await world.glob("**/*.txt")
        capped = await world.glob("**/*.txt", max_count=2)
        assert len(capped.paths) == 2
        assert set(capped.paths) <= set(full.paths)


async def test_name_arm_root_covered_by_a_region_keeps_its_assertion() -> None:
    # A bogus root fails loud even when a sibling region covers its entry:
    # subsumption must not drop the find-operand assertion with the dispatch.
    fs = await _mounted_world()
    await fs.add_mount(InMemoryStorage(), "/data/api")
    await fs.write(path="/data/api/sub/z.txt", content="z", parents=True)
    missing = await fs.glob("*.txt", paths=("/data", "/data/api/nope"))
    assert missing.success is False
    assert missing.errors[0].kind is VFSErrorKind.not_found
    both = await fs.glob("*.txt", paths=("/data", "/data/api/sub"))
    assert both.success is True
    assert sorted(both.paths) == ["/data/a.txt", "/data/api/sub/z.txt", "/data/deep/b.txt"]
    assert len(both.paths) == len(set(both.paths))  # both arms dispatch; the merge dedups


async def test_roots_stay_assertions() -> None:
    # A pattern matching nothing is clean empty success; a missing root
    # is a loud per-anchor error; a file anchor is matched itself.
    fs = await _mounted_world()
    empty = await fs.glob("/data/nothing/*.rs")
    assert empty.success is True and empty.paths == ()
    missing = await fs.glob("**/*.txt", paths=("/missing",))
    assert missing.success is False
    assert missing.errors[0].kind is VFSErrorKind.not_found
    hit = await fs.glob("*.txt", paths=("/notes.txt",))
    assert hit.paths == ("/notes.txt",)
    miss = await fs.glob("*.py", paths=("/notes.txt",))
    assert miss.success is True and miss.paths == ()
