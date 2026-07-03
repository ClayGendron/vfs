"""Tests for the rebuilt ``vfs.base2.VirtualFileSystem`` router.

Built up section by section alongside ``src/vfs/base2.py``.  These tests
exercise only the pure router — no storage, no sessions.  Storage behavior
belongs to ``DatabaseFileSystem`` and is tested elsewhere.
"""

from __future__ import annotations

from typing import Any

import pytest

from vfs.base2 import TwoPathOperation, VirtualFileSystem
from vfs.exceptions import (
    NotFoundError,
    ValidationError,
    VFSError,
    WriteConflictError,
    exception_for_kind,
)
from vfs.models2 import Entry, Observation
from vfs.ops import MUTATING_OPS
from vfs.paths import Path
from vfs.permissions import read_write
from vfs.replace import EditOperation
from vfs.results2 import Result, VFSErrorKind


class SpyFS(VirtualFileSystem):
    """A mount that records how many times it was closed."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.close_count = 0

    async def close(self) -> None:
        self.close_count += 1
        await super().close()


class MountPolicyFS(VirtualFileSystem):
    """A storage-bearing fs that refuses mounts at the given paths."""

    def __init__(self, blocked: set[str]) -> None:
        super().__init__(storage=True)
        self._blocked = set(blocked)

    async def _is_path_mountable(self, path: str) -> bool:
        return path not in self._blocked


# ----------------------------------------------------------------------
# __init__
# ----------------------------------------------------------------------


def test_init_defaults() -> None:
    fs = VirtualFileSystem()
    assert fs._storage is False
    assert fs._raise_on_error is False
    assert fs.name is None
    assert fs.title is None
    assert fs.description is None
    assert fs._mounts == {}
    assert fs._sorted_mount_paths == []
    assert fs._class_name == "VirtualFileSystem"


def test_init_no_engine_required() -> None:
    # The pure router needs no engine/session_factory — that was the point.
    fs = VirtualFileSystem(name="root", storage=True, raise_on_error=True)
    assert fs.name == "root"
    assert fs._storage is True
    assert fs._raise_on_error is True


# ----------------------------------------------------------------------
# _normalize_mount_path
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("data", "/data"), ("/data", "/data"), ("/data/", "/data"), ("docs", "/docs")],
)
def test_normalize_mount_path_valid(raw: str, expected: str) -> None:
    assert VirtualFileSystem._normalize_mount_path(raw) == expected


@pytest.mark.parametrize("raw", ["", "/", "//"])
def test_normalize_mount_path_rejects_empty_or_root(raw: str) -> None:
    with pytest.raises(ValueError):
        VirtualFileSystem._normalize_mount_path(raw)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("data/archive", "/data/archive"), ("/a/b/c", "/a/b/c"), ("data/tmp/", "/data/tmp")],
)
def test_normalize_mount_path_allows_nested(raw: str, expected: str) -> None:
    assert VirtualFileSystem._normalize_mount_path(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (" /data", "/data"),
        ("/ /data", "/data"),
        ("/data/ ", "/data"),
        ("/data/ x", "/data/x"),
        ("/x /y", "/x/y"),
        ("/a/ /b", "/a/b"),
        ("/\tdata", "/data"),
        ("/data\n", "/data"),
    ],
)
def test_normalize_mount_path_canonicalizes_stray_whitespace(raw: str, expected: str) -> None:
    # Leading/trailing per-segment whitespace (incl. tab/newline) is canonicalized
    # by the Path gate, not rejected.
    assert VirtualFileSystem._normalize_mount_path(raw) == expected


@pytest.mark.parametrize("raw", ["/My Documents", "/a/My Documents/b"])
def test_normalize_mount_path_allows_interior_space(raw: str) -> None:
    assert VirtualFileSystem._normalize_mount_path(raw) == raw


@pytest.mark.parametrize("raw", [".", "..", "/.", "/..", "/./", "/../"])
def test_normalize_mount_path_rejects_relative_segments(raw: str) -> None:
    # These normalize away to "/" and would create dead, unreachable mounts.
    with pytest.raises(ValueError):
        VirtualFileSystem._normalize_mount_path(raw)


@pytest.mark.parametrize("raw", [".vfs", "/.vfs", "/.vfs/"])
def test_normalize_mount_path_rejects_reserved_metadata_root(raw: str) -> None:
    with pytest.raises(ValueError, match="reserved"):
        VirtualFileSystem._normalize_mount_path(raw)


@pytest.mark.parametrize("raw", [" ", "/ ", "/da\tta", "/data\x7f"])
def test_normalize_mount_path_rejects_whitespace_and_control(raw: str) -> None:
    # " " and "/ " collapse to root; interior control chars are structurally invalid.
    with pytest.raises(ValueError):
        VirtualFileSystem._normalize_mount_path(raw)


# ----------------------------------------------------------------------
# add_mount
# ----------------------------------------------------------------------


async def test_add_mount_accepts_bare_and_slashed() -> None:
    parent = VirtualFileSystem()
    await parent.add_mount(VirtualFileSystem(), "data")
    await parent.add_mount(VirtualFileSystem(), "/docs")
    assert set(parent._mounts) == {"/data", "/docs"}


async def test_add_mount_uses_filesystem_name_when_path_omitted() -> None:
    parent = VirtualFileSystem()
    child = VirtualFileSystem(name="data")
    await parent.add_mount(child)
    assert set(parent._mounts) == {"/data"}


async def test_add_mount_explicit_path_overrides_name() -> None:
    parent = VirtualFileSystem()
    child = VirtualFileSystem(name="data")
    await parent.add_mount(child, "/elsewhere")
    assert set(parent._mounts) == {"/elsewhere"}


async def test_add_mount_requires_path_or_named_filesystem() -> None:
    parent = VirtualFileSystem()
    with pytest.raises(ValueError, match="path or a named filesystem"):
        await parent.add_mount(VirtualFileSystem())


async def test_add_mount_rejects_duplicate() -> None:
    parent = VirtualFileSystem()
    await parent.add_mount(VirtualFileSystem(), "data")
    with pytest.raises(ValueError, match="already exists"):
        await parent.add_mount(VirtualFileSystem(), "/data")


async def test_add_mount_propagates_raise_on_error() -> None:
    parent = VirtualFileSystem(raise_on_error=True)
    child = VirtualFileSystem()
    await parent.add_mount(child, "data")
    assert child._raise_on_error is True


async def test_add_mount_rejects_same_instance_twice() -> None:
    parent = VirtualFileSystem()
    child = VirtualFileSystem()
    await parent.add_mount(child, "here")
    with pytest.raises(ValueError, match="already mounted"):
        await parent.add_mount(child, "there")
    assert set(parent._mounts) == {"/here"}


async def test_add_mount_rejects_same_instance_nested_elsewhere() -> None:
    # The same instance cannot appear twice even across delegation levels.
    root = VirtualFileSystem()
    data = VirtualFileSystem()
    shared = VirtualFileSystem()
    await root.add_mount(data, "/data")
    await root.add_mount(shared, "/x")
    with pytest.raises(ValueError, match="already mounted"):
        await root.add_mount(shared, "/data/shared")  # would delegate into data
    assert set(data._mounts) == set()


async def test_add_mount_denied_when_disallowed() -> None:
    root = VirtualFileSystem(allow_child_mounts=False)
    with pytest.raises(ValueError, match="does not allow child mounts"):
        await root.add_mount(VirtualFileSystem(), "/data")
    assert set(root._mounts) == set()


async def test_add_mount_delegation_respects_child_policy() -> None:
    # root allows, but the /remote mount forbids child mounts (e.g. an MCP
    # adapter): a delegated add into it is refused.
    root = VirtualFileSystem()
    remote = VirtualFileSystem(allow_child_mounts=False)
    await root.add_mount(remote, "/remote")
    with pytest.raises(ValueError, match="does not allow child mounts"):
        await root.add_mount(VirtualFileSystem(), "/remote/cache")
    assert set(remote._mounts) == set()
    assert set(root._mounts) == {"/remote"}


async def test_add_mount_rejects_self_mount() -> None:
    parent = VirtualFileSystem()
    with pytest.raises(ValueError, match="into itself"):
        await parent.add_mount(parent, "loop")


async def test_add_mount_nested_delegates_to_parent_mount() -> None:
    # Forward order: /data mounted, then /data/tmp delegates into /data.
    root = VirtualFileSystem()
    data = VirtualFileSystem()
    tmp = VirtualFileSystem()
    await root.add_mount(data, "/data")
    await root.add_mount(tmp, "/data/tmp")
    assert set(root._mounts) == {"/data"}
    assert set(data._mounts) == {"/tmp"}
    fs, rel, prefix = root._resolve_terminal("/data/tmp/file.txt")
    assert fs is tmp
    assert rel == "/file.txt"
    assert prefix == "/data/tmp"


async def test_add_mount_reverse_order_conflict() -> None:
    # Reverse order: /data/tmp first, then /data is owned by the deeper mount.
    root = VirtualFileSystem()
    await root.add_mount(VirtualFileSystem(), "/data/tmp")
    assert set(root._mounts) == {"/data/tmp"}
    with pytest.raises(ValueError, match="deeper mount"):
        await root.add_mount(VirtualFileSystem(), "/data")
    assert set(root._mounts) == {"/data/tmp"}


async def test_add_mount_deep_nested_delegation() -> None:
    root = VirtualFileSystem()
    a = VirtualFileSystem()
    b = VirtualFileSystem()
    leaf = VirtualFileSystem()
    await root.add_mount(a, "/a")
    await a.add_mount(b, "/b")
    await root.add_mount(leaf, "/a/b/leaf")  # delegates root -> a -> b
    assert set(b._mounts) == {"/leaf"}
    fs, _rel, prefix = root._resolve_terminal("/a/b/leaf/x")
    assert fs is leaf
    assert prefix == "/a/b/leaf"


async def test_remove_mount_nested_delegates() -> None:
    root = VirtualFileSystem()
    data = VirtualFileSystem()
    tmp = VirtualFileSystem()
    await root.add_mount(data, "/data")
    await root.add_mount(tmp, "/data/tmp")
    await root.remove_mount("/data/tmp")
    assert set(data._mounts) == set()
    assert set(root._mounts) == {"/data"}


async def test_add_mount_storageless_allows_sparse_nested() -> None:
    root = VirtualFileSystem()
    await root.add_mount(VirtualFileSystem(), "/a/b/c")
    assert set(root._mounts) == {"/a/b/c"}


async def test_add_mount_rejects_unmountable_storage_path() -> None:
    root = MountPolicyFS({"/projects"})
    with pytest.raises(ValueError, match="conflict"):
        await root.add_mount(VirtualFileSystem(), "/projects")
    await root.add_mount(VirtualFileSystem(), "/free")  # mountable path is fine
    assert set(root._mounts) == {"/free"}


async def test_add_mount_mountable_check_runs_after_delegation() -> None:
    # The policy check runs on the fs that ultimately owns the mount.
    root = VirtualFileSystem()
    data = MountPolicyFS({"/tmp"})
    await root.add_mount(data, "/data")
    with pytest.raises(ValueError, match="conflict"):
        await root.add_mount(VirtualFileSystem(), "/data/tmp")
    assert set(data._mounts) == set()


async def test_is_path_mountable_default_true() -> None:
    # The pure router has no storage, so the base policy admits any path;
    # add_mount only consults it when self._storage is set.
    fs = VirtualFileSystem()
    assert await fs._is_path_mountable("/anything/at/all") is True


async def test_add_mount_on_subnode_checks_whole_graph() -> None:
    # add_mount on an already-mounted sub-node still sees the whole tree
    # (via parent links), not just that node's own subtree.
    root = VirtualFileSystem()
    a = VirtualFileSystem()
    b = SpyFS()
    await root.add_mount(a, "/a")
    await root.add_mount(b, "/b")
    with pytest.raises(ValueError, match="already mounted"):
        await a.add_mount(b, "/shared")  # b already lives at /b
    assert set(a._mounts) == set()
    await root.close()
    assert b.close_count == 1  # not double-closed


async def test_add_mount_rejects_filesystem_mounted_in_another_tree() -> None:
    # A filesystem mounted under one root cannot be mounted under another
    # (its _parent is already set), so teardown never double-closes it.
    root1 = VirtualFileSystem()
    root2 = VirtualFileSystem()
    child = SpyFS()
    await root1.add_mount(child, "/c")
    with pytest.raises(ValueError, match="already mounted"):
        await root2.add_mount(child, "/c")
    assert set(root2._mounts) == set()
    await root1.close()
    await root2.close()
    assert child.close_count == 1


async def test_add_mount_on_subnode_is_node_relative() -> None:
    # Paths are relative to the node add_mount is called on: data-local
    # "/tmp" lands at global /data/tmp.
    root = VirtualFileSystem()
    data = VirtualFileSystem()
    tmp = VirtualFileSystem()
    await root.add_mount(data, "/data")
    await data.add_mount(tmp, "/tmp")
    fs, _rel, prefix = root._resolve_terminal("/data/tmp/x")
    assert fs is tmp
    assert prefix == "/data/tmp"


async def test_add_mount_allows_unmounted_fs_carrying_its_own_mounts() -> None:
    # Building a subtree first, then mounting the whole thing, is allowed.
    root = VirtualFileSystem()
    sub = VirtualFileSystem()
    leaf = VirtualFileSystem()
    await sub.add_mount(leaf, "/leaf")
    await root.add_mount(sub, "/sub")
    assert sub._parent is root
    assert leaf._parent is sub
    fs, _rel, prefix = root._resolve_terminal("/sub/leaf/x")
    assert fs is leaf
    assert prefix == "/sub/leaf"


async def test_parent_pointer_set_and_cleared() -> None:
    root = VirtualFileSystem()
    child = VirtualFileSystem()
    await root.add_mount(child, "/data")
    assert child._parent is root
    await root.remove_mount("/data")
    assert child._parent is None


async def test_parent_pointer_for_nested_delegation() -> None:
    root = VirtualFileSystem()
    data = VirtualFileSystem()
    tmp = VirtualFileSystem()
    await root.add_mount(data, "/data")
    await root.add_mount(tmp, "/data/tmp")  # delegated into data
    assert data._parent is root
    assert tmp._parent is data
    assert tmp._root() is root


async def test_close_clears_parent_pointers() -> None:
    root = VirtualFileSystem()
    child = VirtualFileSystem()
    await root.add_mount(child, "/data")
    await root.close()
    assert child._parent is None


async def test_add_mount_duplicate_across_delegation_does_not_double_close() -> None:
    # leaf at /other, then mounted again under /data/tmp: the whole-graph
    # duplicate guard refuses it before delegating, so close() does not
    # close leaf twice.
    root = VirtualFileSystem()
    data = VirtualFileSystem()
    leaf = SpyFS()
    await root.add_mount(data, "/data")
    await root.add_mount(leaf, "/other")
    with pytest.raises(ValueError, match="already mounted"):
        await root.add_mount(leaf, "/data/tmp")
    assert set(data._mounts) == set()
    await root.close()
    assert leaf.close_count == 1


async def test_add_mount_allows_distinct_instances() -> None:
    # Two distinct instances (e.g. BindFS wrappers over one upstream) are fine.
    parent = VirtualFileSystem()
    await parent.add_mount(VirtualFileSystem(), "a")
    await parent.add_mount(VirtualFileSystem(), "b")
    assert set(parent._mounts) == {"/a", "/b"}


async def test_add_mount_rejects_direct_cycle() -> None:
    # root -> child -> root
    root = VirtualFileSystem()
    child = VirtualFileSystem()
    await root.add_mount(child, "child")
    with pytest.raises(ValueError, match="cycle"):
        await child.add_mount(root, "back")
    assert child._mounts == {}


async def test_add_mount_rejects_indirect_cycle() -> None:
    # root -> a -> b -> root
    root = VirtualFileSystem()
    a = VirtualFileSystem()
    b = VirtualFileSystem()
    await root.add_mount(a, "a")
    await a.add_mount(b, "b")
    with pytest.raises(ValueError, match="cycle"):
        await b.add_mount(root, "back")
    assert b._mounts == {}


async def test_no_cycle_means_close_terminates() -> None:
    # Once the cycle is refused, the acyclic tree closes cleanly.
    root = VirtualFileSystem()
    child = VirtualFileSystem()
    await root.add_mount(child, "child")
    with pytest.raises(ValueError, match="cycle"):
        await child.add_mount(root, "back")
    await root.close()
    assert root._mounts == {}


async def test_reachable_ids_dedups_shared_node() -> None:
    # The visited-guard makes _reachable_ids dedup and terminate even on a
    # malformed graph where one fs is reachable by two paths — a diamond the
    # public API refuses, so wire _mounts directly to build it.
    root = VirtualFileSystem()
    a = VirtualFileSystem()
    b = VirtualFileSystem()
    shared = VirtualFileSystem()
    root._mounts = {"/a": a, "/b": b}
    a._mounts = {"/s": shared}
    b._mounts = {"/s": shared}
    assert root._reachable_ids() == {id(root), id(a), id(b), id(shared)}


async def test_add_mount_allows_deep_acyclic_tree() -> None:
    root = VirtualFileSystem()
    a = VirtualFileSystem()
    b = VirtualFileSystem()
    await root.add_mount(a, "a")
    await a.add_mount(b, "b")
    fs, rel, prefix = root._resolve_terminal("/a/b/file.txt")
    assert fs is b
    assert rel == "/file.txt"
    assert prefix == "/a/b"


async def test_add_mount_rebuilds_sorted_list_longest_first() -> None:
    parent = VirtualFileSystem()
    await parent.add_mount(VirtualFileSystem(), "a")
    await parent.add_mount(VirtualFileSystem(), "abc")
    await parent.add_mount(VirtualFileSystem(), "ab")
    assert parent._sorted_mount_paths == ["/abc", "/ab", "/a"]


# ----------------------------------------------------------------------
# remove_mount
# ----------------------------------------------------------------------


async def test_remove_mount_updates_table() -> None:
    parent = VirtualFileSystem()
    await parent.add_mount(VirtualFileSystem(), "data")
    await parent.add_mount(VirtualFileSystem(), "docs")
    await parent.remove_mount("/data")
    assert set(parent._mounts) == {"/docs"}
    assert parent._sorted_mount_paths == ["/docs"]


async def test_remove_mount_rejects_missing() -> None:
    parent = VirtualFileSystem()
    with pytest.raises(ValueError, match="No mount at"):
        await parent.remove_mount("/nope")


async def test_remove_mount_does_not_close_child() -> None:
    # Lifecycle is the caller's concern — unmounting must not close the child.
    parent = VirtualFileSystem()
    child = SpyFS()
    await parent.add_mount(child, "data")
    await parent.remove_mount("/data")
    assert child.close_count == 0


# ----------------------------------------------------------------------
# close
# ----------------------------------------------------------------------


async def test_close_is_polymorphic_and_clears() -> None:
    parent = VirtualFileSystem()
    child_a = SpyFS()
    child_b = SpyFS()
    await parent.add_mount(child_a, "a")
    await parent.add_mount(child_b, "b")
    await parent.close()
    assert child_a.close_count == 1
    assert child_b.close_count == 1
    assert parent._mounts == {}
    assert parent._sorted_mount_paths == []


async def test_close_recurses_into_nested_mounts() -> None:
    parent = VirtualFileSystem()
    child = VirtualFileSystem()
    grandchild = SpyFS()
    await child.add_mount(grandchild, "sub")
    await parent.add_mount(child, "data")
    await parent.close()
    assert grandchild.close_count == 1


class BadCloseFS(VirtualFileSystem):
    """A mount whose close always fails."""

    async def close(self) -> None:
        raise RuntimeError("boom")


async def test_close_attempts_all_and_clears_on_failure() -> None:
    # One failing child must not strand siblings or leave the table populated.
    parent = VirtualFileSystem()
    good = SpyFS()
    await parent.add_mount(BadCloseFS(), "a")
    await parent.add_mount(good, "b")
    with pytest.raises(RuntimeError, match="boom"):
        await parent.close()
    assert good.close_count == 1
    assert parent._mounts == {}
    assert parent._sorted_mount_paths == []


async def test_close_groups_multiple_failures() -> None:
    parent = VirtualFileSystem()
    await parent.add_mount(BadCloseFS(), "a")
    await parent.add_mount(BadCloseFS(), "b")
    with pytest.raises(ExceptionGroup):
        await parent.close()
    assert parent._mounts == {}


# ----------------------------------------------------------------------
# _match_mount / _resolve_terminal
# ----------------------------------------------------------------------


async def test_match_mount_longest_prefix() -> None:
    parent = VirtualFileSystem()
    short = VirtualFileSystem()
    long = VirtualFileSystem()
    await parent.add_mount(short, "a")
    await parent.add_mount(long, "ab")
    assert parent._match_mount("/ab/x") == ("/ab", long)
    assert parent._match_mount("/a/x") == ("/a", short)
    assert parent._match_mount("/other") is None


async def test_resolve_terminal_self() -> None:
    parent = VirtualFileSystem()
    fs, rel, prefix = parent._resolve_terminal("/other/file.txt")
    assert fs is parent
    assert rel == "/other/file.txt"
    assert prefix == ""


async def test_resolve_terminal_single_mount() -> None:
    parent = VirtualFileSystem()
    child = VirtualFileSystem()
    await parent.add_mount(child, "data")
    fs, rel, prefix = parent._resolve_terminal("/data/file.txt")
    assert fs is child
    assert rel == "/file.txt"
    assert prefix == "/data"


async def test_resolve_terminal_nested_mounts() -> None:
    parent = VirtualFileSystem()
    child = VirtualFileSystem()
    grandchild = VirtualFileSystem()
    await child.add_mount(grandchild, "sub")
    await parent.add_mount(child, "data")
    fs, rel, prefix = parent._resolve_terminal("/data/sub/file.txt")
    assert fs is grandchild
    assert rel == "/file.txt"
    assert prefix == "/data/sub"


async def test_resolve_terminal_mount_root() -> None:
    parent = VirtualFileSystem()
    child = VirtualFileSystem()
    await parent.add_mount(child, "data")
    fs, rel, prefix = parent._resolve_terminal("/data")
    assert fs is child
    assert rel == "/"
    assert prefix == "/data"


# ----------------------------------------------------------------------
# _error and kind-based exception dispatch
# ----------------------------------------------------------------------


def test_exception_for_kind_maps_known_kinds() -> None:
    assert exception_for_kind(VFSErrorKind.not_found) is NotFoundError
    assert exception_for_kind(VFSErrorKind.read_only) is WriteConflictError
    assert exception_for_kind(VFSErrorKind.invalid) is ValidationError


def test_exception_for_kind_unmapped_and_unknown_fall_back_to_base() -> None:
    # internal is a real kind with no explicit mapping; the str is a newer peer's kind.
    assert exception_for_kind(VFSErrorKind.internal) is VFSError
    assert exception_for_kind("vfs.quota_exceeded") is VFSError


def test_error_returns_failed_result_by_default() -> None:
    fs = VirtualFileSystem()
    r = fs._error("gone", kind=VFSErrorKind.not_found, path="/x")
    assert r.success is False
    assert r.errors[0].kind is VFSErrorKind.not_found
    assert r.errors[0].path == "/x"


def test_error_attaches_structured_data() -> None:
    fs = VirtualFileSystem()
    r = fs._error("stale", kind=VFSErrorKind.conflict, data={"expected": 1})
    assert r.errors[0].data == {"expected": 1}


def test_error_raises_classified_exception_when_configured() -> None:
    fs = VirtualFileSystem(raise_on_error=True)
    with pytest.raises(NotFoundError) as exc:
        fs._error("gone", kind=VFSErrorKind.not_found)
    # the raised exception still carries the full failed result
    assert exc.value.result is not None
    assert exc.value.result.success is False


# ----------------------------------------------------------------------
# capabilities gate + run verb
# ----------------------------------------------------------------------


class RunnerFS(VirtualFileSystem):
    """A storage-less leaf that answers read/run and records the calls it gets."""

    def __init__(self, *, caps: frozenset[str] | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._caps = caps
        self.calls: list[tuple[str, str, object]] = []

    def capabilities(self) -> frozenset[str] | None:
        return self._caps

    async def read(self, path=None, observations=None, *, columns=None, user_id=None) -> Result:
        self.calls.append(("read", path, columns))
        return Result(function="read", observations=[Observation(path=Path(path), kind="tool")])

    async def run(self, path=None, *, arguments=None, user_id=None) -> Result:
        self.calls.append(("run", path, arguments))
        return Result(function="run", observations=[Observation(path=Path(path), kind="tool")])


async def test_run_on_pure_router_is_not_found() -> None:
    root = VirtualFileSystem()
    r = await root.run("/nope/tool")
    assert r.success is False
    assert r.errors[0].kind is VFSErrorKind.not_found


async def test_run_routes_to_child_and_rebases() -> None:
    root = VirtualFileSystem()
    catalog = RunnerFS()
    await root.add_mount(catalog, "/nonvfs")
    r = await root.run("/nonvfs/clone-repo", arguments={"repo": "org/proj"})
    assert catalog.calls == [("run", "/clone-repo", {"repo": "org/proj"})]
    assert r.success is True
    assert r.paths == ("/nonvfs/clone-repo",)


async def test_capabilities_gate_blocks_unsupported_op() -> None:
    root = VirtualFileSystem()
    catalog = RunnerFS(caps=frozenset({"read"}))
    await root.add_mount(catalog, "/nonvfs")
    blocked = await root.run("/nonvfs/clone-repo")
    assert blocked.success is False
    assert blocked.errors[0].kind is VFSErrorKind.unsupported
    assert catalog.calls == []  # never dispatched


async def test_capabilities_gate_allows_supported_op() -> None:
    root = VirtualFileSystem()
    catalog = RunnerFS(caps=frozenset({"read"}))
    await root.add_mount(catalog, "/nonvfs")
    ok = await root.read("/nonvfs/clone-repo")
    assert ok.success is True
    assert ok.paths == ("/nonvfs/clone-repo",)
    assert catalog.calls == [("read", "/clone-repo", None)]


async def test_capabilities_none_imposes_no_gate() -> None:
    # A plain child (capabilities() is None) answers run with no restriction.
    root = VirtualFileSystem()
    catalog = RunnerFS()
    await root.add_mount(catalog, "/nonvfs")
    r = await root.run("/nonvfs/x")
    assert r.success is True


# ----------------------------------------------------------------------
# verb-surface fakes
# ----------------------------------------------------------------------


class RecorderFS(VirtualFileSystem):
    """Storage-backed fake recording every local dispatch, returning success."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("storage", True)
        super().__init__(**kwargs)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def _call_local_impl(self, op, *, user_id=None, **kwargs) -> Result:  # type: ignore[override]
        self.calls.append((op, dict(kwargs)))
        return Result(function=op, observations=[])


