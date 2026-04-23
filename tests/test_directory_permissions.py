"""Tests for directory-level permissions on a mount.

Mirrors :mod:`tests.test_permissions` but exercises the
:class:`vfs.permissions.PermissionMap` value type and the
per-path resolution flow through the five chokepoints in
:mod:`vfs.base`.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from vfs import permissions as permissions_ns
from vfs.backends.database import DatabaseFileSystem
from vfs.base import VirtualFileSystem
from vfs.client import VFSClient, VFSClientAsync
from vfs.exceptions import WriteConflictError
from vfs.models import VFSEntry
from vfs.permissions import (
    PermissionMap,
    check_writable,
    coerce_permissions,
    read_only,
    read_write,
)
from vfs.results import TwoPathOperation

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


async def _sqlite_engine():
    """Return an engine whose ``vfs_entries`` schema is ready to use.

    A throwaway :class:`DatabaseFileSystem` mints an entry-table class
    to drive ``create_all``; subsequent filesystems constructed on the
    same engine mint their own classes against the same physical table,
    which is all SQLAlchemy DML needs.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    seed = DatabaseFileSystem(engine=engine)
    async with engine.begin() as conn:
        await conn.run_sync(seed._model.metadata.create_all)
    return engine


async def _seed(fs: DatabaseFileSystem, path: str, content: str = "hi") -> None:
    """Seed a file directly via ``_write_impl``, bypassing the router."""
    async with fs._use_session() as s:
        await fs._write_impl(path, content=content, session=s)


# ==================================================================
# PermissionMap construction and validation
# ==================================================================


class TestPermissionMapConstruction:
    def test_default_only(self):
        pm = PermissionMap(default="read")
        assert pm.default == "read"
        assert pm.overrides == ()

    def test_default_default_is_read_write(self):
        pm = PermissionMap()
        assert pm.default == "read_write"

    def test_normalizes_override_paths(self):
        pm = PermissionMap(
            default="read",
            overrides=(("/foo/", "read_write"), ("/bar/./baz", "read_write")),
        )
        paths = {p for p, _ in pm.overrides}
        assert paths == {"/foo", "/bar/baz"}

    def test_overrides_sorted_longest_first(self):
        pm = PermissionMap(
            default="read",
            overrides=(
                ("/a", "read_write"),
                ("/a/b/c", "read_write"),
                ("/a/b", "read_write"),
            ),
        )
        lengths = [len(p) for p, _ in pm.overrides]
        assert lengths == sorted(lengths, reverse=True)

    def test_duplicate_override_rejected(self):
        with pytest.raises(ValueError, match="Duplicate override"):
            PermissionMap(
                default="read",
                overrides=(("/x", "read_write"), ("/x", "read")),
            )

    def test_root_override_rejected(self):
        with pytest.raises(ValueError, match="must not be '/'"):
            PermissionMap(default="read", overrides=(("/", "read_write"),))

    def test_invalid_default_rejected(self):
        with pytest.raises(ValueError, match="'read' or 'read_write'"):
            PermissionMap(default="readonly")  # type: ignore[arg-type]

    def test_invalid_override_permission_rejected(self):
        with pytest.raises(ValueError, match="'read' or 'read_write'"):
            PermissionMap(default="read", overrides=(("/x", "ro"),))  # type: ignore[arg-type]

    def test_frozen(self):
        pm = PermissionMap(default="read")
        with pytest.raises((AttributeError, TypeError)):
            pm.default = "read_write"  # type: ignore[misc]


