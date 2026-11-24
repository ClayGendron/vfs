"""The vid contract: every row that carries a version carries a vid, and the vid names that entry at that version.

Mixed into each conformance subclass beside the storage, grants and
cursor contracts, so every backend that declares the ``vid`` trait runs
it. A row's vid and its version share one mask; a bare row carries
neither; one row read by four verbs has one vid; and the vid moves with
the version and nothing else.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Protocol

import pytest

from vfs.authority import Authority
from vfs.models import Edge, Entry, Observation
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
from vfs.storage.backends.memory import InMemoryStorage
from vfs.storage.replace import EditOperation
from vfs.vid import ABSENT, is_vid

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


# Each call the contract makes, unpaged and paged, on the world `_world` seeds; each returns rows with a version.
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
    "write-bumped-unchanged": lambda s: s.write(
        entries=[Entry(path=Path("/d"), kind="directory"), Entry(path=Path("/d/new.txt"), content="fresh")]
    ),
    "edit": lambda s: s.edit(path=Path("/d/a.txt"), edits=[EditOperation("alpha", "omega")]),
    "mkdir": lambda s: s.mkdir(path=Path("/e")),
    "move": lambda s: s.move(operations=[ResolvedPair(Path("/d/b.txt"), Path("/d/moved.txt"))]),
    "copy": lambda s: s.copy(operations=[ResolvedPair(Path("/d"), Path("/copied"))]),
    "delete": lambda s: s.delete(path=Path("/d/b.txt")),
    "restore": lambda s: _deleted_then(s, "/gone.txt", lambda path: s.restore(path=path)),
    "sweep": lambda s: s.sweep(path=Path("/d/sub")),
    "ls-trash": lambda s: _deleted_then(s, "/gone.txt", lambda path: s.ls(path=Path(TRASH_ROOT))),
    "ls-page": lambda s: s.ls(path=Path("/d"), limit=1),
    "tree-page": lambda s: s.tree(path=Path("/d"), limit=1),
    "glob-page": lambda s: s.glob(patterns=("/d/**",), limit=1),
    "ls-trash-page": lambda s: _deleted_then(s, "/gone.txt", lambda path: s.ls(path=Path(TRASH_ROOT), limit=1)),
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


async def _vid(storage: VidBackend, path: str) -> str:
    """The vid a ``stat`` of *path* returns now; a row with a version always has one."""
    vid = (await storage.stat(path=Path(path))).one().vid
    assert vid is not None
    return vid


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
        "call",
        [
            "write-created",
            "write-updated",
            "write-unchanged",
            "write-bumped-unchanged",
            "edit",
            "mkdir",
            "move",
            "copy",
            "restore",
        ],
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

    @pytest.mark.parametrize("case", ["a new file", "another file moved in", "a copy", "the parent replaced"])
    async def test_a_path_freed_by_a_move_is_refused(self, storage: VidBackend, case: str) -> None:
        """Mutation guarded: a precondition judged on the version alone, which each of the four cases passes."""
        files = {"/x/p": "the file that was read", "/x/q": "another file", "/w/r": "one more"}
        entries = [Entry(path=Path(path), content=body) for path, body in files.items()]
        assert (await storage.write(entries=entries, parents=True)).success is True
        seen = await _vid(storage, "/x/p")
        assert seen is not None
        await _FREED[case](storage)
        standing = (await storage.read(path=Path("/x/p"))).one()
        refused = await storage.write(entries=[Entry(path=Path("/x/p"), content="mine")], if_vids={Path("/x/p"): seen})
        now = {"version": standing.version, "vid": standing.vid}
        assert [(error.kind, error.data) for error in refused.errors] == [(ErrorKind.conflict, now)]
        assert (await storage.read(path=Path("/x/p"))).one().content == standing.content

    async def test_a_vid_minted_by_another_storage_is_conflict(self, storage: VidBackend) -> None:
        other = InMemoryStorage()
        for each in (storage, other):
            assert (await each.write(entries=[Entry(path=Path("/a.txt"), content="x")])).success is True
        foreign = await _vid(other, "/a.txt")
        await other.close()
        refused = await storage.write(
            entries=[Entry(path=Path("/a.txt"), content="y")], if_vids={Path("/a.txt"): foreign}
        )
        assert [error.kind for error in refused.errors] == [ErrorKind.conflict]
        assert (await storage.read(path=Path("/a.txt"))).one().content == "x"

    async def test_twenty_writers_that_require_one_vid_land_once(self, storage: VidBackend) -> None:
        assert (await storage.write(entries=[Entry(path=Path("/a.txt"), content="seed")])).success is True
        seen = {Path("/a.txt"): await _vid(storage, "/a.txt")}
        writes = [
            storage.write(entries=[Entry(path=Path("/a.txt"), content=f"body {n}")], if_vids=seen) for n in range(20)
        ]
        results = await asyncio.gather(*writes)
        assert sum(result.success for result in results) == 1
        assert sorted(error.kind for result in results for error in result.errors) == [ErrorKind.conflict] * 19

    async def test_a_required_vid_over_a_directory_is_conflict(self, storage: VidBackend) -> None:
        assert (await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])).success is True
        seen = await _vid(storage, "/a.txt")
        assert (await storage.delete(path=Path("/a.txt"))).success is True
        assert (await storage.sweep(path=Path("/a.txt"))).success is True
        assert (await storage.mkdir(path=Path("/a.txt"))).success is True
        required = await storage.write(
            entries=[Entry(path=Path("/a.txt"), content="y")], if_vids={Path("/a.txt"): seen}
        )
        directory = (await storage.stat(path=Path("/a.txt"))).one()
        now = {"version": directory.version, "vid": directory.vid}
        assert [(error.kind, error.data) for error in required.errors] == [(ErrorKind.conflict, now)]
        plain = await storage.write(entries=[Entry(path=Path("/a.txt"), content="y")])
        assert [error.kind for error in plain.errors] == [ErrorKind.wrong_kind]

    async def test_a_required_vid_over_a_tombstoned_directory_is_not_found(self, storage: VidBackend) -> None:
        assert (await storage.mkdir(path=Path("/d"))).success is True
        seen = await _vid(storage, "/d")
        assert (await storage.delete(path=Path("/d"))).success is True
        required = await storage.write(entries=[Entry(path=Path("/d"), content="y")], if_vids={Path("/d"): seen})
        assert [(e.kind, (e.data or {}).get("vfs.trashed")) for e in required.errors] == [(ErrorKind.not_found, True)]

    async def test_the_mark_creates_and_never_replaces(self, storage: VidBackend) -> None:
        """Mutation guarded: the mark read as a plain write, which replaces the occupant and reports success."""
        assert (await storage.write(entries=[Entry(path=Path("/keyed.txt"), content="old")])).success is True
        keyed = await _vid(storage, "/keyed.txt")
        batch = [Entry(path=Path(path), content="new") for path in ("/keyed.txt", "/marked.txt", "/plain.txt")]
        marks = {Path("/keyed.txt"): keyed, Path("/marked.txt"): ABSENT}
        landed = await storage.write(entries=batch, if_vids=marks)
        assert [(row.path, row.status) for row in landed.observations] == [
            ("/keyed.txt", "updated"),
            ("/marked.txt", "created"),
            ("/plain.txt", "created"),
        ]
        occupant = (await storage.stat(path=Path("/marked.txt"))).one()
        again = [Entry(path=Path(path), content="newer") for path in ("/marked.txt", "/plain.txt")]
        refused = await storage.write(entries=again, if_vids={Path("/marked.txt"): ABSENT})
        named = {"version": occupant.version, "content_hash": occupant.content_hash, "vid": occupant.vid}
        assert refused.observations == []
        assert [(error.kind, error.path, error.data) for error in refused.errors] == [
            (ErrorKind.exists, "/marked.txt", named)
        ]
        assert (await storage.read(path=Path("/plain.txt"))).one().content == "new"
        assert (await storage.delete(path=Path("/marked.txt"))).success is True
        revived = await storage.write(
            entries=[Entry(path=Path("/marked.txt"), content="back")], if_vids={Path("/marked.txt"): ABSENT}
        )
        assert [row.status for row in revived.observations] == ["updated"]

    async def test_the_mark_over_a_live_directory_is_exists_and_a_tombstoned_one_wrong_kind(
        self, storage: VidBackend
    ) -> None:
        assert (await storage.mkdir(path=Path("/live"))).success is True
        assert (await storage.mkdir(path=Path("/gone"))).success is True
        assert (await storage.delete(path=Path("/gone"))).success is True
        live = (await storage.stat(path=Path("/live"))).one()
        over_live = await storage.write(
            entries=[Entry(path=Path("/live"), content="x")], if_vids={Path("/live"): ABSENT}
        )
        assert [(e.kind, e.data) for e in over_live.errors] == [
            (ErrorKind.exists, {"version": live.version, "vid": live.vid})
        ]
        over_gone = await storage.write(
            entries=[Entry(path=Path("/gone"), content="x")], if_vids={Path("/gone"): ABSENT}
        )
        assert [(e.kind, (e.data or {}).get("vfs.trashed")) for e in over_gone.errors] == [(ErrorKind.wrong_kind, True)]

    async def test_twenty_marked_creates_of_one_path_land_once(self, storage: VidBackend) -> None:
        own = [Entry(path=Path(f"/own{n}.txt"), content="seed") for n in range(20)]
        assert (await storage.write(entries=own)).success is True

        def batch(n: int) -> Awaitable[Result]:
            entries = [
                Entry(path=Path("/lock"), content=f"holder {n}"),
                Entry(path=Path(f"/own{n}.txt"), content="mine"),
            ]
            return storage.write(entries=entries, if_vids={Path("/lock"): ABSENT})

        results = await asyncio.gather(*(batch(n) for n in range(20)))
        assert sum(result.success for result in results) == 1
        assert sorted(error.kind for result in results for error in result.errors) == [ErrorKind.exists] * 19

    async def test_an_edit_with_a_matching_vid_updates(self, storage: VidBackend) -> None:
        assert (await storage.write(entries=[Entry(path=Path("/a.txt"), content="alpha")])).success is True
        seen = await _vid(storage, "/a.txt")
        edited = await storage.edit(
            path=Path("/a.txt"), edits=[EditOperation("alpha", "beta")], if_vids={Path("/a.txt"): seen}
        )
        assert edited.success is True, edited.errors
        assert (await storage.read(path=Path("/a.txt"))).one().content == "beta"
        assert edited.observations[0].vid == await _vid(storage, "/a.txt") != seen

    async def test_an_edit_with_a_stale_vid_is_conflict_before_any_text_is_matched(self, storage: VidBackend) -> None:
        """Mutation guarded: the vid judged after the edits run, so a missing text answers in its place."""
        assert (await storage.write(entries=[Entry(path=Path("/a.txt"), content="alpha")])).success is True
        seen = {Path("/a.txt"): await _vid(storage, "/a.txt")}
        assert (await storage.write(entries=[Entry(path=Path("/a.txt"), content="gamma")])).success is True
        missing = await storage.edit(path=Path("/a.txt"), edits=[EditOperation("no such text", "x")], if_vids=seen)
        now = {"version": 2, "vid": await _vid(storage, "/a.txt")}
        assert [(error.kind, error.data, error.retryable) for error in missing.errors] == [
            (ErrorKind.conflict, now, False)
        ]
        # An edit that landed and is sent again with the same vid meets the vid it moved.
        current = {Path("/a.txt"): await _vid(storage, "/a.txt")}
        once = await storage.edit(path=Path("/a.txt"), edits=[EditOperation("gamma", "delta")], if_vids=current)
        assert once.success is True, once.errors
        twice = await storage.edit(path=Path("/a.txt"), edits=[EditOperation("gamma", "delta")], if_vids=current)
        assert [error.kind for error in twice.errors] == [ErrorKind.conflict]
        assert (await storage.read(path=Path("/a.txt"))).one().content == "delta"

    async def test_an_edit_over_a_directory_that_required_a_file_is_conflict(self, storage: VidBackend) -> None:
        assert (await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])).success is True
        seen = await _vid(storage, "/a.txt")
        assert (await storage.delete(path=Path("/a.txt"))).success is True
        assert (await storage.sweep(path=Path("/a.txt"))).success is True
        assert (await storage.mkdir(path=Path("/a.txt"))).success is True
        required = await storage.edit(
            path=Path("/a.txt"), edits=[EditOperation("x", "y")], if_vids={Path("/a.txt"): seen}
        )
        directory = (await storage.stat(path=Path("/a.txt"))).one()
        now = {"version": directory.version, "vid": directory.vid}
        assert [(error.kind, error.data) for error in required.errors] == [(ErrorKind.conflict, now)]

    async def test_a_batch_edit_with_one_stale_key_edits_nothing(self, storage: VidBackend) -> None:
        entries = [Entry(path=Path(path), content="alpha") for path in ("/a.txt", "/b.txt")]
        assert (await storage.write(entries=entries)).success is True
        seen = {Path(path): await _vid(storage, path) for path in ("/a.txt", "/b.txt")}
        assert (await storage.write(entries=[Entry(path=Path("/b.txt"), content="alpha again")])).success is True
        rows = [Observation(path=Path("/a.txt")), Observation(path=Path("/b.txt"))]
        edited = await storage.edit(observations=rows, edits=[EditOperation("alpha", "beta")], if_vids=seen)
        assert [(error.kind, error.path) for error in edited.errors] == [(ErrorKind.conflict, "/b.txt")]
        bodies = [(await storage.read(path=Path(path))).one().content for path in ("/a.txt", "/b.txt")]
        assert bodies == ["alpha", "alpha again"]

    async def test_the_mark_on_an_edit_of_what_is_there(self, storage: VidBackend) -> None:
        assert (await storage.write(entries=[Entry(path=Path("/a.txt"), content="alpha")])).success is True
        there = (await storage.stat(path=Path("/a.txt"))).one()
        live = await storage.edit(
            path=Path("/a.txt"), edits=[EditOperation("alpha", "x")], if_vids={Path("/a.txt"): ABSENT}
        )
        assert [(error.kind, error.data) for error in live.errors] == [
            (ErrorKind.conflict, {"version": there.version, "vid": there.vid})
        ]
        empty = await storage.edit(
            path=Path("/none.txt"), edits=[EditOperation("a", "b")], if_vids={Path("/none.txt"): ABSENT}
        )
        assert [error.kind for error in empty.errors] == [ErrorKind.not_found]

    async def test_a_delete_requires_what_it_was_shown(self, storage: VidBackend) -> None:
        """Mutation guarded: a delete that judges the key after ``not_empty``, or not at all on a directory."""
        files = {"/f.txt": "x", "/d/a.txt": "x", "/g/sub/a.txt": "x", "/e/a.txt": "x"}
        entries = [Entry(path=Path(path), content=body) for path, body in files.items()]
        assert (await storage.write(entries=entries, parents=True)).success is True
        seen = {path: await _vid(storage, path) for path in ("/f.txt", "/d", "/g", "/e")}
        assert (await storage.write(entries=[Entry(path=Path("/f.txt"), content="y")])).success is True
        stale = await storage.delete(path=Path("/f.txt"), if_vids={Path("/f.txt"): seen["/f.txt"]})
        assert [error.kind for error in stale.errors] == [ErrorKind.conflict]
        current = {Path("/f.txt"): await _vid(storage, "/f.txt")}
        assert (await storage.delete(path=Path("/f.txt"), if_vids=current)).success is True
        gone = await storage.delete(path=Path("/f.txt"), if_vids=current)
        assert [error.kind for error in gone.errors] == [ErrorKind.not_found]
        # A child made since moves the directory's vid; a grandchild does not.
        assert (await storage.write(entries=[Entry(path=Path("/d/b.txt"), content="x")])).success is True
        child = await storage.delete(path=Path("/d"), if_vids={Path("/d"): seen["/d"]})
        assert [error.kind for error in child.errors] == [ErrorKind.conflict]
        assert len((await storage.ls(path=Path("/d"))).observations) == 2
        assert (await storage.write(entries=[Entry(path=Path("/g/sub/b.txt"), content="x")])).success is True
        assert (await storage.delete(path=Path("/g"), if_vids={Path("/g"): seen["/g"]})).success is True
        # An empty directory with a child removed since is the directory changed, and only a plain delete lands.
        assert (await storage.delete(path=Path("/e/a.txt"))).success is True
        emptied = await storage.delete(path=Path("/e"), cascade=False, if_vids={Path("/e"): seen["/e"]})
        assert [error.kind for error in emptied.errors] == [ErrorKind.conflict]
        assert (await storage.delete(path=Path("/e"), cascade=False)).success is True

    async def test_a_batch_delete_with_one_stale_key_deletes_nothing(self, storage: VidBackend) -> None:
        paths = ["/a.txt", "/b.txt", "/d/c.txt"]
        assert (await storage.write(entries=[Entry(path=Path(p), content="x") for p in paths], parents=True)).success
        seen = {Path(p): await _vid(storage, p) for p in paths}
        assert (await storage.write(entries=[Entry(path=Path("/d/c.txt"), content="y")])).success is True
        rows = [Observation(path=Path(p)) for p in ("/a.txt", "/b.txt", "/d", "/d/c.txt")]
        # /d/c.txt is covered by /d's cascade, and its key is judged all the same.
        deleted = await storage.delete(observations=rows, if_vids=seen)
        assert [(error.kind, error.path) for error in deleted.errors] == [(ErrorKind.conflict, "/d/c.txt")]
        assert len((await storage.glob(patterns=("/**/*.txt",))).observations) == 3

    async def test_a_move_requires_its_source(self, storage: VidBackend) -> None:
        assert (await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])).success is True
        seen = await _vid(storage, "/a.txt")
        assert (await storage.write(entries=[Entry(path=Path("/a.txt"), content="y")])).success is True
        pair = [ResolvedPair(Path("/a.txt"), Path("/b.txt"))]
        stale = await storage.move(operations=pair, if_vids={Path("/a.txt"): seen})
        now = {"version": 2, "vid": await _vid(storage, "/a.txt")}
        assert [(error.kind, error.data) for error in stale.errors] == [(ErrorKind.conflict, now)]
        assert (await storage.stat(path=Path("/b.txt"))).success is False
        current = await _vid(storage, "/a.txt")
        moved = await storage.move(operations=pair, if_vids={Path("/a.txt"): current})
        assert moved.success is True, moved.errors
        assert moved.observations[0].vid not in (None, current)
        assert (await storage.write(entries=[Entry(path=Path("/c.txt"), content="z")])).success is True
        onto = [ResolvedPair(Path("/c.txt"), Path("/b.txt"))]
        for required in ({Path("/c.txt"): await _vid(storage, "/c.txt")}, None):
            occupied = await storage.move(operations=onto, if_vids=required)
            assert [error.kind for error in occupied.errors] == [ErrorKind.exists]

    async def test_a_restore_requires_its_tombstone(self, storage: VidBackend) -> None:
        """Mutation guarded: a restore that judges the vid the delete returned, not the tombstone's own."""
        assert (await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])).success is True
        deleted = await storage.delete(path=Path("/a.txt"))
        before = deleted.observations[0].vid
        assert before is not None
        tombstone = await _vid(storage, "/.vfs/trash/a.txt")
        refused = await storage.restore(path=Path("/a.txt"), if_vids={Path("/a.txt"): before})
        trashed = (await storage.stat(path=Path("/.vfs/trash/a.txt"))).one()
        assert [(error.kind, error.data) for error in refused.errors] == [
            (ErrorKind.conflict, {"version": trashed.version, "vid": trashed.vid})
        ]
        assert (await storage.stat(path=Path("/a.txt"))).success is False
        assert (await storage.restore(path=Path("/a.txt"), if_vids={Path("/a.txt"): tombstone})).success is True
        # Another caller restores, edits and deletes again: the first tombstone's vid is stale.
        assert (await storage.edit(path=Path("/a.txt"), edits=[EditOperation("x", "y")])).success is True
        assert (await storage.delete(path=Path("/a.txt"))).success is True
        again = await storage.restore(path=Path("/a.txt"), if_vids={Path("/a.txt"): tombstone})
        assert [error.kind for error in again.errors] == [ErrorKind.conflict]
        assert (await storage.restore(path=Path("/a.txt"))).success is True
        live = await storage.restore(path=Path("/a.txt"), if_vids={Path("/a.txt"): tombstone})
        assert [error.kind for error in live.errors] == [ErrorKind.exists]
        missing = await storage.restore(path=Path("/none.txt"), if_vids={Path("/none.txt"): tombstone})
        assert [error.kind for error in missing.errors] == [ErrorKind.not_found]

    async def test_a_batch_restore_with_one_stale_key_restores_nothing(self, storage: VidBackend) -> None:
        paths = ["/a.txt", "/b.txt"]
        assert (await storage.write(entries=[Entry(path=Path(p), content="x") for p in paths])).success is True
        for path in paths:
            assert (await storage.delete(path=Path(path))).success is True
        keys = {Path("/a.txt"): await _vid(storage, "/.vfs/trash/a.txt"), Path("/b.txt"): "0" * 20}
        rows = [Observation(path=Path(p)) for p in paths]
        restored = await storage.restore(observations=rows, if_vids=keys)
        assert [(error.kind, error.path) for error in restored.errors] == [(ErrorKind.conflict, "/b.txt")]
        assert (await storage.stat(path=Path("/a.txt"))).success is False

    async def test_the_mark_on_a_delete_or_a_move_of_what_is_there(self, storage: VidBackend) -> None:
        assert (await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])).success is True
        there = (await storage.stat(path=Path("/a.txt"))).one()
        named = {"version": there.version, "vid": there.vid}
        marked = {Path("/a.txt"): ABSENT}
        deleted = await storage.delete(path=Path("/a.txt"), if_vids=marked)
        moved = await storage.move(operations=[ResolvedPair(Path("/a.txt"), Path("/b.txt"))], if_vids=marked)
        assert [(e.kind, e.data) for e in (*deleted.errors, *moved.errors)] == [(ErrorKind.conflict, named)] * 2
        empty = {Path("/none.txt"): ABSENT}
        none_deleted = await storage.delete(path=Path("/none.txt"), if_vids=empty)
        none_moved = await storage.move(operations=[ResolvedPair(Path("/none.txt"), Path("/b.txt"))], if_vids=empty)
        assert [e.kind for e in (*none_deleted.errors, *none_moved.errors)] == [ErrorKind.not_found] * 2

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


async def _free_by_moving(storage: VidBackend, then: Callable[[], Awaitable[Result]]) -> None:
    """Move ``/x/p`` away, then let *then* put another file at the path."""
    assert (await storage.move(operations=[ResolvedPair(Path("/x/p"), Path("/w/p"))])).success is True
    assert (await then()).success is True


async def _replace_the_parent(storage: VidBackend) -> None:
    assert (await storage.move(operations=[ResolvedPair(Path("/x"), Path("/y"))])).success is True
    assert (await storage.write(entries=[Entry(path=Path("/x/p"), content="a new file")], parents=True)).success


_FREED: dict[str, Callable[[VidBackend], Awaitable[None]]] = {
    "a new file": lambda s: _free_by_moving(s, lambda: s.write(entries=[Entry(path=Path("/x/p"), content="new")])),
    "another file moved in": lambda s: _free_by_moving(
        s, lambda: s.move(operations=[ResolvedPair(Path("/x/q"), Path("/x/p"))])
    ),
    "a copy": lambda s: _free_by_moving(s, lambda: s.copy(operations=[ResolvedPair(Path("/w/r"), Path("/x/p"))])),
    "the parent replaced": _replace_the_parent,
}

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
