"""Edge cases for permission enforcement in the routing/dispatch layer.

Pins behavior around the subtler corners of how
:class:`grover.permissions.PermissionMap` interacts with the chokepoints
in :mod:`grover.base` and the storage paths in
:mod:`grover.backends.database` — parent-directory creation vs revival,
empty batches, user scoping, the self-storage routing path, mount
remove/re-add, and the rule against rebinding ``_permission_map``.
Two tests are pinned ``xfail(strict=True)`` to lock in accepted-design
trade-offs (parent-dir creation gets a free pass; user-scoped rules
live in unscoped logical coordinates).
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, select

from grover.backends.database import DatabaseFileSystem
from grover.client import GroverAsync
from grover.models import GroverObject
from grover.permissions import PermissionMap, read_only


async def _sqlite_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    return engine


async def _seed(fs: DatabaseFileSystem, path: str, content: str = "x") -> None:
    async with fs._use_session() as s:
        await fs._write_impl(path, content=content, session=s)


async def _raw_has_path(fs: DatabaseFileSystem, path: str) -> bool:
    assert fs._session_factory is not None
    async with fs._session_factory() as s:
        stmt = select(GroverObject).where(GroverObject.path == path)
        result = await s.execute(stmt)
        return result.scalar_one_or_none() is not None


async def _raw_deleted_at(fs: DatabaseFileSystem, path: str):
    assert fs._session_factory is not None
    async with fs._session_factory() as s:
        stmt = select(GroverObject).where(GroverObject.path == path)
        result = await s.execute(stmt)
        obj = result.scalar_one_or_none()
        return obj.deleted_at if obj is not None else "missing"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "ACCEPTED DESIGN: _resolve_parent_dirs creates brand-new ancestor "
        "directory rows without consulting the permission map.  This is "
        "intentional — a writable carve-out (e.g. /wh/a/b/c) inside a "
        "read-only mount needs reachable ancestors, and forcing the user "
        "to seed them manually would make the carve-out useless.  Note "
        "that REVIVAL of soft-deleted ancestors IS checked (see "
        "test_parent_dir_revival_does_not_undelete_read_only_ancestors): "
        "creation gets a free pass, revival does not.  This test is "
        "pinned strict-xfail so any future change in policy must update "
        "it deliberately."
    ),
)
async def test_parent_dir_creation_respects_read_only_ancestors():
    engine = await _sqlite_engine()
    fs = DatabaseFileSystem(
        engine=engine,
        permissions=PermissionMap(
            default="read",
            overrides=(("/wh/a/b/c", "read_write"),),
        ),
    )
    router = GroverAsync()
    await router.add_mount("mnt", fs)
    try:
        r = await router.write("/mnt/wh/a/b/c/x.md", "ok")
        assert r.success, r.error_message
        for ancestor in ("/wh", "/wh/a", "/wh/a/b"):
            assert not await _raw_has_path(fs, ancestor), (
                f"BYPASS: row at read-only ancestor {ancestor}"
            )
    finally:
        await router.close()


async def test_parent_dir_revival_does_not_undelete_read_only_ancestors():
    """Soft-deleted ancestors in a read-only region must NOT be revived
    as a side-effect of a write to a deeper writable carve-out.

    Brand-new ancestors get a free pass (the carve-out needs reachable
    parents) — but if the user explicitly deleted a path AND then made
    it read-only, silently un-deleting it would violate both intents."""
    engine = await _sqlite_engine()
    fs = DatabaseFileSystem(engine=engine, permissions="read_write")
    await _seed(fs, "/wh/a/b/c/sibling.md", "s")
    await fs.delete("/wh/a")
    # Now flip the rule so /wh/a/b/c is the only writable region.
    fs._permission_map = PermissionMap(
        default="read",
        overrides=(("/wh/a/b/c", "read_write"),),
    )
    router = GroverAsync()
    await router.add_mount("mnt", fs)
    try:
        r = await router.write("/mnt/wh/a/b/c/new.md", "ok")
        assert not r.success
        assert "Cannot write to read-only path" in r.error_message
        # The soft-deleted ancestors must remain soft-deleted.
        # (/wh itself was never deleted — only /wh/a and below.)
        for ancestor in ("/wh/a", "/wh/a/b"):
            deleted_at = await _raw_deleted_at(fs, ancestor)
            assert deleted_at is not None and deleted_at != "missing", (
                f"REGRESSION: {ancestor} revived (deleted_at={deleted_at!r})"
            )
    finally:
        await router.close()


async def test_route_two_path_empty_ops_is_noop():
    engine = await _sqlite_engine()
    fs = DatabaseFileSystem(engine=engine, permissions="read")
    router = GroverAsync()
    await router.add_mount("mnt", fs)
    try:
        r = await router.move(moves=[])
        assert r.success and r.candidates == []
        r = await router.copy(copies=[])
        assert r.success and r.candidates == []
    finally:
        await router.close()


async def test_empty_write_batch_is_noop_under_read_only():
    engine = await _sqlite_engine()
    fs = DatabaseFileSystem(engine=engine, permissions="read")
    router = GroverAsync()
    await router.add_mount("mnt", fs)
    try:
        r = await router.write(objects=[])
        assert r.success and r.candidates == []
    finally:
        await router.close()


async def test_user_scoped_pre_scoped_path_no_double_write():
    engine = await _sqlite_engine()
    fs = DatabaseFileSystem(
        engine=engine,
        user_scoped=True,
        permissions=read_only(write=["/synthesis"]),
    )
    router = GroverAsync()
    await router.add_mount("wiki", fs)
    try:
        r = await router.write(
            "/wiki/alice/synthesis/x.md", "x", user_id="alice"
        )
        assert not r.success
        assert "Cannot write" in r.error_message
        assert not await _raw_has_path(fs, "/alice/alice/synthesis/x.md")
    finally:
        await router.close()


@pytest.mark.xfail(
    strict=True,
    reason=(
        "ACCEPTED FOOTGUN (documented in permissions.py): rules live in "
        "unscoped logical coordinates.  Embedding a user_id in a rule "
        "path (e.g. '/alice/synthesis') makes the rule fire for any user "
        "who can construct that path under their OWN scope.  No data "
        "leak — bob's data still lands in /bob/... — but the rule does "
        "not actually scope to alice.  Use the share / ReBAC layer for "
        "per-user policy.  This test pins the behavior so any future "
        "policy change updates the docstring + test together."
    ),
)
async def test_user_scoped_rule_in_physical_coordinates_blocks_other_users():
    engine = await _sqlite_engine()
    fs = DatabaseFileSystem(
        engine=engine,
        user_scoped=True,
        permissions=read_only(write=["/alice/synthesis"]),
    )
    router = GroverAsync()
    await router.add_mount("wiki", fs)
    try:
        r = await router.write(
            "/wiki/alice/synthesis/x.md", "bob-wrote-this", user_id="bob"
        )
        assert not r.success, (
            "BYPASS: bob wrote through /alice/synthesis rule"
        )
        assert not await _raw_has_path(fs, "/bob/alice/synthesis/x.md")
    finally:
        await router.close()


async def test_remove_and_readd_uses_fresh_filesystem():
    engine1 = await _sqlite_engine()
    engine2 = await _sqlite_engine()
    writable = DatabaseFileSystem(engine=engine1, permissions="read_write")
    readonly = DatabaseFileSystem(engine=engine2, permissions="read")
    router = GroverAsync()
    await router.add_mount("mnt", writable)
    r = await router.write("/mnt/ok.md", "ok")
    assert r.success
    await router.remove_mount("mnt")
    await router.add_mount("mnt", readonly)
    try:
        r = await router.write("/mnt/evil.md", "nope")
        assert not r.success
        assert "Cannot write" in r.error_message
    finally:
        await router.close()


async def test_self_storage_database_fs_checks_own_permissions():
    engine = await _sqlite_engine()
    fs = DatabaseFileSystem(
        engine=engine,
        permissions=read_only(write=["/writable"]),
    )
    try:
        r = await fs.write("/writable/ok.md", "ok")
        assert r.success, r.error_message
        r = await fs.write("/other/blocked.md", "nope")
        assert not r.success
        assert "Cannot write" in r.error_message
    finally:
        if fs._engine is not None:
            await fs._engine.dispose()


def test_database_py_does_not_reassign_permission_map():
    from pathlib import Path

    import grover.backends.database as dbmod

    text = Path(dbmod.__file__).read_text(encoding="utf-8")
    assert "self._permission_map =" not in text
