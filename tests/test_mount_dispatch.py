"""Tests for protocol dispatch — filesystem, SearchEngine, and graph interactions."""

from __future__ import annotations

from typing import Any

import pytest

from grover.mount import Mount, ProtocolConflictError, ProtocolNotAvailableError
from grover.mount.protocols import (
    SupportsEmbedding,
    SupportsGlob,
    SupportsGrep,
    SupportsHybridSearch,
    SupportsLexicalSearch,
    SupportsListDir,
    SupportsTree,
    SupportsVectorSearch,
)

# ------------------------------------------------------------------
# Fake components
# ------------------------------------------------------------------


class MinimalFilesystem:
    """Backend with no dispatch protocol methods."""

    async def open(self) -> None: ...

    async def close(self) -> None: ...


class GlobOnlyFilesystem:
    """Backend that satisfies only SupportsGlob."""

    async def glob(self, pattern: str, path: str = "/", **kwargs: Any) -> Any:
        return []


class FullDispatchFilesystem:
    """Backend satisfying SupportsGlob, SupportsGrep, SupportsTree, SupportsListDir."""

    async def glob(self, pattern: str, path: str = "/", **kwargs: Any) -> Any:
        return []

    async def grep(self, pattern: str, path: str = "/", **kwargs: Any) -> Any:
        return []

    async def tree(self, path: str = "/", **kwargs: Any) -> Any:
        return []

    async def list_dir(self, path: str = "/", **kwargs: Any) -> Any:
        return []


class FakeSearchEngineWithProtocols:
    """Search engine exposing supported_protocols()."""

    def __init__(self, protos: set[type] | None = None) -> None:
        self._protos = protos or set()

    def supported_protocols(self) -> set[type]:
        return self._protos


class GlobClaimingSearch:
    """A search component that claims to support SupportsGlob."""

    def supported_protocols(self) -> set[type]:
        return {SupportsGlob}


class VectorClaimingGraph:
    """A graph component that accidentally satisfies SupportsVectorSearch."""

    async def vector_search(self, query: str, **kwargs: Any) -> Any:
        return []


# ==================================================================
# Filesystem dispatch
# ==================================================================


class TestFilesystemDispatch:
    def test_glob_only(self):
        fs = GlobOnlyFilesystem()
        m = Mount(path="/p", filesystem=fs)
        assert m.dispatch(SupportsGlob) is fs

    def test_no_grep(self):
        fs = GlobOnlyFilesystem()
        m = Mount(path="/p", filesystem=fs)
        with pytest.raises(ProtocolNotAvailableError, match="SupportsGrep"):
            m.dispatch(SupportsGrep)

    def test_full_dispatch(self):
        fs = FullDispatchFilesystem()
        m = Mount(path="/p", filesystem=fs)
        for proto in [SupportsGlob, SupportsGrep, SupportsTree, SupportsListDir]:
            assert m.dispatch(proto) is fs

    def test_isinstance_check_works(self):
        """Dispatch protocols use isinstance() for filesystem components."""
        fs = FullDispatchFilesystem()
        assert isinstance(fs, SupportsGlob)
        assert isinstance(fs, SupportsGrep)
        assert isinstance(fs, SupportsTree)
        assert isinstance(fs, SupportsListDir)

    def test_minimal_not_dispatched(self):
        """Backend without dispatch methods doesn't satisfy any dispatch protocol."""
        fs = MinimalFilesystem()
        m = Mount(path="/p", filesystem=fs)
        assert m.supported_protocols() == set()


# ==================================================================
# Search dispatch via supported_protocols()
# ==================================================================


