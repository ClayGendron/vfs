"""Tests for the rebuilt ``vfs.base2.VirtualFileSystem`` router.

Built up section by section alongside ``src/vfs/base2.py``.  These tests
exercise only the pure router — no storage, no sessions.  Storage behavior
belongs to ``DatabaseFileSystem`` and is tested elsewhere.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from vfs.base2 import ResolvedPair, TwoPathOperation, VirtualFileSystem
from vfs.exceptions import (
    NotFoundError,
    ValidationError,
    VFSError,
    WriteConflictError,
    exception_for_kind,
    raise_if_failed,
)
from vfs.models2 import Entry, Observation
from vfs.ops import MUTATING_OPS
from vfs.paths import MAX_PATH_LENGTH, ObjectKind, Path
from vfs.permissions import read_write
from vfs.replace import EditOperation
from vfs.results2 import Result, ResultError, VFSErrorKind


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

    async def _is_path_mountable(self, path: Path) -> tuple[bool, str]:
        if path in self._blocked:
            return False, "storage contents conflict with that mount point"
        return True, ""


class DictStorageFS(VirtualFileSystem):
    """Minimal storage terminal: a path -> kind dict behind stat/glob."""

    def __init__(self, entries: dict[str, ObjectKind], **kwargs: Any) -> None:
        super().__init__(storage=True, **kwargs)
        self._entries = entries

    async def _stat_impl(
        self,
        *,
        path: str | None = None,
        observations: list[Observation] | None = None,
        **_: object,
    ) -> Result:
        wanted = [path] if path is not None else [o.path for o in observations or []]
        rows = [Observation(path=Path(p), kind=self._entries[p]) for p in wanted if p in self._entries]
        if path is not None and not rows:
            return self._error(f"Not found: {path}", kind=VFSErrorKind.not_found, path=Path(path))
        return Result(function="stat", observations=rows)


# ----------------------------------------------------------------------
# __init__
# ----------------------------------------------------------------------


def test_init_defaults() -> None:
    fs = VirtualFileSystem()
    assert fs._storage is False
    assert fs.name is None
    assert fs.title is None
    assert fs.description is None
    assert fs._mounts == {}
    assert fs._sorted_mount_paths == []
    assert fs._class_name == "VirtualFileSystem"


def test_init_no_engine_required() -> None:
    # The pure router needs no engine/session_factory — that was the point.
    fs = VirtualFileSystem(name="root", storage=True)
    assert fs.name == "root"
    assert fs._storage is True


def test_init_rejects_removed_raise_on_error_kwarg() -> None:
    # Result is the only node-level failure channel; raising is the call
    # boundary's job (raise_if_failed) and the old kwarg is gone for good.
    with pytest.raises(TypeError):
        VirtualFileSystem(raise_on_error=True)  # ty: ignore[unknown-argument]


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
    fs, rel, prefix = root._resolve_terminal(Path("/data/tmp/file.txt"))
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
    fs, _rel, prefix = root._resolve_terminal(Path("/a/b/leaf/x"))
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
    # The pure router has no storage, so the policy admits any path
    # without probing.
    fs = VirtualFileSystem()
    assert await fs._is_path_mountable(Path("/anything/at/all")) == (True, "")


async def test_mountable_rejects_occupied_point() -> None:
    fs = DictStorageFS({"/data": "directory"})
    with pytest.raises(ValueError, match="conflict"):
        await fs.add_mount(VirtualFileSystem(), "/data")


async def test_mountable_rejects_file_ancestor() -> None:
    fs = DictStorageFS({"/a": "file"})
    with pytest.raises(ValueError, match="conflict"):
        await fs.add_mount(VirtualFileSystem(), "/a/b")


async def test_mountable_rejects_shadowed_descendant() -> None:
    # Connected namespace: a descendant implies its ancestors, so the shadow
    # case surfaces as the mount point existing as a directory.
    fs = DictStorageFS({"/data": "directory", "/data/kept.txt": "file"})
    with pytest.raises(ValueError, match="conflict"):
        await fs.add_mount(VirtualFileSystem(), "/data")


async def test_mountable_allows_clean_sparse_point() -> None:
    fs = DictStorageFS({"/a": "directory", "/other.txt": "file"})
    await fs.add_mount(VirtualFileSystem(), "/a/b/c")
    assert set(fs._mounts) == {"/a/b/c"}


async def test_mountable_conservative_on_backend_error() -> None:
    # "Cannot verify" rejects the mount, never permits it — and says so,
    # rather than diagnosing a phantom contents conflict.
    class BrokenFS(VirtualFileSystem):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(storage=True, **kwargs)

        async def _stat_impl(self, **_: object) -> Result:
            return self._error("db down", kind=VFSErrorKind.unavailable)

    with pytest.raises(ValueError, match="cannot verify") as excinfo:
        await BrokenFS().add_mount(VirtualFileSystem(), "/data")
    assert "conflict" not in str(excinfo.value)
    assert "db down" in str(excinfo.value)


async def test_mountable_treats_not_found_as_absence() -> None:
    # A backend reporting lineage misses as a not_found result reads as
    # pure absence: mountable.
    class SparseFS(DictStorageFS):
        async def _stat_impl(self, **_: object) -> Result:
            return self._error("nothing here", kind=VFSErrorKind.not_found)

    plain = SparseFS({})
    await plain.add_mount(VirtualFileSystem(), "/data")
    assert set(plain._mounts) == {"/data"}


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
    fs, _rel, prefix = root._resolve_terminal(Path("/data/tmp/x"))
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
    fs, _rel, prefix = root._resolve_terminal(Path("/sub/leaf/x"))
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
    root._mounts = {Path("/a"): a, Path("/b"): b}
    a._mounts = {Path("/s"): shared}
    b._mounts = {Path("/s"): shared}
    assert root._reachable_ids() == {id(root), id(a), id(b), id(shared)}


async def test_add_mount_allows_deep_acyclic_tree() -> None:
    root = VirtualFileSystem()
    a = VirtualFileSystem()
    b = VirtualFileSystem()
    await root.add_mount(a, "a")
    await a.add_mount(b, "b")
    fs, rel, prefix = root._resolve_terminal(Path("/a/b/file.txt"))
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
    assert parent._match_mount(Path("/ab/x")) == ("/ab", long)
    assert parent._match_mount(Path("/a/x")) == ("/a", short)
    assert parent._match_mount(Path("/other")) is None


async def test_resolve_terminal_self() -> None:
    parent = VirtualFileSystem()
    fs, rel, prefix = parent._resolve_terminal(Path("/other/file.txt"))
    assert fs is parent
    assert rel == "/other/file.txt"
    assert prefix == "/"


async def test_resolve_terminal_single_mount() -> None:
    parent = VirtualFileSystem()
    child = VirtualFileSystem()
    await parent.add_mount(child, "data")
    fs, rel, prefix = parent._resolve_terminal(Path("/data/file.txt"))
    assert fs is child
    assert rel == "/file.txt"
    assert prefix == "/data"


async def test_resolve_terminal_nested_mounts() -> None:
    parent = VirtualFileSystem()
    child = VirtualFileSystem()
    grandchild = VirtualFileSystem()
    await child.add_mount(grandchild, "sub")
    await parent.add_mount(child, "data")
    fs, rel, prefix = parent._resolve_terminal(Path("/data/sub/file.txt"))
    assert fs is grandchild
    assert rel == "/file.txt"
    assert prefix == "/data/sub"


async def test_resolve_terminal_mount_root() -> None:
    parent = VirtualFileSystem()
    child = VirtualFileSystem()
    await parent.add_mount(child, "data")
    fs, rel, prefix = parent._resolve_terminal(Path("/data"))
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
    r = fs._error("gone", kind=VFSErrorKind.not_found, path=Path("/x"))
    assert r.success is False
    assert r.errors[0].kind is VFSErrorKind.not_found
    assert r.errors[0].path == "/x"


def test_error_attaches_structured_data() -> None:
    fs = VirtualFileSystem()
    r = fs._error("stale", kind=VFSErrorKind.conflict, data={"expected": 1})
    assert r.errors[0].data == {"expected": 1}


def test_error_never_raises_and_carries_function() -> None:
    # The node layer has one failure channel: a returned Result. The op
    # travels as function so a wire consumer can tell which verb failed.
    fs = VirtualFileSystem()
    r = fs._error("gone", kind=VFSErrorKind.not_found, function="read")
    assert r.success is False
    assert r.function == "read"


def test_raise_if_failed_passes_success_through() -> None:
    ok = Result(function="read", observations=[])
    assert raise_if_failed(ok) is ok


def test_raise_if_failed_maps_single_error_to_kind_exception() -> None:
    failed = VirtualFileSystem()._error("gone", kind=VFSErrorKind.not_found, function="read")
    with pytest.raises(NotFoundError) as exc:
        raise_if_failed(failed)
    # the raised exception still carries the full failed result
    assert exc.value.result is failed
    assert exc.value.result.success is False


def test_raise_if_failed_groups_multiple_errors() -> None:
    # A fan-out failure reports every downed terminal, not just the first.
    failed = Result(
        success=False,
        errors=[
            ResultError(kind=VFSErrorKind.not_found, message="gone"),
            ResultError(kind=VFSErrorKind.read_only, message="frozen"),
        ],
    )
    with pytest.raises(ExceptionGroup) as exc:
        raise_if_failed(failed)
    matched = {type(e) for e in exc.value.exceptions}
    assert matched == {NotFoundError, WriteConflictError}


def test_raise_if_failed_handles_errorless_failure() -> None:
    with pytest.raises(VFSError):
        raise_if_failed(Result(success=False))


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

    async def read(
        self,
        path: str | None = None,
        observations: list[Observation] | None = None,
        *,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result:
        assert path is not None  # the router always dispatches here with a path
        self.calls.append(("read", path, columns))
        return Result(function="read", observations=[Observation(path=Path(path), kind="tool")])

    async def run(
        self,
        path: str,
        *,
        arguments: dict[str, Any] | None = None,
        user_id: str | None = None,
    ) -> Result:
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

    async def _is_path_mountable(self, path: Path) -> tuple[bool, str]:
        # Echoed rows are not namespace truth — always accept mounts.
        return True, ""


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
        ("move", {"operations": [ResolvedPair(src=Path("/a.txt"), dest=Path("/b.txt"))], "overwrite": True}),
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
    result = await root.move(moves=[TwoPathOperation(src="/a/x.txt", dest="/a/y.txt"), ("/a/z.txt", "/b/w.txt")])
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
    assert src_frozen.errors[0].path == "/m/frozen/a.txt"
    assert dest_frozen.errors[0].kind is VFSErrorKind.read_only
    assert dest_frozen.errors[0].path == "/m/frozen/b.txt"
    assert child.calls == []


async def test_copy_gates_dest_only() -> None:
    root = VirtualFileSystem()
    child = RecorderFS(permissions=read_write(read=["/frozen"]))
    await root.add_mount(child, "/m")
    result = await root.copy(src="/m/frozen/a.txt", dest="/m/b.txt")
    assert result.success is True  # read-only source is fine for copy
    assert child.calls == [
        ("copy", {"operations": [ResolvedPair(src=Path("/frozen/a.txt"), dest=Path("/b.txt"))], "overwrite": True}),
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


class DeepRowFS(EchoFS):
    """Echo mount whose impl answers a deep row plus an ordinary sibling."""

    DEEP = "/" + "/".join(["a" * 250] * 4)  # 1004 chars — valid locally

    async def _call_local_impl(self, op, *, user_id=None, **kwargs) -> Result:  # type: ignore[override]
        rows = [Observation(path=Path(self.DEEP)), Observation(path=Path("/ok.py"))]
        return Result(function=op, observations=rows)


async def test_fanout_rebase_overflow_classifies_instead_of_raising() -> None:
    # A child row valid in local coordinates but over 1024 once rebased is
    # refused as an `invalid` error; the sibling row in the same result survives.
    root = VirtualFileSystem()
    mount = "/" + "m" * 30
    await root.add_mount(DeepRowFS(), mount)
    result = await root.glob("**/*")
    assert result.success is False
    assert result.paths == (f"{mount}/ok.py",)
    [err] = result.errors
    assert err.kind is VFSErrorKind.invalid
    assert err.data == {"mount": mount, "local_path": DeepRowFS.DEEP}
    # re-addressability: every surviving path is valid input to the next request
    assert all(len(p) <= MAX_PATH_LENGTH and Path(p) is p for p in result.paths)


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
    neither = await fs.read()
    both = await fs.read("/f.txt", observations=[Observation(path=Path("/f.txt"))])
    assert neither.success is False and neither.errors[0].kind is VFSErrorKind.invalid
    assert both.success is False and both.errors[0].kind is VFSErrorKind.invalid
    assert fs.calls == []


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


# ----------------------------------------------------------------------
# one terminal gate — structured error paths and pinned order
# ----------------------------------------------------------------------


async def _gated_namespace() -> VirtualFileSystem:
    """Router with a read-only mount and a capability-limited mount."""
    root = VirtualFileSystem()
    await root.add_mount(RecorderFS(permissions="read"), "/ro")
    await root.add_mount(LimitedEchoFS(caps=frozenset({"read"})), "/dim")
    return root


GATE_FAILURES = [
    (
        "single/no-mount",
        lambda r: r.write(path="/nowhere/x.txt", content="c"),
        VFSErrorKind.not_found,
        "/nowhere/x.txt",
    ),
    (
        "grouped/no-mount",
        lambda r: r.delete(observations=[Observation(path=Path("/nowhere/f.txt"))]),
        VFSErrorKind.not_found,
        "/nowhere/f.txt",
    ),
    (
        "pair/no-mount",
        lambda r: r.move(src="/nowhere/a.txt", dest="/nowhere/b.txt"),
        VFSErrorKind.not_found,
        "/nowhere/a.txt",
    ),
    (
        "entries/no-mount",
        lambda r: r.write(entries=[Entry(path=Path("/nowhere/f.txt"), content="c")]),
        VFSErrorKind.not_found,
        "/nowhere/f.txt",
    ),
    ("scoped/no-mount", lambda r: r.grep("x", paths=("/nowhere/sub",)), VFSErrorKind.not_found, "/nowhere/sub"),
    (
        "mkedge/no-mount",
        lambda r: r.mkedge("/nowhere/a.py", "/nowhere/b.py", "imports"),
        VFSErrorKind.not_found,
        "/nowhere/a.py",
    ),
    ("single/read-only", lambda r: r.write(path="/ro/x.txt", content="c"), VFSErrorKind.read_only, "/ro/x.txt"),
    (
        "grouped/read-only",
        lambda r: r.delete(observations=[Observation(path=Path("/ro/f.txt"))]),
        VFSErrorKind.read_only,
        "/ro/f.txt",
    ),
    ("pair-src/read-only", lambda r: r.move(src="/ro/a.txt", dest="/ro/b.txt"), VFSErrorKind.read_only, "/ro/a.txt"),
    ("pair-dest/read-only", lambda r: r.copy(src="/ro/a.txt", dest="/ro/b.txt"), VFSErrorKind.read_only, "/ro/b.txt"),
    (
        "entries/read-only",
        lambda r: r.write(entries=[Entry(path=Path("/ro/y.txt"), content="c")]),
        VFSErrorKind.read_only,
        "/ro/y.txt",
    ),
    ("single/incapable", lambda r: r.write(path="/dim/x.txt", content="c"), VFSErrorKind.unsupported, "/dim/x.txt"),
    (
        "grouped/incapable",
        lambda r: r.stat(observations=[Observation(path=Path("/dim/f.txt"))]),
        VFSErrorKind.unsupported,
        "/dim/f.txt",
    ),
    ("pair/incapable", lambda r: r.move(src="/dim/a.txt", dest="/dim/b.txt"), VFSErrorKind.unsupported, "/dim/a.txt"),
    (
        "entries/incapable",
        lambda r: r.write(entries=[Entry(path=Path("/dim/f.txt"), content="c")]),
        VFSErrorKind.unsupported,
        "/dim/f.txt",
    ),
    ("scoped/incapable", lambda r: r.grep("x", paths=("/dim/sub",)), VFSErrorKind.unsupported, "/dim/sub"),
    (
        "mkedge/incapable",
        lambda r: r.mkedge("/dim/a.py", "/dim/b.py", "imports"),
        VFSErrorKind.unsupported,
        "/dim/a.py",
    ),
]


@pytest.mark.parametrize(("call", "kind", "path"), [c[1:] for c in GATE_FAILURES], ids=[c[0] for c in GATE_FAILURES])
async def test_gate_failures_carry_the_router_side_path(call: Any, kind: VFSErrorKind, path: str) -> None:
    # Every chokepoint x every gate failure reachable there: the error's
    # structured path is the path the caller addressed — never None.
    root = await _gated_namespace()
    result = await call(root)
    assert result.success is False
    assert result.errors[0].kind is kind
    assert result.errors[0].path == path


async def test_mkedge_permission_denial_reports_the_derived_edge_path() -> None:
    # mkedge's write target is the derived canonical out-edge path — the one
    # gate error implicating a path the caller never typed — and even that
    # path is reported router-side, rebased under the mount prefix.
    root = await _gated_namespace()
    result = await root.mkedge("/ro/a.py", "/ro/b.py", "imports")
    assert result.errors[0].kind is VFSErrorKind.read_only
    assert result.errors[0].path == "/ro/.vfs/a.py/__meta__/edges/out/imports/b.py"


async def test_gate_order_capability_outranks_permission() -> None:
    # A terminal that is simultaneously incapable and read-only fails
    # unsupported: what the terminal cannot do outranks what policy denies.
    root = VirtualFileSystem()
    await root.add_mount(LimitedEchoFS(caps=frozenset({"read"}), permissions="read"), "/m")
    result = await root.write(path="/m/f.txt", content="c")
    assert result.errors[0].kind is VFSErrorKind.unsupported


async def test_gate_order_routability_outranks_capability() -> None:
    # A pure router with no mount at the path is not_found even when the op
    # is also outside its own capability set.
    class IncapableRouter(VirtualFileSystem):
        def capabilities(self) -> frozenset[str] | None:
            return frozenset()

    result = await IncapableRouter().write(path="/nowhere/f.txt", content="c")
    assert result.errors[0].kind is VFSErrorKind.not_found


# ----------------------------------------------------------------------
# audit hardening — gate ordering, error fan-in, input validation
# ----------------------------------------------------------------------


async def test_observation_batch_mutation_gates_capability_before_dispatch() -> None:
    # Finding 1: a delete batch spanning a capable and a capability-limited
    # terminal must dispatch to NEITHER — the capability check runs before
    # any group executes, like every other chokepoint.
    root = VirtualFileSystem()
    capable = RecorderFS()
    limited = LimitedEchoFS(caps=frozenset({"read"}))
    await root.add_mount(capable, "/cap")
    await root.add_mount(limited, "/lim")
    rows = [Observation(path=Path("/cap/a.txt")), Observation(path=Path("/lim/b.txt"))]
    result = await root.delete(observations=rows)
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.unsupported
    assert capable.calls == []  # not dispatched despite being capable


async def test_grouped_observations_reject_non_observation_element() -> None:
    result = await RecorderFS().delete(observations=["notanobs"])  # ty: ignore[invalid-argument-type]
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.invalid


async def test_merge_preserves_distinct_but_equal_errors_from_different_mounts() -> None:
    # Finding 2: two mounts failing identically are two real failures.
    left = Result(function="grep", errors=[ResultError(kind=VFSErrorKind.unavailable, message="down")])
    right = Result(function="grep", errors=[ResultError(kind=VFSErrorKind.unavailable, message="down")])
    merged = left | right
    assert len(merged.errors) == 2


async def test_merge_still_dedups_the_same_error_object_in_a_diamond() -> None:
    err = ResultError(kind=VFSErrorKind.unavailable, message="down")
    a = Result(function="grep", observations=[Observation(path=Path("/a"))], errors=[err])
    b = Result(function="grep", errors=[err])
    diamond = (a | b) & b  # same err instance flows down both arms
    assert len(diamond.errors) == 1


@pytest.mark.parametrize("bad", [("/a",), ("/a", "/b", "/c"), ("/a", 123), "ab"])
async def test_two_path_batch_rejects_malformed_pairs(bad: object) -> None:
    result = await RecorderFS().move(moves=[bad])  # ty: ignore[invalid-argument-type]
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.invalid


async def test_write_entries_rejects_non_entry_element() -> None:
    result = await RecorderFS().write(entries=["notanentry"])  # ty: ignore[invalid-argument-type]
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.invalid


async def test_mkedge_rejects_non_string_edge_type() -> None:
    result = await RecorderFS().mkedge("/a.py", "/b.py", 123)  # ty: ignore[invalid-argument-type]
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.invalid


async def test_write_rejects_entries_and_path_together() -> None:
    result = await RecorderFS().write(entries=[Entry(path=Path("/a.txt"))], path="/b.txt", content="x")
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.invalid


async def test_edit_rejects_old_new_and_edits_together() -> None:
    result = await RecorderFS().edit(path="/f.txt", old="a", new="b", edits=[EditOperation(old="c", new="d")])
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.invalid


@pytest.mark.parametrize("op", ["move", "copy"])
async def test_two_path_rejects_pair_and_batch_together(op: str) -> None:
    method = getattr(RecorderFS(), op)
    result = await method(src="/a.txt", dest="/b.txt", **{"moves" if op == "move" else "copies": [("/c", "/d")]})
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.invalid


@pytest.mark.parametrize("op", ["glob", "grep", "glean"])
async def test_fanout_rejects_paths_and_observations_together(op: str) -> None:
    root = VirtualFileSystem()
    await root.add_mount(EchoFS(), "/m")
    result = await _fan(root, op, paths=("/m/x",), observations=[Observation(path=Path("/m/y"))])
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.invalid


# ----------------------------------------------------------------------
# audit round 2 — batch containers, generators, edit hardening
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("verb", "kwargs"),
    [
        ("delete", {"observations": 5}),
        ("read", {"observations": 5}),
        ("write", {"entries": 5}),
        ("move", {"moves": 5}),
        ("copy", {"copies": 5}),
        ("edit", {"path": "/f.txt", "edits": 5}),
    ],
)
async def test_non_iterable_batch_arg_is_invalid_not_crash(verb: str, kwargs: dict[str, Any]) -> None:
    result = await getattr(RecorderFS(), verb)(**kwargs)
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.invalid


async def test_generator_observations_are_not_silently_dropped() -> None:
    # F2: a single-use generator must survive the validate + group passes.
    root = VirtualFileSystem()
    child = RecorderFS()
    await root.add_mount(child, "/m")
    gen = (Observation(path=Path(p)) for p in ("/m/a.txt", "/m/b.txt"))
    result = await root.delete(observations=gen)  # ty: ignore[invalid-argument-type]
    assert result.success is True
    assert len(child.calls) == 1
    assert len(child.calls[0][1]["observations"]) == 2  # both rows dispatched


async def test_generator_entries_survive() -> None:
    root = VirtualFileSystem()
    child = RecorderFS()
    await root.add_mount(child, "/m")
    gen = (Entry(path=Path(p), content="x") for p in ("/m/a.txt", "/m/b.txt"))
    result = await root.write(gen)  # ty: ignore[invalid-argument-type]
    assert result.success is True
    assert len(child.calls[0][1]["entries"]) == 2


@pytest.mark.parametrize("bad", ["foo", [None], ["notanedit"], [EditOperation(old="a", new="b"), None]])
async def test_edit_rejects_malformed_edits(bad: object) -> None:
    result = await RecorderFS().edit(path="/f.txt", edits=bad)  # ty: ignore[invalid-argument-type]
    assert result.success is False
    assert result.errors[0].kind is VFSErrorKind.invalid


async def test_observation_dispatch_unroutable_path_is_not_found() -> None:
    # F6: obs dispatch matches single-path — storageless self → not_found.
    fs = VirtualFileSystem()
    single = await fs.read("/nope")
    batch = await fs.read(observations=[Observation(path=Path("/nope"))])
    assert single.errors[0].kind is VFSErrorKind.not_found
    assert batch.errors[0].kind is VFSErrorKind.not_found


async def test_prebuilt_subtree_denial_is_a_result_until_the_boundary() -> None:
    # A read-only grandchild deep in a prebuilt subtree denies as a Result;
    # only the caller-applied boundary adapter turns it into an exception.
    grandchild = RecorderFS(permissions="read")
    parent = VirtualFileSystem()
    await parent.add_mount(grandchild, "/c")
    root = VirtualFileSystem()
    await root.add_mount(parent, "/b")
    denied = await root.write(path="/b/c/f.txt", content="x")
    assert denied.success is False
    assert denied.errors[0].kind is VFSErrorKind.read_only
    assert denied.function == "write"
    with pytest.raises(WriteConflictError):
        raise_if_failed(denied)


# ----------------------------------------------------------------------
# settled dispatch — every sibling finishes before the router reports
# ----------------------------------------------------------------------


class SlowWriteFS(VirtualFileSystem):
    """Storage fake whose write is slow and logged — for settle-order proof."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(storage=True, **kwargs)
        self.write_log: list[str] = []

    async def _write_impl(self, *, entries=None, overwrite=True, user_id=None, **_: object) -> Result:
        await asyncio.sleep(0.02)
        rows = []
        for entry in entries or []:
            self.write_log.append(entry.path)
            rows.append(Observation(path=entry.path, kind="file", status="created"))
        return Result(function="write", observations=rows)


