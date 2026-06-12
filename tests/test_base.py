"""Tests for the rebuilt ``vfs.base2.VirtualFileSystem`` router.

Built up section by section alongside ``src/vfs/base2.py``.  These tests
exercise only the pure router — no storage, no sessions.  Storage behavior
belongs to ``DatabaseFileSystem`` and is tested elsewhere.
"""

from __future__ import annotations

import pytest

from vfs.base2 import VirtualFileSystem


class SpyFS(VirtualFileSystem):
    """A mount that records how many times it was closed."""

    def __init__(self, **kwargs: object) -> None:
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


@pytest.mark.parametrize("raw", [" /data", "/ /data", "/data/ ", "/data/ x", "/x /y", "/a/ /b"])
def test_normalize_mount_path_rejects_whitespace_segments(raw: str) -> None:
    with pytest.raises(ValueError):
        VirtualFileSystem._normalize_mount_path(raw)


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


@pytest.mark.parametrize("raw", [" ", "/ ", "/\tdata", "/data\n", "/da\tta", "/data\x7f"])
def test_normalize_mount_path_rejects_whitespace_and_control(raw: str) -> None:
    with pytest.raises(ValueError):
        VirtualFileSystem._normalize_mount_path(raw)


# ----------------------------------------------------------------------
# add_mount
# ----------------------------------------------------------------------


async def test_add_mount_accepts_bare_and_slashed() -> None:
    parent = VirtualFileSystem()
    await parent.add_mount("data", VirtualFileSystem())
    await parent.add_mount("/docs", VirtualFileSystem())
    assert set(parent._mounts) == {"/data", "/docs"}


async def test_add_mount_rejects_duplicate() -> None:
    parent = VirtualFileSystem()
    await parent.add_mount("data", VirtualFileSystem())
    with pytest.raises(ValueError, match="already exists"):
        await parent.add_mount("/data", VirtualFileSystem())


async def test_add_mount_propagates_raise_on_error() -> None:
    parent = VirtualFileSystem(raise_on_error=True)
    child = VirtualFileSystem()
    await parent.add_mount("data", child)
    assert child._raise_on_error is True


async def test_add_mount_rejects_same_instance_twice() -> None:
    parent = VirtualFileSystem()
    child = VirtualFileSystem()
    await parent.add_mount("here", child)
    with pytest.raises(ValueError, match="already mounted"):
        await parent.add_mount("there", child)
    assert set(parent._mounts) == {"/here"}


async def test_add_mount_rejects_same_instance_nested_elsewhere() -> None:
    # The same instance cannot appear twice even across delegation levels.
    root = VirtualFileSystem()
    data = VirtualFileSystem()
    shared = VirtualFileSystem()
    await root.add_mount("/data", data)
    await root.add_mount("/x", shared)
    with pytest.raises(ValueError, match="already mounted"):
        await root.add_mount("/data/shared", shared)  # would delegate into data
    assert set(data._mounts) == set()


async def test_add_mount_denied_when_disallowed() -> None:
    root = VirtualFileSystem(allow_child_mounts=False)
    with pytest.raises(ValueError, match="does not allow child mounts"):
        await root.add_mount("/data", VirtualFileSystem())
    assert set(root._mounts) == set()


async def test_add_mount_delegation_respects_child_policy() -> None:
    # root allows, but the /remote mount forbids child mounts (e.g. an MCP
    # adapter): a delegated add into it is refused.
    root = VirtualFileSystem()
    remote = VirtualFileSystem(allow_child_mounts=False)
    await root.add_mount("/remote", remote)
    with pytest.raises(ValueError, match="does not allow child mounts"):
        await root.add_mount("/remote/cache", VirtualFileSystem())
    assert set(remote._mounts) == set()
    assert set(root._mounts) == {"/remote"}


async def test_add_mount_rejects_self_mount() -> None:
    parent = VirtualFileSystem()
    with pytest.raises(ValueError, match="into itself"):
        await parent.add_mount("loop", parent)


async def test_add_mount_nested_delegates_to_parent_mount() -> None:
    # Forward order: /data mounted, then /data/tmp delegates into /data.
    root = VirtualFileSystem()
    data = VirtualFileSystem()
    tmp = VirtualFileSystem()
    await root.add_mount("/data", data)
    await root.add_mount("/data/tmp", tmp)
    assert set(root._mounts) == {"/data"}
    assert set(data._mounts) == {"/tmp"}
    fs, rel, prefix = root._resolve_terminal("/data/tmp/file.txt")
    assert fs is tmp
    assert rel == "/file.txt"
    assert prefix == "/data/tmp"


async def test_add_mount_reverse_order_conflict() -> None:
    # Reverse order: /data/tmp first, then /data is owned by the deeper mount.
    root = VirtualFileSystem()
    await root.add_mount("/data/tmp", VirtualFileSystem())
    assert set(root._mounts) == {"/data/tmp"}
    with pytest.raises(ValueError, match="deeper mount"):
        await root.add_mount("/data", VirtualFileSystem())
    assert set(root._mounts) == {"/data/tmp"}


