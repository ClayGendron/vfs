"""The vid contract: every row that carries a version carries a vid, and the vid names that entry at that version.

Mixed into each conformance subclass beside the storage, grants and
cursor contracts, so every backend that declares the ``vid`` trait runs
it. A row's vid and its version share one mask; a bare row carries
neither; one row read by four verbs has one vid; and the vid moves with
the version and nothing else.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

import pytest

from vfs.authority import Authority
from vfs.models import Edge, Entry
from vfs.paths import TRASH_ROOT, Path
from vfs.results import ErrorKind
from vfs.storage import (
    ResolvedPair,
    StorageBackend,
    SupportsClose,
    SupportsGrants,
    SupportsMutation,
    SupportsPatternSearch,
    SupportsRankedSearch,
    SupportsTraits,
    SupportsTraversal,
)
from vfs.storage.replace import EditOperation
from vfs.vid import is_vid

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from vfs.results import Result

needs = pytest.mark.needs

SYSTEM = Authority.system()
ANON = Authority.anonymous()


class VidBackend(
    StorageBackend,
    SupportsPatternSearch,
    SupportsRankedSearch,
    SupportsTraversal,
    SupportsMutation,
    SupportsGrants,
    SupportsTraits,
    SupportsClose,
    Protocol,
):
    """The verb surface the vid contract calls."""


# Each call of the nineteen, made on the world `_world` seeds; each returns rows with a version or none.
CALLS: dict[str, Callable[[VidBackend], Awaitable[Result]]] = {
    "read": lambda s: s.read(path=Path("/d/a.txt")),
    "stat": lambda s: s.stat(observations=None, path=Path("/d")),
    "ls": lambda s: s.ls(path=Path("/d")),
    "tree": lambda s: s.tree(path=Path("/d")),
    "glob": lambda s: s.glob(patterns=("/d/**",)),
    "grep": lambda s: s.grep(pattern="alpha", allow_scan=True),
    "search": lambda s: s.search(query="alpha"),
    "traverse": lambda s: s.traverse(method="outbound", path=Path("/d/a.txt")),
    "write-created": lambda s: s.write(entries=[Entry(path=Path("/d/new.txt"), content="fresh")]),
    "write-updated": lambda s: s.write(entries=[Entry(path=Path("/d/a.txt"), content="alpha two")]),
    "write-unchanged": lambda s: s.write(entries=[Entry(path=Path("/d/b.txt"), content="beta")]),
    "edit": lambda s: s.edit(path=Path("/d/a.txt"), edits=[EditOperation("alpha", "omega")]),
    "mkdir": lambda s: s.mkdir(path=Path("/e")),
    "move": lambda s: s.move(operations=[ResolvedPair(Path("/d/b.txt"), Path("/d/moved.txt"))]),
    "copy": lambda s: s.copy(operations=[ResolvedPair(Path("/d"), Path("/copied"))]),
    "delete": lambda s: s.delete(path=Path("/d/b.txt")),
    "restore": lambda s: _deleted_then(s, "/gone.txt", lambda path: s.restore(path=path)),
    "sweep": lambda s: s.sweep(path=Path("/d/sub")),
    "ls-trash": lambda s: _deleted_then(s, "/gone.txt", lambda path: s.ls(path=Path(TRASH_ROOT))),
}


async def _world(storage: VidBackend) -> None:
    """Two files and a subdirectory under ``/d``, a file to delete, and one edge."""
    files = {"/d/a.txt": "alpha", "/d/b.txt": "beta", "/d/sub/c.txt": "gamma", "/gone.txt": "gone"}
    entries = [Entry(path=Path(path), content=body) for path, body in files.items()]
    assert (await storage.write(entries=entries, parents=True)).success is True
    edge = Edge(source=Path("/d/a.txt"), target=Path("/d/b.txt"), edge_type="cites")
    assert (await storage.mkedge(edges=[edge])).success is True


async def _deleted_then(storage: VidBackend, path: str, then: Callable[[Path], Awaitable[Result]]) -> Result:
    assert (await storage.delete(path=Path(path))).success is True
    return await then(Path(path))


async def _vid(storage: VidBackend, path: str) -> str | None:
    """The vid a ``stat`` of *path* returns now."""
    return (await storage.stat(path=Path(path))).one().vid


class VidContract:
    """Every row a storage fills a version on carries a vid, and the vid follows the entry and its version."""

    @pytest.mark.parametrize("call", list(CALLS))
    async def test_every_row_with_a_version_carries_a_vid(self, storage: VidBackend, call: str) -> None:
        """Mutation guarded: a row builder that sets ``version`` and leaves the vid out of the row or the mask."""
        await _world(storage)
        result = await CALLS[call](storage)
        assert result.success is True, result.errors
        rows = result.observations
        assert sum((row.version is None) != (row.vid is None) for row in rows) == 0
        assert sum(("version" in row.populated) != ("vid" in row.populated) for row in rows) == 0
        named = [row.vid for row in rows if row.vid is not None]
        assert named, f"{call} returned no row with a version"
        assert all(is_vid(vid) for vid in named)

    @pytest.mark.parametrize(
        "call", ["write-created", "write-updated", "write-unchanged", "edit", "mkdir", "move", "copy", "restore"]
    )
    async def test_a_change_names_the_row_it_left(self, storage: VidBackend, call: str) -> None:
        """Mutation guarded: a result row minted at the version before an arbitration or a bump moved it."""
        await _world(storage)
        result = await CALLS[call](storage)
        assert result.success is True, result.errors
        rows = [row for row in result.observations if row.vid is not None]
        assert rows
        assert [row.vid for row in rows] == [await _vid(storage, str(row.path)) for row in rows]

    async def test_a_delete_names_the_row_as_it_was(self, storage: VidBackend) -> None:
        await _world(storage)
        before = await _vid(storage, "/d/b.txt")
        deleted = await storage.delete(path=Path("/d/b.txt"))
        assert [row.vid for row in deleted.observations] == [before]

    @needs("set_posture", "stat", "ls")
    async def test_a_bare_row_carries_no_vid(self, storage: VidBackend) -> None:
        await _world(storage)
        assert (await storage.set_posture(path=Path("/"), posture="list", authority=SYSTEM)).success is True
        stat = await storage.stat(path=Path("/d/a.txt"), authority=ANON)
        listed = await storage.ls(path=Path("/d"), authority=ANON)
        rows = [*stat.observations, *listed.observations]
        assert len(rows) == 4
        assert sum(row.vid is not None or "vid" in row.populated for row in rows) == 0

    async def test_one_row_has_one_vid_from_every_verb(self, storage: VidBackend) -> None:
        await _world(storage)
        stat = await storage.stat(path=Path("/d/a.txt"))
        read = await storage.read(path=Path("/d/a.txt"))
        listed = await storage.ls(path=Path("/d"))
        globbed = await storage.glob(patterns=("/d/a.txt",))
        rows = [*stat.observations, *read.observations, *globbed.observations]
        rows += [row for row in listed.observations if row.path == "/d/a.txt"]
        assert len(rows) == 4
        assert len({row.vid for row in rows}) == 1

    @pytest.mark.parametrize(
        ("case", "moves"),
        [
            ("a new body", True),
            ("the same body", False),
            ("an edit", True),
            ("an append", True),
            ("a delete and a restore", True),
            ("a delete and a write", True),
            ("a move", True),
            ("a parent moved", False),
            ("a parent deleted and restored", False),
            ("a copy", True),
        ],
    )
    async def test_what_moves_a_vid_and_what_keeps_it(self, storage: VidBackend, case: str, moves: bool) -> None:
        """Mutation guarded: a vid minted from anything but the entry and its version, such as the path."""
        await _world(storage)
        before = await _vid(storage, "/d/sub/c.txt")
        after_path = await _CHANGES[case](storage)
        after = await _vid(storage, after_path)
        assert after is not None and before is not None
        assert (after != before) is moves
        if case == "a copy":
            assert await _vid(storage, "/d/sub/c.txt") == before

    async def test_an_exists_names_the_vid_of_what_is_there(self, storage: VidBackend) -> None:
        await _world(storage)
        stored = (await storage.stat(path=Path("/d/a.txt"))).one()
        refused = await storage.write(entries=[Entry(path=Path("/d/a.txt"), content="other")], if_absent=True)
        (error,) = refused.errors
        assert (error.kind, error.data) == (
            ErrorKind.exists,
            {"version": stored.version, "content_hash": stored.content_hash, "vid": stored.vid},
        )

    async def test_the_storage_declares_the_vid_trait(self, storage: VidBackend) -> None:
        assert storage.traits()["vid"] == "entry_version"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _rewrite(storage: VidBackend, body: str) -> str:
    assert (await storage.write(entries=[Entry(path=Path("/d/sub/c.txt"), content=body)])).success is True
    return "/d/sub/c.txt"


async def _edit(storage: VidBackend) -> str:
    edited = await storage.edit(path=Path("/d/sub/c.txt"), edits=[EditOperation("gamma", "delta")])
    assert edited.success is True
    return "/d/sub/c.txt"


async def _append(storage: VidBackend) -> str:
    entry = Entry(path=Path("/d/sub/c.txt"), content=" more")
    assert (await storage.write(entries=[entry], append=True)).success is True
    return "/d/sub/c.txt"


async def _delete_and(storage: VidBackend, path: str, then: Callable[[], Awaitable[Result]]) -> str:
    assert (await storage.delete(path=Path(path))).success is True
    assert (await then()).success is True
    return "/d/sub/c.txt"


async def _move(storage: VidBackend, src: str, dest: str, landed: str) -> str:
    assert (await storage.move(operations=[ResolvedPair(Path(src), Path(dest))])).success is True
    return landed


async def _copy(storage: VidBackend) -> str:
    copied = await storage.copy(operations=[ResolvedPair(Path("/d/sub/c.txt"), Path("/d/sub/copy.txt"))])
    assert copied.success is True
    return "/d/sub/copy.txt"


_CHANGES: dict[str, Callable[[VidBackend], Awaitable[str]]] = {
    "a new body": lambda s: _rewrite(s, "another body"),
    "the same body": lambda s: _rewrite(s, "gamma"),
    "an edit": _edit,
    "an append": _append,
    "a delete and a restore": lambda s: _delete_and(s, "/d/sub/c.txt", lambda: s.restore(path=Path("/d/sub/c.txt"))),
    "a delete and a write": lambda s: _delete_and(
        s, "/d/sub/c.txt", lambda: s.write(entries=[Entry(path=Path("/d/sub/c.txt"), content="gamma")])
    ),
    "a move": lambda s: _move(s, "/d/sub/c.txt", "/d/sub/moved.txt", "/d/sub/moved.txt"),
    "a parent moved": lambda s: _move(s, "/d/sub", "/d/elsewhere", "/d/elsewhere/c.txt"),
    "a parent deleted and restored": lambda s: _delete_and(s, "/d/sub", lambda: s.restore(path=Path("/d/sub"))),
    "a copy": _copy,
}
