"""Mount-spine visibility: synthesized directories, composed ls/tree, scoped
fan-out expansion, and spine mutation classification.
"""

from __future__ import annotations

from typing import Any

import pytest

from base_doubles import EchoFS, LimitedEchoFS, RecorderFS, RecorderStorage, _fan
from vfs.base2 import VirtualFileSystem
from vfs.models2 import Entry, Observation
from vfs.ops import MUTATING_OPS
from vfs.paths import Path
from vfs.results2 import Result, ResultError, VFSErrorKind

# ----------------------------------------------------------------------
# mount-spine visibility — the namespace is discoverable top-down
# ----------------------------------------------------------------------


class CannedStorage(RecorderStorage):
    """Backend answering each op from a canned Result, recording calls."""

    def __init__(self, answers: dict[str, Result] | None = None) -> None:
        super().__init__()
        self.answers = answers or {}

    def _answer(self, op: str, kwargs: dict[str, Any]) -> Result:
        self.calls.append((op, kwargs))
        return self.answers.get(op, Result(function=op, observations=[]))


class CannedFS(RecorderFS):
    """Node over a :class:`CannedStorage` terminal."""

    def __init__(self, answers: dict[str, Result] | None = None, **kwargs: Any) -> None:
        super().__init__(storage=CannedStorage(answers), **kwargs)

    async def _is_path_mountable(self, path: Path) -> tuple[bool, str]:
        # Canned rows are not namespace truth — always accept mounts.
        return True, ""


class SpyRouterFS(VirtualFileSystem):
    """Pure router recording its public read calls — proves a parent dispatched to it."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.reads: list[tuple[str, str | None]] = []

    async def stat(self, path=None, observations=None, *, columns=None, user_id=None) -> Result:  # type: ignore[override]
        self.reads.append(("stat", path))
        return await super().stat(path, observations, columns=columns, user_id=user_id)

    async def ls(self, path=None, observations=None, *, columns=None, user_id=None) -> Result:  # type: ignore[override]
        self.reads.append(("ls", path))
        return await super().ls(path, observations, columns=columns, user_id=user_id)


class ScopeSpyFS(EchoFS):
    """Echo mount recording the scope its public grep receives."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.scopes: list[tuple[str, ...]] = []

    async def grep(self, pattern: str, *, paths: tuple[str, ...] = (), **kwargs: Any) -> Result:  # type: ignore[override]
        self.scopes.append(tuple(paths))
        return await super().grep(pattern, paths=paths, **kwargs)


async def test_ls_root_merges_storage_and_mount_rows() -> None:
    # The acceptance criterion: stored entries, the mount-point row with the
    # mount's description, and the intermediate spine row — one local dispatch.
    root = CannedFS({"ls": Result(function="ls", observations=[Observation(path=Path("/notes.txt"), kind="file")])})
    await root.add_mount(RecorderFS(description="alpha docs"), "/a")
    await root.add_mount(RecorderFS(), "/b/c")
    result = await root.ls("/")
    assert result.success is True
    assert set(result.paths) == {"/notes.txt", "/a", "/b"}
    by_path = {str(o.path): o for o in result}
    assert by_path["/a"].kind == "directory"
    assert by_path["/a"].description == "alpha docs"
    assert by_path["/b"].kind == "directory"
    assert by_path["/b"].description is None
    assert root.calls[-1] == ("ls", {"path": "/", "columns": None})


async def test_spine_is_routable_on_a_pure_router() -> None:
    root = VirtualFileSystem()
    await root.add_mount(EchoFS(), "/data/a")
    await root.add_mount(EchoFS(), "/data/b")
    ls_root = await root.ls("/")
    assert ls_root.success is True
    assert ls_root.paths == ("/data",)
    ls_data = await root.ls("/data")
    assert set(ls_data.paths) == {"/data/a", "/data/b"}
    stat_data = await root.stat("/data")
    assert stat_data.one().kind == "directory"
    assert stat_data.one().description is None  # intermediates carry no metadata
    tree_root = await root.tree("/")
    assert set(tree_root.paths) == {"/data", "/data/a", "/data/b", "/data/a/hit.md", "/data/b/hit.md"}


async def test_ls_empty_pure_router_root_is_empty_success() -> None:
    # The root always exists; a path off the spine keeps today's not_found.
    root = VirtualFileSystem()
    result = await root.ls("/")
    assert result.success is True
    assert len(result) == 0
    assert result.function == "ls"
    ghost = await root.ls("/ghost")
    assert ghost.success is False
    assert ghost.errors[0].kind is VFSErrorKind.not_found


