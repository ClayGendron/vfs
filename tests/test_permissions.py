"""Tests for mount-level read/read_write permissions."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from vfs.backends.database import DatabaseFileSystem
from vfs.base import VirtualFileSystem
from vfs.client import VFSClient, VFSClientAsync
from vfs.exceptions import WriteConflictError
from vfs.models import VFSEntry
from vfs.permissions import (
    MUTATING_OPS,
    _join,
    check_writable,
    validate_permission,
)

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


async def _sqlite_engine():
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
    """Seed a file on *fs* by calling ``_write_impl`` directly.

    Bypasses the router so seeding works on read-only mounts.
    """
    async with fs._use_session() as s:
        await fs._write_impl(path, content=content, session=s)


async def _make_router(
    *,
    ro_seed: tuple[str, str] | None = ("/doc.md", "hello"),
    rw_seed: tuple[str, str] | None = ("/doc.md", "hello"),
) -> tuple[VirtualFileSystem, DatabaseFileSystem, DatabaseFileSystem]:
    """Build a VirtualFileSystem with ``/ro`` (read) and ``/rw`` (read_write) mounts."""
    ro_engine = await _sqlite_engine()
    rw_engine = await _sqlite_engine()
    ro = DatabaseFileSystem(engine=ro_engine, permissions="read")
    rw = DatabaseFileSystem(engine=rw_engine, permissions="read_write")
    if ro_seed is not None:
        await _seed(ro, *ro_seed)
    if rw_seed is not None:
        await _seed(rw, *rw_seed)
    router = VFSClientAsync()
    await router.add_mount("ro", ro)
    await router.add_mount("rw", rw)
    return router, ro, rw


# ==================================================================
# validate_permission
# ==================================================================


class TestValidatePermission:
    def test_accepts_read(self):
        assert validate_permission("read") == "read"

    def test_accepts_read_write(self):
        assert validate_permission("read_write") == "read_write"

    def test_rejects_readonly(self):
        with pytest.raises(ValueError, match="'read' or 'read_write'"):
            validate_permission("readonly")

    def test_rejects_empty_string(self):
        with pytest.raises(ValueError, match="'read' or 'read_write'"):
            validate_permission("")

    def test_rejects_write(self):
        with pytest.raises(ValueError, match="'read' or 'read_write'"):
            validate_permission("write")


# ==================================================================
# Construction
# ==================================================================


class TestConstruction:
    async def test_default_is_read_write(self):
        engine = await _sqlite_engine()
        try:
            fs = DatabaseFileSystem(engine=engine)
            assert fs._permission_map.default == "read_write"
        finally:
            await engine.dispose()

    async def test_explicit_read_write(self):
        engine = await _sqlite_engine()
        try:
            fs = DatabaseFileSystem(engine=engine, permissions="read_write")
            assert fs._permission_map.default == "read_write"
        finally:
            await engine.dispose()

    async def test_explicit_read(self):
        engine = await _sqlite_engine()
        try:
            fs = DatabaseFileSystem(engine=engine, permissions="read")
            assert fs._permission_map.default == "read"
        finally:
            await engine.dispose()

    async def test_invalid_value_raises(self):
        engine = await _sqlite_engine()
        try:
            with pytest.raises(ValueError, match="'read' or 'read_write'"):
                DatabaseFileSystem(engine=engine, permissions="ro")  # type: ignore[arg-type]
        finally:
            await engine.dispose()

    def test_base_class_default(self):
        fs = VirtualFileSystem(storage=False)
        assert fs._permission_map.default == "read_write"

    def test_base_class_read(self):
        fs = VirtualFileSystem(storage=False, permissions="read")
        assert fs._permission_map.default == "read"


# ==================================================================
# check_writable unit
# ==================================================================


class TestCheckWritable:
    def test_mutating_ops_set(self):
        assert "write" in MUTATING_OPS
        assert "edit" in MUTATING_OPS
        assert "delete" in MUTATING_OPS
        assert "mkdir" in MUTATING_OPS
        assert "mkedge" in MUTATING_OPS
        assert "move" in MUTATING_OPS
        assert "copy" in MUTATING_OPS
        # Read ops must not be in the set
        assert "read" not in MUTATING_OPS
        assert "stat" not in MUTATING_OPS
        assert "ls" not in MUTATING_OPS
        assert "glob" not in MUTATING_OPS
        assert "grep" not in MUTATING_OPS

    def test_returns_none_for_writable_mount(self):
        fs = VirtualFileSystem(storage=False, permissions="read_write")
        assert check_writable(fs, "write", "/a") is None

    def test_returns_none_for_read_op_on_read_only_mount(self):
        fs = VirtualFileSystem(storage=False, permissions="read")
        assert check_writable(fs, "read", "/a") is None
        assert check_writable(fs, "stat", "/a") is None
        assert check_writable(fs, "glob", "/a") is None

    def test_returns_error_for_mutation_on_read_only_mount(self):
        fs = VirtualFileSystem(storage=False, permissions="read")
        result = check_writable(fs, "write", "/a")
        assert result is not None
        assert not result.success
        assert "Cannot write to read-only path" in result.error_message
        assert "/a" in result.error_message


# ==================================================================
# Per-op rejection on a read-only mount
# ==================================================================


class TestReadOnlyBlocksMutations:
    async def test_write_rejected(self):
        router, _ro, _rw = await _make_router()
        try:
            result = await router.write("/ro/new.md", "nope")
            assert not result.success
            assert "Cannot write to read-only path" in result.error_message
        finally:
            await router.close()

    async def test_edit_rejected(self):
        router, _ro, _rw = await _make_router()
        try:
            result = await router.edit("/ro/doc.md", "hello", "bye")
            assert not result.success
            assert "Cannot write to read-only path" in result.error_message
        finally:
            await router.close()

    async def test_soft_delete_rejected(self):
        router, _ro, _rw = await _make_router()
        try:
            result = await router.delete("/ro/doc.md")
            assert not result.success
            assert "Cannot write to read-only path" in result.error_message
        finally:
            await router.close()

    async def test_permanent_delete_rejected(self):
        router, _ro, _rw = await _make_router()
        try:
            result = await router.delete("/ro/doc.md", permanent=True)
            assert not result.success
            assert "Cannot write to read-only path" in result.error_message
        finally:
            await router.close()

    async def test_mkdir_rejected(self):
        router, _ro, _rw = await _make_router()
        try:
            result = await router.mkdir("/ro/sub")
            assert not result.success
            assert "Cannot write to read-only path" in result.error_message
        finally:
            await router.close()

    async def test_mkedge_rejected(self):
        router, ro, _rw = await _make_router(ro_seed=None)
        try:
            await _seed(ro, "/a.md", "a")
            await _seed(ro, "/b.md", "b")
            result = await router.mkedge("/ro/a.md", "/ro/b.md", "references")
            assert not result.success
            assert "Cannot write to read-only path" in result.error_message
        finally:
            await router.close()

    async def test_same_mount_move_rejected(self):
        router, _ro, _rw = await _make_router()
        try:
            result = await router.move("/ro/doc.md", "/ro/doc2.md")
            assert not result.success
            assert "Cannot write to read-only path" in result.error_message
        finally:
            await router.close()

    async def test_same_mount_copy_rejected(self):
        router, _ro, _rw = await _make_router()
        try:
            result = await router.copy("/ro/doc.md", "/ro/doc2.md")
            assert not result.success
            assert "Cannot write to read-only path" in result.error_message
        finally:
            await router.close()

    async def test_batch_write_rejected(self):
        router, _ro, _rw = await _make_router(ro_seed=None)
        try:
            objs = [VFSEntry(path="/ro/batch.md", content="x")]
            result = await router.write(entries=objs)
            assert not result.success
            assert "Cannot write to read-only path" in result.error_message
        finally:
            await router.close()


# ==================================================================
# Reads succeed on a read-only mount
# ==================================================================


class TestReadsSucceed:
    async def test_read(self):
        router, _ro, _rw = await _make_router()
        try:
            result = await router.read("/ro/doc.md")
            assert result.success
            assert result.candidates[0].content == "hello"
        finally:
            await router.close()

    async def test_stat(self):
        router, _ro, _rw = await _make_router()
        try:
            result = await router.stat("/ro/doc.md")
            assert result.success
        finally:
            await router.close()

    async def test_ls(self):
        router, _ro, _rw = await _make_router()
        try:
            result = await router.ls("/ro/")
            assert result.success
        finally:
            await router.close()

    async def test_tree(self):
        router, _ro, _rw = await _make_router()
        try:
            result = await router.tree("/ro/")
            assert result.success
        finally:
            await router.close()

    async def test_glob(self):
        router, _ro, _rw = await _make_router()
        try:
            result = await router.glob("**/*.md")
            assert result.success
            assert any("/ro/doc.md" in e.path for e in result.candidates)
        finally:
            await router.close()

    async def test_grep(self):
        router, _ro, _rw = await _make_router()
        try:
            result = await router.grep("hello")
            assert result.success
            assert any("/ro/doc.md" in e.path for e in result.candidates)
        finally:
            await router.close()


# ==================================================================
# Cross-mount transfer semantics
# ==================================================================


class TestCrossMount:
    async def test_copy_ro_to_rw_succeeds(self):
        """Read-only source is allowed — reads never mutate."""
        router, _ro, _rw = await _make_router(rw_seed=None)
        try:
            result = await router.copy("/ro/doc.md", "/rw/doc.md")
            assert result.success, result.error_message
            # Verify the file actually landed
            read = await router.read("/rw/doc.md")
            assert read.success
            assert read.candidates[0].content == "hello"
        finally:
            await router.close()

    async def test_copy_rw_to_ro_rejected(self):
        router, _ro, _rw = await _make_router()
        try:
            result = await router.copy("/rw/doc.md", "/ro/new.md")
            assert not result.success
            assert "Cannot write to read-only path" in result.error_message
        finally:
            await router.close()

    async def test_move_ro_to_rw_rejected(self):
        """Move deletes the source — can't delete from a read-only mount."""
        router, _ro, _rw = await _make_router(rw_seed=None)
        try:
            result = await router.move("/ro/doc.md", "/rw/doc.md")
            assert not result.success
            assert "Cannot write to read-only path" in result.error_message
            # Source must still be intact
            read = await router.read("/ro/doc.md")
            assert read.success
        finally:
            await router.close()

    async def test_move_rw_to_ro_rejected(self):
        router, _ro, _rw = await _make_router()
        try:
            result = await router.move("/rw/doc.md", "/ro/new.md")
            assert not result.success
            assert "Cannot write to read-only path" in result.error_message
        finally:
            await router.close()