async def test_add_mount_deep_nested_delegation() -> None:
    root = VirtualFileSystem()
    a = VirtualFileSystem()
    b = VirtualFileSystem()
    leaf = VirtualFileSystem()
    await root.add_mount("/a", a)
    await a.add_mount("/b", b)
    await root.add_mount("/a/b/leaf", leaf)  # delegates root -> a -> b
    assert set(b._mounts) == {"/leaf"}
    fs, _rel, prefix = root._resolve_terminal("/a/b/leaf/x")
    assert fs is leaf
    assert prefix == "/a/b/leaf"


async def test_remove_mount_nested_delegates() -> None:
    root = VirtualFileSystem()
    data = VirtualFileSystem()
    tmp = VirtualFileSystem()
    await root.add_mount("/data", data)
    await root.add_mount("/data/tmp", tmp)
    await root.remove_mount("/data/tmp")
    assert set(data._mounts) == set()
    assert set(root._mounts) == {"/data"}


async def test_add_mount_storageless_allows_sparse_nested() -> None:
    root = VirtualFileSystem()
    await root.add_mount("/a/b/c", VirtualFileSystem())
    assert set(root._mounts) == {"/a/b/c"}


async def test_add_mount_rejects_unmountable_storage_path() -> None:
    root = MountPolicyFS({"/projects"})
    with pytest.raises(ValueError, match="conflict"):
        await root.add_mount("/projects", VirtualFileSystem())
    await root.add_mount("/free", VirtualFileSystem())  # mountable path is fine
    assert set(root._mounts) == {"/free"}


async def test_add_mount_mountable_check_runs_after_delegation() -> None:
    # The policy check runs on the fs that ultimately owns the mount.
    root = VirtualFileSystem()
    data = MountPolicyFS({"/tmp"})
    await root.add_mount("/data", data)
    with pytest.raises(ValueError, match="conflict"):
        await root.add_mount("/data/tmp", VirtualFileSystem())
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
    await root.add_mount("/a", a)
    await root.add_mount("/b", b)
    with pytest.raises(ValueError, match="already mounted"):
        await a.add_mount("/shared", b)  # b already lives at /b
    assert set(a._mounts) == set()
    await root.close()
    assert b.close_count == 1  # not double-closed


async def test_add_mount_rejects_filesystem_mounted_in_another_tree() -> None:
    # A filesystem mounted under one root cannot be mounted under another
    # (its _parent is already set), so teardown never double-closes it.
    root1 = VirtualFileSystem()
    root2 = VirtualFileSystem()
    child = SpyFS()
    await root1.add_mount("/c", child)
    with pytest.raises(ValueError, match="already mounted"):
        await root2.add_mount("/c", child)
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
    await root.add_mount("/data", data)
    await data.add_mount("/tmp", tmp)
    fs, _rel, prefix = root._resolve_terminal("/data/tmp/x")
    assert fs is tmp
    assert prefix == "/data/tmp"


async def test_add_mount_allows_unmounted_fs_carrying_its_own_mounts() -> None:
    # Building a subtree first, then mounting the whole thing, is allowed.
    root = VirtualFileSystem()
    sub = VirtualFileSystem()
    leaf = VirtualFileSystem()
    await sub.add_mount("/leaf", leaf)
    await root.add_mount("/sub", sub)
    assert sub._parent is root
    assert leaf._parent is sub
    fs, _rel, prefix = root._resolve_terminal("/sub/leaf/x")
    assert fs is leaf
    assert prefix == "/sub/leaf"


async def test_parent_pointer_set_and_cleared() -> None:
    root = VirtualFileSystem()
    child = VirtualFileSystem()
    await root.add_mount("/data", child)
    assert child._parent is root
    await root.remove_mount("/data")
    assert child._parent is None


async def test_parent_pointer_for_nested_delegation() -> None:
    root = VirtualFileSystem()
    data = VirtualFileSystem()
    tmp = VirtualFileSystem()
    await root.add_mount("/data", data)
    await root.add_mount("/data/tmp", tmp)  # delegated into data
    assert data._parent is root
    assert tmp._parent is data
    assert tmp._root() is root


async def test_close_clears_parent_pointers() -> None:
    root = VirtualFileSystem()
    child = VirtualFileSystem()
    await root.add_mount("/data", child)
    await root.close()
    assert child._parent is None


async def test_add_mount_duplicate_across_delegation_does_not_double_close() -> None:
    # leaf at /other, then mounted again under /data/tmp: the whole-graph
    # duplicate guard refuses it before delegating, so close() does not
    # close leaf twice.
    root = VirtualFileSystem()
    data = VirtualFileSystem()
    leaf = SpyFS()
    await root.add_mount("/data", data)
    await root.add_mount("/other", leaf)
    with pytest.raises(ValueError, match="already mounted"):
        await root.add_mount("/data/tmp", leaf)
    assert set(data._mounts) == set()
    await root.close()
    assert leaf.close_count == 1


