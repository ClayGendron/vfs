"""Namespace-coordinate glob over real storages — the placement-invariance law.

The dispatch tests prove which mounts receive which patterns with
doubles; these rows prove the *results* over real entries: the same
logical tree returns the same rows for the same call whether a subtree
is plain directories or a mount. Row sets are compared sorted — row
*order* is the fan-out merge order (entries in table order), a
pre-existing contract placement does change.
"""

from __future__ import annotations

import asyncio
import gc
import pathlib
import warnings
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from tests.support.base_doubles import BindableStorage, RecorderStorage
from tests.support.loop_ticks import LoopTicker
from tests.support.oracles import glob as oracle
from tests.support.oracles.grants import GrantWorld, everyone_rank
from tests.support.scope_worlds import (
    DIRECTORIES,
    META_DIRECTORY,
    METACHAR_DIRECTORIES,
    NESTED_HOST,
    POSTURE_DIRECTORIES,
    TRASH_ROOTS,
    ShapeCall,
    ShapeWorlds,
    build_world_files,
    open_worlds,
)
from tests.support.shared_builds import build_once, shared_directory
from vfs import base as base_module
from vfs import chain as chain_module
from vfs import deadline as deadline_module
from vfs import fanout as fanout_module
from vfs.authority import EVERYONE_NAME, Authority
from vfs.base import AsyncVirtualFileSystem
from vfs.deadline import Deadline
from vfs.models import Entry, Observation
from vfs.offload import offload_pool
from vfs.paths import Path, address_of
from vfs.pattern_matching import canonical_pattern, composed_pattern
from vfs.pattern_matching import glob as glob_module
from vfs.results import ErrorKind, Result
from vfs.results.kinds import Severity
from vfs.storage.backends.database import reads as reads_module
from vfs.storage.backends.database.addressing import addressed_by
from vfs.storage.backends.memory import InMemoryStorage
from vfs.storage.grants import LEVEL_RANK, GrantRow

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator, Sequence

    from vfs.storage.grants import Posture

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
    "*.{txt,md}",  # brace alternation, name arms
    "/data/{deep,api}/*.txt",  # brace alternation across the seam
    "{/data/deep/*.txt,notes.*}",  # mixed-subject arms: one anchored, one floating
)


async def _plain_world() -> AsyncVirtualFileSystem:
    fs = AsyncVirtualFileSystem()
    for path, content in TREE:
        await fs.write(path=path, content=content, parents=True)
    return fs


async def _mounted_world() -> AsyncVirtualFileSystem:
    fs = AsyncVirtualFileSystem()
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


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def plain_world() -> AsyncIterator[AsyncVirtualFileSystem]:
    """The plain world once per module; the invariance battery only reads it."""
    fs = await _plain_world()
    yield fs
    await fs.close()


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def mounted_world() -> AsyncIterator[AsyncVirtualFileSystem]:
    """The mounted world once per module; the invariance battery only reads it."""
    fs = await _mounted_world()
    yield fs
    await fs.close()


@pytest.mark.asyncio(loop_scope="module")
@pytest.mark.parametrize("pattern", INVARIANCE_BATTERY)
async def test_mount_placement_is_invisible_to_patterns(
    pattern: str, plain_world: AsyncVirtualFileSystem, mounted_world: AsyncVirtualFileSystem
) -> None:
    plain = await plain_world.glob(pattern)
    mounted = await mounted_world.glob(pattern)
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


async def test_a_pattern_that_ends_at_a_mount_point_returns_the_mounted_root() -> None:
    # /d* is used up at the mount point: the match is the root of the mounted storage, which one
    # stat gives, and the mount is asked for no glob.
    fs = AsyncVirtualFileSystem()
    recorder = RecorderStorage()
    await fs.add_mount(recorder, "/data")
    result = await fs.glob("/d*")
    assert result.paths == ("/data",)
    assert recorder.calls == [("stat", {"path": "/", "columns": None})]


async def test_multiple_roots_into_one_entry_all_serve() -> None:
    # Every scope root must reach the batch: a regression that drops
    # roots after the first per entry loses rows, not duplicates them.
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
    assert missing.errors[0].kind is ErrorKind.not_found
    both = await fs.glob("*.txt", paths=("/data", "/data/api/sub"))
    assert both.success is True
    assert sorted(both.paths) == ["/data/a.txt", "/data/api/sub/z.txt", "/data/deep/b.txt"]
    assert len(both.paths) == len(set(both.paths))  # probe and batch overlap; the merge dedups


async def test_scoped_name_arm_still_hits_direct_children() -> None:
    # The float made spatial must lose nothing: root + /**/ + pattern
    # matches direct children because ** spans zero segments.
    for world in (await _plain_world(), await _mounted_world()):
        result = await world.glob("*.txt", paths=("/data",))
        assert sorted(result.paths) == ["/data/a.txt", "/data/deep/b.txt"]


async def test_root_order_does_not_change_the_answer() -> None:
    # The ripgrep multi-root regression class: the same call with roots
    # in both orders returns the same set and the same per-root errors.
    fs = await _mounted_world()
    forward = await fs.glob("*.txt", paths=("/data", "/data/deep", "/missing"))
    reverse = await fs.glob("*.txt", paths=("/missing", "/data/deep", "/data"))
    assert sorted(forward.paths) == sorted(reverse.paths)
    assert forward.success is False and reverse.success is False
    assert [(e.kind, e.path) for e in forward.failures] == [(e.kind, e.path) for e in reverse.failures]