# ==================================================================
# Candidate-based dispatch fail-fast
# ==================================================================


class TestCandidateDispatch:
    async def test_delete_candidates_spanning_mounts_fails_fast(self):
        router, _ro, _rw = await _make_router()
        try:
            listing = await router.glob("/**/*.md")
            # Both mounts should contribute candidates
            paths = {e.path for e in listing.candidates}
            assert "/ro/doc.md" in paths
            assert "/rw/doc.md" in paths

            result = await router.delete(candidates=listing)
            assert not result.success
            assert "Cannot write to read-only path" in result.error_message

            # Read-only side untouched
            read = await router.read("/ro/doc.md")
            assert read.success
        finally:
            await router.close()


# ==================================================================
# Sync facade raises classified exceptions
# ==================================================================


class TestSyncRaises:
    def test_write_raises_write_conflict_error(self):
        g = VFSClient()
        try:

            async def _setup():
                engine = await _sqlite_engine()
                return DatabaseFileSystem(engine=engine, permissions="read")

            ro = g._run(_setup())
            g.add_mount("ro", ro)

            with pytest.raises(WriteConflictError, match="Cannot write to read-only path"):
                g.write("/ro/new.md", "nope")
        finally:
            g.close()

    def test_mkdir_raises_write_conflict_error(self):
        g = VFSClient()
        try:

            async def _setup():
                engine = await _sqlite_engine()
                return DatabaseFileSystem(engine=engine, permissions="read")

            ro = g._run(_setup())
            g.add_mount("ro", ro)

            with pytest.raises(WriteConflictError, match="Cannot write to read-only path"):
                g.mkdir("/ro/sub")
        finally:
            g.close()

    def test_read_does_not_raise(self):
        g = VFSClient()
        try:

            async def _setup():
                engine = await _sqlite_engine()
                fs = DatabaseFileSystem(engine=engine, permissions="read")
                async with fs._use_session() as s:
                    await fs._write_impl("/doc.md", content="hi", session=s)
                return fs

            ro = g._run(_setup())
            g.add_mount("ro", ro)

            result = g.read("/ro/doc.md")
            assert result.content == "hi"
        finally:
            g.close()


