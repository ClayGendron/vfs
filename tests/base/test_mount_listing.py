"""What a listing shows at a mount point: the mounted root, never the directory beneath it, and never hidden."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import pytest

from tests.support.base_doubles import BindableStorage, RecorderStorage, TransportFailStorage
from vfs import AsyncVirtualFileSystem, InMemoryStorage
from vfs import mounts as mounts_module
from vfs import paths as paths_module
from vfs.authority import Authority, Principal
from vfs.models import Observation
from vfs.mounts import Mount
from vfs.paths import Path
from vfs.results import ErrorKind, Result, ResultError, classified
from vfs.results.kinds import Severity
from vfs.storage import TransportError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from vfs.ops import Op

    Share = Callable[[AsyncVirtualFileSystem], Awaitable[None]]

SYSTEM = Authority.system()
ADA = Authority.of(Principal("ada"))
GRACE = Authority.of(Principal("grace"))
ANONYMOUS = Authority.anonymous()

BARE = frozenset({"path", "kind"})
MARK = 7


def ok(result: Result) -> Result:
    assert result.success is True, result.error_message
    return result


async def world(*, mounted: bool) -> AsyncVirtualFileSystem:
    """A closed root where ``/data`` holds two files. With ``mounted``, ``/data`` is a closed storage of its own."""
    fs = AsyncVirtualFileSystem()
    ok(await fs.set_posture("/", "none", authority=SYSTEM))
    if mounted:
        await fs.add_mount(InMemoryStorage(), "/data", authority=SYSTEM)
        ok(await fs.set_posture("/data", "none", authority=SYSTEM))
    else:
        ok(await fs.mkdir("/data", authority=SYSTEM))
    ok(await fs.write(path="/data/report.md", content="r", authority=SYSTEM))
    ok(await fs.write(path="/data/sub/deep.md", content="d", parents=True, authority=SYSTEM))
    return fs


async def read_at_the_top(fs: AsyncVirtualFileSystem) -> None:
    """Ada is granted ``read`` at ``/data``."""
    ok(await fs.grant("/data", "ada", "read", authority=SYSTEM))


async def read_deeper(fs: AsyncVirtualFileSystem) -> None:
    """Ada is granted ``read`` on one file two levels inside ``/data``, and nothing above it."""
    ok(await fs.grant("/data/sub/deep.md", "ada", "read", authority=SYSTEM))


async def owns_a_row(fs: AsyncVirtualFileSystem) -> None:
    """Ada wrote one file inside ``/data`` while she held a grant, and the grant is gone."""
    ok(await fs.grant("/data/sub", "ada", "read_write", authority=SYSTEM))
    ok(await fs.write(path="/data/sub/mine.md", content="m", authority=ADA))
    ok(await fs.revoke("/data/sub", "ada", authority=SYSTEM))


async def listings(fs: AsyncVirtualFileSystem, who: Authority) -> dict[str, set[str]]:
    """The paths each listing of the root returns to ``who``."""
    calls = {
        "ls": fs.ls("/", authority=who),
        "tree": fs.tree("/", authority=who),
        "tree to depth 1": fs.tree("/", max_depth=1, authority=who),
        "glob": fs.glob("/*", authority=who),
        "glob by name": fs.glob("data", authority=who),
    }
    return {name: {str(path) for path in ok(await call).paths} for name, call in calls.items()}


def row_at(result: Result, path: str) -> Observation:
    [row] = [row for row in result.observations if row.path == path]
    return row


# ----------------------------------------------------------------------
# A mount shows as a directory with the same contents shows
# ----------------------------------------------------------------------


@pytest.mark.parametrize("share", [read_at_the_top, read_deeper, owns_a_row])
async def test_a_mount_lists_as_a_directory_with_the_same_contents_does(share: Share) -> None:
    plain, mounted = await world(mounted=False), await world(mounted=True)
    await share(plain)
    await share(mounted)
    seen, wanted = await listings(mounted, ADA), await listings(plain, ADA)
    # The mount's own row is the one path a mount may add: a mount's path is never hidden, and a
    # directory shows only when a row the caller may see lies beneath it within the listing's depth.
    for name, found in seen.items():
        assert wanted[name] <= found <= wanted[name] | {"/data"}, name
        assert "/data" in found, name
    assert seen["ls"] == wanted["ls"]
    assert seen["tree"] == wanted["tree"]
    assert seen["glob"] == wanted["glob"]


async def test_a_caller_granted_read_in_the_mounted_storage_sees_the_mount_with_no_grant_above_it() -> None:
    fs = await world(mounted=True)
    await read_at_the_top(fs)
    assert ok(await fs.ls("/", authority=ADA)).paths == ("/data",)
    assert set(ok(await fs.tree("/", authority=ADA)).paths) == {
        "/data",
        "/data/report.md",
        "/data/sub",
        "/data/sub/deep.md",
    }
    assert ok(await fs.tree("/", max_depth=1, authority=ADA)).paths == ("/data",)
    assert ok(await fs.glob("/*", authority=ADA)).paths == ("/data",)


@pytest.mark.parametrize("share", [read_deeper, owns_a_row, None])
async def test_a_caller_with_no_rights_at_the_mounted_root_sees_the_mount_as_a_bare_row(share: Share | None) -> None:
    fs = await world(mounted=True)
    if share is not None:
        await share(fs)
    for listing in (fs.ls("/", authority=ADA), fs.tree("/", max_depth=1, authority=ADA), fs.glob("/*", authority=ADA)):
        [row] = ok(await listing).observations
        assert (row.path, row.kind, row.populated) == ("/data", "directory", BARE)


async def test_a_caller_who_holds_nothing_sees_a_mount_and_does_not_see_a_directory() -> None:
    # The one place a mount and a directory differ: a mount's path is not a secret.
    assert (await listings(await world(mounted=False), GRACE))["ls"] == set()
    assert (await listings(await world(mounted=True), GRACE))["ls"] == {"/data"}


@pytest.mark.parametrize("who", [SYSTEM, ADA], ids=["system", "named"])
async def test_the_row_at_a_mount_point_is_the_row_stat_returns(who: Authority) -> None:
    fs = await world(mounted=True)
    await read_at_the_top(fs)
    stat = ok(await fs.stat("/data", authority=who)).one()
    assert row_at(ok(await fs.ls("/", authority=who)), "/data") == stat
    assert row_at(ok(await fs.tree("/", authority=who)), "/data") == stat
    assert row_at(ok(await fs.glob("/*", authority=who)), "/data") == stat


class CoveredStorage(BindableStorage):
    """A parent whose listings return a marked row at ``/data``, as a stored mount-point directory would be."""

    def _answer(self, op: str, kwargs: dict[str, Any], authority: Authority | None = None) -> Result:
        self.calls.append((op, kwargs))
        covered = Observation(path="/data", kind="directory", size_bytes=MARK)
        return Result(ops=(op,), observations=[covered, Observation(path="/z.md", kind="file")])

    async def ls(self, *, path: Path | None = None, authority: Authority | None = None, **kwargs: Any) -> Result:
        if path == "/data":
            return await super().ls(path=path, authority=authority, **kwargs)
        return self._answer("ls", {"path": path, **kwargs})


class RootedStorage(RecorderStorage):
    """A child whose root is a directory at version 3, and which holds one file."""

    ROOT = Observation(path="/", kind="directory", version=3, populated=frozenset({"path", "kind", "version"}))

    def _answer(self, op: str, kwargs: dict[str, Any], authority: Authority | None = None) -> Result:
        self.calls.append((op, kwargs))
        row = self.ROOT if op == "stat" else Observation(path="/n.md", kind="file")
        return Result(ops=(op,), observations=[row])


async def covered_world() -> tuple[AsyncVirtualFileSystem, CoveredStorage, RootedStorage]:
    parent, child = CoveredStorage(), RootedStorage()
    fs = AsyncVirtualFileSystem(storage=parent)
    await fs.add_mount(child, "/data")
    parent.calls.clear()
    child.calls.clear()
    return fs, parent, child


async def test_a_listing_returns_one_row_at_a_mount_point_with_no_field_of_the_directory_beneath_it() -> None:
    fs, _parent, _child = await covered_world()
    for listing in (fs.ls("/"), fs.tree("/"), fs.glob("/*"), fs.glob("*")):
        result = ok(await listing)
        row = row_at(result, "/data")
        assert (row.version, row.size_bytes) == (3, None)
        assert "/z.md" in result.paths


async def test_columns_reach_the_mounted_storage_and_the_row_keeps_its_field_mask() -> None:
    fs, _parent, child = await covered_world()
    wanted = frozenset({"version"})
    row = row_at(ok(await fs.ls("/", columns=wanted)), "/data")
    assert child.calls == [("stat", {"path": "/", "columns": wanted})]
    assert row.populated == RootedStorage.ROOT.populated


async def test_ls_puts_the_mount_in_name_order() -> None:
    fs = AsyncVirtualFileSystem()
    for name in ("/a.md", "/z.md"):
        ok(await fs.write(path=name, content="x"))
    await fs.add_mount(InMemoryStorage(), "/m")
    assert ok(await fs.ls("/")).paths == ("/a.md", "/m", "/z.md")


# ----------------------------------------------------------------------
# A directory that leads to a mount is on the road
# ----------------------------------------------------------------------


async def deep_mount() -> AsyncVirtualFileSystem:
    """A closed root with a closed storage mounted at ``/a/b``, which holds one file that ada may read."""
    fs = AsyncVirtualFileSystem()
    ok(await fs.set_posture("/", "none", authority=SYSTEM))
    await fs.add_mount(InMemoryStorage(), "/a/b", parents=True, authority=SYSTEM)
    ok(await fs.set_posture("/a/b", "none", authority=SYSTEM))
    ok(await fs.write(path="/a/b/n.md", content="n", authority=SYSTEM))
    ok(await fs.grant("/a/b", "ada", "read", authority=SYSTEM))
    return fs


@pytest.mark.parametrize("who", [ADA, GRACE], ids=["granted in the mount", "holds nothing"])
async def test_a_caller_can_walk_down_to_a_mount_through_directories_they_hold_nothing_on(who: Authority) -> None:
    fs = await deep_mount()
    [top] = ok(await fs.ls("/", authority=who)).observations
    assert (top.path, top.kind, top.populated) == ("/a", "directory", BARE)
    assert ok(await fs.ls("/a", authority=who)).paths == ("/a/b",)
    assert ok(await fs.stat("/a", authority=who)).one() == top
    assert ok(await fs.glob("/*", authority=who)).observations == [top]
    assert (await fs.locate("/a", exists=True, authority=who)).exists is True


async def test_tree_shows_the_directories_above_a_mount_it_reaches() -> None:
    fs = await deep_mount()
    assert ok(await fs.tree("/", authority=ADA)).paths == ("/a", "/a/b", "/a/b/n.md")
    assert ok(await fs.tree("/a", authority=ADA)).paths == ("/a/b", "/a/b/n.md")
    assert ok(await fs.tree("/", max_depth=2, authority=ADA)).paths == ("/a", "/a/b")
    # A mount deeper than the listing goes brings no directory above it into the listing.
    assert ok(await fs.tree("/", max_depth=1, authority=ADA)).paths == ()


async def test_a_directory_above_a_mount_that_the_caller_may_see_keeps_its_own_row() -> None:
    fs = await deep_mount()
    stored = ok(await fs.stat("/a", authority=SYSTEM)).one()
    assert stored.populated > BARE
    assert ok(await fs.ls("/", authority=SYSTEM)).observations == [stored]
    assert row_at(ok(await fs.tree("/", authority=SYSTEM)), "/a") == stored


async def test_a_batch_answers_for_a_directory_above_a_mount_and_keeps_the_error_of_a_missing_one() -> None:
    fs = await deep_mount()
    batch = [Observation(path="/a"), Observation(path="/nope")]
    stat = await fs.stat(observations=batch, authority=ADA)
    assert [(row.path, row.populated) for row in stat.observations] == [("/a", BARE)]
    assert [(error.kind, error.path) for error in stat.errors] == [(ErrorKind.not_found, "/nope")]
    listed = await fs.ls(observations=batch, authority=ADA)
    assert listed.paths == ("/a/b",)
    assert [(error.kind, error.path) for error in listed.errors] == [(ErrorKind.not_found, "/nope")]


async def test_a_search_beneath_a_directory_above_a_mount_does_not_fail_on_that_directory() -> None:
    fs = await deep_mount()
    found = ok(await fs.glob("*.md", paths=("/a",), authority=ADA))
    assert found.paths == ("/a/b/n.md",)
    assert found.errors == []


# ----------------------------------------------------------------------
# A refusal stands, and a mounted storage that cannot answer is named
# ----------------------------------------------------------------------


async def test_the_anonymous_caller_on_a_closed_root_is_refused_and_learns_no_mount() -> None:
    fs = await world(mounted=True)
    for listing in (fs.ls("/"), fs.tree("/")):
        refused = await listing
        assert [error.kind for error in refused.errors] == [ErrorKind.unauthenticated]
        assert refused.observations == []


async def test_a_mount_that_refuses_the_caller_still_shows_its_name_and_says_nothing_more() -> None:
    fs = AsyncVirtualFileSystem()
    await fs.add_mount(InMemoryStorage(), "/data")
    ok(await fs.set_posture("/data", "none", authority=SYSTEM))
    assert (await fs.stat("/data")).errors[0].kind is ErrorKind.unauthenticated
    listed = ok(await fs.ls("/"))
    assert [(row.path, row.populated) for row in listed.observations] == [("/data", BARE)]
    assert listed.errors == []


async def test_a_mount_that_cannot_answer_shows_bare_with_one_warning_that_names_it() -> None:
    fs = AsyncVirtualFileSystem()
    ok(await fs.write(path="/z.md", content="z"))
    await fs.add_mount(TransportFailStorage(), "/dead")
    for listing in (fs.ls("/"), fs.tree("/"), fs.glob("/*")):
        result = ok(await listing)
        assert set(result.paths) == {"/dead", "/z.md"}
        assert row_at(result, "/dead").populated == BARE
        [warning] = result.errors
        assert (warning.kind, warning.severity) == (ErrorKind.backend_unavailable, Severity.warning)
        assert (warning.path, warning.source) == ("/dead", "/dead")


async def test_a_mounted_storage_that_returns_no_row_for_its_root_shows_bare() -> None:
    fs = AsyncVirtualFileSystem(storage=BindableStorage())
    await fs.add_mount(RecorderStorage(), "/quiet")
    listed = ok(await fs.ls("/"))
    assert [(row.path, row.kind, row.populated) for row in listed.observations] == [("/quiet", "directory", BARE)]
    assert listed.errors == []


async def test_a_mount_that_cannot_stat_shows_bare_and_is_not_asked() -> None:
    fs = AsyncVirtualFileSystem(storage=BindableStorage())
    child = RecorderStorage(caps=frozenset({"read", "ls", "tree"}))
    await fs.add_mount(child, "/mute")
    assert [(row.path, row.populated) for row in ok(await fs.ls("/")).observations] == [("/mute", BARE)]
    assert child.calls == []


# ----------------------------------------------------------------------
# Depth, limits and batches
# ----------------------------------------------------------------------


async def test_a_mount_exactly_at_the_depth_limit_shows_its_row_and_is_not_listed() -> None:
    fs, _parent, child = await covered_world()
    result = ok(await fs.tree("/", max_depth=1))
    assert row_at(result, "/data").version == 3
    assert "/data/n.md" not in result.paths
    assert [op for op, _kwargs in child.calls] == ["stat"]
    child.calls.clear()
    assert "/data/n.md" in ok(await fs.tree("/", max_depth=2)).paths
    assert ("tree", {"path": "/", "max_depth": 1, "columns": None}) in child.calls


async def test_a_limit_is_spent_on_rows_the_caller_gets() -> None:
    fs = await world(mounted=True)
    ok(await fs.write(path="/z.md", content="z", authority=SYSTEM))
    assert len(ok(await fs.glob("/*", max_count=1, authority=SYSTEM)).observations) == 1
    assert set(ok(await fs.glob("/*", max_count=2, authority=SYSTEM)).paths) == {"/data", "/z.md"}


async def test_mount_points_that_were_not_judged_in_time_are_left_out_with_a_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def out_of_time(*_args: Any) -> tuple[list[Observation], bool]:
        return [], False

    monkeypatch.setattr(mounts_module, "judge_in_hand", out_of_time)
    fs = AsyncVirtualFileSystem()
    await fs.add_mount(InMemoryStorage(), "/data")
    result = ok(await fs.glob("/*"))
    assert result.paths == ()
    [warning] = result.errors
    assert (warning.kind, warning.severity) == (ErrorKind.truncated, Severity.warning)


async def test_glob_filters_apply_to_the_row_at_a_mount_point() -> None:
    fs = await world(mounted=True)
    assert ok(await fs.glob("/*", kind="file", authority=SYSTEM)).paths == ()
    assert ok(await fs.glob("/*", kind="directory", authority=SYSTEM)).paths == ("/data",)
    assert ok(await fs.glob("/*", globs_not=("/d*",), authority=SYSTEM)).paths == ()
    assert ok(await fs.glob("/*", ext=("md",), authority=SYSTEM)).paths == ()
    assert ok(await fs.glob("/data/**", authority=SYSTEM)).paths.count("/data") == 0
    assert "/data" not in ok(await fs.glob("*.md", authority=SYSTEM)).paths


async def test_glob_beneath_a_root_returns_the_mount_points_beneath_it() -> None:
    fs = await deep_mount()
    assert ok(await fs.glob("b", paths=("/a",), authority=ADA)).paths == ("/a/b",)
    assert ok(await fs.glob("/b", paths=("/a",), authority=ADA)).paths == ("/a/b",)
    assert ok(await fs.glob("a", paths=("/",), authority=ADA)).paths == ("/a",)
    # A root's own row is the root probe's to return, and a root is never beneath itself.
    assert ok(await fs.glob("b", paths=("/a/b",), authority=ADA)).paths == ("/a/b",)
    assert ok(await fs.glob("/b", paths=("/a/b",), authority=ADA)).paths == ()


async def test_a_batch_lists_a_directory_once_for_each_time_it_is_named() -> None:
    fs = AsyncVirtualFileSystem()
    ok(await fs.write(path="/z.md", content="z"))
    ok(await fs.write(path="/plain/p.md", content="p", parents=True))
    await fs.add_mount(InMemoryStorage(), "/data")
    batch = [Observation(path=path) for path in ("/", "/plain", "/", "/missing")]
    listed = await fs.ls(observations=batch)
    assert listed.paths == ("/plain/p.md", "/data", "/plain", "/z.md", "/data", "/plain", "/z.md")
    assert [(error.kind, error.path) for error in listed.errors] == [(ErrorKind.not_found, "/missing")]


# ----------------------------------------------------------------------
# Cost, counted in storage calls
# ----------------------------------------------------------------------


async def test_listing_a_directory_that_holds_no_mount_point_makes_one_storage_call() -> None:
    parent, child = BindableStorage(), BindableStorage()
    fs = AsyncVirtualFileSystem(storage=parent)
    await fs.add_mount(child, "/data")
    parent.calls.clear()
    child.calls.clear()
    ok(await fs.ls("/elsewhere"))
    ok(await fs.stat("/elsewhere"))
    assert parent.calls == [
        ("ls", {"path": "/elsewhere", "columns": None}),
        ("stat", {"path": "/elsewhere", "columns": None}),
    ]
    assert child.calls == []


async def test_listing_a_directory_makes_one_more_call_for_each_mount_point_in_it() -> None:
    parent = BindableStorage()
    fs = AsyncVirtualFileSystem(storage=parent)
    children = {path: BindableStorage() for path in ("/a", "/b", "/c")}
    for path, child in children.items():
        await fs.add_mount(child, path)
    for storage in (parent, *children.values()):
        storage.calls.clear()
    assert ok(await fs.ls("/")).paths == ("/a", "/b", "/c")
    assert parent.calls == [("ls", {"path": "/", "columns": None})]
    for child in children.values():
        assert child.calls == [("stat", {"path": "/", "columns": None})]


async def test_a_nested_mount_is_listed_by_the_mount_that_holds_its_mount_point() -> None:
    parent, outer, inner = BindableStorage(), BindableStorage(), BindableStorage()
    fs = AsyncVirtualFileSystem(storage=parent)
    await fs.add_mount(outer, "/m")
    await fs.add_mount(inner, "/m/n")
    for storage in (parent, outer, inner):
        storage.calls.clear()
    assert ok(await fs.ls("/")).paths == ("/m",)
    assert inner.calls == []
    assert ok(await fs.ls("/m")).paths == ("/m/n",)
    assert parent.calls == [("ls", {"path": "/", "columns": None})]
    assert inner.calls == [("stat", {"path": "/", "columns": None})]


async def test_stat_of_a_batch_makes_one_storage_call_however_many_directories_lead_to_mounts() -> None:
    parent = BindableStorage()
    fs = AsyncVirtualFileSystem(storage=parent)
    roads = [f"/r{index}" for index in range(3)]
    for road in roads:
        await fs.add_mount(BindableStorage(), f"{road}/m", parents=True)
    parent.calls.clear()
    stat = ok(await fs.stat(observations=[Observation(path=road) for road in roads]))
    assert set(roads) <= set(stat.paths)
    ok(await fs.glob("*", paths=tuple(roads)))
    assert [op for op, _kwargs in parent.calls if op == "stat"] == ["stat", "stat"]


def batch_of(*paths: str) -> list[Observation]:
    return [Observation(path=path) for path in paths]


def misses(result: Result) -> list[tuple[ErrorKind | str, str | None, object]]:
    """Each error of ``result`` as its kind, its path and the path it was raised for."""
    return [(error.kind, error.path, (error.data or {}).get("vfs.target")) for error in result.errors]


async def roads_world() -> AsyncVirtualFileSystem:
    """A closed root with mounts at ``/a/x/m``, ``/a/y/m`` and ``/b/z/m``, and no grant anywhere."""
    fs = AsyncVirtualFileSystem()
    ok(await fs.set_posture("/", "none", authority=SYSTEM))
    for path in ("/a/x/m", "/a/y/m", "/b/z/m"):
        await fs.add_mount(InMemoryStorage(), path, parents=True, authority=SYSTEM)
    return fs


async def test_a_batch_keeps_the_miss_of_the_path_that_is_missing_beside_directories_above_mounts() -> None:
    fs = await roads_world()
    stat = await fs.stat(observations=batch_of("/a/x", "/a/nope", "/a/y"), authority=GRACE)
    assert [(row.path, row.populated) for row in stat.observations] == [("/a/x", BARE), ("/a/y", BARE)]
    assert misses(stat) == [(ErrorKind.not_found, "/a", "/a/nope")]


async def test_a_batch_that_names_directories_above_mounts_twice_returns_each_row_twice_with_no_error() -> None:
    fs = await roads_world()
    stat = ok(await fs.stat(observations=batch_of("/a/x", "/a/x", "/a/y", "/b/z", "/b/z"), authority=GRACE))
    assert stat.paths == ("/a/x", "/a/x", "/a/y", "/b/z", "/b/z")
    assert stat.errors == []


async def test_a_batch_keeps_each_miss_beneath_a_directory_above_a_mount() -> None:
    fs = await roads_world()
    names = ("/a/x", "/a/x/n", "/a/y", "/a/x", "/b/z", "/b/z/n", "/b/z/q")
    stat = await fs.stat(observations=batch_of(*names), authority=GRACE)
    assert stat.paths == ("/a/x", "/a/y", "/a/x", "/b/z")
    assert misses(stat) == [
        (ErrorKind.not_found, "/a", "/a/x/n"),
        (ErrorKind.not_found, "/b", "/b/z/n"),
        (ErrorKind.not_found, "/b", "/b/z/q"),
    ]


class Targetless(BindableStorage):
    """A parent whose ``stat`` of a batch gives no row and one ``not_found`` that names no path."""

    async def stat(self, *, path: Path | None = None, authority: Authority | None = None, **kwargs: Any) -> Result:
        if path is not None:
            return await super().stat(path=path, authority=authority, **kwargs)
        return Result(ops=("stat",), errors=[classified(ErrorKind.not_found)])


async def test_a_miss_that_names_no_target_is_kept_and_recovers_nothing() -> None:
    fs = AsyncVirtualFileSystem(storage=Targetless())
    await fs.add_mount(BindableStorage(), "/a/m", parents=True)
    stat = await fs.stat(observations=batch_of("/a", "/a/missing"))
    assert [(row.path, row.populated) for row in stat.observations] == [("/a", BARE)]
    assert misses(stat) == [(ErrorKind.not_found, None, None)]


class Noting(BindableStorage):
    """A parent whose ``stat`` of a batch gives no row and the records in ``errors``."""

    errors: tuple[Any, ...] = ()

    async def stat(self, *, path: Path | None = None, authority: Authority | None = None, **kwargs: Any) -> Result:
        if path is not None:
            return await super().stat(path=path, authority=authority, **kwargs)
        return Result(ops=("stat",), errors=list(self.errors))


WARNED = classified(ErrorKind.truncated, severity=Severity.warning)


@pytest.mark.parametrize(
    ("errors", "paths"),
    [((WARNED,), ("/a",)), ((WARNED, classified(ErrorKind.backend_unavailable)), ())],
    ids=["a warning", "a failure that names no path"],
)
async def test_a_batch_keeps_its_records_beside_a_directory_above_a_mount(
    errors: tuple[Any, ...], paths: tuple[str, ...]
) -> None:
    parent = Noting()
    fs = AsyncVirtualFileSystem(storage=parent)
    await fs.add_mount(BindableStorage(), "/a/m", parents=True)
    parent.errors = errors
    stat = await fs.stat(observations=batch_of("/a", "/a/missing"))
    assert stat.paths == paths
    assert [error.kind for error in stat.errors] == [error.kind for error in errors]


class Missing(BindableStorage):
    """A parent whose ``stat`` of a batch finds nothing, and names each path it was asked for."""

    async def stat(self, *, path: Path | None = None, authority: Authority | None = None, **kwargs: Any) -> Result:
        if path is not None:
            return await super().stat(path=path, authority=authority, **kwargs)
        errors = [classified(ErrorKind.not_found, row.path) for row in kwargs["observations"]]
        return Result(ops=("stat",), errors=errors)


async def test_the_misses_of_a_batch_are_matched_to_directories_above_mounts_in_linear_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checks = 0
    original = mounts_module._target

    def counted(error: ResultError) -> Path | None:
        nonlocal checks
        checks += 1
        return original(error)

    fs = AsyncVirtualFileSystem(storage=Missing())
    roads = [f"/r{index:02}" for index in range(40)]
    for road in roads:
        await fs.add_mount(BindableStorage(), f"{road}/m", parents=True)
    names = [*roads, *(f"/f{index}" for index in range(1_000))]
    monkeypatch.setattr(mounts_module, "_target", counted)
    stat = await fs.stat(observations=batch_of(*names))
    assert stat.paths == tuple(roads)
    assert len(stat.errors) == 1_000
    assert checks <= len(names)


async def test_a_batch_that_names_a_directory_above_a_mount_twice_lists_it_once() -> None:
    parent = BindableStorage()
    fs = AsyncVirtualFileSystem(storage=parent)
    await fs.add_mount(BindableStorage(), "/a/m", parents=True)
    parent.calls.clear()
    ok(await fs.ls(observations=[Observation(path="/a"), Observation(path="/a")]))
    assert parent.calls == [("ls", {"path": "/a", "columns": None})]


async def test_the_containment_checks_of_a_listing_do_not_grow_with_mounts_times_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checks = 0
    original = mounts_module._lies_in

    def counted(path: Path, directory: Path) -> bool:
        nonlocal checks
        checks += 1
        return original(path, directory)

    parent = BindableStorage()
    fs = AsyncVirtualFileSystem(storage=parent)
    mounted = [f"/m{index:02}" for index in range(50)]
    for path in mounted:
        await fs.add_mount(BindableStorage(), path)
    monkeypatch.setattr(mounts_module, "_lies_in", counted)
    ok(await fs.ls("/"))
    ok(await fs.stat(observations=[Observation(path=f"/f{index}") for index in range(1_000)]))
    assert checks <= len(mounted)


async def test_glob_beneath_roots_that_hold_no_mount_point_judges_no_mount_point(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    judged: list[object] = []
    original = mounts_module.judge_in_hand

    async def spied(*args: Any) -> tuple[list[Observation], bool]:
        judged.append(args)
        return await original(*args)

    monkeypatch.setattr(mounts_module, "judge_in_hand", spied)
    fs = AsyncVirtualFileSystem()
    ok(await fs.write(path="/src/a.py", content="a", parents=True))
    await fs.add_mount(InMemoryStorage(), "/elsewhere")
    assert ok(await fs.glob("*.py", paths=("/src",))).paths == ("/src/a.py",)
    assert judged == []


async def test_glob_under_a_limit_asks_no_more_mounted_roots_than_the_limit_can_use() -> None:
    fs = AsyncVirtualFileSystem(storage=BindableStorage())
    children = [BindableStorage() for _index in range(5)]
    for index, child in enumerate(children):
        await fs.add_mount(child, f"/m{index}")
        child.calls.clear()
    assert len(ok(await fs.glob("/*", max_count=1)).observations) == 1
    assert sum(len(child.calls) for child in children) == 1


async def test_glob_under_a_limit_passes_the_callers_columns_to_the_mounted_storage() -> None:
    fs = AsyncVirtualFileSystem(storage=BindableStorage())
    child = BindableStorage()
    await fs.add_mount(child, "/m")
    child.calls.clear()
    wanted = frozenset({"version"})
    ok(await fs.glob("/*", max_count=1, columns=wanted))
    assert child.calls == [("stat", {"path": "/", "columns": wanted})]


def deep_path() -> Path:
    """A legal path of 1,024 bytes, the longest a path may be."""
    return Path("/x" * 512)


@pytest.mark.parametrize("mounted", [(), ("/y",), ("/x/x", "/x/x/x/x", "/y")], ids=["root", "beside", "above"])
def test_finding_the_mount_that_holds_a_path_checks_no_path_again(
    mounted: tuple[str, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    deep = deep_path()
    table = {Path(path): Mount(Path(path), BindableStorage()) for path in ("/", *mounted)}
    listing = mounts_module.MountListing(table)
    checked: list[str] = []
    original = paths_module.validate_path

    def counted(path: str) -> tuple[bool, str]:
        checked.append(path)
        return original(path)

    monkeypatch.setattr(paths_module, "validate_path", counted)
    holder = listing.holder(deep)
    assert holder is not None
    assert holder.path == max((path for path in table if path == "/" or deep.startswith(path + "/")), key=len)
    assert checked == []


@pytest.mark.parametrize(("mounted", "steps"), [((), 0), (("/y",), 512)], ids=["root alone", "beside"])
def test_a_table_that_holds_only_the_root_answers_without_walking_the_path(
    mounted: tuple[str, ...], steps: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    table = {Path(path): Mount(Path(path), BindableStorage()) for path in ("/", *mounted)}
    listing = mounts_module.MountListing(table)
    walked: list[str] = []
    original = mounts_module._parent

    def counted(path: str) -> str:
        walked.append(path)
        return original(path)

    monkeypatch.setattr(mounts_module, "_parent", counted)
    holder = listing.holder(deep_path())
    assert holder is not None
    assert holder.path == "/"
    assert len(walked) == steps


# ----------------------------------------------------------------------
# A refused parent keeps its mount names
# ----------------------------------------------------------------------


async def test_glob_shows_no_mount_name_to_a_caller_whose_listing_is_refused() -> None:
    flat, deep = await world(mounted=True), await deep_mount()
    for search in (flat.glob("/*"), flat.glob("data"), deep.glob("/*"), deep.glob("**"), deep.glob("*", paths=("/a",))):
        refused = await search
        assert refused.success is False
        assert refused.observations == []


class StatFails(BindableStorage):
    """A child whose ``stat`` fails with a message of its own, and whose other verbs answer."""

    async def stat(self, *, path: Path | None = None, authority: Authority | None = None, **kwargs: Any) -> Result:
        return Result(ops=("stat",), errors=[classified(ErrorKind.backend_unavailable, detail="stat failed")])


async def test_a_mount_point_whose_parent_refused_the_glob_is_left_out_with_its_warning() -> None:
    fs = AsyncVirtualFileSystem()
    await fs.add_mount(InMemoryStorage(), "/x", authority=SYSTEM)
    await fs.add_mount(StatFails(), "/x/m", authority=SYSTEM)
    await fs.add_mount(StatFails(), "/y", authority=SYSTEM)
    ok(await fs.set_posture("/x", "none", authority=SYSTEM))
    found = ok(await fs.glob("**"))
    assert set(found.paths) == {"/x", "/y"}
    assert {(error.kind, error.source) for error in found.errors} == {
        (ErrorKind.unauthenticated, "/x"),
        (ErrorKind.backend_unavailable, "/y"),
    }


async def test_a_root_that_fails_its_probe_hides_no_mount_point_beneath_another_root() -> None:
    fs = await roads_world()
    found = await fs.glob("m", paths=("/a/x", "/a/nope"), authority=GRACE)
    assert found.paths == ("/a/x/m",)
    assert misses(found) == [(ErrorKind.not_found, "/a", "/a/nope")]


class PathlessProbe(BindableStorage):
    """A storage whose ``stat`` of a batch fails with an error that names no path."""

    async def stat(self, *, path: Path | None = None, authority: Authority | None = None, **kwargs: Any) -> Result:
        if path is not None:
            return await super().stat(path=path, authority=authority, **kwargs)
        return Result(ops=("stat",), errors=[classified(ErrorKind.backend_unavailable)])


async def test_a_probe_failure_that_names_no_root_hides_only_the_mount_points_of_the_mount_probed() -> None:
    fs = AsyncVirtualFileSystem(storage=BindableStorage())
    await fs.add_mount(PathlessProbe(), "/broken")
    await fs.add_mount(BindableStorage(), "/broken/m")
    await fs.add_mount(BindableStorage(), "/ok")
    await fs.add_mount(BindableStorage(), "/ok/road/m", parents=True)
    found = await fs.glob("m", paths=("/broken", "/ok/road"))
    assert found.paths == ("/ok/road/m",)
    assert [(error.kind, error.source) for error in found.errors] == [(ErrorKind.backend_unavailable, "/broken")]
    alone = AsyncVirtualFileSystem(storage=PathlessProbe())
    await alone.add_mount(BindableStorage(), "/y/m", parents=True)
    assert (await alone.glob("m", paths=("/x", "/y"))).paths == ()


class PartialHolder(BindableStorage):
    """A parent whose ``glob`` answers its rows and fails at ``/bad`` when that root is in its scope."""

    async def glob(self, *, authority: Authority | None = None, **kwargs: Any) -> Result:
        scope = kwargs.get("scope")
        errors = [classified(ErrorKind.backend_unavailable, Path("/bad"))] if scope and "/bad" in scope.roots else []
        return Result(ops=("glob",), observations=[Observation(path="/ok/marker", kind="file")], errors=errors)


async def test_a_parent_that_fails_one_root_keeps_the_mount_points_beneath_its_other_roots() -> None:
    fs = AsyncVirtualFileSystem(storage=PartialHolder())
    await fs.add_mount(BindableStorage(), "/ok/m", parents=True)
    await fs.add_mount(BindableStorage(), "/bad/m", parents=True)
    found = await fs.glob("m*", paths=("/ok", "/bad"))
    assert set(found.paths) == {"/ok/m", "/ok/marker"}
    assert [(error.kind, error.path) for error in found.errors] == [(ErrorKind.backend_unavailable, "/bad")]


class GlobFails(BindableStorage):
    """A storage whose ``glob`` fails with an error that names no path."""

    async def glob(self, *, authority: Authority | None = None, **kwargs: Any) -> Result:
        return Result(ops=("glob",), errors=[classified(ErrorKind.backend_unavailable)])


async def test_a_limit_is_spent_only_on_mount_points_the_glob_shows() -> None:
    fs = AsyncVirtualFileSystem(storage=BindableStorage())
    await fs.add_mount(GlobFails(), "/a")
    await fs.add_mount(BindableStorage(), "/z")
    hidden, shown = BindableStorage(), BindableStorage()
    await fs.add_mount(hidden, "/a/m")
    await fs.add_mount(shown, "/z/m")
    hidden.calls.clear()
    shown.calls.clear()
    found = await fs.glob("m", max_count=1)
    assert found.paths == ("/z/m",)
    stats = [[call for call in child.calls if call[0] == "stat"] for child in (hidden, shown)]
    assert stats == [[], [("stat", {"path": "/", "columns": None})]]


async def test_a_mount_point_whose_parent_was_not_asked_to_glob_still_shows() -> None:
    parent = BindableStorage()
    fs = AsyncVirtualFileSystem(storage=BindableStorage(caps=parent.capabilities() - {"glob"}))
    await fs.add_mount(BindableStorage(), "/m")
    assert ok(await fs.glob("/*")).paths == ("/m",)


async def test_the_anonymous_caller_on_a_closed_root_is_refused_a_directory_above_a_mount() -> None:
    fs = await deep_mount()
    for refused in (await fs.stat("/a"), await fs.tree("/a"), await fs.ls("/a")):
        assert [error.kind for error in refused.errors] == [ErrorKind.unauthenticated]
        assert refused.observations == []
    located = await fs.locate("/a", exists=True)
    assert (located.exists, located.note) == (None, "Unauthenticated")


@pytest.mark.parametrize("kind", [ErrorKind.permission_denied, ErrorKind.not_found])
async def test_a_mount_that_refuses_the_caller_in_any_way_shows_bare_with_no_record(kind: ErrorKind) -> None:
    class Refusing(BindableStorage):
        async def stat(self, *, path: Path | None = None, authority: Authority | None = None, **kwargs: Any) -> Result:
            return Result(ops=("stat",), errors=[classified(kind, Path("/"))])

    fs = AsyncVirtualFileSystem(storage=BindableStorage())
    await fs.add_mount(Refusing(), "/m")
    for listing in (fs.ls("/"), fs.tree("/", max_depth=1), fs.glob("/*")):
        listed = ok(await listing)
        assert [(row.path, row.populated) for row in listed.observations] == [("/m", BARE)]
        assert listed.errors == []


async def test_a_named_caller_who_holds_nothing_is_told_the_first_missing_part_of_a_path() -> None:
    fs = await deep_mount()
    missing = await fs.stat("/a/nope", authority=GRACE)
    assert [(error.kind, error.path) for error in missing.errors] == [(ErrorKind.not_found, "/a")]
    assert ok(await fs.glob("*.md", paths=("/a",), authority=GRACE)).observations == []
    assert ok(await fs.glob("*.md", paths=("/a",), authority=GRACE)).errors == []


async def test_a_directory_above_a_removed_mount_is_no_longer_shown() -> None:
    fs = await deep_mount()
    assert ok(await fs.ls("/", authority=GRACE)).paths == ("/a",)
    await fs.remove_mount("/a/b", authority=SYSTEM)
    assert ok(await fs.ls("/", authority=GRACE)).paths == ()


async def test_a_missing_plain_path_is_refused_by_tree_on_a_kernel_with_mounts() -> None:
    fs = await deep_mount()
    missing = await fs.tree("/nope", authority=SYSTEM)
    assert [error.kind for error in missing.errors] == [ErrorKind.not_found]


# ----------------------------------------------------------------------
# What a mounted storage says is not taken on trust
# ----------------------------------------------------------------------


class FileAtRoot(BindableStorage):
    """A child whose ``stat`` says its root is a file."""

    async def stat(self, *, path: Path | None = None, authority: Authority | None = None, **kwargs: Any) -> Result:
        return Result(ops=("stat",), observations=[Observation(path="/", kind="file", size_bytes=MARK)])


class Pathless(RecorderStorage):
    """A child whose every verb fails with an error that names no path."""

    def _answer(self, op: str, kwargs: dict[str, Any], authority: Authority | None = None) -> Result:
        return Result(ops=(op,), errors=[classified(ErrorKind.backend_unavailable)])


class Noted(BindableStorage):
    """A child whose ``stat`` succeeds with no row and one warning of its own."""

    async def stat(self, *, path: Path | None = None, authority: Authority | None = None, **kwargs: Any) -> Result:
        return Result(ops=("stat",), errors=[classified(ErrorKind.truncated, severity=Severity.warning)])


class Down(RecorderStorage):
    """A child whose every verb fails on the wire, with a message that names the verb."""

    def _answer(self, op: str, kwargs: dict[str, Any], authority: Authority | None = None) -> Result:
        msg = f"{op} timed out"
        raise TransportError(msg)


async def test_a_mount_whose_root_is_not_a_directory_shows_bare() -> None:
    fs = AsyncVirtualFileSystem(storage=BindableStorage())
    await fs.add_mount(FileAtRoot(), "/m")
    for listing in (fs.ls("/"), fs.tree("/", max_depth=1), fs.glob("/*")):
        assert [(row.path, row.populated) for row in ok(await listing).observations] == [("/m", BARE)]


class FailedWithRow(RootedStorage):
    """A child whose ``stat`` returns the row of its root beside a failure."""

    async def stat(self, *, authority: Authority | None = None, **kwargs: Any) -> Result:
        return Result(ops=("stat",), observations=[self.ROOT], errors=[classified(ErrorKind.backend_unavailable)])


async def test_a_row_that_comes_with_a_failure_is_not_shown_at_a_mount_point() -> None:
    fs = AsyncVirtualFileSystem(storage=BindableStorage())
    await fs.add_mount(FailedWithRow(), "/m")
    for listing in (fs.ls("/"), fs.tree("/", max_depth=1), fs.glob("/*")):
        listed = ok(await listing)
        assert [(row.path, row.populated) for row in listed.observations] == [("/m", BARE)]
        assert [(error.kind, error.severity) for error in listed.errors] == [
            (ErrorKind.backend_unavailable, Severity.warning)
        ]


async def test_a_failure_that_names_no_path_becomes_a_warning_at_the_mount_path() -> None:
    fs = AsyncVirtualFileSystem(storage=BindableStorage())
    await fs.add_mount(Pathless(), "/m")
    [warning] = ok(await fs.ls("/")).errors
    assert (warning.kind, warning.severity, warning.path) == (ErrorKind.backend_unavailable, Severity.warning, "/m")


async def test_a_record_of_a_mounted_storage_that_answers_is_kept() -> None:
    fs = AsyncVirtualFileSystem(storage=BindableStorage())
    await fs.add_mount(Noted(), "/m")
    for listing in (fs.ls("/"), fs.tree("/", max_depth=1), fs.glob("/*")):
        listed = ok(await listing)
        assert [(error.kind, error.source) for error in listed.errors] == [(ErrorKind.truncated, "/m")]


async def test_tree_reports_a_mount_that_fails_once() -> None:
    fs = AsyncVirtualFileSystem(storage=BindableStorage())
    await fs.add_mount(Down(), "/m")
    listed = ok(await fs.tree("/"))
    assert listed.paths == ("/m",)
    [warning] = listed.errors
    assert "tree timed out" in warning.message


async def test_a_mounted_storage_that_raises_raises_out_of_the_listing() -> None:
    class Broken(BindableStorage):
        async def stat(self, *, path: Path | None = None, authority: Authority | None = None, **kwargs: Any) -> Result:
            msg = "a fault in the storage"
            raise RuntimeError(msg)

    fs = AsyncVirtualFileSystem(storage=BindableStorage())
    await fs.add_mount(Broken(), "/m")
    with pytest.raises(RuntimeError, match="a fault in the storage"):
        await fs.ls("/")


# ----------------------------------------------------------------------
# A directory above a mount, as its own storage answers for it
# ----------------------------------------------------------------------


class Answered(BindableStorage):
    """A parent that answers ``/road`` with ``rows`` and ``errors``, and binds everything else."""

    def __init__(self, rows: list[Observation], errors: list[Any]) -> None:
        super().__init__()
        self.rows, self.errors, self.active = rows, errors, False

    async def _road(self, op: Op, path: Path | None, kwargs: dict[str, Any]) -> Result:
        if not self.active or path != "/road":
            return await getattr(super(), op)(path=path, **kwargs)
        rows = [row for row in self.rows if op != "stat"]
        return Result(ops=(op,), observations=rows, errors=self.errors, trace_token="t")

    async def stat(self, *, path: Path | None = None, authority: Authority | None = None, **kwargs: Any) -> Result:
        return await self._road("stat", path, kwargs)

    async def ls(self, *, path: Path | None = None, authority: Authority | None = None, **kwargs: Any) -> Result:
        return await self._road("ls", path, kwargs)

    async def tree(self, *, path: Path | None = None, authority: Authority | None = None, **kwargs: Any) -> Result:
        return await self._road("tree", path, kwargs)


async def answered(rows: list[Observation], errors: list[Any]) -> AsyncVirtualFileSystem:
    parent = Answered(rows, errors)
    fs = AsyncVirtualFileSystem(storage=parent)
    await fs.add_mount(BindableStorage(), "/road/m", parents=True)
    parent.active = True
    return fs


KEPT = Observation(path="/road/kept.md", kind="file")
NOTE = classified(ErrorKind.truncated, Path("/road"), severity=Severity.warning)


async def test_a_directory_above_a_mount_that_its_storage_misses_keeps_the_other_rows_and_records() -> None:
    fs = await answered([KEPT], [classified(ErrorKind.not_found, Path("/road")), NOTE])
    for listing, paths in ((fs.ls("/road"), ("/road/kept.md", "/road/m")), (fs.stat("/road"), ("/road",))):
        listed = ok(await listing)
        assert listed.paths == paths
        assert [error.kind for error in listed.errors] == [ErrorKind.truncated]
    assert set(ok(await fs.tree("/road")).paths) == {"/road/kept.md", "/road/m"}


async def test_a_miss_beneath_a_directory_above_a_mount_is_a_miss_like_any_other() -> None:
    fs = await answered([KEPT], [classified(ErrorKind.not_found, Path("/road/gone.md"))])
    for listing, paths in (
        (fs.ls("/road"), ("/road/kept.md", "/road/m")),
        (fs.tree("/road"), ("/road/kept.md", "/road/m")),
        (fs.stat("/road"), ("/road",)),
    ):
        listed = ok(await listing)
        assert set(listed.paths) == set(paths)
        assert listed.errors == []
    located = await fs.locate("/road", exists=True)
    assert (located.exists, located.kind, located.note) == (True, "directory", None)


async def test_a_failed_listing_never_returns_the_directory_beneath_a_mount() -> None:
    covered = Observation(path="/road/m", kind="directory", version=77)
    fs = await answered([covered, KEPT], [classified(ErrorKind.backend_unavailable, Path("/road/gone.md"))])
    for listing in (fs.ls("/road"), fs.tree("/road"), fs.ls(observations=batch_of("/road", "/road"))):
        refused = await listing
        assert set(refused.paths) == {"/road/kept.md"}
        assert {(error.kind, error.path) for error in refused.errors} == {
            (ErrorKind.backend_unavailable, "/road/gone.md")
        }


class FarRoad(BindableStorage):
    """A parent whose ``stat`` of ``/road`` gives no row and the one error in ``error``."""

    error: Any = None

    async def stat(self, *, path: Path | None = None, authority: Authority | None = None, **kwargs: Any) -> Result:
        if self.error is None or path != "/road":
            return await super().stat(path=path, authority=authority, **kwargs)
        return Result(ops=("stat",), errors=[self.error])


# A miss so deep that, with the mount's path in front, it is longer than a path may be.
TOO_DEEP = Path("/road" + ("/" + "d" * 247) * 4)


@pytest.mark.parametrize(
    ("error", "shown"),
    [
        (classified(ErrorKind.not_found, Path("/road/gone"), target=Path("/road")), True),
        (classified(ErrorKind.not_found, TOO_DEEP, target=Path("/road")), True),
        (classified(ErrorKind.permission_denied, Path("/road"), detail="the road is closed"), False),
    ],
    ids=["a miss beneath it", "a miss too deep to name", "a refusal"],
)
async def test_locate_and_stat_agree_on_a_directory_above_a_mount(error: Any, shown: bool) -> None:
    parent = FarRoad()
    fs = AsyncVirtualFileSystem(storage=BindableStorage())
    site = "/" + "z" * 80
    await fs.add_mount(parent, site)
    await fs.add_mount(BindableStorage(), f"{site}/road/m", parents=True)
    parent.error = error
    stat = await fs.stat(f"{site}/road")
    located = await fs.locate(f"{site}/road", exists=True)
    assert stat.success is shown
    if shown:
        assert [(row.path, row.populated) for row in stat.observations] == [(f"{site}/road", BARE)]
        assert (located.exists, located.kind, located.note) == (True, "directory", None)
    else:
        assert stat.observations == []
        [refusal] = stat.errors
        assert (located.exists, located.kind, located.note) == (None, None, refusal.message)


async def test_a_directory_above_a_mount_that_its_storage_answers_with_nothing_is_there() -> None:
    fs = await answered([], [])
    assert [(row.path, row.populated) for row in ok(await fs.stat("/road")).observations] == [("/road", BARE)]
    located = await fs.locate("/road", exists=True)
    assert (located.exists, located.kind) == (True, "directory")


class Unreachable(BindableStorage):
    """A storage whose ``stat``, ``ls`` and ``tree`` fail on the wire once ``down`` is set."""

    down = False

    def _wire(self) -> None:
        if self.down:
            msg = "offline"
            raise TransportError(msg)

    async def stat(self, *, path: Path | None = None, authority: Authority | None = None, **kwargs: Any) -> Result:
        self._wire()
        return await super().stat(path=path, authority=authority, **kwargs)

    async def ls(self, *, path: Path | None = None, authority: Authority | None = None, **kwargs: Any) -> Result:
        self._wire()
        return await super().ls(path=path, authority=authority, **kwargs)

    async def tree(self, *, authority: Authority | None = None, **kwargs: Any) -> Result:
        self._wire()
        return await super().tree(authority=authority, **kwargs)


async def test_a_storage_that_cannot_answer_gets_no_row_made_up_for_a_directory_above_a_mount() -> None:
    parent = Unreachable()
    fs = AsyncVirtualFileSystem(storage=BindableStorage())
    await fs.add_mount(parent, "/box")
    await fs.add_mount(BindableStorage(), "/box/road/m", parents=True)
    parent.down = True
    for answer in (
        fs.stat("/box/road"),
        fs.stat(observations=batch_of("/box/road", "/box/road")),
        fs.ls("/box/road"),
        fs.tree("/box/road"),
        fs.glob("road", paths=("/box/road",)),
    ):
        failed = await answer
        assert failed.observations == []
        assert [error.kind for error in failed.errors] == [ErrorKind.backend_unavailable]


class Halved(BindableStorage):
    """A parent whose ``stat`` of a batch gives one row for ``/road`` and one ``not_found`` for it."""

    async def stat(self, *, path: Path | None = None, authority: Authority | None = None, **kwargs: Any) -> Result:
        if path is not None:
            return await super().stat(path=path, authority=authority, **kwargs)
        road = Path("/road")
        row = Observation(path=road, kind="directory", version=MARK)
        return Result(ops=("stat",), observations=[row], errors=[classified(ErrorKind.not_found, road)])


async def test_a_batch_fills_only_the_rows_its_storage_did_not_give_for_a_directory_above_a_mount() -> None:
    fs = AsyncVirtualFileSystem(storage=Halved())
    await fs.add_mount(BindableStorage(), "/road/m", parents=True)
    twice = ok(await fs.stat(observations=batch_of("/road", "/road")))
    assert [(row.path, row.version) for row in twice.observations] == [("/road", MARK), ("/road", None)]
    assert twice.errors == []
    once = ok(await fs.stat(observations=batch_of("/road")))
    assert [(row.path, row.version) for row in once.observations] == [("/road", MARK)]
    assert once.errors == []


class Judged(BindableStorage):
    """A parent whose ``stat`` gives no row and the errors that ``errors`` makes from the paths asked."""

    errors: Any = None

    async def stat(self, *, path: Path | None = None, authority: Authority | None = None, **kwargs: Any) -> Result:
        if self.errors is None:
            return await super().stat(path=path, authority=authority, **kwargs)
        asked = [path] if path is not None else [row.path for row in kwargs["observations"]]
        return Result(ops=("stat",), errors=self.errors(asked))


async def judged_world() -> tuple[AsyncVirtualFileSystem, Judged]:
    parent = Judged()
    fs = AsyncVirtualFileSystem(storage=parent)
    await fs.add_mount(BindableStorage(), "/road/m", parents=True)
    return fs, parent


def each_on_its_own(asked: list[Path]) -> list[ResultError]:
    kinds = {"/offline": ErrorKind.backend_unavailable}
    return [classified(kinds.get(path, ErrorKind.not_found), path, target=path) for path in asked]


async def test_each_target_of_a_batch_is_judged_on_its_own_errors() -> None:
    fs, parent = await judged_world()
    parent.errors = each_on_its_own
    stat = await fs.stat(observations=batch_of("/road", "/offline"))
    assert [(row.path, row.populated) for row in stat.observations] == [("/road", BARE)]
    assert [(error.kind, error.path) for error in stat.errors] == [(ErrorKind.backend_unavailable, "/offline")]
    found = await fs.glob("m", paths=("/road", "/offline"))
    assert found.paths == ("/road/m",)
    assert [(error.kind, error.path) for error in found.errors] == [(ErrorKind.backend_unavailable, "/offline")]


@pytest.mark.parametrize("where", [None, Path("/")], ids=["at no path", "at the storage's root"])
async def test_a_failure_no_target_can_claim_withholds_every_bare_row(where: Path | None) -> None:
    fs, parent = await judged_world()
    parent.errors = lambda _asked: [classified(ErrorKind.backend_unavailable, where)]
    stat = await fs.stat(observations=batch_of("/road", "/other"))
    assert stat.observations == []
    assert [error.kind for error in stat.errors] == [ErrorKind.backend_unavailable]


@pytest.mark.parametrize(
    "made",
    [
        lambda _asked: [classified(ErrorKind.not_found, Path("/road/part"))],
        lambda _asked: [classified(ErrorKind.not_found)],
        lambda _asked: [classified(ErrorKind.backend_unavailable, Path("/"))],
        lambda _asked: [classified(ErrorKind.permission_denied, Path("/road"), target=Path("/road"))],
    ],
    ids=["a miss beneath it", "a miss at no path", "a failure at the root", "a refusal of it"],
)
async def test_a_single_path_and_a_batch_of_that_path_give_the_same_answer(made: Any) -> None:
    fs, parent = await judged_world()
    parent.errors = made

    def shape(result: Result) -> tuple[object, ...]:
        rows = [(row.path, row.populated) for row in result.observations]
        return rows, [(error.kind, error.path, error.severity) for error in result.errors]

    assert shape(await fs.stat("/road")) == shape(await fs.stat(observations=batch_of("/road")))


class BadRoad(BindableStorage):
    """A parent whose ``stat`` of a batch fails at ``/road``, or whose ``glob`` fails there, as ``fails`` says."""

    fails = ""

    async def stat(self, *, path: Path | None = None, authority: Authority | None = None, **kwargs: Any) -> Result:
        if path is not None or self.fails != "stat":
            return await super().stat(path=path, authority=authority, **kwargs)
        return Result(ops=("stat",), errors=[classified(ErrorKind.backend_unavailable, Path("/road"))])

    async def glob(self, *, authority: Authority | None = None, **kwargs: Any) -> Result:
        failed = [classified(ErrorKind.backend_unavailable, Path("/road"))] if self.fails == "glob" else []
        return Result(ops=("glob",), errors=failed)


async def test_a_failed_probe_of_a_root_hides_only_what_lies_strictly_beneath_it() -> None:
    parent = BadRoad()
    fs = AsyncVirtualFileSystem(storage=parent)
    await fs.add_mount(BindableStorage(), "/road/m", parents=True)
    assert ok(await fs.glob("*", paths=("/",))).paths == ("/road", "/road/m")
    parent.fails = "stat"
    probed = await fs.glob("*", paths=("/", "/road"))
    assert probed.paths == ("/road",)
    assert [(error.kind, error.path) for error in probed.errors] == [(ErrorKind.backend_unavailable, "/road")]
    # A failed glob names a region whose own top is in it.
    parent.fails = "glob"
    listed = await fs.glob("*", paths=("/",))
    assert listed.paths == ()
    assert [(error.kind, error.path) for error in listed.errors] == [(ErrorKind.backend_unavailable, "/road")]


async def test_the_answer_for_a_directory_above_a_mount_keeps_its_storage_envelope() -> None:
    fs = await answered([KEPT], [])
    for listing in (fs.ls("/road"), fs.stat("/road")):
        assert ok(await listing).model_extra == {"trace_token": "t"}


# ----------------------------------------------------------------------
# One listing reads one mount table
# ----------------------------------------------------------------------


class Held(BindableStorage):
    """A parent that lists ``/anchor`` and ``/site`` at its root, and can hold that listing until released."""

    def __init__(self) -> None:
        super().__init__()
        self.hold = False
        self.started, self.release = asyncio.Event(), asyncio.Event()

    async def _root(self, op: Op, path: Path | None) -> Result:
        if path != "/":
            return Result(ops=(op,))
        if self.hold:
            self.started.set()
            await self.release.wait()
        rows = [Observation(path=name, kind="directory", version=17) for name in ("/anchor", "/site")]
        return Result(ops=(op,), observations=rows)

    async def ls(self, *, path: Path | None = None, authority: Authority | None = None, **kwargs: Any) -> Result:
        return await self._root("ls", path)

    async def tree(self, *, path: Path | None = None, authority: Authority | None = None, **kwargs: Any) -> Result:
        return await self._root("tree", path)


async def held_listing(verb: str) -> tuple[AsyncVirtualFileSystem, Held, asyncio.Task[Result]]:
    parent = Held()
    fs = AsyncVirtualFileSystem(storage=parent)
    await fs.add_mount(RootedStorage(), "/anchor")
    parent.hold = True
    pending = asyncio.create_task(fs.ls("/") if verb == "ls" else fs.tree("/", max_depth=1))
    await asyncio.wait_for(parent.started.wait(), 5)
    parent.hold = False
    return fs, parent, pending


@pytest.mark.parametrize("verb", ["ls", "tree"])
async def test_a_mount_added_while_a_listing_waits_leaves_that_listing_as_it_began(verb: str) -> None:
    fs, parent, pending = await held_listing(verb)
    await fs.add_mount(RootedStorage(), "/site")
    parent.release.set()
    listed = ok(await asyncio.wait_for(pending, 5))
    assert {(row.path, row.version) for row in listed.observations} == {("/anchor", 3), ("/site", 17)}


@pytest.mark.parametrize("verb", ["ls", "tree"])
async def test_closing_the_kernel_while_a_listing_waits_leaves_that_listing_as_it_began(verb: str) -> None:
    fs, parent, pending = await held_listing(verb)
    await fs.close()
    parent.release.set()
    listed = ok(await asyncio.wait_for(pending, 5))
    # The mount is still listed as a mount. Its storage is not asked once the kernel is closed.
    assert {(row.path, row.version) for row in listed.observations} == {("/anchor", None), ("/site", 17)}
    assert [(error.kind, error.severity) for error in listed.errors] == [
        (ErrorKind.backend_unavailable, Severity.warning)
    ]


class HeldGlob(BindableStorage):
    """A parent whose ``glob`` waits until it is released."""

    def __init__(self) -> None:
        super().__init__()
        self.started, self.release = asyncio.Event(), asyncio.Event()

    async def glob(self, *, authority: Authority | None = None, **kwargs: Any) -> Result:
        self.started.set()
        await self.release.wait()
        return Result(ops=("glob",))


@pytest.mark.parametrize("roots", [(), ("/",)], ids=["whole", "named"])
@pytest.mark.parametrize("cap", [None, 1], ids=["no limit", "a limit"])
async def test_a_glob_that_finds_the_kernel_closed_asks_no_storage(cap: int | None, roots: tuple[str, ...]) -> None:
    parent, child = HeldGlob(), BindableStorage()
    fs = AsyncVirtualFileSystem(storage=parent)
    await fs.add_mount(child, "/m")
    pending = asyncio.create_task(fs.glob("m", paths=roots, max_count=cap))
    await asyncio.wait_for(parent.started.wait(), 5)
    await fs.close()
    child.calls.clear()
    parent.release.set()
    found = await asyncio.wait_for(pending, 5)
    assert child.calls == []
    # The mounted root is refused as closed, so it shows as any mounted root that cannot answer.
    assert [(row.path, row.populated) for row in found.observations] == [("/m", BARE)]
    assert [(error.kind, error.severity) for error in found.errors] == [
        (ErrorKind.backend_unavailable, Severity.warning)
    ]


class Watched(BindableStorage):
    """A storage that records each call made on it once its kernel's mount table is empty."""

    def __init__(self) -> None:
        super().__init__()
        self.fs: AsyncVirtualFileSystem | None = None
        self.late: list[str] = []

    def _watch(self, op: str) -> None:
        if self.fs is not None and not self.fs.mounts():
            self.late.append(op)

    def _answer(self, op: str, kwargs: dict[str, Any], authority: Authority | None = None) -> Result:
        self._watch(op)
        return super()._answer(op, kwargs, authority)

    async def stat(self, *, path: Path | None = None, authority: Authority | None = None, **kwargs: Any) -> Result:
        self._watch("stat")
        return await super().stat(path=path, authority=authority, **kwargs)

    async def ls(self, *, path: Path | None = None, authority: Authority | None = None, **kwargs: Any) -> Result:
        self._watch("ls")
        return await super().ls(path=path, authority=authority, **kwargs)