async def test_a_matching_directory_root_row_is_served_from_the_probe() -> None:
    # find parity the anchor channel missed: a directory operand whose
    # own row matches the pattern appears, served by the probe.
    fs = await _mounted_world()
    result = await fs.glob("d*", paths=("/data/deep",))
    assert result.paths == ("/data/deep",)


async def test_roots_stay_assertions() -> None:
    # A pattern matching nothing is clean empty success; a missing root
    # is a loud per-root error; a file root is matched itself.
    fs = await _mounted_world()
    empty = await fs.glob("/data/nothing/*.rs")
    assert empty.success is True and empty.paths == ()
    missing = await fs.glob("**/*.txt", paths=("/missing",))
    assert missing.success is False
    assert missing.errors[0].kind is ErrorKind.not_found
    hit = await fs.glob("*.txt", paths=("/notes.txt",))
    assert hit.paths == ("/notes.txt",)
    miss = await fs.glob("*.py", paths=("/notes.txt",))
    assert miss.success is True and miss.paths == ()


# ----------------------------------------------------------------------
# Metachar roots — a scope root is a path, never glob syntax
# ----------------------------------------------------------------------

METACHAR_ROOT_NAMES = ("[x]", "{a}", "a*b", "c?d", "data [prod]")


async def test_metachar_roots_serve_exactly_their_own_subtree() -> None:
    # The regression class: an unquoted root spliced into pattern text
    # captured siblings ([x] served /x) or refused whole calls ({a}).
    for fs in (await _plain_world(), await _mounted_world()):
        for name in METACHAR_ROOT_NAMES:
            await fs.write(path=f"/data/{name}/hit.txt", content="hit", parents=True)
        await fs.write(path="/data/x/decoy.txt", content="decoy", parents=True)
        await fs.write(path="/data/ab/decoy.txt", content="decoy", parents=True)
        for name in METACHAR_ROOT_NAMES:
            result = await fs.glob("*.txt", paths=(f"/data/{name}",))
            assert result.success is True, (name, result.errors)
            assert result.paths == (f"/data/{name}/hit.txt",), name


async def test_every_root_sees_exactly_its_prefix_subtree() -> None:
    # Property shape: for any legal path p, glob("**", paths=(p,)) is
    # exactly p's subtree — p's own row included, nothing beside it.
    fs = await _plain_world()
    for name in METACHAR_ROOT_NAMES:
        await fs.write(path=f"/m/{name}/deep/d.txt", content="x", parents=True)
    everything = sorted((await fs.glob("**")).paths)
    for root in everything:
        scoped = await fs.glob("**", paths=(root,))
        assert scoped.success is True, root
        expected = [p for p in everything if p == root or p.startswith(root + "/")]
        assert sorted(scoped.paths) == expected, root


# ----------------------------------------------------------------------
# Brace alternation — arms expand at the chokepoint, results union
# ----------------------------------------------------------------------


async def test_brace_arms_union_across_the_namespace() -> None:
    fs = await _mounted_world()
    result = await fs.glob("/data/{a,deep/b}.txt")
    assert sorted(result.paths) == ["/data/a.txt", "/data/deep/b.txt"]


async def test_brace_expansion_past_the_cap_refuses_loudly() -> None:
    fs = await _mounted_world()
    result = await fs.glob("{a,b}{c,d}{e,f}{g,h}{i,j}{k,l}{m,n}")  # 128 arms
    assert result.success is False
    assert result.errors[0].kind == ErrorKind.invalid
    assert "arm cap" in result.errors[0].message


async def test_exclusion_refusals_share_one_label_across_verbs() -> None:
    # One channel, one label: the exclusion channel's refusal vocabulary
    # is verb-independent, minted from GLOB_CHANNEL_LABELS everywhere.
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    globbed = await fs.glob("*", globs_not=("{a",))
    grepped = await fs.grep("x", globs_not=("{a",))
    assert globbed.success is False and grepped.success is False
    for result in (globbed, grepped):
        assert result.errors[0].message.startswith("Invalid: glob exclusion '{a'"), result.errors[0].message


async def test_brace_defect_refuses_naming_the_manufactured_arm() -> None:
    fs = await _mounted_world()
    result = await fs.glob("/data/{deep,}/b.txt")
    assert result.success is False
    assert result.errors[0].kind == ErrorKind.invalid
    assert "'/data//b.txt'" in result.errors[0].message


async def test_grep_glob_channels_expand_braces() -> None:
    # The subject is channel expansion; allow_scan sidesteps the index
    # tier's refusal gate for the short unindexable pattern.
    fs = await _mounted_world()
    result = await fs.grep("a|b|root", globs=("*.{txt,md}",), allow_scan=True)
    assert sorted(result.paths) == ["/data/a.txt", "/data/deep/b.txt", "/notes.txt"]
    excluded = await fs.grep("a|b|root", globs_not=("{notes,b}.*",), allow_scan=True)
    assert excluded.paths == ("/data/a.txt",)


# ----------------------------------------------------------------------
# Exclusion channels and the kind filter — rejection honors every gate
# ----------------------------------------------------------------------


async def test_globs_not_excludes_in_both_worlds() -> None:
    for world in (await _plain_world(), await _mounted_world()):
        by_path = await world.glob("**/*.txt", globs_not=("/data/deep/**",))
        assert sorted(by_path.paths) == ["/data/a.txt", "/notes.txt"]
        by_name = await world.glob("*.txt", globs_not=("{a,b}.txt",))
        assert by_name.paths == ("/notes.txt",)


