"""Tests for user-scoped filesystem support.

Covers path scoping utilities, DatabaseFileSystem with user_scoped=True,
result unscoping, and graph isolation.
"""

from __future__ import annotations

import pytest
from sqlmodel import select

from vfs.backends.database import DatabaseFileSystem
from vfs.models import VFSObject
from vfs.paths import (
    decompose_edge,
    edge_out_path,
    scope_path,
    unscope_path,
    validate_user_id,
)
from vfs.results import Entry, VFSResult

# ---------------------------------------------------------------------------
# Path utility tests
# ---------------------------------------------------------------------------


class TestValidateUserId:
    def test_accepts_alphanumeric(self):
        assert validate_user_id("user123") == (True, "")

    def test_accepts_uuid(self):
        assert validate_user_id("550e8400-e29b-41d4-a716-446655440000") == (True, "")

    def test_accepts_hyphen_underscore(self):
        assert validate_user_id("user-name_1") == (True, "")

    def test_rejects_empty(self):
        ok, _ = validate_user_id("")
        assert not ok

    def test_rejects_whitespace_only(self):
        ok, _ = validate_user_id("   ")
        assert not ok

    def test_rejects_slash(self):
        ok, _ = validate_user_id("user/name")
        assert not ok

    def test_rejects_backslash(self):
        ok, _ = validate_user_id("user\\name")
        assert not ok

    def test_rejects_dotdot(self):
        ok, _ = validate_user_id("user..name")
        assert not ok

    def test_rejects_null_byte(self):
        ok, _ = validate_user_id("user\x00name")
        assert not ok

    def test_rejects_at_sign(self):
        ok, _ = validate_user_id("user@name")
        assert not ok

    def test_rejects_too_long(self):
        ok, _ = validate_user_id("x" * 256)
        assert not ok

    def test_accepts_max_length(self):
        assert validate_user_id("x" * 255) == (True, "")


class TestScopePath:
    def test_basic(self):
        assert scope_path("/docs/README.md", "123") == "/123/docs/README.md"

    def test_root(self):
        assert scope_path("/", "123") == "/123"

    def test_nested(self):
        assert scope_path("/a/b/c/d.py", "u1") == "/u1/a/b/c/d.py"

    def test_rejects_invalid_user_id(self):
        with pytest.raises(ValueError, match="Invalid user_id"):
            scope_path("/docs/README.md", "")


class TestUnscopePath:
    def test_basic(self):
        assert unscope_path("/123/docs/README.md", "123") == "/docs/README.md"

    def test_root(self):
        assert unscope_path("/123", "123") == "/"

    def test_rejects_wrong_prefix(self):
        with pytest.raises(ValueError, match="does not start with"):
            unscope_path("/456/docs/README.md", "123")

    def test_edge_path_both_parts_unscoped(self):
        scoped = edge_out_path("/123/src/main.py", "/123/src/auth.py", "imports")
        # /.vfs/123/src/main.py/__meta__/edges/out/imports/123/src/auth.py
        unscoped = unscope_path(scoped, "123")
        assert unscoped == "/.vfs/src/main.py/__meta__/edges/out/imports/src/auth.py"
        # Verify decomposition matches
        parts = decompose_edge(unscoped)
        assert parts is not None
        assert parts.source == "/src/main.py"
        assert parts.target == "/src/auth.py"
        assert parts.edge_type == "imports"

    def test_roundtrip(self):
        original = "/docs/report.pdf"
        assert unscope_path(scope_path(original, "u1"), "u1") == original

    def test_roundtrip_edge(self):
        src, tgt, ct = "/src/main.py", "/src/auth.py", "imports"
        scoped_conn = edge_out_path(
            scope_path(src, "u1"),
            scope_path(tgt, "u1"),
            ct,
        )
        unscoped = unscope_path(scoped_conn, "u1")
        assert unscoped == edge_out_path(src, tgt, ct)


class TestStripUserScope:
    def test_strips_file_paths(self):
        result = VFSResult(
            function="ls",
            entries=[
                Entry(path="/u1/docs/a.md"),
                Entry(path="/u1/docs/b.md"),
            ],
        )
        stripped = result.strip_user_scope("u1")
        assert [e.path for e in stripped.entries] == ["/docs/a.md", "/docs/b.md"]

    def test_strips_edge_paths(self):
        conn = edge_out_path("/u1/a.py", "/u1/b.py", "imports")
        result = VFSResult(function="ls", entries=[Entry(path=conn)])
        stripped = result.strip_user_scope("u1")
        expected = edge_out_path("/a.py", "/b.py", "imports")
        assert stripped.entries[0].path == expected


# ---------------------------------------------------------------------------
# DatabaseFileSystem integration tests
# ---------------------------------------------------------------------------


@pytest.fixture
async def scoped_db(engine):
    return DatabaseFileSystem(engine=engine, user_scoped=True)