class TestPermissionMapResolve:
    def test_default_when_no_overrides(self):
        pm = PermissionMap(default="read")
        assert pm.resolve("/anywhere") == "read"

    def test_default_when_no_match(self):
        pm = PermissionMap(default="read", overrides=(("/x", "read_write"),))
        assert pm.resolve("/y/z") == "read"

    def test_exact_match(self):
        pm = PermissionMap(default="read", overrides=(("/x", "read_write"),))
        assert pm.resolve("/x") == "read_write"

    def test_descendant_match(self):
        pm = PermissionMap(default="read", overrides=(("/x", "read_write"),))
        assert pm.resolve("/x/y/z.md") == "read_write"

    def test_no_partial_segment_match(self):
        """`/synthesis-archive` must NOT match a `/synthesis` rule."""
        pm = PermissionMap(default="read", overrides=(("/synthesis", "read_write"),))
        assert pm.resolve("/synthesis-archive/foo.md") == "read"

    def test_longest_prefix_wins(self):
        pm = PermissionMap(
            default="read",
            overrides=(
                ("/a", "read_write"),
                ("/a/b", "read"),
            ),
        )
        assert pm.resolve("/a/x") == "read_write"
        assert pm.resolve("/a/b") == "read"
        assert pm.resolve("/a/b/x") == "read"

    def test_nested_three_levels(self):
        pm = PermissionMap(
            default="read",
            overrides=(
                ("/a", "read_write"),
                ("/a/b", "read"),
                ("/a/b/c", "read_write"),
            ),
        )
        assert pm.resolve("/a/x") == "read_write"
        assert pm.resolve("/a/b/x") == "read"
        assert pm.resolve("/a/b/c/x") == "read_write"

    def test_resolves_normalized_lookup(self):
        pm = PermissionMap(default="read", overrides=(("/x", "read_write"),))
        assert pm.resolve("/x/./y") == "read_write"


# ==================================================================
# Factory helpers
# ==================================================================


class TestFactoryHelpers:
    def test_read_only_no_kwargs(self):
        pm = read_only()
        assert pm.default == "read"
        assert pm.overrides == ()

    def test_read_only_with_writable(self):
        pm = read_only(write=["/synthesis", "/index.md"])
        assert pm.default == "read"
        assert pm.resolve("/synthesis/x.md") == "read_write"
        assert pm.resolve("/index.md") == "read_write"
        assert pm.resolve("/raw/y.md") == "read"

    def test_read_only_empty_list(self):
        pm = read_only(write=[])
        assert pm.default == "read"
        assert pm.overrides == ()

    def test_read_write_no_kwargs(self):
        pm = read_write()
        assert pm.default == "read_write"
        assert pm.overrides == ()

    def test_read_write_with_frozen(self):
        pm = read_write(read=["/.frozen"])
        assert pm.default == "read_write"
        assert pm.resolve("/.frozen/x.toml") == "read"
        assert pm.resolve("/src/main.py") == "read_write"

    def test_read_only_rejects_root_in_writable(self):
        with pytest.raises(ValueError, match="must not be '/'"):
            read_only(write=["/"])

    def test_read_write_rejects_root_in_frozen(self):
        with pytest.raises(ValueError, match="must not be '/'"):
            read_write(read=["/"])

    def test_namespace_export(self):
        """`from vfs import permissions` exposes the factories."""
        assert callable(permissions_ns.read_only)
        assert callable(permissions_ns.read_write)
        pm = permissions_ns.read_only(write=["/x"])
        assert pm.resolve("/x/y") == "read_write"


# ==================================================================
# coerce_permissions
# ==================================================================


class TestCoercePermissions:
    def test_string_read(self):
        pm = coerce_permissions("read")
        assert pm.default == "read"
        assert pm.overrides == ()

    def test_string_read_write(self):
        pm = coerce_permissions("read_write")
        assert pm.default == "read_write"

    def test_passthrough(self):
        pm = PermissionMap(default="read", overrides=(("/x", "read_write"),))
        assert coerce_permissions(pm) is pm

    def test_invalid_string(self):
        with pytest.raises(ValueError, match="'read' or 'read_write'"):
            coerce_permissions("readonly")

    def test_invalid_type(self):
        with pytest.raises(TypeError, match="PermissionMap"):
            coerce_permissions(42)  # type: ignore[arg-type]


# ==================================================================
# check_writable with mount_prefix
# ==================================================================