class FailingWriteFS(VirtualFileSystem):
    """Storage fake whose write fails fast with a classified Result."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(storage=True, **kwargs)

    async def _write_impl(self, **_: object) -> Result:
        return self._error("boom", kind=VFSErrorKind.unavailable, function="write")


class BuggyWriteFS(VirtualFileSystem):
    """Storage fake whose write raises a raw exception — an impl bug."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(storage=True, **kwargs)

    async def _write_impl(self, **_: object) -> Result:
        msg = "impl bug"
        raise RuntimeError(msg)


async def test_sibling_writes_settle_before_failure_is_reported() -> None:
    # One terminal fails fast, the other writes slowly: the returned Result
    # must already contain the slow sibling's outcome — never a write that
    # lands behind a caller who has already seen the failure.
    root = VirtualFileSystem()
    ok, bad = SlowWriteFS(), FailingWriteFS()
    await root.add_mount(ok, "/ok")
    await root.add_mount(bad, "/bad")
    result = await root.write(
        entries=[Entry(path=Path("/ok/a.txt"), content="A"), Entry(path=Path("/bad/b.txt"), content="B")],
    )
    assert result.success is False
    assert ok.write_log == ["/a.txt"]  # completed before the router returned
    assert "/ok/a.txt" in result.paths  # and its outcome is reported, not dropped
    assert any(e.kind is VFSErrorKind.unavailable for e in result.errors)