async def test_scoped_exclusion_composes_under_its_root() -> None:
    # "deep/**" is root-relative: it excludes /data/deep/** under the
    # /data root, exactly as the admission pattern would anchor.
    fs = await _mounted_world()
    result = await fs.glob("**/*.txt", paths=("/data",), globs_not=("deep/**",))
    assert result.paths == ("/data/a.txt",)


async def test_ext_not_drops_extensions_normalized() -> None:
    # ext_not drops only the named extensions — an extensionless row
    # (the directory) is never its business.
    fs = await _mounted_world()
    await fs.write(path="/data/readme.md", content="m")
    result = await fs.glob("/data/*", ext_not=(".TXT",))
    assert sorted(result.paths) == ["/data/deep", "/data/readme.md"]


async def test_kind_filters_files_and_directories() -> None:
    fs = await _mounted_world()
    directories = await fs.glob("**", kind="directory")
    assert sorted(directories.paths) == ["/data", "/data/deep"]
    files = await fs.glob("/data/**", kind="file")
    assert sorted(files.paths) == ["/data/a.txt", "/data/deep/b.txt"]


async def test_exclusion_never_reveals_meta() -> None:
    fs = await _mounted_world()
    result = await fs.glob("**", globs_not=("**/*.txt",))
    assert not any(str(path).startswith("/.vfs") for path in result.paths)


async def test_root_row_service_honors_every_channel() -> None:
    # The find-operand law serves a matching root's own row — unless an
    # exclusion glob, ext fact, or kind fact the caller stated rejects it.
    fs = await _mounted_world()
    served = await fs.glob("*.txt", paths=("/data/a.txt",))
    assert "/data/a.txt" in served.paths
    excluded = await fs.glob("*.txt", paths=("/data/a.txt",), globs_not=("a.*",))
    assert "/data/a.txt" not in excluded.paths
    wrong_ext = await fs.glob("*", paths=("/data/a.txt",), ext_not=("txt",))
    assert "/data/a.txt" not in wrong_ext.paths
    wrong_kind = await fs.glob("*", paths=("/data/a.txt",), kind="directory")
    assert "/data/a.txt" not in wrong_kind.paths


# ----------------------------------------------------------------------
# Chaining — observations are rows in hand, filtered without dispatch
# ----------------------------------------------------------------------


async def test_chained_glob_applies_exclusions_and_ext_not_in_memory() -> None:
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    rows = [
        Observation(path=Path("/src/a.py")),
        Observation(path=Path("/src/tests/t.py")),
        Observation(path=Path("/src/b.pyc")),
    ]
    excluded = await fs.glob("**/*", observations=rows, globs_not=("/src/tests/**",))
    assert [str(o.path) for o in excluded.observations] == ["/src/a.py", "/src/b.pyc"]
    by_ext = await fs.glob("**/*", observations=rows, ext_not=("pyc",))
    assert [str(o.path) for o in by_ext.observations] == ["/src/a.py", "/src/tests/t.py"]


async def test_chained_kind_filters_on_the_held_fact_without_storage() -> None:
    # Rows that carry kind are judged as held — storage sees no call.
    fs = AsyncVirtualFileSystem()
    recorder = RecorderStorage()
    await fs.add_mount(recorder, "/data")
    rows = [
        Observation(path=Path("/data/f.txt"), kind="file", populated=frozenset({"path", "kind"})),
        Observation(path=Path("/data/d"), kind="directory", populated=frozenset({"path", "kind"})),
    ]
    result = await fs.glob("**", observations=rows, kind="file")
    assert [str(o.path) for o in result.observations] == ["/data/f.txt"]
    assert recorder.calls == []


async def test_chained_kind_fetches_only_the_lacking_rows() -> None:
    # A hand-built row carries no kind: the load-bearing fact is
    # statted in one batch and the filter judges the fetched value.
    fs = await _mounted_world()
    rows = [Observation(path=Path("/data/a.txt")), Observation(path=Path("/data/deep"))]
    files = await fs.glob("**", observations=rows, kind="file")
    assert files.success is True
    assert [str(o.path) for o in files.observations] == ["/data/a.txt"]
    directories = await fs.glob("**", observations=rows, kind="directory")
    assert [str(o.path) for o in directories.observations] == ["/data/deep"]


async def test_chained_kind_on_a_vanished_row_classifies_loudly() -> None:
    fs = await _mounted_world()
    rows = [Observation(path=Path("/data/a.txt")), Observation(path=Path("/data/gone.txt"))]
    result = await fs.glob("**", observations=rows, kind="file")
    assert [str(o.path) for o in result.observations] == ["/data/a.txt"]
    assert result.success is False
    assert any(e.kind == ErrorKind.not_found for e in result.errors)


async def test_chained_without_kind_never_touches_storage() -> None:
    # The fetch exists only for the kind fact; plain chaining stays pure.
    fs = AsyncVirtualFileSystem()
    recorder = RecorderStorage()
    await fs.add_mount(recorder, "/data")
    rows = [Observation(path=Path("/data/a.txt"))]
    result = await fs.glob("**", observations=rows, globs_not=("*.md",), ext_not=("py",))
    assert [str(o.path) for o in result.observations] == ["/data/a.txt"]
    assert recorder.calls == []


async def test_chained_glob_matches_any_brace_arm() -> None:
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    rows = [
        Observation(path=Path("/src/a.ts")),
        Observation(path=Path("/src/b.tsx")),
        Observation(path=Path("/src/c.css")),
    ]
    result = await fs.glob("*.{ts,tsx}", observations=rows)
    assert [str(o.path) for o in result.observations] == ["/src/a.ts", "/src/b.tsx"]


