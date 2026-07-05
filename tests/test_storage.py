"""Tests for ``vfs.storage`` — the op-family protocols and capability derivation.

The router-facing behavior (gating, funnel dispatch, derived
``capabilities()``) lives in ``test_base.py``; this file pins the
protocol layer itself: what ``storage_ops`` derives, and that the family
map covers the whole op vocabulary.
"""

from __future__ import annotations

from typing import Any

from vfs.ops import ALL_OPS, MUTATING_OPS
from vfs.results2 import Result
from vfs.storage import (
    StorageBackend,
    SupportsClose,
    SupportsGlean,
    SupportsGraph,
    SupportsMutation,
    SupportsPatternSearch,
    storage_ops,
)


def _ok(op: str) -> Result:
    return Result(function=op, observations=[])


class ReadOnly:
    async def read(self, **kwargs: Any) -> Result:
        return _ok("read")

    async def stat(self, **kwargs: Any) -> Result:
        return _ok("stat")

    async def ls(self, **kwargs: Any) -> Result:
        return _ok("ls")

    async def tree(self, **kwargs: Any) -> Result:
        return _ok("tree")


class PatternSearcher(ReadOnly):
    async def glob(self, **kwargs: Any) -> Result:
        return _ok("glob")

    async def grep(self, **kwargs: Any) -> Result:
        return _ok("grep")


class Everything(PatternSearcher):
    async def glean(self, **kwargs: Any) -> Result:
        return _ok("glean")

    async def write(self, **kwargs: Any) -> Result:
        return _ok("write")

    async def edit(self, **kwargs: Any) -> Result:
        return _ok("edit")

    async def delete(self, **kwargs: Any) -> Result:
        return _ok("delete")

    async def mkdir(self, **kwargs: Any) -> Result:
        return _ok("mkdir")

    async def move(self, **kwargs: Any) -> Result:
        return _ok("move")

    async def copy(self, **kwargs: Any) -> Result:
        return _ok("copy")

    async def graph(self, **kwargs: Any) -> Result:
        return _ok("graph")

    async def mkedge(self, **kwargs: Any) -> Result:
        return _ok("mkedge")

    async def run(self, **kwargs: Any) -> Result:
        return _ok("run")


def test_storage_ops_derives_per_family() -> None:
    assert storage_ops(ReadOnly()) == frozenset({"read", "stat", "ls", "tree"})
    assert storage_ops(PatternSearcher()) == frozenset({"read", "stat", "ls", "tree", "glob", "grep"})


def test_family_map_covers_the_whole_op_vocabulary() -> None:
    # The drift guard: a new op added to ops.py must be assigned a family
    # (and routed in the funnel — that half is ty's assert_never).
    assert storage_ops(Everything()) == ALL_OPS


def test_storage_ops_of_a_non_backend_is_empty() -> None:
    assert storage_ops(None) == frozenset()
    assert storage_ops(object()) == frozenset()


def test_families_are_all_or_nothing() -> None:
    # One missing method means the family is not claimed — a partial family
    # cannot half-advertise.
    class AlmostMutating(ReadOnly):
        async def write(self, **kwargs: Any) -> Result:
            return _ok("write")

    assert not isinstance(AlmostMutating(), SupportsMutation)
    assert storage_ops(AlmostMutating()) == storage_ops(ReadOnly())


def test_mutation_family_is_exactly_the_write_gated_ops() -> None:
    # The family boundary follows the write gate: mkedge writes the edge
    # projection, so it belongs to mutation, not graph.
    class Mutating(ReadOnly):
        async def write(self, **kwargs: Any) -> Result:
            return _ok("write")

        async def edit(self, **kwargs: Any) -> Result:
            return _ok("edit")

        async def delete(self, **kwargs: Any) -> Result:
            return _ok("delete")

        async def mkdir(self, **kwargs: Any) -> Result:
            return _ok("mkdir")

        async def move(self, **kwargs: Any) -> Result:
            return _ok("move")

        async def copy(self, **kwargs: Any) -> Result:
            return _ok("copy")

        async def mkedge(self, **kwargs: Any) -> Result:
            return _ok("mkedge")

    assert storage_ops(Mutating()) == storage_ops(ReadOnly()) | MUTATING_OPS


def test_graph_family_is_traversal_only() -> None:
    # A backend can traverse a graph it has no way to write into — the read
    # side stands alone, so dialect-specific traversal composes over a
    # portable mkedge in a base class.
    class TraversalOnly(ReadOnly):
        async def graph(self, **kwargs: Any) -> Result:
            return _ok("graph")

    assert isinstance(TraversalOnly(), SupportsGraph)
    assert storage_ops(TraversalOnly()) == storage_ops(ReadOnly()) | {"graph"}


def test_search_families_are_independent() -> None:
    # glob/grep without glean is the normal partial backend, and vice versa.
    class GleanOnly(ReadOnly):
        async def glean(self, **kwargs: Any) -> Result:
            return _ok("glean")

    assert isinstance(PatternSearcher(), SupportsPatternSearch)
    assert not isinstance(PatternSearcher(), SupportsGlean)
    assert isinstance(GleanOnly(), SupportsGlean)
    assert not isinstance(GleanOnly(), SupportsPatternSearch)


def test_storage_backend_minimum_is_the_read_family() -> None:
    assert isinstance(ReadOnly(), StorageBackend)
    assert not isinstance(object(), StorageBackend)


def test_supports_close_is_optional_and_detected() -> None:
    class Disposable(ReadOnly):
        async def close(self) -> None: ...

    assert isinstance(Disposable(), SupportsClose)
    assert not isinstance(ReadOnly(), SupportsClose)
