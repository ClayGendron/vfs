"""Tests for VFSClient sync wrapper and raise_on_error integration."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

from vfs.backends.database import DatabaseFileSystem
from vfs.client import VFSClient
from vfs.exceptions import (
    GraphError,
    MountError,
    NotFoundError,
    ValidationError,
    VFSError,
    WriteConflictError,
    _classify_error,
)
from vfs.results import VFSResult

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


async def _sqlite_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    return engine


def _make_db_sync(vfs: VFSClient) -> DatabaseFileSystem:
    """Create a DatabaseFileSystem using the sync VFSClient's event loop."""

    async def _setup():
        engine = await _sqlite_engine()
        return DatabaseFileSystem(engine=engine)

    return vfs._run(_setup())


@pytest.fixture
def g():
    vfs = VFSClient()
    vfs.add_mount("data", _make_db_sync(vfs))
    yield vfs
    vfs.close()


# ==================================================================
# Exception hierarchy
# ==================================================================


class TestExceptionHierarchy:
    def test_not_found_is_vfs_error(self):
        assert issubclass(NotFoundError, VFSError)

    def test_mount_error_is_vfs_error(self):
        assert issubclass(MountError, VFSError)

    def test_write_conflict_is_vfs_error(self):
        assert issubclass(WriteConflictError, VFSError)

    def test_validation_is_vfs_error(self):
        assert issubclass(ValidationError, VFSError)

    def test_graph_error_is_vfs_error(self):
        assert issubclass(GraphError, VFSError)

    def test_catch_base_catches_subclass(self):
        with pytest.raises(VFSError):
            raise NotFoundError("gone")

    def test_error_has_result_attribute(self):
        result = VFSResult(success=False, errors=["oops"])
        e = VFSError("oops", result)
        assert e.result is result

    def test_error_result_defaults_to_none(self):
        e = VFSError("oops")
        assert e.result is None


# ==================================================================
# _classify_error
# ==================================================================


class TestClassifyError:
    def _result(self, *errors: str) -> VFSResult:
        return VFSResult(success=False, errors=list(errors))

    def test_not_found(self):
        r = self._result("Not found: /x.txt")
        assert isinstance(_classify_error(r.error_message, r.errors, r), NotFoundError)

    def test_not_a_directory(self):
        r = self._result("Not a directory: /x")
        assert isinstance(_classify_error(r.error_message, r.errors, r), NotFoundError)

    def test_no_mount(self):
        r = self._result("No mount found for path: /x")
        assert isinstance(_classify_error(r.error_message, r.errors, r), MountError)

    def test_already_exists(self):
        r = self._result("Already exists (overwrite=False): /x")
        assert isinstance(_classify_error(r.error_message, r.errors, r), WriteConflictError)

    def test_cannot_write(self):
        r = self._result("Cannot write to root path")
        assert isinstance(_classify_error(r.error_message, r.errors, r), WriteConflictError)

    def test_cannot_delete(self):
        r = self._result("Cannot delete root path")
        assert isinstance(_classify_error(r.error_message, r.errors, r), WriteConflictError)

    def test_invalid_pattern(self):
        r = self._result("Invalid glob pattern: [")
        assert isinstance(_classify_error(r.error_message, r.errors, r), ValidationError)

    def test_requires_missing(self):
        r = self._result("edit requires old and new strings")
        assert isinstance(_classify_error(r.error_message, r.errors, r), ValidationError)

    def test_graph_failed(self):
        r = self._result("predecessors failed: KeyError('x')")
        assert isinstance(_classify_error(r.error_message, r.errors, r), GraphError)

    def test_unknown_falls_back_to_base(self):
        r = self._result("something unexpected")
        e = _classify_error(r.error_message, r.errors, r)
        assert type(e) is VFSError

    def test_result_attached_to_exception(self):
        r = self._result("Not found: /x")
        e = _classify_error(r.error_message, r.errors, r)
        assert e.result is r


# ==================================================================
# raise_on_error on VirtualFileSystem directly
# ==================================================================


class TestRaiseOnErrorFlag:
    async def test_error_returns_result_when_false(self):
        engine = await _sqlite_engine()
        try:
            fs = DatabaseFileSystem(engine=engine)
            assert fs._raise_on_error is False
            r = fs._error("test error")
            assert isinstance(r, VFSResult)
            assert not r.success
        finally:
            await engine.dispose()

    async def test_error_raises_when_true(self):
        engine = await _sqlite_engine()
        try:
            fs = DatabaseFileSystem(engine=engine)
            fs._raise_on_error = True
            with pytest.raises(VFSError, match="test error"):
                fs._error("test error")
        finally:
            await engine.dispose()

    async def test_mount_propagates_raise_on_error(self):
        from vfs.base import VirtualFileSystem

        router = VirtualFileSystem(storage=False, raise_on_error=True)
        engine = await _sqlite_engine()
        try:
            child = DatabaseFileSystem(engine=engine)
            assert child._raise_on_error is False
            await router.add_mount("/data", child)
            assert child._raise_on_error is True
        finally:
            await engine.dispose()