@pytest.mark.parametrize("verb", ["ls", "tree", "stat of a batch", "glob"])
async def test_no_storage_is_called_once_a_close_lands_beside_a_call(verb: str) -> None:
    root, child = Watched(), Watched()
    fs = AsyncVirtualFileSystem(storage=root)
    await fs.add_mount(child, "/m")
    root.fs = child.fs = fs
    calls = {
        "ls": lambda: fs.ls("/"),
        "tree": lambda: fs.tree("/"),
        "stat of a batch": lambda: fs.stat(observations=batch_of("/m", "/")),
        "glob": lambda: fs.glob("/*"),
    }
    answer, _closed = await asyncio.gather(calls[verb](), fs.close())
    assert root.late == child.late == []
    assert answer.observations == []
    assert ErrorKind.backend_unavailable in [error.kind for error in answer.errors]


class Closing(Watched):
    """A mounted storage whose ``stat`` closes its kernel before it answers."""

    async def stat(self, *, path: Path | None = None, authority: Authority | None = None, **kwargs: Any) -> Result:
        assert self.fs is not None
        await self.fs.close()
        return await BindableStorage.stat(self, path=path, authority=authority, **kwargs)


@pytest.mark.parametrize("verb", ["ls", "glob"])
async def test_a_close_that_lands_while_mounted_roots_are_asked_stops_the_ones_not_yet_asked(verb: str) -> None:
    first, second = Closing(), Watched()
    fs = AsyncVirtualFileSystem(storage=BindableStorage())
    await fs.add_mount(first, "/a")
    await fs.add_mount(second, "/b")
    first.fs = second.fs = fs
    listed = await (fs.ls("/") if verb == "ls" else fs.glob("/*"))
    assert second.late == []
    assert [(row.path, row.populated) for row in listed.observations][1] == ("/b", BARE)


