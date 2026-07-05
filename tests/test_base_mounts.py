"""Mount table lifecycle: construction, add/remove, close, the mount lock, and terminal resolution."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from base_doubles import (
    BadCloseFS,
    DictStorageFS,
    GatedCloseFS,
    MountPolicyFS,
    RecorderStorage,
    SlowCloseFS,
    SpyFS,
    SuspendingStorageFS,
    _failed,
)
from vfs.base2 import VirtualFileSystem
from vfs.paths import Path
from vfs.results2 import Result, VFSErrorKind

# ----------------------------------------------------------------------
# __init__
# ----------------------------------------------------------------------


def test_init_defaults() -> None:
    fs = VirtualFileSystem()
    assert fs._storage is None
    assert fs._storage_ops == frozenset()
    assert fs.name is None
    assert fs.title is None
    assert fs.description is None
    assert fs._mounts == {}
    assert fs._sorted_mount_paths == []
    assert fs._class_name == "VirtualFileSystem"


def test_init_holds_the_composed_backend() -> None:
    # Storage is an object the node holds, not a thing the node is.
    backend = RecorderStorage()
    fs = VirtualFileSystem(name="root", storage=backend)
    assert fs.name == "root"
    assert fs._storage is backend


def test_init_rejects_backend_missing_the_read_family() -> None:
    # The read family is the minimum viable backend — fail loud at
    # construction, even for callers ty never saw.
    class StatOnly:
        async def stat(self, **kwargs: Any) -> Result:
            return Result(function="stat", observations=[])

    with pytest.raises(TypeError, match="read family"):
        VirtualFileSystem(storage=StatOnly())  # ty: ignore[invalid-argument-type]


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
    class BrokenStorage(RecorderStorage):
        async def stat(self, **_: Any) -> Result:
            return _failed("stat", VFSErrorKind.unavailable, "db down")

    with pytest.raises(ValueError, match="cannot verify") as excinfo:
        await VirtualFileSystem(storage=BrokenStorage()).add_mount(VirtualFileSystem(), "/data")
    assert "conflict" not in str(excinfo.value)
    assert "db down" in str(excinfo.value)


async def test_mountable_treats_not_found_as_absence() -> None:
    # A backend reporting lineage misses as a not_found result reads as
    # pure absence: mountable.
    class SparseStorage(RecorderStorage):
        async def stat(self, **_: Any) -> Result:
            return _failed("stat", VFSErrorKind.not_found, "nothing here")

    plain = VirtualFileSystem(storage=SparseStorage())
    await plain.add_mount(VirtualFileSystem(), "/data")
    assert set(plain._mounts) == {"/data"}


async def test_mountable_rejects_errorless_failure_conservatively() -> None:
    # A malformed failure (success=False, no errors) is not absence: the
    # probe refuses to verify, mirroring _absorb_not_found's guard.
    class MalformedStatStorage(RecorderStorage):
        async def stat(self, **_: Any) -> Result:
            return Result(function="stat", success=False)

    fs = VirtualFileSystem(storage=MalformedStatStorage())
    ok, reason = await fs._is_path_mountable(Path("/data"))
    assert ok is False
    assert "cannot verify" in reason
    with pytest.raises(ValueError, match="cannot verify"):
        await fs.add_mount(VirtualFileSystem(), "/data")


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
# concurrent mount mutation (the lock + the commit gate)
# ----------------------------------------------------------------------


async def test_concurrent_add_same_path_one_winner_no_orphan() -> None:
    root = SuspendingStorageFS()
    c1 = SuspendingStorageFS(name="c1")
    c2 = SuspendingStorageFS(name="c2")
    results = await asyncio.gather(root.add_mount(c1, "/same"), root.add_mount(c2, "/same"), return_exceptions=True)
    errors = [r for r in results if isinstance(r, Exception)]
    assert len(errors) == 1
    assert "Mount already exists" in str(errors[0])
    winner = root._mounts[Path("/same")]
    loser = c2 if winner is c1 else c1
    assert winner._parent is root
    assert loser._parent is None
    await root.add_mount(loser, "/elsewhere")  # the loser is not orphaned
    assert set(root._mounts) == {"/same", "/elsewhere"}


async def test_concurrent_add_same_child_two_parents_stays_a_tree() -> None:
    p1 = SuspendingStorageFS(name="p1")
    p2 = SuspendingStorageFS(name="p2")
    child = SuspendingStorageFS(name="child")
    results = await asyncio.gather(p1.add_mount(child, "/c"), p2.add_mount(child, "/c"), return_exceptions=True)
    errors = [r for r in results if isinstance(r, Exception)]
    assert len(errors) == 1
    assert "already mounted elsewhere" in str(errors[0])
    holders = [fs for fs in (p1, p2) if "/c" in fs._mounts]
    assert len(holders) == 1
    assert child._parent is holders[0]


async def test_concurrent_add_ancestor_and_descendant_never_flatten() -> None:
    root = SuspendingStorageFS()
    a = SuspendingStorageFS(name="a")
    ab = SuspendingStorageFS(name="ab")
    results = await asyncio.gather(root.add_mount(a, "/a"), root.add_mount(ab, "/a/b"), return_exceptions=True)
    errors = [r for r in results if isinstance(r, Exception)]
    assert not ("/a" in root._mounts and "/a/b" in root._mounts)
    if errors:
        # /a/b committed first, so /a hits the deeper-mount ownership check.
        assert len(errors) == 1
        assert "owned by a deeper mount" in str(errors[0])
        assert set(root._mounts) == {"/a/b"}
    else:
        # /a committed first, so /a/b delegated into it — nested, not flat.
        assert set(root._mounts) == {"/a"}
        assert set(a._mounts) == {"/b"}


async def test_concurrent_mutual_mounts_end_with_one_edge() -> None:
    # The commit gate's cycle re-check: R under F racing F under R.
    r = SuspendingStorageFS(name="r")
    f = SuspendingStorageFS(name="f")
    results = await asyncio.gather(r.add_mount(f, "/f"), f.add_mount(r, "/r"), return_exceptions=True)
    errors = [x for x in results if isinstance(x, Exception)]
    assert len(errors) == 1
    assert "would create a cycle" in str(errors[0])
    assert ("/f" in r._mounts) + ("/r" in f._mounts) == 1
    assert r._root() is f._root()  # one tree; the parent chain terminates


@pytest.mark.parametrize("close_first", [True, False])
async def test_close_racing_add_orphans_nothing(close_first: bool) -> None:
    root = SuspendingStorageFS()
    slow = SlowCloseFS()
    await root.add_mount(slow, "/slow")
    incoming = SuspendingStorageFS(name="incoming")
    ops = [root.close(), root.add_mount(incoming, "/x")]
    if not close_first:
        ops.reverse()
    results = await asyncio.gather(*ops, return_exceptions=True)
    assert [r for r in results if isinstance(r, Exception)] == []
    for fs in (slow, incoming):
        assert (fs._parent is root) == (fs in root._mounts.values())


async def test_cancelled_close_leaves_no_half_detached_child() -> None:
    # Cancellation mid-close splits the loop cleanly: closed children are
    # fully detached, the rest fully attached — and a second close finishes.
    gate = asyncio.Event()
    root = VirtualFileSystem()
    first, blocked, last = SpyFS(), GatedCloseFS(gate), SpyFS()
    await root.add_mount(first, "/a")
    await root.add_mount(blocked, "/b")
    await root.add_mount(last, "/c")

    task = asyncio.ensure_future(root.close())
    while first.close_count == 0:
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert not root._mount_lock.locked()
    assert first._parent is None and Path("/a") not in root._mounts
    assert blocked._parent is root and Path("/b") in root._mounts
    assert last._parent is root and Path("/c") in root._mounts
    assert root._sorted_mount_paths == sorted(root._mounts, reverse=True)

    # The closed child is truly detached — no reverse orphan to double-mount.
    other = VirtualFileSystem()
    await other.add_mount(first, "/adopted")
    assert first._parent is other

    gate.set()
    await root.close()
    assert root._mounts == {}
    assert blocked._parent is None and last._parent is None
    assert blocked.close_count == 1 and last.close_count == 1


async def test_readers_do_not_wait_on_the_mount_lock() -> None:
    gate = asyncio.Event()
    gate.set()
    root = SuspendingStorageFS(gate=gate)
    docs = DictStorageFS({"/file.txt": "file"})
    await root.add_mount(docs, "/docs")

    gate.clear()  # the next probe parks until the test releases it
    pending = asyncio.ensure_future(root.add_mount(SuspendingStorageFS(), "/data"))
    await asyncio.sleep(0)  # let the add reach its probe

    result = await asyncio.wait_for(root.stat("/docs/file.txt"), timeout=1)
    assert result.success
    assert not pending.done()

    gate.set()
    await pending
    assert set(root._mounts) == {"/docs", "/data"}


async def test_concurrent_delegated_and_direct_adds_serialize() -> None:
    # Exercises the parent-before-child lock order: no deadlock, one winner.
    root = SuspendingStorageFS(name="root")
    data = SuspendingStorageFS(name="data")
    await root.add_mount(data, "/data")
    d1 = SuspendingStorageFS(name="d1")
    d2 = SuspendingStorageFS(name="d2")
    results = await asyncio.wait_for(
        asyncio.gather(
            root.add_mount(d1, "/data/deep"),
            data.add_mount(d2, "/deep"),
            return_exceptions=True,
        ),
        timeout=5,
    )
    errors = [r for r in results if isinstance(r, Exception)]
    assert len(errors) == 1
    assert "Mount already exists" in str(errors[0])
    winner = data._mounts[Path("/deep")]
    loser = d2 if winner is d1 else d1
    assert winner._parent is data
    assert loser._parent is None


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
# derived capabilities + own-backend disposal
# ----------------------------------------------------------------------


async def test_close_disposes_own_backend_after_mounts() -> None:
    class DisposableStorage(RecorderStorage):
        def __init__(self) -> None:
            super().__init__()
            self.closed = 0

        async def close(self) -> None:
            self.closed += 1

    backend = DisposableStorage()
    fs = VirtualFileSystem(storage=backend)
    child = SpyFS()
    await fs.add_mount(child, "/c")
    await fs.close()
    assert child.close_count == 1
    assert backend.closed == 1


async def test_close_without_disposable_backend_is_fine() -> None:
    # A backend with no close (in-memory) needs no disposal ceremony.
    fs = VirtualFileSystem(storage=RecorderStorage())
    await fs.close()


async def test_close_collects_backend_failure_like_a_mount_failure() -> None:
    class BadDisposeStorage(RecorderStorage):
        async def close(self) -> None:
            msg = "engine boom"
            raise RuntimeError(msg)

    fs = VirtualFileSystem(storage=BadDisposeStorage())
    good = SpyFS()
    await fs.add_mount(good, "/g")
    with pytest.raises(RuntimeError, match="engine boom"):
        await fs.close()
    assert good.close_count == 1  # the sibling mount was not stranded
    assert fs._mounts == {}