async def test_impl_bug_propagates_only_after_siblings_settle() -> None:
    # A raw exception is an impl bug: it propagates with its traceback, but
    # only after every sibling group has finished mutating.
    root = VirtualFileSystem()
    ok, buggy = SlowWriteFS(), BuggyWriteFS()
    await root.add_mount(ok, "/ok")
    await root.add_mount(buggy, "/bug")
    with pytest.raises(RuntimeError, match="impl bug"):
        await root.write(
            entries=[Entry(path=Path("/ok/a.txt"), content="A"), Entry(path=Path("/bug/b.txt"), content="B")],
        )
    assert ok.write_log == ["/a.txt"]  # the world had settled before the raise


async def test_cancellation_reraises_untouched() -> None:
    # Cancellation is not an impl bug: it re-raises as-is, never collected
    # into an ExceptionGroup, so task teardown semantics stay intact.
    class CancelledWriteFS(VirtualFileSystem):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(storage=True, **kwargs)

        async def _write_impl(self, **_: object) -> Result:
            raise asyncio.CancelledError

    root = VirtualFileSystem()
    await root.add_mount(CancelledWriteFS(), "/c")
    with pytest.raises(asyncio.CancelledError):
        await root.write(entries=[Entry(path=Path("/c/a.txt"), content="A")])