class TestCheckWritable:
    def test_mutation_on_default_read_includes_mount_default(self):
        fs = VirtualFileSystem(storage=False, permissions="read")
        result = check_writable(fs, "write", "/raw/x.md", mount_prefix="/wiki")
        assert result is not None
        assert "Cannot write to read-only path '/wiki/raw/x.md'" in result.error_message
        assert "(mount default)" in result.error_message

    def test_mutation_on_rule_match_includes_rule_prefix(self):
        fs = VirtualFileSystem(
            storage=False,
            permissions=read_only(write=["/synthesis"]),
        )
        result = check_writable(fs, "write", "/raw/x.md", mount_prefix="/wiki")
        assert result is not None
        assert "Cannot write to read-only path '/wiki/raw/x.md'" in result.error_message
        assert "(mount default)" in result.error_message

    def test_mutation_inside_writable_hole_passes(self):
        fs = VirtualFileSystem(
            storage=False,
            permissions=read_only(write=["/synthesis"]),
        )
        assert check_writable(fs, "write", "/synthesis/x.md", mount_prefix="/wiki") is None

    def test_frozen_island_rule_prefix_in_message(self):
        fs = VirtualFileSystem(
            storage=False,
            permissions=read_write(read=["/.frozen"]),
        )
        result = check_writable(fs, "write", "/.frozen/x.toml", mount_prefix="/ws")
        assert result is not None
        assert "Cannot write to read-only path '/ws/.frozen/x.toml'" in result.error_message
        assert "read-only by mount rule '/.frozen'" in result.error_message

    def test_read_op_passes_on_read_default(self):
        fs = VirtualFileSystem(storage=False, permissions="read")
        assert check_writable(fs, "read", "/x", mount_prefix="/m") is None
        assert check_writable(fs, "stat", "/x", mount_prefix="/m") is None
        assert check_writable(fs, "ls", "/x", mount_prefix="/m") is None

    def test_no_mount_prefix(self):
        fs = VirtualFileSystem(storage=False, permissions="read")
        result = check_writable(fs, "write", "/x")
        assert result is not None
        assert "Cannot write to read-only path '/x'" in result.error_message


# ==================================================================
# Integration: read-only mount with writable hole
# ==================================================================


async def _make_wiki_router() -> tuple[VirtualFileSystem, DatabaseFileSystem]:
    """Build a router with one read-only mount that has /synthesis writable."""
    engine = await _sqlite_engine()
    wiki = DatabaseFileSystem(
        engine=engine,
        permissions=read_only(write=["/synthesis", "/index.md"]),
    )
    # Seed both regions directly via _write_impl so we have content to read.
    await _seed(wiki, "/raw/rfc.pdf", "binary")
    await _seed(wiki, "/synthesis/page.md", "draft")
    await _seed(wiki, "/index.md", "# Index")
    router = VFSClientAsync()
    await router.add_mount("wiki", wiki)
    return router, wiki


class TestWritableHoleAllows:
    async def test_write_inside_hole(self):
        router, _wiki = await _make_wiki_router()
        try:
            r = await router.write("/wiki/synthesis/new.md", "hello")
            assert r.success, r.error_message
        finally:
            await router.close()

    async def test_edit_inside_hole(self):
        router, _wiki = await _make_wiki_router()
        try:
            r = await router.edit("/wiki/synthesis/page.md", "draft", "final")
            assert r.success, r.error_message
        finally:
            await router.close()

    async def test_delete_inside_hole(self):
        router, _wiki = await _make_wiki_router()
        try:
            r = await router.delete("/wiki/synthesis/page.md")
            assert r.success, r.error_message
        finally:
            await router.close()

    async def test_mkdir_inside_hole(self):
        router, _wiki = await _make_wiki_router()
        try:
            r = await router.mkdir("/wiki/synthesis/2026")
            assert r.success, r.error_message
        finally:
            await router.close()

    async def test_edit_exact_file_override(self):
        router, _wiki = await _make_wiki_router()
        try:
            r = await router.edit("/wiki/index.md", "# Index", "# Updated")
            assert r.success, r.error_message
        finally:
            await router.close()

    async def test_move_inside_hole(self):
        router, _wiki = await _make_wiki_router()
        try:
            r = await router.move("/wiki/synthesis/page.md", "/wiki/synthesis/page2.md")
            assert r.success, r.error_message
        finally:
            await router.close()

    async def test_copy_inside_hole(self):
        router, _wiki = await _make_wiki_router()
        try:
            r = await router.copy("/wiki/synthesis/page.md", "/wiki/synthesis/page2.md")
            assert r.success, r.error_message
        finally:
            await router.close()

    async def test_mkedge_source_in_hole_target_outside(self):
        """Edges live on the source side — writable source is enough."""
        router, _wiki = await _make_wiki_router()
        try:
            r = await router.mkedge(
                "/wiki/synthesis/page.md",
                "/wiki/raw/rfc.pdf",
                "references",
            )
            assert r.success, r.error_message
        finally:
            await router.close()