class HeldRoot(RootedStorage):
    """A child whose ``stat`` waits until it is released."""

    def __init__(self) -> None:
        super().__init__()
        self.started, self.release = asyncio.Event(), asyncio.Event()

    async def stat(self, *, authority: Authority | None = None, **kwargs: Any) -> Result:
        self.started.set()
        await self.release.wait()
        return await super().stat(authority=authority, **kwargs)


async def test_a_mount_removed_while_a_glob_waits_is_returned_once() -> None:
    fs = AsyncVirtualFileSystem(storage=CoveredStorage())
    child = HeldRoot()
    await fs.add_mount(child, "/data")
    pending = asyncio.create_task(fs.glob("data"))
    await asyncio.wait_for(child.started.wait(), 5)
    await fs.remove_mount("/data")
    child.release.set()
    assert ok(await asyncio.wait_for(pending, 5)).paths.count("/data") == 1


class Marked(BindableStorage):
    """A child whose root and whose one match carry its ``version``, so each row says which storage gave it."""

    def __init__(self, version: int) -> None:
        super().__init__()
        self.version = version

    async def stat(self, *, authority: Authority | None = None, **kwargs: Any) -> Result:
        self.calls.append(("stat", kwargs))
        return Result(ops=("stat",), observations=[Observation(path="/", kind="directory", version=self.version)])

    def _match(self, op: Op) -> Result:
        self.calls.append((op, {}))
        return Result(ops=(op,), observations=[Observation(path=f"/v{self.version}", kind="file")])

    async def glob(self, *, authority: Authority | None = None, **kwargs: Any) -> Result:
        return self._match("glob")

    async def grep(self, *, authority: Authority | None = None, **kwargs: Any) -> Result:
        return self._match("grep")

    async def search(self, *, authority: Authority | None = None, **kwargs: Any) -> Result:
        return self._match("search")