async def test_multiple_impl_bugs_raise_an_exception_group() -> None:
    root = VirtualFileSystem()
    await root.add_mount(BuggyWriteFS(), "/bug1")
    await root.add_mount(BuggyWriteFS(), "/bug2")
    with pytest.raises(ExceptionGroup) as exc:
        await root.write(
            entries=[Entry(path=Path("/bug1/a.txt"), content="A"), Entry(path=Path("/bug2/b.txt"), content="B")],
        )
    assert len(exc.value.exceptions) == 2


# ----------------------------------------------------------------------
# failed results report their verb in function
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("verb", "call"),
    [
        ("read", lambda fs: fs.read("/nope")),
        ("stat", lambda fs: fs.stat("/nope")),
        ("ls", lambda fs: fs.ls("/nope")),
        ("tree", lambda fs: fs.tree("/nope")),
        ("write", lambda fs: fs.write(path="/nope", content="x")),
        ("edit", lambda fs: fs.edit(path="/nope", old="a", new="b")),
        ("delete", lambda fs: fs.delete("/nope")),
        ("mkdir", lambda fs: fs.mkdir("/nope/d")),
        ("mkedge", lambda fs: fs.mkedge("/a.txt", "/b.txt", "ref")),
        ("move", lambda fs: fs.move("/a", "/b")),
        ("copy", lambda fs: fs.copy("/a", "/b")),
        ("graph", lambda fs: fs.graph("descendants", "/nope")),
        ("run", lambda fs: fs.run("/nope")),
        ("glob", lambda fs: fs.glob("*", paths=("/nope",))),
        ("grep", lambda fs: fs.grep("x", paths=("/nope",))),
        ("glean", lambda fs: fs.glean("q", paths=("/nope",))),
    ],
)
async def test_unroutable_failure_reports_its_verb(verb: str, call: Any) -> None:
    # Storageless, mountless root: every verb fails as unroutable — and the
    # failed result names the verb, so a wire consumer knows what failed.
    result = await call(VirtualFileSystem())
    assert result.success is False
    assert result.function == verb


# ----------------------------------------------------------------------
# mount-spine visibility — the namespace is discoverable top-down
# ----------------------------------------------------------------------


class CannedFS(VirtualFileSystem):
    """Storage terminal answering each op from a canned Result, recording calls."""

    def __init__(self, answers: dict[str, Result] | None = None, **kwargs: Any) -> None:
        kwargs.setdefault("storage", True)
        super().__init__(**kwargs)
        self.answers = answers or {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def _call_local_impl(self, op, *, user_id=None, **kwargs) -> Result:  # type: ignore[override]
        self.calls.append((op, dict(kwargs)))
        return self.answers.get(op, Result(function=op, observations=[]))

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