class TestSearchDispatch:
    def test_vector_search_protocol(self):
        search = FakeSearchEngineWithProtocols({SupportsVectorSearch})
        m = Mount(path="/p", filesystem=MinimalFilesystem(), search=search)
        assert m.dispatch(SupportsVectorSearch) is search

    def test_lexical_search_protocol(self):
        search = FakeSearchEngineWithProtocols({SupportsLexicalSearch})
        m = Mount(path="/p", filesystem=MinimalFilesystem(), search=search)
        assert m.dispatch(SupportsLexicalSearch) is search

    def test_hybrid_search_protocol(self):
        search = FakeSearchEngineWithProtocols({SupportsHybridSearch})
        m = Mount(path="/p", filesystem=MinimalFilesystem(), search=search)
        assert m.dispatch(SupportsHybridSearch) is search

    def test_embedding_protocol(self):
        search = FakeSearchEngineWithProtocols({SupportsEmbedding})
        m = Mount(path="/p", filesystem=MinimalFilesystem(), search=search)
        assert m.dispatch(SupportsEmbedding) is search

    def test_no_protocols(self):
        search = FakeSearchEngineWithProtocols(set())
        m = Mount(path="/p", filesystem=MinimalFilesystem(), search=search)
        assert not m.has_capability(SupportsVectorSearch)

    def test_multiple_search_protocols(self):
        search = FakeSearchEngineWithProtocols(
            {SupportsVectorSearch, SupportsLexicalSearch, SupportsEmbedding}
        )
        m = Mount(path="/p", filesystem=MinimalFilesystem(), search=search)
        assert m.has_capability(SupportsVectorSearch)
        assert m.has_capability(SupportsLexicalSearch)
        assert m.has_capability(SupportsEmbedding)
        assert not m.has_capability(SupportsHybridSearch)


# ==================================================================
# Conflict detection
# ==================================================================


class TestConflictDetection:
    def test_fs_and_search_glob_conflict(self):
        """Filesystem and search both satisfying SupportsGlob raises error."""
        fs = GlobOnlyFilesystem()
        search = GlobClaimingSearch()
        with pytest.raises(ProtocolConflictError, match="SupportsGlob"):
            Mount(path="/p", filesystem=fs, search=search)

    def test_graph_and_search_vector_conflict(self):
        """Graph satisfying SupportsVectorSearch via isinstance conflicts with search."""
        graph = VectorClaimingGraph()
        search = FakeSearchEngineWithProtocols({SupportsVectorSearch})
        with pytest.raises(ProtocolConflictError, match="SupportsVectorSearch"):
            Mount(path="/p", filesystem=MinimalFilesystem(), graph=graph, search=search)

    def test_conflict_error_message_names_components(self):
        """Conflict error message includes both component names."""
        fs = GlobOnlyFilesystem()
        search = GlobClaimingSearch()
        with pytest.raises(
            ProtocolConflictError,
            match=r"'filesystem'.*'search'",
        ):
            Mount(path="/p", filesystem=fs, search=search)


# ==================================================================
# Mixed component dispatch
# ==================================================================


class TestMixedDispatch:
    def test_fs_glob_and_search_vector(self):
        """No conflict when FS does glob and search does vector."""
        fs = GlobOnlyFilesystem()
        search = FakeSearchEngineWithProtocols({SupportsVectorSearch})
        m = Mount(path="/p", filesystem=fs, search=search)
        assert m.dispatch(SupportsGlob) is fs
        assert m.dispatch(SupportsVectorSearch) is search

    def test_full_stack(self):
        """FS with all four + search with vector + embedding — no conflict."""
        fs = FullDispatchFilesystem()
        search = FakeSearchEngineWithProtocols({SupportsVectorSearch, SupportsEmbedding})
        m = Mount(path="/p", filesystem=fs, search=search)
        assert m.dispatch(SupportsGlob) is fs
        assert m.dispatch(SupportsGrep) is fs
        assert m.dispatch(SupportsTree) is fs
        assert m.dispatch(SupportsListDir) is fs
        assert m.dispatch(SupportsVectorSearch) is search
        assert m.dispatch(SupportsEmbedding) is search


# ==================================================================
# Graph protocol checking
# ==================================================================


class TestGraphProtocolCheck:
    def test_graph_checked_via_isinstance(self):
        """Graph components without supported_protocols() use isinstance()."""
        graph = VectorClaimingGraph()
        m = Mount(path="/p", filesystem=MinimalFilesystem(), graph=graph)
        # VectorClaimingGraph has vector_search(), so isinstance check passes
        assert m.has_capability(SupportsVectorSearch)
        assert m.dispatch(SupportsVectorSearch) is graph