async def test_chained_glob_filters_rows_in_hand_without_storage() -> None:
    # Pure filter: rows pass or drop on their held paths alone — the
    # rows here exist nowhere in storage, and duplicates survive.
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    rows = [
        Observation(path=Path("/keep/a.txt")),
        Observation(path=Path("/drop/b.md")),
        Observation(path=Path("/keep/a.txt")),
    ]
    result = await fs.glob("*.txt", observations=rows)
    assert result.success is True
    assert [str(o.path) for o in result.observations] == ["/keep/a.txt", "/keep/a.txt"]


async def test_chained_glob_path_arm_anchors_and_ext_applies() -> None:
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    rows = [
        Observation(path=Path("/src/a.py")),
        Observation(path=Path("/lib/b.py")),
        Observation(path=Path("/src/c.txt")),
    ]
    anchored = await fs.glob("/src/*", observations=rows)
    assert [str(o.path) for o in anchored.observations] == ["/src/a.py", "/src/c.txt"]
    by_ext = await fs.glob("*", observations=rows, ext=("py",))
    assert [str(o.path) for o in by_ext.observations] == ["/src/a.py", "/lib/b.py"]


async def test_chained_glob_ext_members_normalize_dots_and_case() -> None:
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    rows = [Observation(path=Path("/src/a.py")), Observation(path=Path("/src/c.txt"))]
    dotted = await fs.glob("*", observations=rows, ext=(".PY",))
    assert [str(o.path) for o in dotted.observations] == ["/src/a.py"]
    dropped = await fs.glob("*", observations=rows, ext_not=(".PY",))
    assert [str(o.path) for o in dropped.observations] == ["/src/c.txt"]


async def test_chained_glob_never_hides_meta_rows_in_hand() -> None:
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    rows = [Observation(path=Path("/.vfs/trash/x"))]
    result = await fs.glob("*", observations=rows)
    assert [str(o.path) for o in result.observations] == ["/.vfs/trash/x"]


# ----------------------------------------------------------------------
# Off the loop: the router's glob judging and planning run on its pool
# ----------------------------------------------------------------------

_SCOPED_GUIDANCE = "Truncated: at the wall-time budget; narrow the patterns, or scope with fewer paths"
_PLANNING_GUIDANCE = "Truncated: at the wall-time budget; scope with fewer paths, or send fewer patterns or brace arms"


def _arms(stem: str, count: int = 64) -> str:
    """One brace pattern of *count* distinct name arms."""
    return "{" + ",".join(f"{stem}{i:02}" for i in range(count)) + "}"


class _HoppingSet:
    """A native set whose judging waits for the loop to turn."""

    def __init__(self, inner: Any, ticker: LoopTicker) -> None:
        self._inner = inner
        self._ticker = ticker

    def judge(self, rows: Sequence[tuple[str, str]], *, budget: float | None) -> tuple[list[int | None], bool]:
        self._ticker.hop()
        return self._inner.judge(rows, budget=budget)


def _spy_sets(monkeypatch: pytest.MonkeyPatch) -> list[list[Any]]:
    """Each native set built, as its program list; the real set is returned."""
    built: list[list[Any]] = []
    real = glob_module.glob_set

    def spied(programs: list[Any], groups: Any, *, budget: float | None) -> Any:
        built.append(programs)
        return real(programs, groups, budget=budget)

    monkeypatch.setattr(glob_module, "glob_set", spied)
    return built