# ==================================================================
# Shared-engine model — documented limitation
# ==================================================================


class TestSharedEngineIsNotIsolated:
    """Pin the per-instance permission model as a known sharp edge.

    Permissions live on a ``DatabaseFileSystem`` instance, not on the
    engine or table it points at.  Two instances sharing an engine are
    independent from the permission system's point of view — a writable
    sibling can mutate the bytes a read-only instance reads from.
    This test documents that reality as executable specification so any
    future change to the model (e.g. engine-level enforcement) has to
    update this test deliberately.

    See :mod:`vfs.permissions` "Limitations" for the rationale.
    Within-mount / directory-level permissions that would close this
    gap for specific use cases are future work.
    """

    async def test_sibling_with_shared_engine_can_write_through(self):
        shared_engine = await _sqlite_engine()
        try:
            ro = DatabaseFileSystem(engine=shared_engine, permissions="read")
            rw = DatabaseFileSystem(engine=shared_engine, permissions="read_write")
            await _seed(ro, "/doc.md", "original")

            router = VFSClientAsync()
            await router.add_mount("ro", ro)
            await router.add_mount("back", rw)
            try:
                # The read-only mount correctly rejects a direct write.
                blocked = await router.write("/ro/doc.md", "blocked")
                assert not blocked.success
                assert "Cannot write to read-only path" in blocked.error_message

                # But the writable sibling on the SAME engine can mutate
                # the underlying row.  Both mounts are reading the same
                # bytes.  The permission check never sees this path because
                # the writable mount is, correctly, writable.
                sibling = await router.write("/back/doc.md", "PWNED_VIA_SIBLING")
                assert sibling.success

                # Reading through the read-only mount now returns the
                # sibling's write — the storage was mutated.
                leaked = await router.read("/ro/doc.md")
                assert leaked.success
                assert leaked.candidates[0].content == "PWNED_VIA_SIBLING"
            finally:
                await router.close()
        finally:
            await shared_engine.dispose()


class TestPermissionHelpers:
    def test_join_returns_mount_prefix_for_root_relative_paths(self):
        assert _join("/docs", "/") == "/docs"