class TestUserScopedWrite:
    async def test_write_and_read_scoped(self, scoped_db):
        await scoped_db.write(path="/docs/README.md", content="hello", user_id="u1")
        result = await scoped_db.read(path="/docs/README.md", user_id="u1")
        assert result.success
        assert result.file is not None
        assert result.file.path == "/docs/README.md"
        assert result.file.content == "hello"

    async def test_two_users_same_path_isolated(self, scoped_db):
        await scoped_db.write(path="/doc.txt", content="alice-content", user_id="alice")
        await scoped_db.write(path="/doc.txt", content="bob-content", user_id="bob")

        alice_result = await scoped_db.read(path="/doc.txt", user_id="alice")
        bob_result = await scoped_db.read(path="/doc.txt", user_id="bob")

        assert alice_result.file is not None
        assert alice_result.file.content == "alice-content"
        assert bob_result.file is not None
        assert bob_result.file.content == "bob-content"

    async def test_owner_id_set_on_write(self, engine, scoped_db):
        await scoped_db.write(path="/doc.txt", content="test", user_id="u1")
        # Read raw from DB to check owner_id
        async with scoped_db._session_factory() as session:
            stmt = select(VFSObject).where(VFSObject.path == "/u1/doc.txt")
            result = await session.execute(stmt)
            obj = result.scalar_one()
            assert obj.owner_id == "u1"

    async def test_user_id_required_when_scoped(self, scoped_db):
        with pytest.raises(ValueError, match="user_id is required"):
            await scoped_db.write(path="/doc.txt", content="test")

    async def test_user_id_none_raises_on_read(self, scoped_db):
        with pytest.raises(ValueError, match="user_id is required"):
            await scoped_db.read(path="/doc.txt")


class TestUserScopedLs:
    async def test_ls_shows_only_user_files(self, scoped_db):
        await scoped_db.write(path="/a.txt", content="a", user_id="u1")
        await scoped_db.write(path="/b.txt", content="b", user_id="u2")

        result = await scoped_db.ls(path="/", user_id="u1")
        paths = [e.path for e in result.entries]
        assert "/a.txt" in paths
        assert "/b.txt" not in paths


class TestUserScopedGlob:
    async def test_glob_scoped(self, scoped_db):
        await scoped_db.write(path="/src/a.py", content="a", user_id="u1")
        await scoped_db.write(path="/src/b.py", content="b", user_id="u2")

        result = await scoped_db.glob(pattern="/src/*.py", user_id="u1")
        paths = [e.path for e in result.entries]
        assert "/src/a.py" in paths
        assert "/src/b.py" not in paths


class TestUserScopedGrep:
    async def test_grep_scoped(self, scoped_db):
        await scoped_db.write(path="/a.py", content="def login():", user_id="u1")
        await scoped_db.write(path="/b.py", content="def login():", user_id="u2")

        result = await scoped_db.grep(pattern="login", user_id="u1")
        paths = [e.path for e in result.entries]
        assert "/a.py" in paths
        assert "/b.py" not in paths

    async def test_grep_relative_positional_path_scoped(self, scoped_db):
        """rg-style relative positional paths are scoped under the user.

        ``paths=("src",)`` (no leading slash) must resolve to
        ``/u1/src/%`` on a user-scoped filesystem.  Cross-user isolation
        is already covered by ``test_grep_scoped``; this test pins the
        narrowing behaviour of the relative-prefix branch in
        ``_scope_filter_prefix``.
        """
        await scoped_db.write(path="/src/a.py", content="hit here", user_id="u1")
        await scoped_db.write(path="/lib/b.py", content="hit here", user_id="u1")

        result = await scoped_db.grep(pattern="hit", paths=("src",), user_id="u1")
        paths = [e.path for e in result.entries]
        assert paths == ["/src/a.py"]

    async def test_glob_relative_positional_path_scoped(self, scoped_db):
        """Same coverage hole for ``_glob_impl``: relative positional
        ``paths`` must prepend ``/user_id`` before the LIKE filter."""
        await scoped_db.write(path="/src/a.py", content="x", user_id="u1")
        await scoped_db.write(path="/lib/b.py", content="y", user_id="u1")

        result = await scoped_db.glob(pattern="**/*.py", paths=("src",), user_id="u1")
        paths = [e.path for e in result.entries]
        assert paths == ["/src/a.py"]


class TestUserScopedDelete:
    async def test_delete_only_affects_user(self, scoped_db):
        await scoped_db.write(path="/doc.txt", content="a", user_id="u1")
        await scoped_db.write(path="/doc.txt", content="b", user_id="u2")

        await scoped_db.delete(path="/doc.txt", user_id="u1")
        # u1's file is gone
        r1 = await scoped_db.read(path="/doc.txt", user_id="u1")
        assert not r1.success or r1.file is None
        # u2's file still exists
        r2 = await scoped_db.read(path="/doc.txt", user_id="u2")
        assert r2.file is not None
        assert r2.file.content == "b"


class TestUserScopedMkedge:
    async def test_mkedge_scoped(self, scoped_db):
        await scoped_db.write(path="/src/main.py", content="main", user_id="u1")
        await scoped_db.write(path="/src/auth.py", content="auth", user_id="u1")

        result = await scoped_db.mkedge(
            source="/src/main.py",
            target="/src/auth.py",
            edge_type="imports",
            user_id="u1",
        )
        assert result.success
        # Edge path should be unscoped in result
        conn = result.entries[0]
        parts = decompose_edge(conn.path)
        assert parts is not None
        assert parts.source == "/src/main.py"
        assert parts.target == "/src/auth.py"
        assert parts.edge_type == "imports"


