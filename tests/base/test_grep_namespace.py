"""Namespace-coordinate grep over real storages — the placement-invariance law.

Grep's analog of the glob namespace battery: the same logical tree
answers the same call identically whether a subtree is plain
directories or a mount, with scoping and the glob channels crossing the
seam as composed pattern text.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.support.base_doubles import RecorderStorage
from vfs.base import VirtualFileSystem
from vfs.models import Observation
from vfs.paths import Path
from vfs.results import VFSErrorKind
from vfs.storage.backends.memory import InMemoryStorage

# The demo tree: needle sits at every level; decoy never matches.
TREE = (("/notes.txt", "needle root"), ("/data/a.txt", "needle a"), ("/data/deep/b.py", "needle b"))


async def _plain_world() -> VirtualFileSystem:
    fs = VirtualFileSystem(storage=InMemoryStorage())
    for path, content in TREE:
        await fs.write(path=path, content=content, parents=True)
    return fs


async def _mounted_world() -> VirtualFileSystem:
    fs = VirtualFileSystem(storage=InMemoryStorage())
    await fs.write(path="/notes.txt", content="needle root")
    await fs.add_mount(InMemoryStorage(), "/data")
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


async def test_metachar_roots_scope_grep_to_their_own_subtree() -> None:
    # Roots are paths, never glob syntax — including the find-operand
    # rule, where the root's own path rides the batch as a literal.
    for fs in (await _plain_world(), await _mounted_world()):
        await fs.write(path="/data/[x]/n.txt", content="needle bracket", parents=True)
        await fs.write(path="/data/x/n.txt", content="needle sibling", parents=True)
        scoped = await fs.grep("needle", paths=("/data/[x]",))
        assert scoped.success is True
        assert scoped.paths == ("/data/[x]/n.txt",)
        operand = await fs.grep("needle", paths=("/data/[x]/n.txt",))
        assert operand.paths == ("/data/[x]/n.txt",)


async def test_defective_globs_refuse_before_any_dispatch() -> None:
    fs = VirtualFileSystem(storage=InMemoryStorage())
    channels: tuple[dict[str, Any], ...] = ({"globs": ("a**b",)}, {"globs_not": ("x/",)})
    for channel in channels:
        result = await fs.grep("needle", **channel)
        assert result.success is False
        assert result.errors[0].kind is VFSErrorKind.invalid


async def test_unscoped_glob_channels_cross_the_seam_composed() -> None:
    # Name-arm filters broadcast verbatim; path-arm filters residuate
    # into entry coordinates; exclusions ride the same composition.
    fs = VirtualFileSystem(storage=InMemoryStorage())
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
    fs = VirtualFileSystem(storage=InMemoryStorage())
    recorder = RecorderStorage()
    await fs.add_mount(recorder, "/m")
    result = await fs.grep("needle", globs=("/elsewhere/**",))
    assert result.success is True
    assert recorder.calls == []
    assert result.errors == []


async def test_ten_thousand_roots_stay_two_calls() -> None:
    # The ETL scale row: contract-scale root batches reach storage as
    # exactly one grep call and one probe call — every root contributes
    # its subtree member and its literal to the composed globs batch.
    fs = VirtualFileSystem(storage=InMemoryStorage())
    data = RecorderStorage()
    await fs.add_mount(data, "/data")
    await fs.grep("needle", paths=tuple(f"/data/part{i:05}" for i in range(10_000)))
    assert [op for op, _ in data.calls] == ["stat", "grep"]
    [grep_call] = [kw for op, kw in data.calls if op == "grep"]
    assert len(grep_call["globs"]) == 20_000
    [probe] = [kw for op, kw in data.calls if op == "stat"]
    assert len(probe["observations"]) == 10_000


async def test_capability_skips_survive_only_where_the_globs_reach() -> None:
    fs = VirtualFileSystem(storage=InMemoryStorage())
    await fs.add_mount(RecorderStorage(caps=frozenset({"read"})), "/thin")
    reached = await fs.grep("needle")
    assert [e.path for e in reached.errors] == ["/thin"]
    unreached = await fs.grep("needle", globs=("/elsewhere/**",))
    assert unreached.errors == []


# ----------------------------------------------------------------------
# Chaining — observations are rows in hand, filtered without dispatch
# ----------------------------------------------------------------------


async def test_chained_grep_matches_held_content_without_storage() -> None:
    # Pure filter posture: the rows' paths exist nowhere in storage,
    # and content in hand still matches — no call, no assertion.
    fs = VirtualFileSystem(storage=InMemoryStorage())
    rows = [
        Observation(path=Path("/a.txt"), kind="file", content="a needle here"),
        Observation(path=Path("/b.txt"), kind="file", content="nothing"),
    ]
    result = await fs.grep("needle", observations=rows)
    assert result.success is True
    assert [str(o.path) for o in result.observations] == ["/a.txt"]
    [hit] = result.observations
    assert hit.matches is not None


async def test_chained_grep_fetches_absent_content_and_errors_loudly() -> None:
    fs = await _plain_world()
    rows = [Observation(path=Path("/data/a.txt"), kind="file"), Observation(path=Path("/ghost.txt"), kind="file")]
    result = await fs.grep("needle", observations=rows)
    assert result.success is False
    assert [str(o.path) for o in result.observations] == ["/data/a.txt"]
    assert [e.kind for e in result.errors] == [VFSErrorKind.not_found]


async def test_chained_grep_skips_contentless_kinds_silently() -> None:
    # A directory row is a filter non-match, never an error and never
    # a fetch.
    fs = await _plain_world()
    rows = [Observation(path=Path("/data"), kind="directory"), Observation(path=Path("/data/a.txt"), kind="file")]
    result = await fs.grep("needle", observations=rows)
    assert result.success is True
    assert [str(o.path) for o in result.observations] == ["/data/a.txt"]


async def test_chained_grep_applies_the_glob_and_ext_gates_in_memory() -> None:
    fs = VirtualFileSystem(storage=InMemoryStorage())
    rows = [
        Observation(path=Path("/x/a.py"), kind="file", content="needle"),
        Observation(path=Path("/x/b.txt"), kind="file", content="needle"),
    ]
    by_glob = await fs.grep("needle", observations=rows, globs=("*.py",))
    assert [str(o.path) for o in by_glob.observations] == ["/x/a.py"]
    by_ext = await fs.grep("needle", observations=rows, ext_not=("py",))
    assert [str(o.path) for o in by_ext.observations] == ["/x/b.txt"]


async def test_chained_grep_ext_members_normalize_dots_and_case() -> None:
    fs = VirtualFileSystem(storage=InMemoryStorage())
    rows = [
        Observation(path=Path("/x/a.py"), kind="file", content="needle"),
        Observation(path=Path("/x/b.txt"), kind="file", content="needle"),
    ]
    dotted = await fs.grep("needle", observations=rows, ext=(".PY",))
    assert [str(o.path) for o in dotted.observations] == ["/x/a.py"]
    dropped = await fs.grep("needle", observations=rows, ext_not=(".PY",))
    assert [str(o.path) for o in dropped.observations] == ["/x/b.txt"]


async def test_chained_grep_never_refuses_on_indexability() -> None:
    # The index tier is not involved: a pattern with no indexable
    # literal matches rows in hand without allow_scan.
    fs = VirtualFileSystem(storage=InMemoryStorage())
    rows = [Observation(path=Path("/a.txt"), kind="file", content="alpha")]
    result = await fs.grep(".*", observations=rows)
    assert result.success is True
    assert [str(o.path) for o in result.observations] == ["/a.txt"]


async def test_chained_grep_never_hides_meta_rows_in_hand() -> None:
    fs = VirtualFileSystem(storage=InMemoryStorage())
    rows = [Observation(path=Path("/.vfs/state/s.txt"), kind="file", content="needle hidden")]
    result = await fs.grep("needle", observations=rows)
    assert [str(o.path) for o in result.observations] == ["/.vfs/state/s.txt"]


async def test_chained_grep_attaches_fetched_content_only_when_projected() -> None:
    fs = await _plain_world()
    rows = [Observation(path=Path("/data/a.txt"), kind="file")]
    bare = await fs.grep("needle", observations=rows)
    assert bare.observations[0].content is None
    projected = await fs.grep("needle", observations=rows, columns=frozenset({"content"}))
    assert projected.observations[0].content == "needle a"


async def test_chained_grep_output_modes_shape_the_held_row() -> None:
    # files mode strips content even when held; count mode reports the
    # hit count on score — same contract as the storage tiers.
    fs = VirtualFileSystem(storage=InMemoryStorage())
    rows = [Observation(path=Path("/a.txt"), kind="file", content="needle\nplain\nneedle")]
    files = await fs.grep("needle", observations=rows, output_mode="files")
    assert files.observations[0].content is None
    assert files.observations[0].matches is None
    counted = await fs.grep("needle", observations=rows, output_mode="count")
    assert counted.observations[0].score == 2.0