class TestWritableHoleBlocks:
    async def test_write_outside_hole(self):
        router, _wiki = await _make_wiki_router()
        try:
            r = await router.write("/wiki/raw/new.pdf", "nope")
            assert not r.success
            assert "Cannot write to read-only path '/wiki/raw/new.pdf'" in r.error_message
            assert "(mount default)" in r.error_message
        finally:
            await router.close()

    async def test_edit_outside_hole(self):
        router, _wiki = await _make_wiki_router()
        try:
            r = await router.edit("/wiki/raw/rfc.pdf", "binary", "tampered")
            assert not r.success
            assert "Cannot write to read-only path '/wiki/raw/rfc.pdf'" in r.error_message
        finally:
            await router.close()

    async def test_delete_outside_hole(self):
        router, _wiki = await _make_wiki_router()
        try:
            r = await router.delete("/wiki/raw/rfc.pdf")
            assert not r.success
            assert "Cannot write to read-only path" in r.error_message
        finally:
            await router.close()

    async def test_mkdir_outside_hole(self):
        router, _wiki = await _make_wiki_router()
        try:
            r = await router.mkdir("/wiki/raw/sub")
            assert not r.success
            assert "Cannot write to read-only path" in r.error_message
        finally:
            await router.close()

    async def test_mkedge_source_outside_hole(self):
        router, _wiki = await _make_wiki_router()
        try:
            r = await router.mkedge(
                "/wiki/raw/rfc.pdf",
                "/wiki/synthesis/page.md",
                "references",
            )
            assert not r.success
            assert "Cannot write to read-only path" in r.error_message
        finally:
            await router.close()

    async def test_partial_segment_does_not_match_hole(self):
        """`/synthesis-archive` does NOT inherit `/synthesis`'s permission."""
        engine = await _sqlite_engine()
        wiki = DatabaseFileSystem(
            engine=engine,
            permissions=read_only(write=["/synthesis"]),
        )
        router = VFSClientAsync()
        await router.add_mount("wiki", wiki)
        try:
            r = await router.write("/wiki/synthesis-archive/x.md", "nope")
            assert not r.success
            assert "Cannot write to read-only path" in r.error_message
        finally:
            await router.close()


# ==================================================================
# Integration: read_write mount with frozen island
# ==================================================================


async def _make_workspace_router() -> tuple[VirtualFileSystem, DatabaseFileSystem]:
    engine = await _sqlite_engine()
    workspace = DatabaseFileSystem(
        engine=engine,
        permissions=read_write(read=["/.frozen", "/vendor"]),
    )
    await _seed(workspace, "/src/main.py", "code")
    await _seed(workspace, "/.frozen/locked.toml", "config")
    await _seed(workspace, "/vendor/lib.so", "binary")
    router = VFSClientAsync()
    await router.add_mount("workspace", workspace)
    return router, workspace