# ==================================================================
# VFSClient sync wrapper — construction and lifecycle
# ==================================================================


class TestVFSClientConstruction:
    def test_creates_with_defaults(self):
        g = VFSClient()
        assert g._async._raise_on_error is True
        assert g._thread.is_alive()
        g.close()

    def test_close_is_idempotent(self):
        g = VFSClient()
        g.close()
        g.close()  # should not raise

    def test_close_joins_thread(self):
        g = VFSClient()
        thread = g._thread
        g.close()
        assert not thread.is_alive()


# ==================================================================
# VFSClient sync wrapper — mount management
# ==================================================================


class TestVFSClientMount:
    def test_add_mount(self):
        g = VFSClient()
        g.add_mount("data", _make_db_sync(g))
        assert "/data" in g._async._mounts
        g.close()

    def test_add_mount_with_leading_slash(self):
        g = VFSClient()
        g.add_mount("/data", _make_db_sync(g))
        assert "/data" in g._async._mounts
        g.close()

    def test_remove_mount(self):
        g = VFSClient()
        g.add_mount("data", _make_db_sync(g))
        g.remove_mount("data")
        assert "/data" not in g._async._mounts
        g.close()


# ==================================================================
# VFSClient sync wrapper — CRUD return types and error raising
# ==================================================================


class TestVFSClientCRUD:
    def test_write_and_read_roundtrip(self, g: VFSClient):
        result = g.write("/data/hello.txt", "hello world")
        assert result.file.path == "/data/hello.txt"

        result = g.read("/data/hello.txt")
        assert result.content == "hello world"

    def test_read_returns_vfs_result(self, g: VFSClient):
        g.write("/data/test.txt", "x")
        result = g.read("/data/test.txt")
        assert isinstance(result, VFSResult)

    def test_write_returns_vfs_result(self, g: VFSClient):
        result = g.write("/data/test.txt", "x")
        assert isinstance(result, VFSResult)

    def test_read_not_found_raises(self, g: VFSClient):
        with pytest.raises(NotFoundError, match="Not found"):
            g.read("/data/nonexistent.txt")

    def test_read_unmounted_path_raises(self, g: VFSClient):
        with pytest.raises(MountError, match="No mount found"):
            g.read("/unknown/file.txt")

    def test_write_overwrite_false_raises(self, g: VFSClient):
        g.write("/data/exists.txt", "first")
        with pytest.raises(WriteConflictError, match="Already exists"):
            g.write("/data/exists.txt", "second", overwrite=False)

    def test_edit_returns_vfs_result(self, g: VFSClient):
        g.write("/data/test.txt", "old text")
        result = g.edit("/data/test.txt", "old", "new")
        assert isinstance(result, VFSResult)

    def test_delete_returns_vfs_result(self, g: VFSClient):
        g.write("/data/test.txt", "x")
        result = g.delete("/data/test.txt")
        assert isinstance(result, VFSResult)

    def test_mkdir_returns_vfs_result(self, g: VFSClient):
        result = g.mkdir("/data/subdir")
        assert isinstance(result, VFSResult)

    def test_stat_returns_vfs_result(self, g: VFSClient):
        g.write("/data/test.txt", "x")
        result = g.stat("/data/test.txt")
        assert isinstance(result, VFSResult)


# ==================================================================
# VFSClient sync wrapper — search and listing
# ==================================================================


class TestVFSClientSearchAndListing:
    def test_glob_returns_vfs_result(self, g: VFSClient):
        g.write("/data/a.py", "a")
        g.write("/data/b.py", "b")
        result = g.glob("**/*.py")
        assert isinstance(result, VFSResult)
        assert len(result.entries) == 2

    def test_grep_returns_vfs_result(self, g: VFSClient):
        g.write("/data/test.txt", "needle in haystack")
        result = g.grep("needle")
        assert isinstance(result, VFSResult)
        assert len(result.entries) >= 1

    def test_set_algebra_works(self, g: VFSClient):
        g.write("/data/a.py", "import os")
        g.write("/data/b.py", "hello world")
        g.write("/data/c.txt", "import sys")

        py_files = g.glob("**/*.py")
        importers = g.grep("import")
        intersection = py_files & importers
        assert any("a.py" in e.path for e in intersection.entries)
        assert not any("b.py" in e.path for e in intersection.entries)

    def test_ls_returns_vfs_result(self, g: VFSClient):
        g.mkdir("/data/subdir")
        result = g.ls("/data")
        assert isinstance(result, VFSResult)

    def test_tree_returns_vfs_result(self, g: VFSClient):
        g.write("/data/a.txt", "a")
        result = g.tree("/data")
        assert isinstance(result, VFSResult)


# ==================================================================
# VFSClient sync wrapper — query engine
# ==================================================================