@pytest.mark.parametrize("verb", ["glob", "grep", "search"])
async def test_a_mount_replaced_while_a_search_plans_its_scope_leaves_that_search_as_it_began(
    verb: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    fs = AsyncVirtualFileSystem(storage=BindableStorage())
    await fs.add_mount(Marked(1), "/m")
    started, resume = asyncio.Event(), asyncio.Event()
    planned = fs._planned

    async def held(*args: Any) -> object:
        plan = await planned(*args)
        started.set()
        await resume.wait()
        return plan

    monkeypatch.setattr(fs, "_planned", held)
    pending = asyncio.create_task(getattr(fs, verb)("*" if verb == "glob" else "needle", paths=("/m",)))
    await asyncio.wait_for(started.wait(), 5)
    await fs.remove_mount("/m")
    replacement = Marked(2)
    await fs.add_mount(replacement, "/m")
    replacement.calls.clear()
    resume.set()
    found = ok(await asyncio.wait_for(pending, 5))
    assert {row.version for row in found.observations if row.version is not None} <= {1}
    assert {str(row.path) for row in found.observations} - {"/m"} == {"/m/v1"}
    assert replacement.calls == []


class Muted(BindableStorage):
    """A child that stops declaring ``stat`` once ``muted`` is set."""

    muted = False

    def capabilities(self) -> frozenset[Op]:
        return super().capabilities() - {"stat"} if self.muted else super().capabilities()


async def test_a_listing_reads_the_mount_as_update_mount_left_it() -> None:
    fs = AsyncVirtualFileSystem(storage=BindableStorage())
    child = Muted()
    await fs.add_mount(child, "/m")
    child.muted = True
    await fs.update_mount("/m", refresh_caps=True)
    child.calls.clear()
    ok(await fs.ls("/"))
    assert child.calls == []


# ----------------------------------------------------------------------
# A mount that loops, the trash view and a graph walk
# ----------------------------------------------------------------------


class Loop(BindableStorage):
    """A child that answers by asking the kernel it is mounted in for its own mount point, so it never ends."""

    def __init__(self, fs: AsyncVirtualFileSystem) -> None:
        super().__init__()
        self.fs = fs

    async def stat(self, *, path: Path | None = None, authority: Authority | None = None, **kwargs: Any) -> Result:
        return await self.fs.stat("/loop", authority=authority)

    async def tree(self, *, path: Path | None = None, authority: Authority | None = None, **kwargs: Any) -> Result:
        return await self.fs.tree("/loop", authority=authority)


async def test_a_mount_that_loops_back_on_its_kernel_shows_bare_with_the_budget_spent() -> None:
    fs = AsyncVirtualFileSystem()
    await fs.add_mount(Loop(fs), "/loop")
    for listing in (fs.ls("/"), fs.tree("/"), fs.glob("/*")):
        listed = ok(await listing)
        assert [(row.path, row.populated) for row in listed.observations] == [("/loop", BARE)]
        assert [(error.kind, error.severity, error.path) for error in listed.errors] == [
            (ErrorKind.budget_exhausted, Severity.warning, "/loop")
        ]
    assert [error.kind for error in (await fs.stat("/loop")).errors] == [ErrorKind.budget_exhausted]


@pytest.mark.parametrize("verb", ["glob", "grep", "search"])
async def test_a_search_with_named_roots_takes_one_hop(verb: str) -> None:
    fs = AsyncVirtualFileSystem(storage=BindableStorage(), hop_budget=1)
    await fs.add_mount(BindableStorage(), "/m")
    search = getattr(fs, verb)
    assert ok(await search("*" if verb == "glob" else "needle", paths=("/m/a", "/b"))).errors == []


class Interrupted(BindableStorage):
    """A storage whose ``stat`` and ``glob`` raise, or cancel the task that waits on them, as ``how`` says."""

    how = ""

    async def _interrupt(self) -> None:
        if self.how == "raise":
            msg = "a fault in the storage"
            raise RuntimeError(msg)
        if self.how == "cancel":
            task = asyncio.current_task()
            assert task is not None
            asyncio.get_running_loop().call_soon(task.cancel)
            await asyncio.Event().wait()

    async def stat(self, *, path: Path | None = None, authority: Authority | None = None, **kwargs: Any) -> Result:
        await self._interrupt()
        return await super().stat(path=path, authority=authority, **kwargs)

    async def glob(self, *, authority: Authority | None = None, **kwargs: Any) -> Result:
        await self._interrupt()
        return await super().glob(authority=authority, **kwargs)


@pytest.mark.parametrize("verb", ["stat", "glob"])
@pytest.mark.parametrize("how", ["raise", "cancel"])
async def test_a_hop_is_given_back_when_the_storage_raises_or_the_call_is_cancelled(how: str, verb: str) -> None:
    storage = Interrupted()
    fs = AsyncVirtualFileSystem(storage=storage, hop_budget=1)
    storage.how = how
    with pytest.raises((RuntimeError, asyncio.CancelledError)):
        await getattr(fs, verb)("/x")
    task = asyncio.current_task()
    assert task is not None
    if how == "cancel":
        task.uncancel()
    storage.how = ""
    assert ok(await getattr(fs, verb)("/x")).errors == []


async def test_the_trash_view_lists_a_deleted_row_at_a_mount_path() -> None:
    backend = InMemoryStorage()
    viewer, writer = AsyncVirtualFileSystem(storage=backend), AsyncVirtualFileSystem(storage=backend)
    await viewer.add_mount(InMemoryStorage(), "/m")
    ok(await writer.delete("/m"))
    for verb, args, kwargs in (
        ("ls", ("/.vfs/trash",), {}),
        ("tree", ("/.vfs/trash",), {}),
        ("stat", ("/.vfs/trash/m",), {}),
        ("glob", ("*",), {"paths": ("/.vfs/trash",)}),
    ):
        seen = ok(await getattr(viewer, verb)(*args, **kwargs)).paths
        assert seen == ok(await getattr(writer, verb)(*args, **kwargs)).paths
        assert "/m" in seen, verb


async def test_a_graph_walk_keeps_the_node_at_a_mount_point() -> None:
    fs = AsyncVirtualFileSystem()
    ok(await fs.mkdir("/m"))

    async def walked() -> list[tuple[str, str | None]]:
        found = ok(await fs.traverse("outbound", path="/", depth=1, edge_types=("fs",)))
        return [(row.path, row.edge_target) for row in found.observations]

    plain = await walked()
    await fs.add_mount(InMemoryStorage(), "/m")
    assert await walked() == plain


# ----------------------------------------------------------------------
# The order of a listing
# ----------------------------------------------------------------------


async def ordered_world() -> AsyncVirtualFileSystem:
    fs = AsyncVirtualFileSystem()
    ok(await fs.write(path="/a.md", content="a"))
    await fs.add_mount(InMemoryStorage(), "/m")
    ok(await fs.write(path="/m/x.md", content="x"))
    await fs.add_mount(InMemoryStorage(), "/n")
    ok(await fs.write(path="/n/y.md", content="y"))
    return fs


async def test_tree_lists_the_addressed_storage_first_and_then_each_mount_from_its_own_row() -> None:
    fs = await ordered_world()
    assert ok(await fs.tree("/")).paths == ("/a.md", "/m", "/m/x.md", "/n", "/n/y.md")


async def test_glob_returns_the_mount_points_and_the_directories_above_them_first() -> None:
    fs = await ordered_world()
    await fs.add_mount(InMemoryStorage(), "/r/s", parents=True)
    found = ok(await fs.glob("**")).paths
    assert found[:4] == ("/m", "/n", "/r", "/r/s")
    assert set(found[4:]) == {"/a.md", "/m/x.md", "/n/y.md"}


async def test_glob_returns_the_mount_points_in_path_order_whatever_order_they_were_added_in() -> None:
    mounted = [f"/d{index}/s/m" for index in range(12)]
    expected = sorted({path for mount in mounted for path in (mount, mount[:-2], mount[:-4])})
    for order in (mounted, mounted[::-1]):
        fs = AsyncVirtualFileSystem(storage=BindableStorage())
        for path in order:
            await fs.add_mount(BindableStorage(), path, parents=True)
        assert list(ok(await fs.glob("**")).paths) == expected
        assert list(ok(await fs.glob("**", max_count=4)).paths) == expected[:4]


async def test_glob_reports_a_mount_that_fails_once() -> None:
    fs = AsyncVirtualFileSystem(storage=BindableStorage())
    await fs.add_mount(Down(), "/m")
    found = ok(await fs.glob("**"))
    assert found.paths == ("/m",)
    [warning] = found.errors
    assert "glob timed out" in warning.message


class TreeAnswers(BindableStorage):
    """A mounted storage whose ``tree`` gives no row and the one error in ``error``."""

    error: Any = None

    async def tree(self, *, authority: Authority | None = None, **kwargs: Any) -> Result:
        return Result(ops=("tree",), errors=[self.error])


@pytest.mark.parametrize(
    ("error", "paths", "kinds"),
    [
        (classified(ErrorKind.backend_unavailable, Path("/")), ("/box",), [ErrorKind.backend_unavailable]),
        (classified(ErrorKind.not_found, Path("/")), ("/box", "/box/road", "/box/road/m"), []),
    ],
    ids=["a failure", "a miss"],
)
async def test_tree_judges_a_mounted_storage_before_it_adds_a_directory_that_storage_holds(
    error: Any, paths: tuple[str, ...], kinds: list[ErrorKind]
) -> None:
    box = TreeAnswers()
    fs = AsyncVirtualFileSystem(storage=BindableStorage())
    await fs.add_mount(box, "/box")
    await fs.add_mount(BindableStorage(), "/box/road/m", parents=True)
    box.error = error
    listed = ok(await fs.tree("/"))
    assert listed.paths == paths
    assert [error.kind for error in listed.errors] == kinds


async def test_tree_puts_a_directory_above_a_mount_under_the_mount_that_holds_it() -> None:
    parent = BindableStorage()
    fs = AsyncVirtualFileSystem(storage=parent)
    await fs.add_mount(BindableStorage(caps=parent.capabilities() - {"tree"}), "/outer")
    await fs.add_mount(BindableStorage(), "/outer/road/m", parents=True)
    assert ok(await fs.tree("/")).paths == ("/outer", "/outer/road", "/outer/road/m")