async def test_stat_root_always_answers_with_node_metadata() -> None:
    root = VirtualFileSystem(description="the top")
    row = (await root.stat("/")).one()
    assert row.path == "/"
    assert row.kind == "directory"
    assert row.description == "the top"


async def test_mount_point_reads_compose_through_the_child() -> None:
    # No parent-side special case: the parent dispatches rel '/' across the
    # boundary and the child's own spine answers for its root.
    outer = VirtualFileSystem()
    inner = SpyRouterFS(description="hub of mounts")
    await outer.add_mount(inner, "/hub")
    await inner.add_mount(EchoFS(), "/leaf")
    stat_hub = await outer.stat("/hub")
    assert stat_hub.one().path == "/hub"
    assert stat_hub.one().kind == "directory"
    assert stat_hub.one().description == "hub of mounts"
    ls_hub = await outer.ls("/hub")
    assert ls_hub.paths == ("/hub/leaf",)
    assert inner.reads == [("stat", "/"), ("ls", "/")]


async def test_tree_budgets_depth_across_the_spine() -> None:
    root = VirtualFileSystem()
    child = RecorderFS()
    await root.add_mount(child, "/data/a")
    depth1 = await root.tree("/", max_depth=1)
    assert depth1.paths == ("/data",)  # spine children only
    assert child.calls == []
    depth2 = await root.tree("/", max_depth=2)
    assert depth2.paths == ("/data", "/data/a")  # skeleton row kept, no dispatch
    assert child.calls == []
    await root.tree("/", max_depth=3)
    assert child.calls == [("tree", {"path": "/", "max_depth": 1, "columns": None})]
    child.calls.clear()
    await root.tree("/")
    assert child.calls == [("tree", {"path": "/", "max_depth": None, "columns": None})]


async def test_spine_tree_rejects_nonpositive_max_depth() -> None:
    root = VirtualFileSystem()
    await root.add_mount(EchoFS(), "/data/a")
    result = await root.tree("/", max_depth=0)
    assert result.success is False
    assert result.errors[0].kind == VFSErrorKind.invalid
    assert "max_depth must be >= 1" in result.errors[0].message


async def test_spine_tree_scopes_to_the_named_region() -> None:
    # A tree over one spine region ignores mounts outside it.
    root = VirtualFileSystem()
    a, b = RecorderFS(), RecorderFS()
    await root.add_mount(a, "/a/x")
    await root.add_mount(b, "/b/y")
    result = await root.tree("/a")
    assert result.success is True
    assert result.paths == ("/a/x",)
    assert b.calls == []


async def test_spine_tree_skips_incapable_mount_silently() -> None:
    # An incapable mount keeps its skeleton row but is never dispatched,
    # matching the unscoped fan-out rule.
    root = VirtualFileSystem()
    a = EchoFS()
    dim = LimitedEchoFS(caps=frozenset({"read"}))
    await root.add_mount(a, "/data/a")
    await root.add_mount(dim, "/data/b")
    result = await root.tree("/")
    assert result.success is True
    assert result.errors == []
    assert set(result.paths) == {"/data", "/data/a", "/data/b", "/data/a/hit.md"}
    assert dim.calls == []


async def test_scoped_fanout_expands_across_the_spine() -> None:
    # A storage-root scope reaches the mounts beneath it — narrowing a scope
    # no longer silently shrinks coverage.
    root = EchoFS(echo_path="/data/local.txt")
    inside = EchoFS(echo_path="/inside.txt")
    await root.add_mount(inside, "/data/a")
    result = await root.grep("g", paths=("/data",))
    assert result.success is True
    assert set(result.paths) == {"/data/local.txt", "/data/a/inside.txt"}
    assert root.calls[-1][1]["paths"] == ("/data",)  # self-storage stays scoped
    assert inside.calls[-1][1]["paths"] == ()  # the covered mount runs unscoped


@pytest.mark.parametrize("op", ["glob", "grep", "glean"])
async def test_scope_at_root_equals_unscoped(op: str) -> None:
    root = VirtualFileSystem()
    a, b = EchoFS(), EchoFS()
    await root.add_mount(a, "/a")
    await root.add_mount(b, "/b")
    scoped = await _fan(root, op, paths=("/",))
    unscoped = await _fan(root, op)
    assert scoped.paths == unscoped.paths == ("/a/hit.md", "/b/hit.md")
    assert a.calls[0][1]["paths"] == a.calls[1][1]["paths"] == ()


