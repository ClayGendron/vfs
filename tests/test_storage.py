"""Tests for ``vfs.storage`` — the op-family protocols and capability derivation.

The router-facing behavior (gating, funnel dispatch, derived
``capabilities()``) lives in ``test_base.py``; this file pins the
protocol layer itself: what ``storage_ops`` derives, the family map's
coverage of the op vocabulary, the ``StorageBackend`` identity minimum,
``TransportError``, and the ``ResolvedPair`` shape.
"""

from __future__ import annotations

from typing import Any

import pytest

from vfs.ops import ALL_OPS, MUTATING_OPS
from vfs.paths import Path
from vfs.results import Result
from vfs.storage import (
    ResolvedPair,
    StorageBackend,
    SupportsClose,
    SupportsGlean,
    SupportsGraph,
    SupportsMutation,
    SupportsPatternSearch,
    TransportError,
    storage_ops,
)


def _ok(op: str) -> Result:
    return Result(ops=(op,), observations=[])


class ReadOnly:
    """The read family, no identity members — the verb minimum without the protocol minimum."""

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


# ----------------------------------------------------------------------
# storage_ops — capability self-derivation
# ----------------------------------------------------------------------


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


# ----------------------------------------------------------------------
# StorageBackend — read family + name/description/capabilities() minimum
# ----------------------------------------------------------------------


class MountableBackend(ReadOnly):
    """The read family plus all three identity members — a mountable backend."""

    name = "mountable"
    description = "Read-family backend with declared identity"

    def capabilities(self) -> frozenset[str]:
        return storage_ops(self)


def test_storage_backend_minimum_is_the_read_family_plus_identity() -> None:
    # Site legality has no probe — mkdir checks and acts in one call — so
    # the read family plus the three identity members makes a mountable,
    # readable backend.
    assert isinstance(MountableBackend(), StorageBackend)


def test_read_family_alone_is_not_a_storage_backend() -> None:
    # Declaration beats inference: method surface without name/description/
    # capabilities() is not enough to be mounted.
    assert not isinstance(ReadOnly(), StorageBackend)
    assert not isinstance(object(), StorageBackend)


def test_missing_name_is_not_a_storage_backend() -> None:
    class NoName(ReadOnly):
        description = "has description, no name"

        def capabilities(self) -> frozenset[str]:
            return storage_ops(self)

    assert not isinstance(NoName(), StorageBackend)


def test_missing_description_is_not_a_storage_backend() -> None:
    class NoDescription(ReadOnly):
        name = "no-description"

        def capabilities(self) -> frozenset[str]:
            return storage_ops(self)

    assert not isinstance(NoDescription(), StorageBackend)


def test_missing_capabilities_is_not_a_storage_backend() -> None:
    class NoCapabilities(ReadOnly):
        name = "no-capabilities"
        description = "has name and description, no capabilities()"

    assert not isinstance(NoCapabilities(), StorageBackend)


def test_supports_close_is_optional_and_detected() -> None:
    class Disposable(ReadOnly):
        async def close(self) -> None: ...

    assert isinstance(Disposable(), SupportsClose)
    assert not isinstance(ReadOnly(), SupportsClose)


# ----------------------------------------------------------------------
# TransportError
# ----------------------------------------------------------------------


def test_transport_error_is_an_exception_subclass() -> None:
    assert issubclass(TransportError, Exception)


def test_transport_error_raises_and_carries_a_message() -> None:
    with pytest.raises(TransportError, match="peer is gone"):
        raise TransportError("peer is gone")


# ----------------------------------------------------------------------
# ResolvedPair
# ----------------------------------------------------------------------


def test_resolved_pair_shape_is_a_src_dest_namedtuple() -> None:
    pair = ResolvedPair(src=Path("/a"), dest=Path("/b"))
    assert pair.src == "/a"
    assert pair.dest == "/b"
    assert pair == (Path("/a"), Path("/b"))
    assert ResolvedPair._fields == ("src", "dest")