class TestFrozenIsland:
    async def test_write_outside_frozen_succeeds(self):
        router, _ws = await _make_workspace_router()
        try:
            r = await router.write("/workspace/src/util.py", "u")
            assert r.success, r.error_message
        finally:
            await router.close()

    async def test_write_inside_frozen_blocked(self):
        router, _ws = await _make_workspace_router()
        try:
            r = await router.write("/workspace/.frozen/new.toml", "x")
            assert not r.success
            assert "Cannot write to read-only path" in r.error_message
            assert "read-only by mount rule '/.frozen'" in r.error_message
        finally:
            await router.close()

    async def test_edit_inside_frozen_blocked(self):
        router, _ws = await _make_workspace_router()
        try:
            r = await router.edit("/workspace/.frozen/locked.toml", "config", "tampered")
            assert not r.success
        finally:
            await router.close()

    async def test_delete_inside_frozen_blocked(self):
        router, _ws = await _make_workspace_router()
        try:
            r = await router.delete("/workspace/.frozen/locked.toml")
            assert not r.success
        finally:
            await router.close()

    async def test_mkdir_inside_frozen_blocked(self):
        router, _ws = await _make_workspace_router()
        try:
            r = await router.mkdir("/workspace/.frozen/sub")
            assert not r.success
        finally:
            await router.close()

    async def test_second_frozen_rule_works(self):
        router, _ws = await _make_workspace_router()
        try:
            r = await router.write("/workspace/vendor/new.so", "x")
            assert not r.success
            assert "read-only by mount rule '/vendor'" in r.error_message
        finally:
            await router.close()

    async def test_reads_inside_frozen_succeed(self):
        router, _ws = await _make_workspace_router()
        try:
            r = await router.read("/workspace/.frozen/locked.toml")
            assert r.success
            assert r.candidates[0].content == "config"
        finally:
            await router.close()


# ==================================================================
# Batch fail-fast: candidate dispatch and object writes
# ==================================================================


class TestCascadeDeleteRespectsNestedRules:
    """`delete("/parent")` must fail-fast if any cascade-collected child
    is protected by a stricter nested rule.  Without this check, a
    `read_write` default would silently swallow read-only children
    when the user deleted a parent directory."""

    async def test_cascade_delete_blocked_by_frozen_child(self):
        engine = await _sqlite_engine()
        fs = DatabaseFileSystem(engine=engine, permissions="read_write")
        # Seed without rules so we can lay down protected children.
        await _seed(fs, "/a/x.md", "x")
        await _seed(fs, "/a/b/protected.md", "p")
        await _seed(fs, "/a/b/also_protected.md", "p2")
        # Now install the rule that protects /a/b.
        fs._permission_map = PermissionMap(
            default="read_write",
            overrides=(("/a/b", "read"),),
        )
        router = VFSClientAsync()
        await router.add_mount("ws", fs)
        try:
            r = await router.delete("/ws/a")
            assert not r.success
            assert "Cannot write to read-only path" in r.error_message
            # Both protected children must still exist.
            check1 = await router.read("/ws/a/b/protected.md")
            assert check1.success
            check2 = await router.read("/ws/a/b/also_protected.md")
            assert check2.success
            # The non-protected child must also still exist (fail-fast,
            # no partial deletes).
            check3 = await router.read("/ws/a/x.md")
            assert check3.success
        finally:
            await router.close()

    async def test_cascade_delete_succeeds_when_all_children_writable(self):
        engine = await _sqlite_engine()
        fs = DatabaseFileSystem(engine=engine, permissions="read_write")
        await _seed(fs, "/a/x.md", "x")
        await _seed(fs, "/a/b/y.md", "y")
        router = VFSClientAsync()
        await router.add_mount("ws", fs)
        try:
            r = await router.delete("/ws/a")
            assert r.success, r.error_message
            check = await router.read("/ws/a/x.md")
            assert not check.success
        finally:
            await router.close()