async def test_spine_scope_skips_incapable_mount_silently() -> None:
    # Expanded targets follow the unscoped rule: the caller named a region,
    # so one incapable catalog under it must not fail the query.
    root = VirtualFileSystem()
    a = EchoFS()
    dim = LimitedEchoFS(caps=frozenset({"read"}))
    await root.add_mount(a, "/data/a")
    await root.add_mount(dim, "/data/b")
    result = await root.grep("g", paths=("/data",))
    assert result.success is True
    assert result.errors == []
    assert result.paths == ("/data/a/hit.md",)
    assert dim.calls == []


async def test_scope_at_exact_mount_point_routes_into_the_mount() -> None:
    root = VirtualFileSystem()
    spy = ScopeSpyFS()
    await root.add_mount(spy, "/data/a")
    result = await root.grep("g", paths=("/data/a",))
    assert result.success is True
    assert result.paths == ("/data/a/hit.md",)
    assert spy.scopes == [("/",)]  # scoped dispatch, not an expansion


async def test_spine_scope_on_mountless_router_is_empty_success() -> None:
    result = await VirtualFileSystem().grep("g", paths=("/",))
    assert result.success is True
    assert len(result) == 0
    assert result.function == "grep"


async def test_overlapping_spine_and_mount_scopes_dispatch_once() -> None:
    # A spine expansion already covers its whole mount unscoped, so a second
    # scope resolving into that mount must not dispatch the terminal again.
    root = VirtualFileSystem()
    inside = EchoFS(echo_path="/x/1.txt")
    await root.add_mount(inside, "/data/a")
    for scopes in (("/data", "/data/a/x"), ("/data/a/x", "/data")):
        inside.calls.clear()
        result = await root.grep("g", paths=scopes)
        assert result.success is True
        assert result.paths == ("/data/a/x/1.txt",)
        assert len(inside.calls) == 1
        assert inside.calls[0][1]["paths"] == ()  # the region dispatch subsumes the narrower scope


async def test_absorb_does_not_promote_an_errorless_failure() -> None:
    # A success=False result with no errors is malformed; it must pass through
    # the spine composition as a failure, never be promoted to success.
    root = CannedFS({"ls": Result(function="ls", success=False)})
    await root.add_mount(RecorderFS(), "/data/a")
    result = await root.ls("/")
    assert result.success is False
    assert "/data" in result.paths  # synthesized rows still present


async def test_absorb_promotes_pure_absence_to_success() -> None:
    # Storage holding nothing at a spine path answers not_found; the mount
    # table makes the directory real, so the composed ls succeeds anyway.
    absent = Result(
        function="ls",
        success=False,
        errors=[ResultError(kind=VFSErrorKind.not_found, message="nf", path=Path("/"))],
    )
    root = CannedFS({"ls": absent})
    await root.add_mount(RecorderFS(), "/data/a")
    result = await root.ls("/")
    assert result.success is True
    assert result.errors == []
    assert result.paths == ("/data",)


async def test_stat_chained_over_root_ls_round_trips() -> None:
    # D1's output feeds straight back in: spine rows answer synthetically,
    # mount-point rows dispatch into their child's own root.
    canned_stat = Result(function="stat", observations=[Observation(path=Path("/notes.txt"), kind="file")])
    canned_ls = Result(function="ls", observations=[Observation(path=Path("/notes.txt"), kind="file")])
    root = CannedFS({"ls": canned_ls, "stat": canned_stat})
    await root.add_mount(RecorderFS(), "/data/a")
    await root.add_mount(RecorderFS(description="alpha"), "/top")
    listing = await root.ls("/")
    assert set(listing.paths) == {"/notes.txt", "/data", "/top"}
    result = await root.stat(observations=list(listing.observations))
    assert result.success is True
    assert set(result.paths) == {"/notes.txt", "/data", "/top"}
    by_path = {str(o.path): o for o in result}
    assert by_path["/data"].kind == "directory"  # answered synthetically
    assert by_path["/top"].kind == "directory"
    assert by_path["/top"].description == "alpha"  # the child's root row, rebased


