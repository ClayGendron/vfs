"""What a listing shows at a mount point: the mounted root, never the directory beneath it, and never hidden."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from tests.support.base_doubles import BindableStorage, RecorderStorage, TransportFailStorage
from vfs import AsyncVirtualFileSystem, InMemoryStorage
from vfs import mounts as mounts_module
from vfs.authority import Authority, Principal
from vfs.models import Observation
from vfs.paths import Path
from vfs.results import ErrorKind, Result
from vfs.results.kinds import Severity

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    Share = Callable[[AsyncVirtualFileSystem], Awaitable[None]]

SYSTEM = Authority.system()
ADA = Authority.of(Principal("ada"))
GRACE = Authority.of(Principal("grace"))

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