class TestMkedgeChecksEdgeWritePath:
    """`mkedge` must check the actual edge metadata path it writes,
    not just the source file path.  A rule placed on
    `/.vfs/<source>/__meta__/edges/out` (or any ancestor of the edge write
    path) must fire just like it would for a direct write."""

    async def test_mkedge_blocked_when_edge_subpath_frozen(self):
        engine = await _sqlite_engine()
        fs = DatabaseFileSystem(
            engine=engine,
            permissions=PermissionMap(
                default="read_write",
                overrides=(("/.vfs/page.md/__meta__/edges/out", "read"),),
            ),
        )
        await _seed(fs, "/page.md", "page")
        await _seed(fs, "/other.md", "other")
        router = VFSClientAsync()
        await router.add_mount("wiki", fs)
        try:
            r = await router.mkedge(
                "/wiki/page.md",
                "/wiki/other.md",
                "references",
            )
            assert not r.success
            assert "Cannot write to read-only path" in r.error_message
            # And no row should have been written under the frozen namespace.
            stat = await router.stat("/wiki/.vfs/page.md/__meta__/edges/out/references/other.md")
            assert not stat.success
        finally:
            await router.close()

    async def test_mkedge_blocked_when_specific_edge_type_frozen(self):
        """Even narrower: freeze just one edge type under one file."""
        engine = await _sqlite_engine()
        fs = DatabaseFileSystem(
            engine=engine,
            permissions=PermissionMap(
                default="read_write",
                overrides=(("/.vfs/page.md/__meta__/edges/out/references", "read"),),
            ),
        )
        await _seed(fs, "/page.md", "page")
        await _seed(fs, "/other.md", "other")
        router = VFSClientAsync()
        await router.add_mount("wiki", fs)
        try:
            # The frozen connection type is rejected.
            r = await router.mkedge(
                "/wiki/page.md",
                "/wiki/other.md",
                "references",
            )
            assert not r.success
            # A different connection type still succeeds.
            r2 = await router.mkedge(
                "/wiki/page.md",
                "/wiki/other.md",
                "imports",
            )
            assert r2.success, r2.error_message
        finally:
            await router.close()


class TestBatchFailFast:
    async def test_candidate_delete_straddling_boundary_fails_fast(self):
        """Glob a writable region + a frozen region, delete by candidates, expect rejection."""
        engine = await _sqlite_engine()
        ws = DatabaseFileSystem(
            engine=engine,
            permissions=read_write(read=["/.frozen"]),
        )
        await _seed(ws, "/src/a.py", "a")
        await _seed(ws, "/src/b.py", "b")
        await _seed(ws, "/.frozen/c.toml", "c")
        router = VFSClientAsync()
        await router.add_mount("ws", ws)
        try:
            listing = await router.glob("/**/*")
            assert listing.success
            paths = {e.path for e in listing.candidates}
            assert "/ws/.frozen/c.toml" in paths
            assert "/ws/src/a.py" in paths

            r = await router.delete(candidates=listing)
            assert not r.success
            assert "Cannot write to read-only path" in r.error_message

            # Frozen file still present
            check = await router.read("/ws/.frozen/c.toml")
            assert check.success
            # Writable file also still present (fail-fast — no partial deletes)
            check2 = await router.read("/ws/src/a.py")
            assert check2.success
        finally:
            await router.close()

    async def test_object_batch_write_straddling_boundary_fails_fast(self):
        engine = await _sqlite_engine()
        ws = DatabaseFileSystem(
            engine=engine,
            permissions=read_write(read=["/.frozen"]),
        )
        router = VFSClientAsync()
        await router.add_mount("ws", ws)
        try:
            objs = [
                VFSEntry(path="/ws/src/new.py", content="ok"),
                VFSEntry(path="/ws/.frozen/blocked.toml", content="nope"),
            ]
            r = await router.write(entries=objs)
            assert not r.success
            assert "Cannot write to read-only path '/ws/.frozen/blocked.toml'" in r.error_message
            # Neither file should exist (fail-fast aborts before any impl call)
            check = await router.read("/ws/src/new.py")
            assert not check.success
        finally:
            await router.close()


# ==================================================================
# Cross-mount move/copy with per-path destinations
# ==================================================================