async def test_spine_merge_is_left_wins_with_null_fill() -> None:
    # A stored directory coinciding with a spine row keeps its stored fields;
    # the synthesized description fills only where storage left null.
    stored = Observation(path=Path("/data/a"), kind="directory", size_bytes=7)
    root = CannedFS({"ls": Result(function="ls", observations=[stored])})
    await root.add_mount(RecorderFS(description="mounted"), "/data/a")
    row = (await root.ls("/data")).one()
    assert row.size_bytes == 7
    assert row.description == "mounted"


@pytest.mark.parametrize("target", ["/", "/data", "/data/deep"])
async def test_non_listing_verbs_classify_spine_paths_as_directories(target: str) -> None:
    # A spine path fails exactly the way a stored directory fails: wrong_kind
    # with the router-side path — never not_found.
    root = VirtualFileSystem()
    await root.add_mount(EchoFS(), "/data/deep/leaf")
    for call in (root.read(target), root.graph("descendants", path=target), root.run(target)):
        result = await call
        assert result.success is False
        assert result.errors[0].kind is VFSErrorKind.wrong_kind
        assert result.errors[0].path == target
    absent = await root.read("/data/ghost")
    assert absent.errors[0].kind is VFSErrorKind.not_found  # the two kinds never blur


async def test_grouped_mutations_reject_spine_targets_as_directories() -> None:
    # A spine directory is not a mutation target through any input shape:
    # the observation form classifies wrong_kind before touching storage.
    root = RecorderFS()
    child = RecorderFS()
    await root.add_mount(child, "/data/a")
    rows = [Observation(path=Path("/data"))]
    attempts = [
        await root.delete(observations=rows),
        await root.edit(observations=rows, old="a", new="b"),
        await root.delete(observations=[Observation(path=Path("/data")), Observation(path=Path("/f.txt"))]),
    ]
    for result in attempts:
        assert result.success is False
        assert result.errors[0].kind is VFSErrorKind.wrong_kind
        assert result.errors[0].path == "/data"
    assert all(op not in MUTATING_OPS for op, _ in root.calls)  # nothing dispatched
    assert child.calls == []


async def test_grouped_mutation_on_pure_router_spine_is_wrong_kind() -> None:
    root = VirtualFileSystem()
    await root.add_mount(RecorderFS(), "/data/a")
    result = await root.delete(observations=[Observation(path=Path("/data"))])
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.wrong_kind
    assert result.errors[0].path == "/data"


async def test_mutations_reaching_routability_on_spine_classify_wrong_kind() -> None:
    root = VirtualFileSystem()
    await root.add_mount(RecorderFS(), "/data/a")
    attempts = [
        await root.write(path="/data", content="x"),
        await root.edit(path="/data", old="a", new="b"),
        await root.delete("/data"),
        await root.mkdir("/data"),
        await root.move(src="/data", dest="/x.txt"),
        await root.copy(src="/y.txt", dest="/data"),
        await root.write(entries=[Entry(path=Path("/data"))]),
    ]
    for result in attempts:
        assert result.success is False
        assert result.errors[0].kind is VFSErrorKind.wrong_kind
        assert result.errors[0].path == "/data"


async def test_writes_under_a_mount_never_land_in_parent_storage() -> None:
    # The no-double-cover argument as executable fact: paths in a mount's
    # territory route away before reaching the parent impl.
    root = RecorderFS()
    child = RecorderFS()
    await root.add_mount(child, "/data/a")
    result = await root.write(path="/data/a/f.txt", content="x")
    assert result.success is True
    assert all(op != "write" for op, _ in root.calls)
    assert child.calls[-1][0] == "write"
    assert child.calls[-1][1]["path"] == "/f.txt"


async def test_tree_absorbs_storage_overlap_on_the_spine() -> None:
    # Parent storage rows on shared spine paths merge left-wins with the
    # skeleton; rows inside mount territory come only from the child.
    stored = Observation(path=Path("/data"), kind="directory", size_bytes=3)
    root = CannedFS({"tree": Result(function="tree", observations=[stored])})
    inside = EchoFS(echo_path="/inside.txt")
    await root.add_mount(inside, "/data/a")
    result = await root.tree("/")
    assert result.success is True
    by_path = {str(o.path): o for o in result}
    assert set(by_path) == {"/data", "/data/a", "/data/a/inside.txt"}
    assert by_path["/data"].size_bytes == 3  # the stored row survived the merge