class TestVFSClientQuery:
    def test_run_query_returns_vfs_result(self, g: VFSClient):
        g.write("/data/hello.py", "print('hi')")
        result = g.run_query('glob "**/*.py"')
        assert isinstance(result, VFSResult)
        assert any("hello.py" in e.path for e in result.entries)

    def test_cli_returns_str(self, g: VFSClient):
        g.write("/data/hello.py", "print('hi')")
        output = g.cli('glob "**/*.py"')
        assert isinstance(output, str)
        assert "hello.py" in output

    def test_parse_query(self, g: VFSClient):
        plan = g.parse_query('glob "**/*.py"')
        assert plan is not None


# ==================================================================
# VFSClient sync wrapper — move, copy, mkconn
# ==================================================================


class TestVFSClientTransferOps:
    def test_move_returns_vfs_result(self, g: VFSClient):
        g.write("/data/src.txt", "content")
        result = g.move("/data/src.txt", "/data/dst.txt")
        assert isinstance(result, VFSResult)
        assert result.success
        with pytest.raises(NotFoundError):
            g.read("/data/src.txt")

    def test_copy_returns_vfs_result(self, g: VFSClient):
        g.write("/data/orig.txt", "content")
        result = g.copy("/data/orig.txt", "/data/dup.txt")
        assert isinstance(result, VFSResult)
        assert result.success
        assert g.read("/data/orig.txt").content == "content"
        assert g.read("/data/dup.txt").content == "content"

    def test_mkconn_returns_vfs_result(self, g: VFSClient):
        g.write("/data/a.py", "import b")
        g.write("/data/b.py", "class B: ...")
        result = g.mkconn("/data/a.py", "/data/b.py", "imports")
        assert isinstance(result, VFSResult)


# ==================================================================
# VFSClient sync wrapper — graph operations
# ==================================================================


class TestVFSClientGraph:
    @pytest.fixture(autouse=True)
    def _setup_graph(self, g: VFSClient):
        g.write("/data/a.py", "x")
        g.write("/data/b.py", "y")
        g.write("/data/c.py", "z")
        g.mkconn("/data/a.py", "/data/b.py", "imports")
        g.mkconn("/data/b.py", "/data/c.py", "calls")

    def test_predecessors(self, g: VFSClient):
        result = g.predecessors("/data/b.py")
        assert isinstance(result, VFSResult)

    def test_successors(self, g: VFSClient):
        result = g.successors("/data/a.py")
        assert isinstance(result, VFSResult)

    def test_ancestors(self, g: VFSClient):
        result = g.ancestors("/data/c.py")
        assert isinstance(result, VFSResult)

    def test_descendants(self, g: VFSClient):
        result = g.descendants("/data/a.py")
        assert isinstance(result, VFSResult)

    def test_neighborhood(self, g: VFSClient):
        result = g.neighborhood("/data/b.py")
        assert isinstance(result, VFSResult)

    def test_meeting_subgraph(self, g: VFSClient):
        seeds = g.glob("**/*.py")
        result = g.meeting_subgraph(seeds)
        assert isinstance(result, VFSResult)

    def test_min_meeting_subgraph(self, g: VFSClient):
        seeds = g.glob("**/*.py")
        result = g.min_meeting_subgraph(seeds)
        assert isinstance(result, VFSResult)

    def test_pagerank(self, g: VFSClient):
        result = g.pagerank()
        assert isinstance(result, VFSResult)

    def test_betweenness_centrality(self, g: VFSClient):
        result = g.betweenness_centrality()
        assert isinstance(result, VFSResult)

    def test_closeness_centrality(self, g: VFSClient):
        result = g.closeness_centrality()
        assert isinstance(result, VFSResult)

    def test_degree_centrality(self, g: VFSClient):
        result = g.degree_centrality()
        assert isinstance(result, VFSResult)

    def test_in_degree_centrality(self, g: VFSClient):
        result = g.in_degree_centrality()
        assert isinstance(result, VFSResult)

    def test_out_degree_centrality(self, g: VFSClient):
        result = g.out_degree_centrality()
        assert isinstance(result, VFSResult)

    def test_hits(self, g: VFSClient):
        result = g.hits()
        assert isinstance(result, VFSResult)


# ==================================================================
# VFSClient sync wrapper — search methods (without embedding provider)
# ==================================================================


class TestVFSClientSearchMethods:
    def test_lexical_search(self, g: VFSClient):
        g.write("/data/test.txt", "the quick brown fox")
        result = g.lexical_search("quick fox")
        assert isinstance(result, VFSResult)

    def test_semantic_search_raises_without_provider(self, g: VFSClient):
        g.write("/data/test.txt", "content")
        with pytest.raises(VFSError):
            g.semantic_search("test query")

    def test_vector_search_raises_without_provider(self, g: VFSClient):
        g.write("/data/test.txt", "content")
        with pytest.raises(VFSError):
            g.vector_search([0.1, 0.2, 0.3])