async def test_add_mount_allows_distinct_instances() -> None:
    # Two distinct instances (e.g. BindFS wrappers over one upstream) are fine.
    parent = VirtualFileSystem()
    await parent.add_mount("a", VirtualFileSystem())
    await parent.add_mount("b", VirtualFileSystem())
    assert set(parent._mounts) == {"/a", "/b"}


async def test_add_mount_rejects_direct_cycle() -> None:
    # root -> child -> root
    root = VirtualFileSystem()
    child = VirtualFileSystem()
    await root.add_mount("child", child)
    with pytest.raises(ValueError, match="cycle"):
        await child.add_mount("back", root)
    assert child._mounts == {}


async def test_add_mount_rejects_indirect_cycle() -> None:
    # root -> a -> b -> root
    root = VirtualFileSystem()
    a = VirtualFileSystem()
    b = VirtualFileSystem()
    await root.add_mount("a", a)
    await a.add_mount("b", b)
    with pytest.raises(ValueError, match="cycle"):
        await b.add_mount("back", root)
    assert b._mounts == {}


async def test_no_cycle_means_close_terminates() -> None:
    # Once the cycle is refused, the acyclic tree closes cleanly.
    root = VirtualFileSystem()
    child = VirtualFileSystem()
    await root.add_mount("child", child)
    with pytest.raises(ValueError, match="cycle"):
        await child.add_mount("back", root)
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
    await root.add_mount("a", a)
    await a.add_mount("b", b)
    fs, rel, prefix = root._resolve_terminal("/a/b/file.txt")
    assert fs is b
    assert rel == "/file.txt"
    assert prefix == "/a/b"


async def test_add_mount_rebuilds_sorted_list_longest_first() -> None:
    parent = VirtualFileSystem()
    await parent.add_mount("a", VirtualFileSystem())
    await parent.add_mount("abc", VirtualFileSystem())
    await parent.add_mount("ab", VirtualFileSystem())
    assert parent._sorted_mount_paths == ["/abc", "/ab", "/a"]


# ----------------------------------------------------------------------
# remove_mount
# ----------------------------------------------------------------------


async def test_remove_mount_updates_table() -> None:
    parent = VirtualFileSystem()
    await parent.add_mount("data", VirtualFileSystem())
    await parent.add_mount("docs", VirtualFileSystem())
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
    await parent.add_mount("data", child)
    await parent.remove_mount("/data")
    assert child.close_count == 0


# ----------------------------------------------------------------------
# close
# ----------------------------------------------------------------------


async def test_close_is_polymorphic_and_clears() -> None:
    parent = VirtualFileSystem()
    child_a = SpyFS()
    child_b = SpyFS()
    await parent.add_mount("a", child_a)
    await parent.add_mount("b", child_b)
    await parent.close()
    assert child_a.close_count == 1
    assert child_b.close_count == 1
    assert parent._mounts == {}
    assert parent._sorted_mount_paths == []


async def test_close_recurses_into_nested_mounts() -> None:
    parent = VirtualFileSystem()
    child = VirtualFileSystem()
    grandchild = SpyFS()
    await child.add_mount("sub", grandchild)
    await parent.add_mount("data", child)
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
    await parent.add_mount("a", BadCloseFS())
    await parent.add_mount("b", good)
    with pytest.raises(RuntimeError, match="boom"):
        await parent.close()
    assert good.close_count == 1
    assert parent._mounts == {}
    assert parent._sorted_mount_paths == []


async def test_close_groups_multiple_failures() -> None:
    parent = VirtualFileSystem()
    await parent.add_mount("a", BadCloseFS())
    await parent.add_mount("b", BadCloseFS())
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
    await parent.add_mount("a", short)
    await parent.add_mount("ab", long)
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
    await parent.add_mount("data", child)
    fs, rel, prefix = parent._resolve_terminal("/data/file.txt")
    assert fs is child
    assert rel == "/file.txt"
    assert prefix == "/data"


async def test_resolve_terminal_nested_mounts() -> None:
    parent = VirtualFileSystem()
    child = VirtualFileSystem()
    grandchild = VirtualFileSystem()
    await child.add_mount("sub", grandchild)
    await parent.add_mount("data", child)
    fs, rel, prefix = parent._resolve_terminal("/data/sub/file.txt")
    assert fs is grandchild
    assert rel == "/file.txt"
    assert prefix == "/data/sub"


async def test_resolve_terminal_mount_root() -> None:
    parent = VirtualFileSystem()
    child = VirtualFileSystem()
    await parent.add_mount("data", child)
    fs, rel, prefix = parent._resolve_terminal("/data")
    assert fs is child
    assert rel == "/"
    assert prefix == "/data"
