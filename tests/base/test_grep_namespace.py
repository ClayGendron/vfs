"""Namespace-coordinate grep over real storages — the placement-invariance law.

Grep's analog of the glob namespace battery: the same logical tree
answers the same call identically whether a subtree is plain
directories or a mount, with scoping and the glob channels crossing the
seam as composed pattern text. The backends declare grep through a
test-local subclass until the capability flip lands; the rows
themselves are already the durable contract.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.support.base_doubles import RecorderStorage
from vfs.base import VirtualFileSystem
from vfs.ops import Op
from vfs.results import VFSErrorKind
from vfs.storage.backends.memory import InMemoryStorage

# The demo tree: needle sits at every level; decoy never matches.
TREE = (("/notes.txt", "needle root"), ("/data/a.txt", "needle a"), ("/data/deep/b.py", "needle b"))


class _GrepMemory(InMemoryStorage):
    """Memory backend declaring grep ahead of the capability flip."""

    def capabilities(self) -> frozenset[Op]:
        return super().capabilities() | frozenset[Op]({"grep"})


async def _plain_world() -> VirtualFileSystem:
    fs = VirtualFileSystem(storage=_GrepMemory())
    for path, content in TREE:
        await fs.write(path=path, content=content, parents=True)
    return fs


async def _mounted_world() -> VirtualFileSystem:
    fs = VirtualFileSystem(storage=_GrepMemory())
    await fs.write(path="/notes.txt", content="needle root")
    await fs.add_mount(_GrepMemory(), "/data")
    await fs.write(path="/data/a.txt", content="needle a")
    await fs.write(path="/data/deep/b.py", content="needle b", parents=True)
    return fs


INVARIANCE_BATTERY: tuple[dict[str, Any], ...] = (
    {},  # unscoped, unfiltered
    {"paths": ("/data",)},  # scope root at the mount point
    {"paths": ("/data/deep",)},  # scope root inside the mount
    {"paths": ("/data/a.txt", "/notes.txt")},  # file operands
    {"globs": ("*.txt",)},  # name-arm filter
    {"globs": ("/data/**",)},  # path-arm filter across the seam
    {"paths": ("/data",), "globs": ("*.py",)},  # scope with filter
    {"globs_not": ("*.py",)},  # exclusion channel
    {"paths": ("/data",), "globs_not": ("deep/**",)},  # composed exclusion
)


@pytest.mark.parametrize("kwargs", INVARIANCE_BATTERY)
async def test_mount_placement_is_invisible_to_grep(kwargs: dict[str, Any]) -> None:
    plain = await (await _plain_world()).grep("needle", **kwargs)
    mounted = await (await _mounted_world()).grep("needle", **kwargs)
    assert plain.success is True and mounted.success is True
    assert sorted(plain.paths) == sorted(mounted.paths)


async def test_scoped_grep_reaches_across_the_seam() -> None:
    fs = await _mounted_world()
    result = await fs.grep("needle", paths=("/data",))
    assert sorted(result.paths) == ["/data/a.txt", "/data/deep/b.py"]


async def test_a_file_operand_is_grepped_itself() -> None:
    # find parity: the operand's own content joins the scan; a glob
    # filter the operand fails drops it as clean success.
    fs = await _mounted_world()
    hit = await fs.grep("needle", paths=("/data/a.txt",))
    assert hit.paths == ("/data/a.txt",)
    miss = await fs.grep("needle", paths=("/data/a.txt",), globs=("*.py",))
    assert miss.success is True and miss.paths == ()


async def test_missing_roots_stay_loud_per_root_assertions() -> None:
    fs = await _mounted_world()
    result = await fs.grep("needle", paths=("/data", "/data/nope"))
    assert result.success is False
    assert [(e.kind, e.path) for e in result.failures] == [(VFSErrorKind.not_found, "/data/nope")]
    assert sorted(result.paths) == ["/data/a.txt", "/data/deep/b.py"]


async def test_root_order_does_not_change_the_answer() -> None:
    fs = await _mounted_world()
    forward = await fs.grep("needle", paths=("/data", "/missing"))
    reverse = await fs.grep("needle", paths=("/missing", "/data"))
    assert sorted(forward.paths) == sorted(reverse.paths)
    assert forward.success is False and reverse.success is False
    assert [(e.kind, e.path) for e in forward.failures] == [(e.kind, e.path) for e in reverse.failures]


async def test_defective_globs_refuse_before_any_dispatch() -> None:
    fs = VirtualFileSystem(storage=_GrepMemory())
    channels: tuple[dict[str, Any], ...] = ({"globs": ("a**b",)}, {"globs_not": ("x/",)})
    for channel in channels:
        result = await fs.grep("needle", **channel)
        assert result.success is False
        assert result.errors[0].kind is VFSErrorKind.invalid


async def test_unscoped_glob_channels_cross_the_seam_composed() -> None:
    # Name-arm filters broadcast verbatim; path-arm filters residuate
    # into entry coordinates; exclusions ride the same composition.
    fs = VirtualFileSystem(storage=_GrepMemory())
    recorder = RecorderStorage()
    await fs.add_mount(recorder, "/m")
    await fs.grep("needle", globs=("*.py", "/m/src/**"), globs_not=("*.log",))
    [(op, kwargs)] = recorder.calls
    assert op == "grep"
    assert kwargs["globs"] == ("*.py", "/src/**")
    assert kwargs["globs_not"] == ("*.log",)
    assert "paths" not in kwargs


async def test_a_dead_admission_set_is_routing_not_a_skip() -> None:
    # The path-arm glob cannot reach /m: the entry is simply not
    # dispatched, with no record minted — dead residuals are routing.
    fs = VirtualFileSystem(storage=_GrepMemory())
    recorder = RecorderStorage()
    await fs.add_mount(recorder, "/m")
    result = await fs.grep("needle", globs=("/elsewhere/**",))
    assert result.success is True
    assert recorder.calls == []
    assert result.errors == []


async def test_capability_skips_survive_only_where_the_globs_reach() -> None:
    fs = VirtualFileSystem(storage=_GrepMemory())
    await fs.add_mount(RecorderStorage(caps=frozenset({"read"})), "/thin")
    reached = await fs.grep("needle")
    assert [e.path for e in reached.errors] == ["/thin"]
    unreached = await fs.grep("needle", globs=("/elsewhere/**",))
    assert unreached.errors == []