class TestUserScopedGraph:
    async def test_predecessors_scoped(self, scoped_db):
        await scoped_db.write(path="/a.py", content="a", user_id="u1")
        await scoped_db.write(path="/b.py", content="b", user_id="u1")
        await scoped_db.mkedge("/a.py", "/b.py", "imports", user_id="u1")

        # u2 has different files
        await scoped_db.write(path="/a.py", content="a2", user_id="u2")
        await scoped_db.write(path="/b.py", content="b2", user_id="u2")
        await scoped_db.mkedge("/a.py", "/b.py", "calls", user_id="u2")

        # u1's predecessors of /b.py should only show u1's /a.py
        result = await scoped_db.predecessors(path="/b.py", user_id="u1")
        paths = [e.path for e in result.entries]
        assert "/a.py" in paths

    async def test_pagerank_scoped(self, scoped_db):
        # u1 graph
        await scoped_db.write(path="/a.py", content="a", user_id="u1")
        await scoped_db.write(path="/b.py", content="b", user_id="u1")
        await scoped_db.mkedge("/a.py", "/b.py", "imports", user_id="u1")

        # u2 graph (larger)
        for name in ["x", "y", "z", "w"]:
            await scoped_db.write(path=f"/{name}.py", content=name, user_id="u2")
        await scoped_db.mkedge("/x.py", "/y.py", "imports", user_id="u2")
        await scoped_db.mkedge("/y.py", "/z.py", "imports", user_id="u2")
        await scoped_db.mkedge("/z.py", "/w.py", "imports", user_id="u2")

        # u1's pagerank should only include u1's nodes
        result = await scoped_db.pagerank(user_id="u1")
        paths = {e.path for e in result.entries}
        assert paths <= {"/a.py", "/b.py"}
        # Should NOT include u2's nodes
        assert not paths & {"/x.py", "/y.py", "/z.py", "/w.py"}


class TestNonScopedIgnoresUserId:
    async def test_user_id_ignored(self, db):
        """A non-scoped DatabaseFileSystem ignores user_id without error."""
        await db.write(path="/doc.txt", content="hello", user_id="u1")
        result = await db.read(path="/doc.txt", user_id="u1")
        assert result.file is not None
        assert result.file.content == "hello"

        # Also works without user_id
        result2 = await db.read(path="/doc.txt")
        assert result2.file is not None
        assert result2.file.content == "hello"


class TestUserScopedTree:
    async def test_tree_scoped(self, scoped_db):
        await scoped_db.mkdir(path="/src", user_id="u1")
        await scoped_db.write(path="/src/a.py", content="a", user_id="u1")
        await scoped_db.mkdir(path="/src", user_id="u2")
        await scoped_db.write(path="/src/b.py", content="b", user_id="u2")

        result = await scoped_db.tree(path="/src", user_id="u1")
        paths = [e.path for e in result.entries]
        assert "/src/a.py" in paths
        assert "/src/b.py" not in paths


class TestUserScopedMoveAndCopy:
    async def test_move_scoped(self, scoped_db):
        await scoped_db.write(path="/old.txt", content="data", user_id="u1")
        result = await scoped_db.move(src="/old.txt", dest="/new.txt", user_id="u1")
        assert result.success

        old = await scoped_db.read(path="/old.txt", user_id="u1")
        assert not old.success or old.file is None

        new = await scoped_db.read(path="/new.txt", user_id="u1")
        assert new.file is not None
        assert new.file.content == "data"

    async def test_copy_scoped(self, scoped_db):
        await scoped_db.write(path="/orig.txt", content="data", user_id="u1")
        result = await scoped_db.copy(src="/orig.txt", dest="/copy.txt", user_id="u1")
        assert result.success

        orig = await scoped_db.read(path="/orig.txt", user_id="u1")
        assert orig.file is not None

        copy_result = await scoped_db.read(path="/copy.txt", user_id="u1")
        assert copy_result.file is not None
        assert copy_result.file.content == "data"


class TestUserScopedEdit:
    async def test_edit_scoped(self, scoped_db):
        await scoped_db.write(path="/doc.txt", content="hello world", user_id="u1")
        result = await scoped_db.edit(path="/doc.txt", old="hello", new="goodbye", user_id="u1")
        assert result.success

        updated = await scoped_db.read(path="/doc.txt", user_id="u1")
        assert updated.file is not None
        assert updated.file.content == "goodbye world"


class TestUserScopedLexicalSearch:
    async def test_lexical_search_scoped(self, scoped_db):
        await scoped_db.write(path="/a.py", content="authentication login handler", user_id="u1")
        await scoped_db.write(path="/b.py", content="authentication login handler", user_id="u2")

        result = await scoped_db.lexical_search(query="authentication", user_id="u1")
        paths = [e.path for e in result.entries]
        assert "/a.py" in paths
        assert "/b.py" not in paths