class EchoFS(RecorderFS):
    """Recorder whose impl answers with one observation at a fixed local path."""

    def __init__(self, echo_path: str = "/hit.md", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._echo_path = echo_path

    async def _call_local_impl(self, op, *, user_id=None, **kwargs) -> Result:  # type: ignore[override]
        self.calls.append((op, dict(kwargs)))
        return Result(function=op, observations=[Observation(path=Path(self._echo_path))])


class LimitedEchoFS(EchoFS):
    """Echo mount that answers only the given capability set."""

    def __init__(self, caps: frozenset[str], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._caps = caps

    def capabilities(self) -> frozenset[str] | None:
        return self._caps


def _mutate(fs: VirtualFileSystem, op: str, base: str):
    """Invoke the mutating *op* against targets under *base* (no trailing slash)."""
    calls = {
        "write": lambda: fs.write(path=f"{base}/f.txt", content="x"),
        "edit": lambda: fs.edit(path=f"{base}/f.txt", old="a", new="b"),
        "delete": lambda: fs.delete(path=f"{base}/f.txt"),
        "mkdir": lambda: fs.mkdir(f"{base}/d"),
        "mkedge": lambda: fs.mkedge(f"{base}/a.py", f"{base}/b.py", "imports"),
        "move": lambda: fs.move(src=f"{base}/a.txt", dest=f"{base}/b.txt"),
        "copy": lambda: fs.copy(src=f"{base}/a.txt", dest=f"{base}/b.txt"),
    }
    return calls[op]()


def _mutate_at_root(fs: VirtualFileSystem, op: str, target: str):
    """Invoke the mutating *op* with *target* (root or reserved) as its write target."""
    calls = {
        "write": lambda: fs.write(path=target, content="x"),
        "edit": lambda: fs.edit(path=target, old="a", new="b"),
        "delete": lambda: fs.delete(path=target),
        "mkdir": lambda: fs.mkdir(target),
        "mkedge": lambda: fs.mkedge(target, "/b.py", "imports"),
        "move": lambda: fs.move(src="/a.txt", dest=target),
        "copy": lambda: fs.copy(src="/a.txt", dest=target),
    }
    return calls[op]()


# ----------------------------------------------------------------------
# mutation gates across the full verb surface
# ----------------------------------------------------------------------


@pytest.mark.parametrize("op", sorted(MUTATING_OPS))
async def test_read_only_mount_rejects_every_mutation(op: str) -> None:
    root = VirtualFileSystem()
    child = RecorderFS(permissions="read")
    await root.add_mount(child, "/m")
    result = await _mutate(root, op, "/m")
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.read_only
    assert child.calls == []  # gated before any dispatch


@pytest.mark.parametrize("op", sorted(MUTATING_OPS))
async def test_writable_mount_dispatches_every_mutation_once(op: str) -> None:
    root = VirtualFileSystem()
    child = RecorderFS()
    await root.add_mount(child, "/m")
    result = await _mutate(root, op, "/m")
    assert result.success is True
    assert len(child.calls) == 1
    assert child.calls[0][0] == op


@pytest.mark.parametrize("op", sorted(MUTATING_OPS))
@pytest.mark.parametrize("target", ["/", "/.vfs"])
async def test_root_and_reserved_targets_rejected(op: str, target: str) -> None:
    fs = RecorderFS()
    result = await _mutate_at_root(fs, op, target)
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.invalid
    assert fs.calls == []


async def test_inverse_edge_projection_is_not_a_write_target() -> None:
    fs = RecorderFS()
    result = await fs.write(path="/.vfs/a.py/__meta__/edges/in/imports/b.py", content="x")
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.invalid
    assert fs.calls == []


# ----------------------------------------------------------------------
# single-shape verbs localize their dispatch
# ----------------------------------------------------------------------


async def test_write_localizes_path_and_passes_kwargs() -> None:
    root = VirtualFileSystem()
    child = RecorderFS()
    await root.add_mount(child, "/m")
    await root.write(path="/m/f.txt", content="x", overwrite=False)
    assert child.calls == [("write", {"path": "/f.txt", "content": "x", "overwrite": False})]


async def test_edit_wraps_old_new_into_edits_list() -> None:
    root = VirtualFileSystem()
    child = RecorderFS()
    await root.add_mount(child, "/m")
    await root.edit(path="/m/f.txt", old="a", new="b")
    assert child.calls == [("edit", {"path": "/f.txt", "edits": [EditOperation(old="a", new="b")]})]


async def test_edit_requires_old_new_or_edits() -> None:
    fs = RecorderFS()
    result = await fs.edit(path="/f.txt")
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.invalid
    assert fs.calls == []


async def test_tree_routes_with_depth_passthrough() -> None:
    root = VirtualFileSystem()
    child = RecorderFS()
    await root.add_mount(child, "/m")
    await root.tree("/m/src", max_depth=2)
    assert child.calls == [("tree", {"path": "/src", "max_depth": 2, "columns": None})]


# ----------------------------------------------------------------------
# two-path shape: move / copy
# ----------------------------------------------------------------------


async def test_move_same_terminal_dispatches_localized_pair() -> None:
    root = VirtualFileSystem()
    child = RecorderFS()
    await root.add_mount(child, "/m")
    result = await root.move(src="/m/a.txt", dest="/m/b.txt")
    assert result.success is True
    assert child.calls == [
        ("move", {"operations": [TwoPathOperation(src="/a.txt", dest="/b.txt")], "overwrite": True}),
    ]


@pytest.mark.parametrize("op", ["move", "copy"])
async def test_two_path_cross_mount_rejected(op: str) -> None:
    root = VirtualFileSystem()
    a, b = RecorderFS(), RecorderFS()
    await root.add_mount(a, "/a")
    await root.add_mount(b, "/b")
    method = getattr(root, op)
    result = await method(src="/a/x.txt", dest="/b/y.txt")
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.cross_mount
    assert a.calls == [] and b.calls == []


async def test_two_path_batch_one_bad_pair_rejects_all() -> None:
    root = VirtualFileSystem()
    a, b = RecorderFS(), RecorderFS()
    await root.add_mount(a, "/a")
    await root.add_mount(b, "/b")
    result = await root.move(moves=[("/a/x.txt", "/a/y.txt"), ("/a/z.txt", "/b/w.txt")])
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.cross_mount
    assert a.calls == [] and b.calls == []  # nothing half-executes


async def test_move_gates_both_endpoints() -> None:
    root = VirtualFileSystem()
    child = RecorderFS(permissions=read_write(read=["/frozen"]))
    await root.add_mount(child, "/m")
    src_frozen = await root.move(src="/m/frozen/a.txt", dest="/m/b.txt")
    dest_frozen = await root.move(src="/m/a.txt", dest="/m/frozen/b.txt")
    assert src_frozen.errors[0].kind is VFSErrorKind.read_only
    assert dest_frozen.errors[0].kind is VFSErrorKind.read_only
    assert child.calls == []


async def test_copy_gates_dest_only() -> None:
    root = VirtualFileSystem()
    child = RecorderFS(permissions=read_write(read=["/frozen"]))
    await root.add_mount(child, "/m")
    result = await root.copy(src="/m/frozen/a.txt", dest="/m/b.txt")
    assert result.success is True  # read-only source is fine for copy
    assert child.calls == [
        ("copy", {"operations": [TwoPathOperation(src="/frozen/a.txt", dest="/b.txt")], "overwrite": True}),
    ]


# ----------------------------------------------------------------------
# endpoint-pair shape: mkedge
# ----------------------------------------------------------------------


async def test_mkedge_localizes_endpoints_on_shared_terminal() -> None:
    root = VirtualFileSystem()
    child = RecorderFS()
    await root.add_mount(child, "/m")
    result = await root.mkedge("/m/a.py", "/m/b.py", "imports")
    assert result.success is True
    assert child.calls == [("mkedge", {"source": "/a.py", "target": "/b.py", "edge_type": "imports"})]


async def test_mkedge_cross_mount_rejected() -> None:
    root = VirtualFileSystem()
    a, b = RecorderFS(), RecorderFS()
    await root.add_mount(a, "/a")
    await root.add_mount(b, "/b")
    result = await root.mkedge("/a/x.py", "/b/y.py", "imports")
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.cross_mount
    assert a.calls == [] and b.calls == []


async def test_mkedge_rejects_bad_edge_type() -> None:
    fs = RecorderFS()
    result = await fs.mkedge("/a.py", "/b.py", "im/ports")
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.invalid
    assert fs.calls == []


# ----------------------------------------------------------------------
# fan-out shape: glob / grep / glean
# ----------------------------------------------------------------------


def _fan(fs: VirtualFileSystem, op: str, **kwargs: Any):
    """Invoke the fan-out verb *op* with its required query argument."""
    calls = {
        "glob": lambda: fs.glob("*.py", **kwargs),
        "grep": lambda: fs.grep("needle", **kwargs),
        "glean": lambda: fs.glean("how does auth work", **kwargs),
    }
    return calls[op]()


@pytest.mark.parametrize("op", ["glob", "grep", "glean"])
async def test_fanout_reaches_every_mount_in_table_order(op: str) -> None:
    root = VirtualFileSystem()
    a, b = EchoFS(), EchoFS()
    await root.add_mount(a, "/a")
    await root.add_mount(b, "/b")
    result = await _fan(root, op)
    assert result.success is True
    assert result.paths == ("/a/hit.md", "/b/hit.md")  # rebased, mount-table order
    assert a.calls[0][0] == op and b.calls[0][0] == op
    assert a.calls[0][1]["paths"] == ()  # child impl sees an unscoped call


@pytest.mark.parametrize("op", ["glob", "grep", "glean"])
async def test_fanout_skips_incapable_terminal_silently(op: str) -> None:
    root = VirtualFileSystem()
    a = EchoFS()
    b = LimitedEchoFS(caps=frozenset({"read"}))
    await root.add_mount(a, "/a")
    await root.add_mount(b, "/b")
    result = await _fan(root, op)
    assert result.success is True
    assert result.errors == []
    assert result.paths == ("/a/hit.md",)
    assert b.calls == []


@pytest.mark.parametrize("op", ["glob", "grep", "glean"])
async def test_fanout_scoped_routes_only_the_target_terminal(op: str) -> None:
    root = VirtualFileSystem()
    a, b = EchoFS(), EchoFS()
    await root.add_mount(a, "/a")
    await root.add_mount(b, "/b")
    result = await _fan(root, op, paths=("/a/src",))
    assert result.success is True
    assert a.calls[0][1]["paths"] == ("/src",)
    assert b.calls == []


async def test_fanout_scoped_incapable_terminal_is_unsupported() -> None:
    root = VirtualFileSystem()
    b = LimitedEchoFS(caps=frozenset({"read"}))
    await root.add_mount(b, "/b")
    result = await root.glob("*.py", paths=("/b/src",))
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.unsupported
    assert b.calls == []


async def test_fanout_includes_self_storage_before_mounts() -> None:
    root = EchoFS(echo_path="/root-hit.md")
    child = EchoFS()
    await root.add_mount(child, "/m")
    result = await root.glob("*.md")
    assert result.paths == ("/root-hit.md", "/m/hit.md")  # self first, then mounts
    assert root.calls[0][1]["paths"] == ()


async def test_fanout_with_no_capable_terminals_is_empty_success() -> None:
    root = VirtualFileSystem()  # storageless, no mounts
    result = await root.glean("anything")
    assert result.success is True
    assert len(result) == 0
    assert result.function == "glean"


async def test_grep_observations_use_grouped_dispatch() -> None:
    root = VirtualFileSystem()
    a, b = RecorderFS(), RecorderFS()
    await root.add_mount(a, "/a")
    await root.add_mount(b, "/b")
    rows = [Observation(path=Path("/a/f.py")), Observation(path=Path("/b/g.py"))]
    await root.grep("needle", observations=rows)
    assert len(a.calls) == 1 and len(b.calls) == 1
    (a_obs,) = a.calls[0][1]["observations"]
    assert a_obs.path == "/f.py"  # rebased into the terminal's coordinates


# ----------------------------------------------------------------------
# grouped shape: graph
# ----------------------------------------------------------------------


async def test_graph_rejects_unknown_and_centrality_methods() -> None:
    fs = RecorderFS()
    for method in ("pagerank", "not_a_method"):
        result = await fs.graph(method, path="/a.py")
        assert result.success is False
        assert result.errors[0].kind is VFSErrorKind.invalid
    assert fs.calls == []


async def test_graph_path_routes_to_one_terminal() -> None:
    root = VirtualFileSystem()
    child = RecorderFS()
    await root.add_mount(child, "/m")
    await root.graph("descendants", path="/m/a.py")
    assert child.calls == [("graph", {"path": "/a.py", "method": "descendants", "depth": None})]


async def test_graph_observations_group_per_mount() -> None:
    root = VirtualFileSystem()
    a, b = RecorderFS(), RecorderFS()
    await root.add_mount(a, "/a")
    await root.add_mount(b, "/b")
    rows = [Observation(path=Path("/a/x.py")), Observation(path=Path("/b/y.py"))]
    await root.graph("neighborhood", observations=rows, depth=2)
    assert len(a.calls) == 1 and len(b.calls) == 1
    (a_obs,) = a.calls[0][1]["observations"]
    assert a_obs.path == "/x.py"  # each mount walks only its own subgraph
    assert a.calls[0][1]["method"] == "neighborhood"
    assert a.calls[0][1]["depth"] == 2


# ----------------------------------------------------------------------
# batch-entry writes
# ----------------------------------------------------------------------


async def test_write_entries_batch_groups_and_localizes() -> None:
    root = VirtualFileSystem()
    a, b = RecorderFS(), RecorderFS()
    await root.add_mount(a, "/a")
    await root.add_mount(b, "/b")
    entries = [Entry(path=Path("/a/f.txt"), content="x"), Entry(path=Path("/b/g.txt"), content="y")]
    result = await root.write(entries)
    assert result.success is True
    assert len(a.calls) == 1 and len(b.calls) == 1
    (a_entry,) = a.calls[0][1]["entries"]
    assert a_entry.path == "/f.txt"
    assert a.calls[0][1]["overwrite"] is True


async def test_write_entries_one_read_only_target_rejects_all() -> None:
    root = VirtualFileSystem()
    a = RecorderFS()
    b = RecorderFS(permissions="read")
    await root.add_mount(a, "/a")
    await root.add_mount(b, "/b")
    entries = [Entry(path=Path("/a/f.txt"), content="x"), Entry(path=Path("/b/g.txt"), content="y")]
    result = await root.write(entries)
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.read_only
    assert a.calls == [] and b.calls == []  # gated before any dispatch


# ----------------------------------------------------------------------
# router edge and error branches
# ----------------------------------------------------------------------


async def test_call_local_impl_without_storage_is_unsupported() -> None:
    result = await VirtualFileSystem()._call_local_impl("read")
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.unsupported


async def test_call_local_impl_reaches_the_op_impl_method() -> None:
    class ImplFS(VirtualFileSystem):
        def __init__(self) -> None:
            super().__init__(storage=True)

        async def _read_impl(self, *, user_id: str | None = None, **kwargs: Any) -> Result:
            return Result(function="read", observations=[Observation(path=Path(str(kwargs["path"])))])

    result = await ImplFS().read("/f.txt")
    assert result.paths == ("/f.txt",)


async def test_route_single_requires_exactly_one_input() -> None:
    fs = RecorderFS()
    with pytest.raises(ValueError, match="Exactly one"):
        await fs.read()
    with pytest.raises(ValueError, match="Exactly one"):
        await fs.read("/f.txt", observations=[Observation(path=Path("/f.txt"))])


async def test_stat_and_ls_route_and_localize() -> None:
    root = VirtualFileSystem()
    child = RecorderFS()
    await root.add_mount(child, "/m")
    await root.stat("/m/f.txt")
    await root.ls("/m/dir")
    assert child.calls == [
        ("stat", {"path": "/f.txt", "columns": None}),
        ("ls", {"path": "/dir", "columns": None}),
    ]


async def test_grouped_observations_empty_list_is_empty_success() -> None:
    result = await RecorderFS().read(observations=[])
    assert result.success is True
    assert len(result) == 0


async def test_grouped_observations_mutation_gate_rejects_invalid_target() -> None:
    fs = RecorderFS()
    result = await fs.delete(observations=[Observation(path=Path("/"))])
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.invalid
    assert fs.calls == []


async def test_grouped_observations_respect_read_only_mount() -> None:
    root = VirtualFileSystem()
    child = RecorderFS(permissions="read")
    await root.add_mount(child, "/m")
    result = await root.delete(observations=[Observation(path=Path("/m/f.txt"))])
    assert result.errors[0].kind is VFSErrorKind.read_only
    assert child.calls == []


async def test_grouped_observations_capability_error_is_rebased() -> None:
    root = VirtualFileSystem()
    child = LimitedEchoFS(caps=frozenset({"glob"}))
    await root.add_mount(child, "/m")
    result = await root.read(observations=[Observation(path=Path("/m/f.txt"))])
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.unsupported
    assert child.calls == []


async def test_merge_results_of_nothing_is_empty() -> None:
    merged = VirtualFileSystem._merge_results([])
    assert merged.success is True
    assert len(merged) == 0


async def test_two_path_empty_batch_is_empty_success() -> None:
    result = await RecorderFS().move(moves=[])
    assert result.success is True
    assert len(result) == 0


async def test_two_path_invalid_src_rejected() -> None:
    result = await RecorderFS().move(src="/a\x00b.txt", dest="/b.txt")
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.invalid


@pytest.mark.parametrize("op", ["move", "copy"])
async def test_two_path_requires_pair_or_batch(op: str) -> None:
    result = await getattr(RecorderFS(), op)()
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.invalid


async def test_two_path_on_pure_router_is_not_found() -> None:
    root = VirtualFileSystem()
    result = await root.move(src="/nope/a.txt", dest="/nope/b.txt")
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.not_found


async def test_two_path_capability_gate_blocks() -> None:
    root = VirtualFileSystem()
    child = LimitedEchoFS(caps=frozenset({"read"}))
    await root.add_mount(child, "/m")
    result = await root.move(src="/m/a.txt", dest="/m/b.txt")
    assert result.errors[0].kind is VFSErrorKind.unsupported
    assert child.calls == []


async def test_write_entries_empty_batch_is_empty_success() -> None:
    result = await RecorderFS().write(entries=[])
    assert result.success is True
    assert len(result) == 0


async def test_write_entries_inverse_edge_target_rejected() -> None:
    fs = RecorderFS()
    entry = Entry(path=Path("/.vfs/a.py/__meta__/edges/in/imports/b.py"))
    result = await fs.write(entries=[entry])
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.invalid
    assert fs.calls == []


async def test_write_entries_on_pure_router_is_not_found() -> None:
    root = VirtualFileSystem()
    result = await root.write(entries=[Entry(path=Path("/f.txt"), content="x")])
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.not_found


async def test_write_entries_capability_gate_blocks() -> None:
    root = VirtualFileSystem()
    child = LimitedEchoFS(caps=frozenset({"read"}))
    await root.add_mount(child, "/m")
    result = await root.write(entries=[Entry(path=Path("/m/f.txt"), content="x")])
    assert result.errors[0].kind is VFSErrorKind.unsupported
    assert child.calls == []


async def test_mkedge_invalid_endpoints_rejected() -> None:
    fs = RecorderFS()
    bad_source = await fs.mkedge("/a\x00.py", "/b.py", "imports")
    bad_target = await fs.mkedge("/a.py", "/b\x00.py", "imports")
    assert bad_source.errors[0].kind is VFSErrorKind.invalid
    assert bad_target.errors[0].kind is VFSErrorKind.invalid
    assert fs.calls == []


async def test_mkedge_on_pure_router_is_not_found() -> None:
    root = VirtualFileSystem()
    result = await root.mkedge("/nope/a.py", "/nope/b.py", "imports")
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.not_found


async def test_mkedge_capability_gate_blocks() -> None:
    root = VirtualFileSystem()
    child = LimitedEchoFS(caps=frozenset({"read"}))
    await root.add_mount(child, "/m")
    result = await root.mkedge("/m/a.py", "/m/b.py", "imports")
    assert result.errors[0].kind is VFSErrorKind.unsupported
    assert child.calls == []