class TestCrossMountPerPath:
    async def test_copy_destinations_split_across_frozen_rejects(self):
        """Cross-mount copy where one dest lands in a frozen island fails fast."""
        src_engine = await _sqlite_engine()
        dst_engine = await _sqlite_engine()
        src = DatabaseFileSystem(engine=src_engine, permissions="read")
        dst = DatabaseFileSystem(
            engine=dst_engine,
            permissions=read_write(read=["/locked"]),
        )
        await _seed(src, "/a.md", "alpha")
        await _seed(src, "/b.md", "beta")
        router = VFSClientAsync()
        await router.add_mount("src", src)
        await router.add_mount("dst", dst)
        try:
            ops = [
                TwoPathOperation(src="/src/a.md", dest="/dst/normal/a.md"),
                TwoPathOperation(src="/src/b.md", dest="/dst/locked/b.md"),
            ]
            r = await router.copy(copies=ops)
            assert not r.success
            assert "Cannot write to read-only path '/dst/locked/b.md'" in r.error_message
            # Neither destination written
            ck = await router.read("/dst/normal/a.md")
            assert not ck.success
        finally:
            await router.close()

    async def test_copy_all_destinations_writable_succeeds(self):
        src_engine = await _sqlite_engine()
        dst_engine = await _sqlite_engine()
        src = DatabaseFileSystem(engine=src_engine, permissions="read")
        dst = DatabaseFileSystem(
            engine=dst_engine,
            permissions=read_write(read=["/locked"]),
        )
        await _seed(src, "/a.md", "alpha")
        await _seed(src, "/b.md", "beta")
        router = VFSClientAsync()
        await router.add_mount("src", src)
        await router.add_mount("dst", dst)
        try:
            ops = [
                TwoPathOperation(src="/src/a.md", dest="/dst/normal/a.md"),
                TwoPathOperation(src="/src/b.md", dest="/dst/normal/b.md"),
            ]
            r = await router.copy(copies=ops)
            assert r.success, r.error_message
            ck = await router.read("/dst/normal/a.md")
            assert ck.success
        finally:
            await router.close()

    async def test_move_blocked_by_read_only_source_path(self):
        """Move from a writable mount whose source path falls in a frozen subtree."""
        src_engine = await _sqlite_engine()
        dst_engine = await _sqlite_engine()
        src = DatabaseFileSystem(
            engine=src_engine,
            permissions=read_write(read=["/.frozen"]),
        )
        dst = DatabaseFileSystem(engine=dst_engine, permissions="read_write")
        await _seed(src, "/.frozen/x.md", "frozen")
        router = VFSClientAsync()
        await router.add_mount("src", src)
        await router.add_mount("dst", dst)
        try:
            r = await router.move("/src/.frozen/x.md", "/dst/x.md")
            assert not r.success
            assert "Cannot write to read-only path '/src/.frozen/x.md'" in r.error_message
            # Source intact
            ck = await router.read("/src/.frozen/x.md")
            assert ck.success
        finally:
            await router.close()


# ==================================================================
# Metadata path inheritance
# ==================================================================


class TestMetadataInheritance:
    async def test_chunk_under_read_only_file_blocked(self):
        """A chunk path inherits its file's permission via prefix matching."""
        engine = await _sqlite_engine()
        wiki = DatabaseFileSystem(
            engine=engine,
            permissions=read_only(write=["/synthesis"]),
        )
        await _seed(wiki, "/raw/rfc.pdf", "binary")
        router = VFSClientAsync()
        await router.add_mount("wiki", wiki)
        try:
            # Writes targeted at the projected chunk namespace under a read-only file
            # should be blocked just like the file itself.
            chunk_path = "/wiki/.vfs/raw/rfc.pdf/__meta__/chunks/section1"
            r = await router.write(chunk_path, "chunk-content")
            assert not r.success
            assert "Cannot write to read-only path" in r.error_message
        finally:
            await router.close()


# ==================================================================
# Sync facade still raises classified exceptions
# ==================================================================


class TestSyncRaisesWithRules:
    def test_write_outside_hole_raises(self):
        g = VFSClient()
        try:

            async def _setup():
                engine = await _sqlite_engine()
                return DatabaseFileSystem(
                    engine=engine,
                    permissions=read_only(write=["/synthesis"]),
                )

            wiki = g._run(_setup())
            g.add_mount("wiki", wiki)
            with pytest.raises(WriteConflictError, match="Cannot write to read-only path"):
                g.write("/wiki/raw/x.md", "nope")
        finally:
            g.close()

    def test_write_inside_hole_succeeds(self):
        g = VFSClient()
        try:

            async def _setup():
                engine = await _sqlite_engine()
                return DatabaseFileSystem(
                    engine=engine,
                    permissions=read_only(write=["/synthesis"]),
                )

            wiki = g._run(_setup())
            g.add_mount("wiki", wiki)
            # No exception raised → write succeeded under the writable hole.
            g.write("/wiki/synthesis/x.md", "ok")
            r = g.read("/wiki/synthesis/x.md")
            assert r.content == "ok"
        finally:
            g.close()