def _spy_judges(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """The executor each router judge hop ran on."""
    executors: list[Any] = []
    real = chain_module.judge_rows

    async def spied(executor: Any, gates: Any, rows: Any, *, deadline: Deadline) -> Any:
        executors.append(executor)
        return await real(executor, gates, rows, deadline=deadline)

    monkeypatch.setattr(chain_module, "judge_rows", spied)
    monkeypatch.setattr(base_module, "judge_rows", spied)
    return executors


async def test_chained_glob_leaves_the_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guards: chained glob judging its rows inline on the loop."""
    ticker = LoopTicker().start()
    real = glob_module.glob_set
    monkeypatch.setattr(glob_module, "glob_set", lambda *args, **kwargs: _HoppingSet(real(*args, **kwargs), ticker))
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    result = await fs.glob("*.txt", observations=[Observation(path=Path("/a.txt")), Observation(path=Path("/b.md"))])
    ticker.stop()
    assert [str(o.path) for o in result.observations] == ["/a.txt"]
    assert ticker.hops == 1
    await fs.close()


async def test_chained_glob_judges_once_on_the_process_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guards: one hop per row or per arm, or a program built per row."""
    executors = _spy_judges(monkeypatch)
    built = _spy_sets(monkeypatch)
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    dirs = ("src", "src/app", "docs", "lib/app", "x")
    names = ("a.py", "b.md", "c.txt", "Makefile")
    rows = [Observation(path=Path(f"/{dirs[i % 5]}/{i}{names[i % 4]}")) for i in range(1_000)]
    result = await fs.glob("{*.py,src/**,*.md}", observations=rows, globs_not=("**/app/**",))
    assert len(executors) == 1 and executors[0] is offload_pool()
    assert [len(programs) for programs in built] == [4]
    arms = [canonical_pattern(arm) for arm in ("*.py", "src/**", "*.md")]
    expected = [
        str(row.path)
        for row in rows
        if oracle.passes_filters(
            str(row.path),
            row.path.name,
            row.path.ext,
            arms,
            [canonical_pattern("**/app/**")],
            frozenset(),
            frozenset(),
            marked=lambda _pattern: False,
            marked_only=False,
        )
    ]
    assert 0 < len(expected) < len(rows)
    assert [str(o.path) for o in result.observations] == expected
    await fs.close()


async def test_chained_glob_truncates_at_the_wall(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(base_module, "WALL_TIME_BUDGET", -1.0)
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    result = await fs.glob("*.txt", observations=[Observation(path=Path("/a.txt")), Observation(path=Path("/b.txt"))])
    assert result.observations == []
    [error] = result.errors
    assert (error.kind, error.severity) == (ErrorKind.truncated, Severity.warning)
    assert error.message == (
        "Truncated: at the wall-time budget; narrow the pattern or its exclusions, or send fewer rows"
    )
    await fs.close()


async def test_chained_glob_reads_its_wall_before_it_materializes_the_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guards: chained glob's wall read after the caller's rows are drawn, so
    an iterable that is slow to draw no longer spends it."""
    clock = [0.0]
    monkeypatch.setattr(deadline_module, "monotonic", lambda: clock[0])
    monkeypatch.setattr(base_module, "WALL_TIME_BUDGET", 10.0)

    def drawn_slowly() -> Iterator[Observation]:
        clock[0] = 1e12
        yield Observation(path=Path("/a.txt"))
        yield Observation(path=Path("/b.txt"))

    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    result = await fs.glob("*.txt", observations=drawn_slowly())  # ty: ignore[invalid-argument-type]
    assert result.observations == []
    [error] = result.errors
    assert (error.kind, error.severity) == (ErrorKind.truncated, Severity.warning)
    await fs.close()


@pytest.mark.parametrize("batch", [5, "abc", ["/a.txt"], [Observation(path=Path("/a.txt")), "x"]])
async def test_chained_glob_refuses_a_batch_that_is_not_rows(batch: object) -> None:
    """Guards: the refusal of a batch that is not rows dropped from the chained
    branch, so the call answers success with no row."""
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    result = await fs.glob("*", observations=batch)  # ty: ignore[invalid-argument-type]
    assert result.observations == []
    [error] = result.errors
    assert error.kind is ErrorKind.invalid
    await fs.close()


async def test_the_root_probe_builds_each_name_arm_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guards: the probe composing and building one program per row per arm."""
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    matching = [f"/{'ab'[i % 2]}{i:02}.txt" for i in range(25)]
    others = [f"/c{i:02}.txt" for i in range(25)]
    for root in (*matching, *others):
        assert (await fs.mkdir(path=root)).success is True
    built = _spy_sets(monkeypatch)
    probing = [False]
    during: list[Any] = []
    real_program = glob_module.glob_program
    real_probe = base_module.AsyncVirtualFileSystem._root_probe

    def counted_program(*args: Any, **kwargs: Any) -> Any:
        if probing[0]:
            during.append(args)
        return real_program(*args, **kwargs)

    async def flagged_probe(self: AsyncVirtualFileSystem, *args: Any, **kwargs: Any) -> Any:
        probing[0] = True
        try:
            return await real_probe(self, *args, **kwargs)
        finally:
            probing[0] = False

    monkeypatch.setattr(glob_module, "glob_program", counted_program)
    monkeypatch.setattr(base_module.AsyncVirtualFileSystem, "_root_probe", flagged_probe)
    result = await fs.glob("{a,b}*.txt", paths=(*matching, *others))
    assert sorted(result.paths) == sorted(matching)
    assert during == []
    probe_sets = [programs for programs in built if not any(by_path for _atoms, by_path in programs)]
    assert [len(programs) for programs in probe_sets] == [2]
    await fs.close()


async def test_a_path_arm_never_serves_a_scope_roots_own_row(monkeypatch: pytest.MonkeyPatch) -> None:
    executors = _spy_judges(monkeypatch)
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    await fs.write(path="/docs/x.txt", content="x", parents=True)
    served = await fs.glob("/**", paths=("/docs",))
    assert served.paths == ("/docs/x.txt",)
    assert executors == []
    missing = await fs.glob("/**", paths=("/nope",))
    assert [(e.kind, str(e.path)) for e in missing.errors] == [(ErrorKind.not_found, "/nope")]
    await fs.close()


async def test_a_root_probe_past_its_wall_warns(monkeypatch: pytest.MonkeyPatch) -> None:
    async def unjudged(executor: Any, gates: Any, rows: Any, *, deadline: float) -> Any:
        return [None] * len(rows), False

    monkeypatch.setattr(chain_module, "judge_rows", unjudged)
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    await fs.write(path="/docs/x.txt", content="x", parents=True)
    result = await fs.glob("*", paths=("/docs",))
    assert result.paths == ("/docs/x.txt",)
    [error] = result.errors
    assert (error.kind, error.severity, error.message) == (ErrorKind.truncated, Severity.warning, _SCOPED_GUIDANCE)
    await fs.close()


async def test_planning_leaves_the_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guards: the residual walk run inline on the loop, which then cannot turn."""
    # The namespace root composes whole, so the walk residuates every arm in every entry.
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    for index in range(8):
        await fs.add_mount(RecorderStorage(), f"/m{index}")
    ticker = LoopTicker().start()
    real = fanout_module.plan_scope

    def watched(*args: Any, **kwargs: Any) -> Any:
        ticker.hop()
        return real(*args, **kwargs)

    monkeypatch.setattr(fanout_module, "plan_scope", watched)
    exclusions = tuple(_arms(f"e{j:02}x") for j in range(31))
    result = await fs.glob(_arms("x") + "*.txt", paths=("/",), globs_not=exclusions)
    ticker.stop()
    assert result.ops == ("glob",)
    assert ticker.hops == 1
    await fs.close()


async def test_planning_past_the_wall_truncates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(base_module, "WALL_TIME_BUDGET", -1.0)
    monkeypatch.setattr(fanout_module, "WALL_TIME_BUDGET", -1.0)
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    roots = [f"/d{i:02}" for i in range(50)]
    for root in roots:
        assert (await fs.write(path=f"{root}/a.txt", content="a", parents=True)).success is True
    composed: list[Any] = []
    real = fanout_module.composed_pattern

    def counted(root: Path, pattern: str) -> str:
        composed.append(root)
        return real(root, pattern)

    plans: list[Any] = []
    real_plan = fanout_module.plan_scope

    def recorded(*args: Any, **kwargs: Any) -> Any:
        plans.append(real_plan(*args, **kwargs))
        return plans[-1]

    monkeypatch.setattr(fanout_module, "composed_pattern", counted)
    monkeypatch.setattr(fanout_module, "plan_scope", recorded)
    result = await fs.glob("/**/*.txt", paths=tuple(roots))
    walls = [error for error in result.errors if error.kind is ErrorKind.truncated]
    assert [(e.severity, e.message) for e in walls] == [(Severity.warning, _PLANNING_GUIDANCE)]
    assert len(set(composed)) <= 1
    [plan] = plans
    assert (plan.roots, plan.completed) == ((), False)
    await fs.close()


async def test_one_large_root_stops_inside_its_walk(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guards: the planning deadline read only between roots, so one root
    reaching every entry walks all its arms past the wall."""
    root = InMemoryStorage()
    root_globs: list[Any] = []

    async def recorded_glob(**kwargs: Any) -> Any:
        root_globs.append(kwargs)
        return Result(ops=("glob",))

    fs = AsyncVirtualFileSystem(storage=root)
    mounts = [RecorderStorage() for _ in range(20)]
    for index, mount in enumerate(mounts):
        await fs.add_mount(mount, f"/m{index:02}")
    monkeypatch.setattr(root, "glob", recorded_glob)
    residuations = [0]
    real_residuals = fanout_module.residuals
    real_clock = deadline_module.monotonic

    def counted(pattern: str, bind_path: Path) -> Any:
        residuations[0] += 1
        return real_residuals(pattern, bind_path)

    monkeypatch.setattr(fanout_module, "residuals", counted)
    monkeypatch.setattr(deadline_module, "monotonic", lambda: 1e12 if residuations[0] else real_clock())
    monkeypatch.setattr(fanout_module, "WALL_TIME_BUDGET", 10.0)
    exclusions = tuple(_arms(f"e{j:02}x") for j in range(31))
    result = await fs.glob(_arms("x"), paths=("/",), globs_not=exclusions)
    assert residuations[0] <= 64
    assert root_globs == []
    for mount in mounts:
        assert [op for op, _kwargs in mount.calls if op == "glob"] == []
    walls = [error for error in result.errors if error.kind is ErrorKind.truncated]
    assert [e.message for e in walls] == [_PLANNING_GUIDANCE]
    await fs.close()


@pytest.mark.parametrize("verb", ["glob", "grep"])
@pytest.mark.parametrize("yields", [0, 1])
async def test_a_close_during_the_planning_hop_answers_a_result(verb: str, yields: int) -> None:
    """Guards: the builders reading the mount table after their hops, so a
    close() landing during one raises out of the verb or strands a coroutine."""
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    await fs.write(path="/docs/a.txt", content="needle", parents=True)

    async def closer() -> None:
        for _ in range(yields):
            await asyncio.sleep(0)
        await fs.close()

    call = fs.glob("*.txt", paths=("/docs",)) if verb == "glob" else fs.grep("needle", paths=("/docs",))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result, closed = await asyncio.gather(call, closer(), return_exceptions=True)
        gc.collect()
    assert closed is None
    assert isinstance(result, Result), result
    assert result.success or [e.kind for e in result.errors] == [ErrorKind.backend_unavailable]
    assert not [w for w in caught if "never awaited" in str(w.message)]


# ----------------------------------------------------------------------
# The scope channel — roots ride beside the arms
# ----------------------------------------------------------------------


def _counted(monkeypatch: pytest.MonkeyPatch, module: Any, name: str) -> list[tuple[Any, ...]]:
    """Every call to *module*'s *name*, its arguments recorded."""
    calls: list[tuple[Any, ...]] = []
    real = getattr(module, name)

    def counted(*args: Any, **kwargs: Any) -> Any:
        calls.append(args)
        return real(*args, **kwargs)

    monkeypatch.setattr(module, name, counted)
    return calls


@pytest.mark.slow
async def test_a_wide_scoped_glob_builds_roots_plus_arms(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guards: the router composing every arm under every root, or storage taking
    the composed prefilter past its limit, so one pattern arm is built per
    product element."""
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    data = InMemoryStorage()
    await fs.add_mount(data, "/data")
    rows = [Entry(path=Path(f"/data/d{i:05}/x.zz"), content="x") for i in range(10_000)]
    assert (await fs.write(entries=[*rows, Entry(path=Path("/data/d00007/x.e05"), content="x")], parents=True)).success
    # The crossing write's own statistics pass lands before the plans are read.
    await data._host.settle_statistics()
    # A count pin never reads the runner's clock: a loaded machine must not end this glob at its wall.
    monkeypatch.setattr(deadline_module, "monotonic", lambda: 0.0)
    root_arms = _counted(monkeypatch, reads_module, "scope_root_arm")
    facts = _counted(monkeypatch, reads_module, "channel_facts")
    pattern_arms = _counted(monkeypatch, reads_module, "pattern_arm")
    paths = tuple(f"/data/d{i:05}" for i in range(10_000))
    result = await fs.glob("*." + _arms("e"), paths=paths, authority=Authority.system())
    assert result.paths == ("/data/d00007/x.e05",)
    assert len(root_arms) == 10_000
    assert [len(call[2].arms) for call in facts] == [64]
    assert pattern_arms == []
    await fs.close()


async def test_planning_composes_only_the_bounded_pairs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guards: planning composing every owned root's arms, the product the
    scope channel exists to avoid."""
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    await fs.add_mount(BindableStorage(), "/data")
    await fs.add_mount(RecorderStorage(), "/data/part00007/inner")
    composed = _counted(monkeypatch, fanout_module, "composed_pattern")
    result = await fs.glob("*." + _arms("e"), paths=tuple(f"/data/part{i:05}" for i in range(10_000)))
    assert result.ops == ("glob",)
    assert len(composed) == 64
    assert {str(root) for root, _arm in composed} == {"/data/part00007"}
    await fs.close()


SCOPED_GLOB_CALLS = (
    ShapeCall("name-arm", "glob", "*.py", DIRECTORIES),
    ShapeCall("path-arm", "glob", "src/**", DIRECTORIES),
    ShapeCall("brace-arms", "glob", "{a,b}/*.txt", DIRECTORIES[:120]),
    ShapeCall("exclusion", "glob", "*.py", DIRECTORIES, options=(("globs_not", ("**/test_*",)),)),
    ShapeCall("ext", "glob", "**", DIRECTORIES, options=(("ext", ("md",)),)),
    ShapeCall("whole-side-root", "glob", "*.py", ("/m", *DIRECTORIES)),
    ShapeCall("nested-mount", "glob", "*.py", (NESTED_HOST, *DIRECTORIES[1:])),
    ShapeCall("trash-view", "glob", "*", ("/.vfs/trash", *TRASH_ROOTS)),
    ShapeCall("nested-roots", "glob", "*.py", tuple(p for d in DIRECTORIES[:125] for p in (d, f"{d}/src"))),
    ShapeCall("metachar-roots", "glob", "[ab]*", METACHAR_DIRECTORIES),
    ShapeCall("meta-root", "glob", ".vf?/**", ("/", META_DIRECTORY)),
    ShapeCall("anonymous-private-roots", "glob", "src/**", POSTURE_DIRECTORIES, world="private_roots"),
    ShapeCall("anonymous-private-src", "glob", "src/**", POSTURE_DIRECTORIES, world="private_src"),
)


# The one call the anonymous posture gate refuses whole, before any prefilter is chosen.
_REFUSED_WHOLE = frozenset({"anonymous-private-src"})


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def shape_worlds(tmp_path_factory: pytest.TempPathFactory) -> AsyncIterator[ShapeWorlds]:
    """The both-prefilters worlds, built once per session, opened from copies per module; the rows only read them."""
    shared = shared_directory(tmp_path_factory)
    source = await asyncio.to_thread(build_once, shared, "scope-worlds", build_world_files)
    worlds = await open_worlds(pathlib.Path(source), tmp_path_factory.mktemp("shape-worlds"))
    yield worlds
    for fs in worlds:
        await fs.close()


@pytest.mark.slow
@pytest.mark.asyncio(loop_scope="module")
@pytest.mark.parametrize("call", SCOPED_GLOB_CALLS, ids=[call.name for call in SCOPED_GLOB_CALLS])
async def test_both_prefilters_answer_alike(
    call: ShapeCall, shape_worlds: ShapeWorlds, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Guards: any row, refusal or record that differs between prefiltering a scope
    with its root clauses and with its roots composed under its arms, or a side
    that takes the other plan than the limit names."""
    answers: list[Result] = []
    plans: list[set[bool]] = []
    real = reads_module.AdmittedScope.composed
    for limit in (0, 10**9):
        monkeypatch.setattr(reads_module, "COMPOSED_PREFILTER_LIMIT", limit)
        taken: set[bool] = set()

        def spied(self: Any, *, trashed: bool, taken: set[bool] = taken) -> Any:
            answer = real(self, trashed=trashed)
            if self.roots(trashed=trashed):
                taken.add(answer is not None)
            return answer

        monkeypatch.setattr(reads_module.AdmittedScope, "composed", spied)
        answers.append(await call.run(shape_worlds))
        plans.append(taken)
    fan, composed = answers
    assert plans == ([set(), set()] if call.name in _REFUSED_WHOLE else [{False}, {True}])
    assert fan.observations == composed.observations
    assert fan.errors == composed.errors
    assert composed.observations or composed.errors
    assert not any(error.kind is ErrorKind.truncated for error in composed.errors)


# ----------------------------------------------------------------------
# A view-ancestor root — a live root above the trash head reads as its joined text
# ----------------------------------------------------------------------

_VIEW_ROOT = "/.vfs"
_VIEW_ARM = "trash/t/src/**"

# What everyone holds at each postured path of the trashed tree, in both orders.
_VIEW_POSTURES: dict[str, dict[str, Posture]] = {
    "private-roots": {"/": "none", "/t": "none", "/t/src": "read"},
    "private-src": {"/": "none", "/t": "read", "/t/src": "none"},
}


def _private(world: GrantWorld, path: str) -> bool:
    """Whether the test's own posture table gives everyone nothing at *path*."""
    return everyone_rank(world, path) == LEVEL_RANK["none"]


async def _ask_the_view(fs: AsyncVirtualFileSystem, verb: str, authority: Authority) -> Result:
    """The one scoped call of *verb* whose root is the view ancestor and whose arm enters the trash view."""
    if verb == "glob":
        return await fs.glob(_VIEW_ARM, paths=(_VIEW_ROOT,), authority=authority)
    return await getattr(fs, verb)("needle", paths=(_VIEW_ROOT,), globs=(_VIEW_ARM,), authority=authority)


@pytest.mark.parametrize("order", sorted(_VIEW_POSTURES))
@pytest.mark.parametrize("verb", ["glob", "grep", "search"])
async def test_a_view_ancestor_root_leaks_nothing_under_either_posture_order(verb: str, order: str) -> None:
    """Guards: a live root above the trash head read apart from its arm, so the
    anonymous gate judges beneath the head, where no posture stands, and the
    trash view's rows are lost or served past a private directory."""
    postures = _VIEW_POSTURES[order]
    world = GrantWorld(grants=[GrantRow(EVERYONE_NAME, path, level) for path, level in postures.items()])
    system = Authority.system()
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    rows = [Entry(path=Path(f"/t/{name}"), content="needle") for name in ("a.py", "src/c.py")]
    assert (await fs.write(entries=rows, parents=True, authority=system)).success is True
    for path, level in postures.items():
        assert (await fs.set_posture(path, level, authority=system)).success is True
    assert (await fs.delete(observations=[Observation(path=Path("/t"))], authority=system)).success is True
    composed = [composed_pattern(Path(_VIEW_ROOT), _VIEW_ARM)]
    judged = {address_of(path).stored for path in addressed_by(composed)}
    refusals = {path for path in judged if _private(world, path)}
    result = await _ask_the_view(fs, verb, Authority.anonymous())
    # The router's own probe of the root answers for /.vfs itself; the gate's records are the rest.
    refused = {str(error.path) for error in result.errors if error.kind is ErrorKind.unauthenticated} - {_VIEW_ROOT}
    assert refused == refusals
    reference = await _ask_the_view(fs, verb, system)
    readable = [str(o.path) for o in reference.observations if not _private(world, str(o.path))]
    served = [str(o.path) for o in result.observations]
    assert served == ([] if refusals else readable)
    assert not any(_private(world, path) for path in served)
    assert (judged, served) == ({"/t/src"}, ["/t/src/c.py"] if order == "private-roots" else [])
    await fs.close()


async def test_a_wildcard_headed_pattern_hides_the_meta_root_at_every_size() -> None:
    """Guards: a row beneath ``/.vfs`` served to a wildcard-headed pattern once the
    call names enough roots to change storage's prefilter, where the same call
    with two roots hides it; a root that names the meta subtree still serves it."""
    system = Authority.system()
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    others = tuple(f"/o{index:03}" for index in range(201))
    rows = [Entry(path=Path("/.vfs/state/s.txt"), content="x"), Entry(path=Path("/.vfx/k.txt"), content="x")]
    rows += [Entry(path=Path(f"{other}/k.txt"), content="x") for other in others]
    assert (await fs.write(entries=rows, parents=True, authority=system)).success is True
    for paths in (("/", "/.vfs/state"), ("/", "/.vfs/state", *others)):
        result = await fs.glob(".vf?/**", paths=paths, authority=system)
        assert (sorted(result.paths), result.errors) == (["/.vfx/k.txt"], [])
    named = await fs.glob("*.txt", paths=("/.vfs/state", *others[:1]), authority=system)
    assert sorted(named.paths) == ["/.vfs/state/s.txt", "/o000/k.txt"]
    await fs.close()


async def test_a_view_ancestor_root_reads_its_joined_text_at_every_size() -> None:
    """Guards: a live root above the trash head riding the scope beside many roots,
    where its arm no longer enters the trash view and the bare head is no longer refused."""
    system = Authority.system()
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    others = tuple(f"/o{index:03}" for index in range(201))
    rows = [Entry(path=Path(f"/x/{name}"), content="x") for name in ("a.py", "b.py")]
    rows += [Entry(path=Path(f"{other}/k.txt"), content="x") for other in others]
    assert (await fs.write(entries=rows, parents=True, authority=system)).success is True
    assert (await fs.delete(observations=[Observation(path=Path("/x"))], authority=system)).success is True
    alone = await fs.glob("trash/x/**", paths=(_VIEW_ROOT,), authority=system)
    crowded = await fs.glob("trash/x/**", paths=(_VIEW_ROOT, *others), authority=system)
    assert sorted(alone.paths) == ["/x/a.py", "/x/b.py"]
    assert sorted(crowded.paths) == ["/x/a.py", "/x/b.py"]
    # No row is stored at /.vfs, and the root's own probe says so at every size.
    probe = [(ErrorKind.not_found, _VIEW_ROOT)]
    assert [(error.kind, error.path) for error in alone.errors] == probe
    assert crowded.errors == alone.errors
    head = await fs.glob("/trash", paths=(_VIEW_ROOT, *others), authority=system)
    assert head.observations == []
    assert [(error.kind, error.path) for error in head.errors] == [*probe, (ErrorKind.invalid, None)]
    await fs.close()
