"""Edge cases for permission path handling.

Pins behavior across the path-normalization surface that
:class:`vfs.permissions.PermissionMap` and
:func:`vfs.paths.normalize_path` interact with: leading double
slashes, dot segments, whitespace, unicode, control characters,
percent encoding, and case sensitivity.  Each test exists because the
underlying behavior was at least once a real or near-bypass; flipping
any of them on accident should be loud.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

from vfs.backends.database import DatabaseFileSystem
from vfs.client import VFSClientAsync
from vfs.models import VFSObject
from vfs.permissions import PermissionMap, read_only, read_write


async def _sqlite_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    return engine


async def _wiki_fs() -> DatabaseFileSystem:
    engine = await _sqlite_engine()
    return DatabaseFileSystem(
        engine=engine,
        permissions=read_only(write=["/synthesis"]),
    )


async def _workspace_fs() -> DatabaseFileSystem:
    engine = await _sqlite_engine()
    return DatabaseFileSystem(
        engine=engine,
        permissions=read_write(read=["/.frozen"]),
    )


# ======================================================================
# Pure PermissionMap-level probes
# ======================================================================


class TestResolveDirectDoubleSlash:
    """Regression pins for the leading-`//` bypass.

    POSIX §4.12 lets ``posixpath.normpath`` preserve exactly two leading
    slashes (``//x`` → ``//x``).  VFS's :func:`normalize_path`
    explicitly collapses this so ``//path`` and ``/path`` resolve to the
    same logical location for both rule matching and storage routing.
    """

    def test_leading_double_slash_resolves_under_frozen_rule(self):
        pm = read_write(read=["/.frozen"])
        assert pm.resolve("//.frozen/locked.toml") == "read"

    def test_leading_double_slash_resolves_under_vendor_rule(self):
        pm = read_write(read=["/vendor"])
        assert pm.resolve("//vendor/lib.so") == "read"

    def test_triple_leading_slash_collapses(self):
        pm = read_write(read=["/.frozen"])
        assert pm.resolve("///.frozen/locked.toml") == "read"

    def test_leading_double_slash_resolves_under_writable_hole(self):
        """Both `//synthesis/x.md` and `/synthesis/x.md` resolve identically."""
        pm = read_only(write=["/synthesis"])
        assert pm.resolve("//synthesis/x.md") == "read_write"
        assert pm.resolve("//raw/x.md") == "read"


class TestResolveCaseSensitivity:
    def test_case_mismatch_not_matched(self):
        pm = read_write(read=["/.frozen"])
        assert pm.resolve("/.Frozen/x.toml") == "read_write"


class TestResolveTrailingSlashRule:
    def test_trailing_slash_rule_normalized(self):
        pm = PermissionMap(default="read", overrides=(("/synthesis/", "read_write"),))
        stored = {p for p, _ in pm.overrides}
        assert stored == {"/synthesis"}
        assert pm.resolve("/synthesis/x.md") == "read_write"
        assert pm.resolve("/synthesis") == "read_write"


class TestResolveDotSegments:
    def test_leading_dot_slash(self):
        pm = read_write(read=["/.frozen"])
        assert pm.resolve("/./.frozen/x.toml") == "read"

    def test_middle_dot_slash(self):
        pm = read_write(read=["/.frozen"])
        assert pm.resolve("/.frozen/./x.toml") == "read"

    def test_collapsing_double_slash_inside(self):
        pm = read_write(read=["/.frozen"])
        assert pm.resolve("/.frozen//x.toml") == "read"

    def test_dot_dot_inside_escapes(self):
        pm = read_write(read=["/.frozen"])
        assert pm.resolve("/.frozen/../evil") == "read_write"


class TestResolveWhitespace:
    def test_trailing_space(self):
        pm = read_write(read=["/.frozen"])
        assert pm.resolve("/.frozen/locked.toml ") == "read"

    def test_leading_space(self):
        pm = read_write(read=["/.frozen"])
        assert pm.resolve(" /.frozen/locked.toml") == "read"

    def test_tab_inside_segment(self):
        pm = read_write(read=["/.frozen"])
        assert pm.resolve("/.fro\tzen/locked.toml") == "read_write"


class TestResolveUnicode:
    def test_nfc_equivalence_same_bytes(self):
        pm = read_write(read=["/caf\u00e9"])
        decomposed = "/cafe\u0301/x.md"
        assert pm.resolve(decomposed) == "read"

    def test_nfkc_not_applied_fullwidth(self):
        pm = read_write(read=["/frozen"])
        fullwidth = "/\uff46rozen/x.md"
        assert pm.resolve(fullwidth) == "read_write"

    def test_zero_width_space_prefix(self):
        pm = read_write(read=["/.frozen"])
        sneaky = "/\u200b.frozen/locked.toml"
        assert pm.resolve(sneaky) == "read_write"


class TestResolveControlAndNull:
    def test_null_byte_in_lookup_does_not_crash(self):
        pm = read_write(read=["/.frozen"])
        assert pm.resolve("/\x00.frozen/x") == "read_write"

    def test_control_char_in_lookup_does_not_crash(self):
        pm = read_write(read=["/.frozen"])
        assert pm.resolve("/\x07.frozen/x") == "read_write"


class TestResolveURLEncoding:
    def test_percent_encoded_dot_not_decoded(self):
        pm = read_write(read=["/.frozen"])
        assert pm.resolve("/%2Efrozen/locked.toml") == "read_write"


# ======================================================================
# Integration probes - direct DatabaseFileSystem writes
# ======================================================================


class TestIntegrationDirectDoubleSlash:
    async def test_direct_write_double_slash_evades_frozen(self):
        ws = await _workspace_fs()
        try:
            r = await ws.write("//.frozen/evil.toml", "owned")
            assert not r.success
            assert "Cannot write to read-only path" in r.error_message
        finally:
            if ws._engine is not None:
                await ws._engine.dispose()

    async def test_direct_write_object_double_slash_evades_frozen(self):
        ws = await _workspace_fs()
        try:
            obj = VFSObject(path="//.frozen/evil.toml", content="owned")
            r = await ws.write(objects=[obj])
            assert not r.success
            assert "Cannot write to read-only path" in r.error_message
        finally:
            if ws._engine is not None:
                await ws._engine.dispose()

    async def test_direct_write_triple_slash_is_collapsed(self):
        ws = await _workspace_fs()
        try:
            r = await ws.write("///.frozen/evil.toml", "owned")
            assert not r.success
            assert "Cannot write to read-only path" in r.error_message
        finally:
            if ws._engine is not None:
                await ws._engine.dispose()


class TestIntegrationRouterCollapsesDoubleSlash:
    async def test_router_rejects_leading_double_slash_no_mount(self):
        ws = await _workspace_fs()
        router = VFSClientAsync()
        try:
            await router.add_mount("ws", ws)
            r = await router.write("//ws/.frozen/evil.toml", "owned")
            assert not r.success
        finally:
            await router.close()

    async def test_router_inner_double_slash_collapses(self):
        ws = await _workspace_fs()
        router = VFSClientAsync()
        try:
            await router.add_mount("ws", ws)
            r = await router.write("/ws//.frozen/evil.toml", "owned")
            assert not r.success
            assert "Cannot write to read-only path" in r.error_message
        finally:
            await router.close()


class TestIntegrationReadOnlyDefault:
    async def test_double_slash_on_default_still_blocked(self):
        wiki = await _wiki_fs()
        try:
            r = await wiki.write("//raw/evil.md", "owned")
            assert not r.success
            assert "Cannot write to read-only path" in r.error_message
        finally:
            if wiki._engine is not None:
                await wiki._engine.dispose()

    async def test_double_slash_into_writable_hole_succeeds(self):
        """Both `//synthesis/x.md` and `/synthesis/x.md` route identically
        — `//` collapses to `/` and the writable carve-out applies."""
        wiki = await _wiki_fs()
        try:
            r = await wiki.write("//synthesis/new.md", "hi")
            assert r.success, r.error_message
        finally:
            if wiki._engine is not None:
                await wiki._engine.dispose()


# ======================================================================
# Rule construction normalization
# ======================================================================


class TestRulePathNormalization:
    def test_rule_with_dot_segment(self):
        pm = PermissionMap(default="read", overrides=(("/a/./b", "read_write"),))
        stored = {p for p, _ in pm.overrides}
        assert stored == {"/a/b"}

    def test_rule_with_double_slash_inside(self):
        pm = PermissionMap(default="read", overrides=(("/a//b", "read_write"),))
        stored = {p for p, _ in pm.overrides}
        assert stored == {"/a/b"}

    def test_rule_with_trailing_slash(self):
        pm = PermissionMap(default="read", overrides=(("/a/b/", "read_write"),))
        stored = {p for p, _ in pm.overrides}
        assert stored == {"/a/b"}

    def test_rule_with_leading_double_slash_collapses(self):
        """A rule declared with leading `//` is collapsed to `/` at
        construction so the natural `/.frozen/x` lookup matches."""
        pm = PermissionMap(default="read_write", overrides=(("//.frozen", "read"),))
        stored = {p for p, _ in pm.overrides}
        assert stored == {"/.frozen"}
        assert pm.resolve("/.frozen/x") == "read"
        assert pm.resolve("//.frozen/x") == "read"
