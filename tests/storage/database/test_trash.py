"""The trash arm of DatabaseStorage — a tombstone on the row.

Delete marks the row and its live descendants deleted where they sit;
restore clears a root's set; a write at a tombstoned file's path revives
it and keeps the replaced body as a version; sweep expires roots by
their time. The trash is a view: ``/.vfs/trash`` addresses the
tombstoned rows at their own paths, and nothing is written there.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from datetime import UTC, datetime
from math import ceil
from typing import TYPE_CHECKING, Any, NamedTuple, cast

import pytest
from sqlalchemy import delete, event, func, insert, select, text, update
from sqlalchemy.dialects import postgresql
from ulid import ULID

from tests.support.database_helpers import _ReturningSession, _url
from vfs.authority import Authority, Principal
from vfs.models import Edge, Entry, Observation
from vfs.models.rows import build_vfs_tables
from vfs.paths import Path
from vfs.results import ErrorKind
from vfs.storage import ResolvedPair
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database import backend as backend_module
from vfs.storage.backends.database import trash as trash_module
from vfs.storage.backends.database import versions as versions_module
from vfs.storage.backends.database.descent import DELETED_AT_KEY, TRASH_ROOT_KEY, TRASHED_KEY, subtree_filter
from vfs.storage.backends.database.dialects import (
    POSTGRESQL,
    StaleSnapshot,
    membership_budget,
    op_execution_options,
    rows_per_statement,
)
from vfs.storage.backends.database.engine import EngineHost
from vfs.storage.backends.database.scope import passes_gates
from vfs.storage.backends.database.seams import clear, installed
from vfs.storage.backends.database.serialized import Claim, claim_rows
from vfs.storage.backends.database.signals import collect_graph
from vfs.storage.backends.database.staging import WritePlan
from vfs.storage.backends.database.trash import _purge
from vfs.storage.backends.database.writes import _apply, _fetch_committed, _guarded_stmt
from vfs.storage.replace import EditOperation

if TYPE_CHECKING:
    from sqlalchemy.engine import RowMapping
    from sqlalchemy.ext.asyncio import AsyncSession

ANN = Authority.of(Principal("ann"))

# Statements the spy ignores: transaction control, never work.
_CONTROL = ("BEGIN", "COMMIT", "PRAGMA", "SAVEPOINT", "RELEASE", "ROLLBACK")


class Row(NamedTuple):
    """One stored entry row's identity, tombstone, root and version."""

    id: str
    deleted_at: datetime | None
    root: str | None
    version: int


async def _rows(storage: DatabaseStorage) -> dict[str, Row]:
    """Every stored entry row by path."""
    entry = storage._host.tables.entry
    async with storage._host.session_factory() as session:
        stmt = select(entry.c.path, entry.c.entry_id, entry.c.deleted_at, entry.c.trash_root_id, entry.c.version)
        rows = await session.execute(stmt)
        return {row.path: Row(row.entry_id, row.deleted_at, row.trash_root_id, row.version) for row in rows}


async def _count(storage: DatabaseStorage, table_name: str) -> int:
    table = getattr(storage._host.tables, table_name)
    async with storage._host.session_factory() as session:
        return (await session.execute(select(func.count()).select_from(table))).scalar_one()


def _hinted(result, kind: ErrorKind = ErrorKind.not_found) -> dict[str, object]:
    """The one error of a refused *result*, asserted to carry the trashed hint; its data."""
    assert result.success is False, result
    [error] = result.errors
    assert error.kind == kind
    data = error.data or {}
    assert data.get(TRASHED_KEY) is True and isinstance(data.get(DELETED_AT_KEY), str), data
    return data


async def _tree(storage: DatabaseStorage) -> None:
    await storage.mkdir(path=Path("/d/sub"), parents=True)
    files = [
        Entry(path=Path("/d/a.txt"), content="alpha needle"),
        Entry(path=Path("/d/sub/b.txt"), content="beta needle"),
        Entry(path=Path("/keep.txt"), content="kept"),
    ]
    assert (await storage.write(entries=files)).success is True


# ---------------------------------------------------------------------------
# Delete — the tombstone
# ---------------------------------------------------------------------------


class TestTombstone:
    """Delete marks the row where it sits; nothing moves, and the row reads as absent."""

    async def test_delete_marks_the_row_and_its_live_descendants_where_they_sit(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await _tree(storage)
        postings = await _count(storage, "segments")
        result = await storage.delete(path=Path("/d"))
        assert result.success is True
        [observed] = result.observations
        assert observed.status == "deleted" and observed.deleted_at is not None and "deleted_at" in observed.populated
        rows = await _rows(storage)
        root = rows["/d"].id
        for path in ("/d", "/d/a.txt", "/d/sub", "/d/sub/b.txt"):
            assert rows[path].deleted_at is not None and rows[path].root == root, path
        assert rows["/keep.txt"].deleted_at is None and rows["/keep.txt"].root is None
        # Nothing moved: the same paths are stored, and the postings never changed.
        assert set(rows) == {"/", "/d", "/d/a.txt", "/d/sub", "/d/sub/b.txt", "/keep.txt"}
        assert await _count(storage, "segments") == postings
        await storage.close()

    async def test_a_descendant_deleted_earlier_keeps_its_own_root_and_time(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await _tree(storage)
        assert (await storage.delete(path=Path("/d/a.txt"))).success is True
        first = await _rows(storage)
        assert (await storage.delete(path=Path("/d"))).success is True
        rows = await _rows(storage)
        assert rows["/d/a.txt"] == first["/d/a.txt"]
        assert rows["/d/sub/b.txt"].root == rows["/d"].id != rows["/d/a.txt"].root
        # Restore of the root clears its set alone; the earlier delete restores on its own.
        assert (await storage.restore(path=Path("/d"))).success is True
        rows = await _rows(storage)
        assert rows["/d"].deleted_at is None and rows["/d/sub/b.txt"].deleted_at is None
        assert rows["/d/a.txt"].deleted_at is not None
        assert (await storage.restore(path=Path("/d/a.txt"))).success is True
        assert (await storage.read(path=Path("/d/a.txt"))).observations[0].content == "alpha needle"
        await storage.close()

    async def test_a_tombstoned_row_reads_as_absent_with_the_trashed_hint(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await _tree(storage)
        assert (await storage.delete(path=Path("/d/a.txt"))).success is True
        target = Path("/d/a.txt")
        _hinted(await storage.read(path=target))
        _hinted(await storage.stat(path=target))
        _hinted(await storage.edit(path=target, edits=[EditOperation(old="alpha", new="omega")]))
        _hinted(await storage.mkdir(path=target))
        _hinted(await storage.move(operations=[ResolvedPair(src=target, dest=Path("/moved.txt"))]))
        _hinted(await storage.copy(operations=[ResolvedPair(src=target, dest=Path("/copied.txt"))]))
        edge = Edge(source=Path("/keep.txt"), target=target, edge_type="ref")
        _hinted(await storage.mkedge(edges=[edge]))
        _hinted(await storage.delete(path=target))
        # Every enumeration and search reads around it.
        assert [str(o.path) for o in (await storage.ls(path=Path("/d"))).observations] == ["/d/sub"]
        assert "/d/a.txt" not in {str(o.path) for o in (await storage.tree(path=Path("/"))).observations}
        assert [str(o.path) for o in (await storage.glob(patterns=("/d/*.txt",))).observations] == []
        found = await storage.grep(pattern="needle")
        assert [str(o.path) for o in found.observations] == ["/d/sub/b.txt"]
        found = await storage.glean(query="needle")
        assert [str(o.path) for o in found.observations] == ["/d/sub/b.txt"]
        # A row the caller sends with the batch form answers the same way.
        batch = await storage.read(observations=[Observation(path=target), Observation(path=Path("/keep.txt"))])
        assert [str(o.path) for o in batch.observations] == ["/keep.txt"]
        assert _hinted(batch)[TRASHED_KEY] is True
        await storage.close()

    async def test_a_tombstoned_ancestor_is_not_found_for_every_parent_gate(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await _tree(storage)
        assert (await storage.delete(path=Path("/d"))).success is True
        for parents in (False, True):
            refused = await storage.write(entries=[Entry(path=Path("/d/new.md"), content="x")], parents=parents)
            assert _hinted(refused) and refused.errors[0].path == "/d"
            assert (refused.errors[0].data or {}).get("vfs.target") == "/d/new.md"
            refused = await storage.mkdir(path=Path("/d/x"), parents=parents)
            assert _hinted(refused) and refused.errors[0].path == "/d"
        moved = await storage.move(operations=[ResolvedPair(src=Path("/keep.txt"), dest=Path("/d/k.txt"))])
        assert _hinted(moved) and moved.errors[0].path == "/d"
        copied = await storage.copy(operations=[ResolvedPair(src=Path("/keep.txt"), dest=Path("/d/sub/k.txt"))])
        assert _hinted(copied) and copied.errors[0].path == "/d"
        # Nothing was minted or revived under the tombstone.
        rows = await _rows(storage)
        assert "/d/new.md" not in rows and "/d/x" not in rows and rows["/d"].deleted_at is not None
        await storage.close()

    async def test_a_directory_at_a_tombstoned_path_is_absent_and_a_file_there_is_wrong_kind(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await _tree(storage)
        assert (await storage.delete(path=Path("/d"))).success is True
        _hinted(await storage.mkdir(path=Path("/d")))
        _hinted(await storage.write(entries=[Entry(path=Path("/d"), kind="directory")]))
        file_here = await storage.write(entries=[Entry(path=Path("/d"), content="a file now")])
        data = _hinted(file_here, ErrorKind.wrong_kind)
        assert data["kind"] == "directory"
        assert (await _rows(storage))["/d"].deleted_at is not None
        await storage.close()

    async def test_a_transfer_onto_a_tombstoned_occupant_is_exists_with_the_hint(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await _tree(storage)
        assert (await storage.delete(path=Path("/d/a.txt"))).success is True
        pair = ResolvedPair(src=Path("/keep.txt"), dest=Path("/d/a.txt"))
        for verb in (storage.move, storage.copy):
            refused = await verb(operations=[pair])
            data = _hinted(refused, ErrorKind.exists)
            assert refused.errors[0].path == "/d/a.txt" and data.get("vfs.target") == "/keep.txt"
        await storage.close()

    async def test_without_cascade_occupancy_is_judged_in_request_order(self, tmp_path) -> None:
        # A directory ahead of its last child is occupied; behind it, emptied by the batch.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/d"))
        await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="x")])
        reverse = [Observation(path=Path("/d")), Observation(path=Path("/d/f.txt"))]
        refused = await storage.delete(observations=reverse, cascade=False)
        assert refused.success is False
        assert [(e.kind, e.path) for e in refused.errors] == [(ErrorKind.not_empty, "/d")]
        assert all(r.deleted_at is None for r in (await _rows(storage)).values())
        assert (await storage.delete(observations=list(reversed(reverse)), cascade=False)).success is True
        assert set(await _rows(storage)) == {"/", "/d", "/d/f.txt"}
        assert all(r.deleted_at is not None for p, r in (await _rows(storage)).items() if p != "/")
        await storage.close()

    async def test_a_delete_in_a_batch_covers_its_descendants_and_classifies_the_rest(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await _tree(storage)
        assert (await storage.delete(path=Path("/d/a.txt"))).success is True
        targets = [Observation(path=Path("/d/sub/b.txt")), Observation(path=Path("/d")), Observation(path=Path("/d"))]
        result = await storage.delete(observations=targets)
        assert result.success is True
        assert [str(o.path) for o in result.observations] == ["/d/sub/b.txt", "/d", "/d"]
        assert all(o.status == "deleted" and o.deleted_at is not None for o in result.observations)
        # A covered target already tombstoned is a miss with the hint, and the batch never commits.
        rows = await _rows(storage)
        assert rows["/d"].deleted_at is not None
        assert (await storage.restore(path=Path("/d"))).success is True
        again = await storage.delete(observations=[Observation(path=Path("/d/a.txt")), Observation(path=Path("/d"))])
        assert _hinted(again) and again.errors[0].path == "/d/a.txt"
        assert (await _rows(storage))["/d"].deleted_at is None
        await storage.close()

    async def test_a_move_carries_a_tombstoned_descendant_and_a_copy_leaves_it(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await _tree(storage)
        assert (await storage.delete(path=Path("/d/a.txt"))).success is True
        assert (await storage.copy(operations=[ResolvedPair(src=Path("/d"), dest=Path("/c"))])).success is True
        assert (await storage.move(operations=[ResolvedPair(src=Path("/d"), dest=Path("/m"))])).success is True
        rows = await _rows(storage)
        assert rows["/m/a.txt"].deleted_at is not None and "/c/a.txt" not in rows and "/c/sub/b.txt" in rows
        assert (await storage.restore(path=Path("/m/a.txt"))).success is True
        assert (await storage.read(path=Path("/m/a.txt"))).observations[0].content == "alpha needle"
        await storage.close()


# ---------------------------------------------------------------------------
# Restore — the root's set
# ---------------------------------------------------------------------------


class TestRestore:
    async def test_restore_clears_the_roots_set_and_bumps_the_parent(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await _tree(storage)
        assert (await storage.delete(path=Path("/d"))).success is True
        before = (await storage.stat(path=Path("/"))).observations[0].version
        result = await storage.restore(path=Path("/d"))
        assert result.success is True
        assert str(result.observations[0].path) == "/d" and result.observations[0].status == "created"
        rows = await _rows(storage)
        assert all(rows[p].deleted_at is None and rows[p].root is None for p in rows)
        assert (await storage.stat(path=Path("/"))).observations[0].version == (before or 0) + 1
        assert (await storage.read(path=Path("/d/sub/b.txt"))).observations[0].content == "beta needle"
        await storage.close()

    async def test_a_target_repeated_in_the_batch_is_exists_the_second_time(self, tmp_path) -> None:
        # The first restore revives the set for the batch; the repeat finds the row live.
        storage = DatabaseStorage(url=_url(tmp_path))
        await _tree(storage)
        assert (await storage.delete(path=Path("/d"))).success is True
        twice = [Observation(path=Path("/d")), Observation(path=Path("/d"))]
        result = await storage.restore(observations=twice)
        assert result.success is False
        assert [(e.kind, e.path) for e in result.errors] == [(ErrorKind.exists, "/d")]
        assert (await _rows(storage))["/d"].deleted_at is not None  # a failed batch never commits
        await storage.close()

    async def test_only_a_root_restores(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await _tree(storage)
        assert (await storage.delete(path=Path("/d"))).success is True
        refused = await storage.restore(path=Path("/d/sub/b.txt"))
        data = _hinted(refused)
        assert refused.errors[0].path == "/d/sub/b.txt" and data[TRASH_ROOT_KEY] == (await _rows(storage))["/d"].id
        assert (await _rows(storage))["/d/sub/b.txt"].deleted_at is not None
        await storage.close()

    async def test_a_root_under_a_tombstoned_parent_is_not_found_at_the_parent(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await _tree(storage)
        assert (await storage.delete(path=Path("/d/a.txt"))).success is True
        assert (await storage.delete(path=Path("/d"))).success is True
        refused = await storage.restore(path=Path("/d/a.txt"))
        data = _hinted(refused)
        assert refused.errors[0].path == "/d" and data.get("vfs.target") == "/d/a.txt"
        assert (await storage.restore(path=Path("/d"))).success is True
        assert (await storage.restore(path=Path("/d/a.txt"))).success is True
        await storage.close()

    async def test_a_live_row_at_the_path_is_exists_and_a_missing_one_classifies(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await _tree(storage)
        live = await storage.restore(path=Path("/keep.txt"))
        assert live.success is False and live.errors[0].kind == ErrorKind.exists
        missing = await storage.restore(path=Path("/ghost/deep.txt"))
        assert missing.success is False
        assert missing.errors[0].kind == ErrorKind.not_found and missing.errors[0].path == "/ghost"
        await storage.close()

    async def test_restore_batch_error_fails_the_batch_whole(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await _tree(storage)
        assert (await storage.delete(path=Path("/d/a.txt"))).success is True
        targets = [Observation(path=Path("/d/a.txt")), Observation(path=Path("/ghost.txt"))]
        result = await storage.restore(observations=targets)
        assert result.success is False
        assert (await _rows(storage))["/d/a.txt"].deleted_at is not None
        await storage.close()


# ---------------------------------------------------------------------------
# The revive and the version mint
# ---------------------------------------------------------------------------


async def _versions(storage: DatabaseStorage, path: str) -> list[dict[str, Any]]:
    tables = storage._host.tables
    entry, versions, subjects = tables.entry, tables.versions, tables.version_subjects
    async with storage._host.session_factory() as session:
        entry_id = (await session.execute(select(entry.c.entry_id).where(entry.c.path == path))).scalar_one()
        rows = (
            await session.execute(
                select(versions).where(versions.c.entry_id == entry_id).order_by(versions.c.version_number)
            )
        ).mappings()
        out = [dict(row) for row in rows]
        for row in out:
            stmt = select(subjects.c.principal_id).where(
                subjects.c.entry_id == entry_id, subjects.c.version_number == row["version_number"]
            )
            row["subjects"] = sorted((await session.execute(stmt)).scalars())
    return out


class TestRevive:
    async def test_a_write_at_a_tombstoned_file_revives_it_and_keeps_the_replaced_body(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        assert (await storage.write(entries=[Entry(path=Path("/f.md"), content="one")])).success is True
        before = (await _rows(storage))["/f.md"]
        assert (await storage.delete(path=Path("/f.md"))).success is True
        parent = (await storage.stat(path=Path("/"))).observations[0].version
        # overwrite=False admits the revive: no live row occupies the path.
        result = await storage.write(entries=[Entry(path=Path("/f.md"), content="two")], overwrite=False, authority=ANN)
        assert result.success is True
        [observed] = result.observations
        assert observed.status == "updated"
        after = (await _rows(storage))["/f.md"]
        assert after.id == before.id and after.deleted_at is None and after.root is None
        assert (await storage.read(path=Path("/f.md"))).observations[0].content == "two"
        assert (await storage.stat(path=Path("/"))).observations[0].version == (parent or 0) + 1
        [version] = await _versions(storage, "/f.md")
        assert version["content"] == "one" and version["data"] is None and version["is_snapshot"] is True
        assert version["version_number"] == before.version + 1  # the delete's bump is the replaced version
        assert version["actor"] == "ann" and version["subjects"] == ["ann"] and version["lines"] == 1
        assert version["size_bytes"] == 3 and len(version["content_hash"]) == 64
        await storage.close()

    async def test_every_overwrite_keeps_the_body_it_replaced(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        for body in ("one", "two", "three"):
            assert (await storage.write(entries=[Entry(path=Path("/f.md"), content=body)])).success is True
        versions = await _versions(storage, "/f.md")
        assert [(v["version_number"], v["content"]) for v in versions] == [(1, "one"), (2, "two")]
        # A direct storage write naming no authority is trusted code: the
        # system actor, attributed as such, acting for no subject.
        assert all(v["actor"] == "system" and v["provenance"] == "system" and v["subjects"] == [] for v in versions)
        await storage.close()

    @pytest.mark.parametrize("body", ["same", b"\x00same"])
    async def test_an_identical_body_mints_nothing(self, tmp_path, body: str | bytes) -> None:
        # Nothing was lost: an agent rewriting an unchanged file leaves no
        # history behind — for a text body and for a bytes body alike.
        storage = DatabaseStorage(url=_url(tmp_path))

        def entry(value: str | bytes) -> Entry:
            if isinstance(value, bytes):
                return Entry(path=Path("/f"), data=value)
            return Entry(path=Path("/f"), content=value)

        column = "data" if isinstance(body, bytes) else "content"
        for _ in range(3):
            assert (await storage.write(entries=[entry(body)])).success is True
        assert await _versions(storage, "/f") == []
        changed = b"\x00changed" if isinstance(body, bytes) else "changed"
        assert (await storage.write(entries=[entry(changed)])).success is True
        [version] = await _versions(storage, "/f")
        encoded = body if isinstance(body, bytes) else body.encode()
        assert version[column] == body and version["content_hash"] == hashlib.sha256(encoded).hexdigest()
        await storage.close()

    async def test_a_bytes_overwrite_snapshots_the_bytes(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        assert (await storage.write(entries=[Entry(path=Path("/b.bin"), data=b"\x00old")])).success is True
        assert (await storage.write(entries=[Entry(path=Path("/b.bin"), data=b"\x00new")])).success is True
        [version] = await _versions(storage, "/b.bin")
        assert version["data"] == b"\x00old" and version["content"] is None and version["size_bytes"] == 4
        await storage.close()

    async def test_a_row_with_no_body_mints_nothing(self, tmp_path) -> None:
        # The body tables hold nothing for the row (an orphan the sweep's
        # fence has not reached): there is no pre-image to keep.
        storage = DatabaseStorage(url=_url(tmp_path))
        assert (await storage.write(entries=[Entry(path=Path("/f.md"), content="one")])).success is True
        content = storage._host.tables.content
        async with storage._host.engine.begin() as conn:
            await conn.execute(delete(content))
        assert (await storage.write(entries=[Entry(path=Path("/f.md"), content="two")])).success is True
        assert await _count(storage, "versions") == 0
        await storage.close()

    async def test_a_create_and_a_directory_mint_nothing(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await _tree(storage)
        assert (await storage.delete(path=Path("/d"))).success is True
        assert (await storage.restore(path=Path("/d"))).success is True
        assert await _count(storage, "versions") == 0
        await storage.close()

    async def test_a_bulk_overwrite_mints_in_bounded_statements(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        count = 2_000
        entries = [Entry(path=Path(f"/d/f{i:04}.txt"), content=f"body {i}") for i in range(count)]
        assert (await storage.write(entries=entries, parents=True)).success is True
        statements: list[str] = []

        def record(conn, cursor, statement, parameters, context, executemany) -> None:
            if "vfs_versions" in statement and statement.lstrip().upper().startswith("INSERT"):
                statements.append(statement)

        changed = [Entry(path=Path(f"/d/f{i:04}.txt"), content=f"body {i} changed") for i in range(count)]
        event.listen(storage._host.engine.sync_engine, "before_cursor_execute", record)
        try:
            assert (await storage.write(entries=changed)).success is True
        finally:
            event.remove(storage._host.engine.sync_engine, "before_cursor_execute", record)
        assert await _count(storage, "versions") == count
        host = storage._host
        sample: dict[str, object] = {
            "entry_id": "x" * 26,
            "version_number": 1,
            "is_snapshot": True,
            "content_hash": "h",
            "lines": 1,
            "size_bytes": 1,
            "actor": None,
            "provenance": None,
            "source_identity": None,
            "grant_revision": 0,
            "created_at": None,
            "content": "x",
            "version_diff": None,
            "data": None,
        }
        per_statement = rows_per_statement(host.parameter_budget, [sample])
        assert len(statements) <= ceil(count / per_statement) + ceil(count / host.membership_budget)
        await storage.close()

    async def test_the_mint_reads_pre_image_bodies_in_byte_bounded_pages(self, tmp_path, monkeypatch) -> None:
        # Six-byte bodies under a ten-byte page: no two fit together, so a
        # five-file overwrite reads its pre-images in five pages, not one.
        monkeypatch.setattr(versions_module, "BLOB_PAGE_BYTES", 10)
        storage = DatabaseStorage(url=_url(tmp_path))
        paths = [Path(f"/f{i}.txt") for i in range(5)]
        assert (await storage.write(entries=[Entry(path=p, content="body 0") for p in paths])).success is True
        reads: list[str] = []

        def record(conn, cursor, statement, parameters, context, executemany) -> None:
            upper = statement.lstrip().upper()
            if upper.startswith("SELECT") and "vfs_content" in statement and "vfs_blobs" in statement:
                reads.append(statement)

        event.listen(storage._host.engine.sync_engine, "before_cursor_execute", record)
        try:
            assert (await storage.write(entries=[Entry(path=p, content="body 1") for p in paths])).success is True
        finally:
            event.remove(storage._host.engine.sync_engine, "before_cursor_execute", record)
        assert len(reads) == len(paths)
        assert all(statement.count("?") == 1 for statement in reads)
        assert await _count(storage, "versions") == len(paths)
        await storage.close()

    async def test_the_revive_holds_with_asserts_stripped(self, tmp_path) -> None:
        # Asserts narrow, never validate: the whole arc runs the same with them stripped.
        script = """
import asyncio
from vfs.models import Entry
from vfs.paths import Path
from vfs.storage.backends.memory import InMemoryStorage

async def main():
    storage = InMemoryStorage()
    written = await storage.write(entries=[Entry(path=Path("/f.md"), content="one")])
    deleted = await storage.delete(path=Path("/f.md"))
    refused = await storage.mkdir(path=Path("/f.md"))
    revived = await storage.write(entries=[Entry(path=Path("/f.md"), content="two")])
    listing = await storage.ls(path=Path("/.vfs/trash"))
    status = revived.observations[0].status if revived.observations else revived.errors
    print(written.success, deleted.success, refused.success, revived.success, status, len(listing.observations))
    await storage.close()

asyncio.run(main())
"""
        done = subprocess.run([sys.executable, "-O", "-c", script], capture_output=True, text=True, check=False)
        assert done.returncode == 0, done.stderr
        assert done.stdout.strip() == "True True False True updated 0"


# ---------------------------------------------------------------------------
# The update guard — a stale snapshot never crosses the tombstone
# ---------------------------------------------------------------------------


async def _stale_plan(storage: DatabaseStorage, entry: Entry, *, overwrite: bool, status: str = "updated") -> WritePlan:
    """A write plan staged from the committed state at call time — the victim's snapshot."""
    host = storage._host
    async with host.session_factory() as session:
        committed = await _fetch_committed(session, host.tables, host.profile, host.membership_budget, {entry.path})
    plan = WritePlan(committed, authority=None, budget=host.profile.key_byte_budget, value_cap=host.value_cap)
    staged = plan.put_file(
        entry.path,
        kind=entry.kind,
        content=entry.content,
        content_hash=entry.content_hash,
        size_bytes=entry.size_bytes,
        lines=entry.lines,
        mime_type=entry.mime_type,
        overwrite=overwrite,
        parents=False,
        owner_id=entry.owner_id,
        data=entry.data,
        source=entry.source,
    )
    assert staged is not None and staged == status and not plan.errors, plan.errors
    plan.pending.append((entry.path, staged))
    return plan


async def _apply_stale(storage: DatabaseStorage, plan: WritePlan) -> bool:
    """Run *plan*'s statements against committed state; whether the guard refused (classified or redriven)."""
    host = storage._host
    async with host.session_factory() as session:
        try:
            errors = await _apply(
                session, host.tables, host.profile, host.parameter_budget, host.membership_budget, plan, overwrite=True
            )
        except StaleSnapshot:
            await session.rollback()
            return True
        if errors:
            await session.rollback()
            assert {e.kind for e in errors} <= {ErrorKind.conflict, ErrorKind.not_found}, errors
            return True
        await session.commit()
        return False


class TestStaleSnapshotGuards:
    """Writes are not serialized with topology, and a delete rewrites no path and bumps no descendant.

    The version-and-path guard alone would pass after a parent's delete,
    and the clobber would clear the child's tombstone. Each test stages
    the victim's plan from a live snapshot, lets the rival commit, then
    runs the victim's statements against committed state.
    """

    async def test_an_overwrite_whose_snapshot_predates_the_parents_delete_refuses(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path), trash_days=0)
        assert (await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="old")], parents=True)).success
        plan = await _stale_plan(storage, Entry(path=Path("/d/f.txt"), content="mine"), overwrite=True)
        assert (await storage.delete(path=Path("/d"))).success is True
        assert await _apply_stale(storage, plan) is True
        rows = await _rows(storage)
        assert rows["/d/f.txt"].deleted_at is not None and rows["/d/f.txt"].root == rows["/d"].id
        assert (await storage.stat(path=Path("/d/f.txt"))).success is False
        assert (await storage.read(path=Path("/.vfs/trash/d/f.txt"))).observations[0].content == "old"
        assert await _count(storage, "versions") == 0
        # Retention purges the root's whole set: no child survives its parent.
        assert (await storage.sweep(path=Path("/.vfs/trash"))).success is True
        assert set(await _rows(storage)) == {"/"}
        await storage.close()

    async def test_a_create_whose_snapshot_predates_the_parents_delete_refuses(self, tmp_path) -> None:
        # A create's own row is new, so only the parent bump can notice the
        # parent went: its guard requires the parent live, and tears the batch.
        storage = DatabaseStorage(url=_url(tmp_path), trash_days=0)
        assert (await storage.mkdir(path=Path("/d"))).success is True
        new = Entry(path=Path("/d/new.md"), content="mine")
        plan = await _stale_plan(storage, new, overwrite=False, status="created")
        assert (await storage.delete(path=Path("/d"))).success is True
        assert await _apply_stale(storage, plan) is True
        rows = await _rows(storage)
        assert "/d/new.md" not in rows and rows["/d"].deleted_at is not None
        assert (await storage.sweep(path=Path("/.vfs/trash"))).success is True
        assert set(await _rows(storage)) == {"/"}
        await storage.close()

    def test_only_the_live_side_carries_a_tombstone_term(self) -> None:
        # A revive is staged only at a set's root, and every clearing of a
        # root's tombstone bumps its version: the version term already refuses.
        entry = build_vfs_tables().entry
        live, revive = (str(_guarded_stmt(entry, revive=flag)).split(" WHERE ")[1] for flag in (False, True))
        assert "deleted_at IS NULL" in live and "deleted_at" not in revive
        assert "version = :b_base" in live and "version = :b_base" in revive

    async def test_a_revive_whose_snapshot_predates_a_rival_restore_refuses(self, tmp_path) -> None:
        # The restore bumped the row's version, so the revive's version term
        # misses; a fresh ladder judges the live row. No tombstone term is needed.
        storage = DatabaseStorage(url=_url(tmp_path))
        assert (await storage.write(entries=[Entry(path=Path("/f.md"), content="one")])).success is True
        assert (await storage.delete(path=Path("/f.md"))).success is True
        plan = await _stale_plan(storage, Entry(path=Path("/f.md"), content="two"), overwrite=False)
        assert plan.staged[Path("/f.md")].revive is True
        assert (await storage.restore(path=Path("/f.md"))).success is True
        assert await _apply_stale(storage, plan) is True
        assert (await storage.read(path=Path("/f.md"))).observations[0].content == "one"
        assert await _count(storage, "versions") == 0
        await storage.close()

    async def test_a_live_overwrite_and_a_revive_each_pass_their_own_guard(self, tmp_path) -> None:
        # The two sides run as two groups in one batch; neither term refuses the other's rows.
        storage = DatabaseStorage(url=_url(tmp_path))
        files = [Entry(path=Path("/live.md"), content="one"), Entry(path=Path("/gone.md"), content="one")]
        assert (await storage.write(entries=files)).success is True
        assert (await storage.delete(path=Path("/gone.md"))).success is True
        both = [Entry(path=Path("/live.md"), content="two"), Entry(path=Path("/gone.md"), content="two")]
        result = await storage.write(entries=both)
        assert result.success is True and [o.status for o in result.observations] == ["updated", "updated"]
        rows = await _rows(storage)
        assert rows["/gone.md"].deleted_at is None and rows["/live.md"].deleted_at is None
        assert [v["content"] for v in await _versions(storage, "/gone.md")] == ["one"]
        await storage.close()


# ---------------------------------------------------------------------------
# Sweep — retention by time
# ---------------------------------------------------------------------------


class TestSweep:
    async def test_sweep_purges_expired_roots_with_their_sets_and_family_rows(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path), trash_days=0)
        await _tree(storage)
        assert await storage.mkedge(edges=[Edge(source=Path("/keep.txt"), target=Path("/d/a.txt"), edge_type="ref")])
        assert (await storage.delete(path=Path("/d/a.txt"))).success is True
        assert (await storage.delete(path=Path("/d"))).success is True
        counts = {name: await _count(storage, name) for name in ("content", "segments", "edges")}
        result = await storage.sweep(path=Path("/.vfs/trash"))
        assert result.success is True
        assert [(str(o.path), o.status) for o in result.observations] == [("/d", "deleted"), ("/d/a.txt", "deleted")]
        rows = await _rows(storage)
        assert set(rows) == {"/", "/keep.txt"}
        assert await _count(storage, "content") == counts["content"] - 2
        assert await _count(storage, "segments") < counts["segments"]
        assert await _count(storage, "edges") == counts["edges"] - 5  # four fs rows and the authored edge
        # Idempotent and silent once nothing is tombstoned.
        again = await storage.sweep(path=Path("/.vfs/trash"))
        assert again.success is True and again.observations == [] and again.errors == []
        await storage.close()

    async def test_sweep_takes_the_version_rows_of_what_it_purges(self, tmp_path) -> None:
        # An attributed overwrite mints a version row and its subject row; both arms destroy them.
        storage = DatabaseStorage(url=_url(tmp_path), trash_days=0)
        await storage.mkdir(path=Path("/d"))
        for name in ("expired", "swept"):
            path = Path(f"/d/{name}.txt")
            assert (await storage.write(entries=[Entry(path=path, content="one")])).success is True
            assert (await storage.write(entries=[Entry(path=path, content="two")], authority=ANN)).success is True
        assert await _count(storage, "versions") == 2 and await _count(storage, "version_subjects") == 2
        assert (await storage.delete(path=Path("/d/expired.txt"))).success is True
        assert (await storage.sweep(path=Path("/.vfs/trash"))).success is True
        assert await _count(storage, "versions") == 1 and await _count(storage, "version_subjects") == 1
        assert (await storage.sweep(path=Path("/d/swept.txt"))).success is True
        assert await _count(storage, "versions") == 0 and await _count(storage, "version_subjects") == 0
        await storage.close()

    async def test_sweep_retains_a_young_root(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path), trash_days=90)
        await _tree(storage)
        assert (await storage.delete(path=Path("/d"))).success is True
        result = await storage.sweep(path=Path("/.vfs/trash"))
        assert result.success is True and result.observations == []
        assert (await _rows(storage))["/d/a.txt"].deleted_at is not None
        await storage.close()

    async def test_sweep_at_a_path_purges_live_and_tombstoned_rows_alike(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await _tree(storage)
        assert (await storage.delete(path=Path("/d/a.txt"))).success is True
        assert (await storage.sweep(path=Path("/d"))).success is True
        assert set(await _rows(storage)) == {"/", "/keep.txt"}
        assert (await storage.delete(path=Path("/keep.txt"))).success is True
        swept = await storage.sweep(path=Path("/keep.txt"))
        assert swept.success is True and swept.observations[0].status == "deleted"
        assert set(await _rows(storage)) == {"/"}
        await storage.close()

    async def test_negative_trash_days_refuses_at_construction(self, tmp_path) -> None:
        with pytest.raises(ValueError, match="trash_days"):
            DatabaseStorage(url=_url(tmp_path), trash_days=-1)

    async def test_sweep_purge_miss_classifies_through_the_descent_ladder(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])
        deep = await storage.sweep(path=Path("/ghost/deep"))
        assert deep.success is False
        assert deep.errors[0].kind == ErrorKind.not_found
        assert deep.errors[0].path == "/ghost"
        wrong = await storage.sweep(path=Path("/a.txt/child"))
        assert wrong.success is False
        assert wrong.errors[0].kind == ErrorKind.wrong_kind
        assert wrong.errors[0].path == "/a.txt"
        await storage.close()

    async def test_sweep_purge_bumps_the_parent(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/d"))
        await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="x")])
        before = (await storage.stat(path=Path("/d"))).observations[0].version
        assert before is not None
        assert (await storage.sweep(path=Path("/d/f.txt"))).success
        after = (await storage.stat(path=Path("/d"))).observations[0].version
        assert after == before + 1
        await storage.close()


# ---------------------------------------------------------------------------
# The trash view
# ---------------------------------------------------------------------------


class TestTrashView:
    async def test_ls_of_the_head_lists_tombstoned_roots_at_every_depth(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await _tree(storage)
        await storage.write(entries=[Entry(path=Path("/x/y.txt"), content="y")], parents=True)
        assert (await storage.delete(path=Path("/d"))).success is True
        assert (await storage.delete(path=Path("/x/y.txt"))).success is True
        roots = await storage.ls(path=Path("/.vfs/trash"))
        assert roots.success is True
        assert [str(o.path) for o in roots.observations] == ["/d", "/x/y.txt"]
        assert all(o.deleted_at is not None and "deleted_at" in o.populated for o in roots.observations)
        children = await storage.ls(path=Path("/.vfs/trash/d"))
        assert [str(o.path) for o in children.observations] == ["/d/a.txt", "/d/sub"]
        head = await storage.stat(path=Path("/.vfs/trash"))
        assert head.observations[0].kind == "directory"
        assert (await storage.read(path=Path("/.vfs/trash"))).errors[0].kind == ErrorKind.wrong_kind
        # The meta root lists the view beside its stored children.
        await storage.write(entries=[Entry(path=Path("/.vfs/docs/a.txt"), content="meta")], parents=True)
        listed = await storage.ls(path=Path("/.vfs"))
        assert [str(o.path) for o in listed.observations] == ["/.vfs/docs", "/.vfs/trash"]
        await storage.close()

    async def test_tree_glob_grep_and_glean_under_the_head_match_row_paths(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await _tree(storage)
        assert (await storage.reindex()).success is True
        assert (await storage.delete(path=Path("/d"))).success is True
        assert (await storage.reindex()).success is True
        walked = await storage.tree(path=Path("/.vfs/trash"))
        assert [str(o.path) for o in walked.observations] == ["/d", "/d/a.txt", "/d/sub", "/d/sub/b.txt"]
        shallow = await storage.tree(path=Path("/.vfs/trash/d"), max_depth=1)
        assert [str(o.path) for o in shallow.observations] == ["/d/a.txt", "/d/sub"]
        globbed = await storage.glob(patterns=("/.vfs/trash/**/*.txt",))
        assert [str(o.path) for o in globbed.observations] == ["/d/a.txt", "/d/sub/b.txt"]
        both = await storage.glob(patterns=("/**/*.txt", "/.vfs/trash/d/*.txt"))
        assert [str(o.path) for o in both.observations] == ["/d/a.txt", "/keep.txt"]
        grepped = await storage.grep(pattern="needle", globs=("/.vfs/trash/**",))
        assert [str(o.path) for o in grepped.observations] == ["/d/a.txt", "/d/sub/b.txt"]
        assert (await storage.grep(pattern="needle")).observations == []
        gleaned = await storage.glean(query="needle", globs=("/.vfs/trash/**",))
        assert {str(o.path) for o in gleaned.observations} == {"/d/a.txt", "/d/sub/b.txt"}
        assert (await storage.glean(query="needle")).observations == []
        await storage.close()

    async def test_point_reads_through_the_head_address_the_tombstoned_row(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await _tree(storage)
        assert (await storage.delete(path=Path("/d"))).success is True
        read = await storage.read(path=Path("/.vfs/trash/d/a.txt"))
        assert read.observations[0].content == "alpha needle" and read.observations[0].deleted_at is not None
        assert str(read.observations[0].path) == "/d/a.txt"
        stat = await storage.stat(path=Path("/.vfs/trash/d"))
        assert stat.observations[0].kind == "directory"
        # A live row has no trash-view address, and the view names no ghosts.
        live = await storage.stat(path=Path("/.vfs/trash/keep.txt"))
        assert live.errors[0].kind == ErrorKind.not_found and live.errors[0].path == "/.vfs/trash/keep.txt"
        ghost = await storage.ls(path=Path("/.vfs/trash/nope"))
        assert ghost.errors[0].kind == ErrorKind.not_found
        await storage.close()

    async def test_nothing_is_written_into_the_view(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await _tree(storage)
        assert (await storage.delete(path=Path("/d"))).success is True
        for target in (Path("/.vfs/trash"), Path("/.vfs/trash/x.txt"), Path("/.vfs/trash/d/a.txt")):
            written = await storage.write(entries=[Entry(path=target, content="x")], parents=True)
            assert written.errors[0].kind == ErrorKind.invalid and written.errors[0].path == target
            made = await storage.mkdir(path=target, parents=True)
            assert made.errors[0].kind == ErrorKind.invalid
            as_dir = await storage.write(entries=[Entry(path=target, kind="directory")], parents=True)
            assert as_dir.errors[0].kind == ErrorKind.invalid
        assert set(await _rows(storage)) == {"/", "/d", "/d/a.txt", "/d/sub", "/d/sub/b.txt", "/keep.txt"}
        await storage.close()

    def test_the_row_gate_admits_one_side_of_the_tombstone(self) -> None:
        # The SQL pushdown carries the term too; the gate is the law a row passes.
        live = cast("RowMapping", {"path": "/d/a.txt", "name": "a.txt", "ext": "txt", "deleted_at": None})
        gone = cast("RowMapping", {**live, "deleted_at": datetime(2026, 10, 11, tzinfo=UTC)})
        cases = ((live, False, True), (live, True, False), (gone, False, False), (gone, True, True))
        for mapping, trashed, admitted in cases:
            assert passes_gates(mapping, [], [], frozenset(), frozenset(), trashed=trashed) is admitted

    async def test_a_search_scope_cannot_mix_the_view_with_live_paths(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await _tree(storage)
        mixed = await storage.grep(pattern="needle", globs=("/.vfs/trash/**", "/d/**"))
        assert mixed.success is False and mixed.errors[0].kind == ErrorKind.invalid
        mixed = await storage.glean(query="needle", globs=("/.vfs/trash/**", "/d/**"))
        assert mixed.success is False and mixed.errors[0].kind == ErrorKind.invalid
        await storage.close()

    async def test_the_bare_head_is_no_search_pattern_on_any_verb(self, tmp_path) -> None:
        # The head strips to the bare root, which the live side already
        # refuses as a pattern; the view refuses it the same way on every
        # verb and every channel — a Result, never a raised PatternError.
        storage = DatabaseStorage(url=_url(tmp_path))
        await _tree(storage)
        assert (await storage.delete(path=Path("/d"))).success is True
        attempts = [
            storage.glob(patterns=("/.vfs/trash",)),
            storage.grep(pattern="needle", globs=("/.vfs/trash",)),
            storage.glean(query="needle", globs=("/.vfs/trash",)),
            storage.glob(patterns=("/**",), globs_not=("/.vfs/trash",)),
            storage.grep(pattern="needle", globs_not=("/.vfs/trash",)),
            storage.glean(query="needle", globs_not=("/.vfs/trash",)),
        ]
        for attempt in attempts:
            result = await attempt
            assert result.success is False and result.errors[0].kind == ErrorKind.invalid, result
            assert "/.vfs/trash" in (result.errors[0].message or "")
        live_root = await storage.grep(pattern="needle", globs=("/",))
        assert live_root.success is False and live_root.errors[0].kind == ErrorKind.invalid
        await storage.close()

    async def test_an_exclusion_excludes_on_the_side_it_addresses(self, tmp_path) -> None:
        # A head-addressed exclusion hides tombstoned rows alone; a bare
        # one hides live rows alone. Neither reaches across the tombstone.
        storage = DatabaseStorage(url=_url(tmp_path))
        await _tree(storage)
        await storage.write(entries=[Entry(path=Path("/notes/c.txt"), content="live needle")], parents=True)
        assert (await storage.reindex()).success is True
        assert (await storage.delete(path=Path("/d"))).success is True
        assert (await storage.reindex()).success is True
        live = await storage.glob(patterns=("/**/*.txt",), globs_not=("/.vfs/trash/d/**",))
        assert [str(o.path) for o in live.observations] == ["/keep.txt", "/notes/c.txt"]
        trashed = await storage.glob(patterns=("/.vfs/trash/**/*.txt",), globs_not=("/d/**",))
        assert [str(o.path) for o in trashed.observations] == ["/d/a.txt", "/d/sub/b.txt"]
        both = await storage.glob(patterns=("/**/*.txt", "/.vfs/trash/**/*.txt"), globs_not=("/.vfs/trash/d/sub/**",))
        assert [str(o.path) for o in both.observations] == ["/d/a.txt", "/keep.txt", "/notes/c.txt"]
        grepped = await storage.grep(pattern="needle", globs_not=("/.vfs/trash/notes/**",))
        assert [str(o.path) for o in grepped.observations] == ["/notes/c.txt"]
        grepped = await storage.grep(pattern="needle", globs=("/.vfs/trash/**",), globs_not=("/d/sub/**",))
        assert [str(o.path) for o in grepped.observations] == ["/d/a.txt", "/d/sub/b.txt"]
        grepped = await storage.grep(pattern="needle", globs=("/.vfs/trash/**",), globs_not=("/.vfs/trash/d/sub/**",))
        assert [str(o.path) for o in grepped.observations] == ["/d/a.txt"]
        gleaned = await storage.glean(query="needle", globs_not=("/.vfs/trash/notes/**",))
        assert {str(o.path) for o in gleaned.observations} == {"/notes/c.txt"}
        gleaned = await storage.glean(query="needle", globs=("/.vfs/trash/**",), globs_not=("/.vfs/trash/d/sub/**",))
        assert {str(o.path) for o in gleaned.observations} == {"/d/a.txt"}
        await storage.close()

    async def test_a_miss_inside_a_deleted_tree_names_the_deleted_boundary_for_every_verb(self, tmp_path) -> None:
        # Reads climb the same ladder writes do: the first failing boundary
        # is the tombstoned root, hinted, whoever asks and whatever the leaf.
        for authority in (None, ANN):
            home = tmp_path / ("anon" if authority is None else "ann")
            home.mkdir()
            storage = DatabaseStorage(url=_url(home))
            await _tree(storage)
            assert (await storage.delete(path=Path("/d"), authority=authority)).success is True
            for target in ("/d/a.txt", "/d/missing.txt", "/d/sub/b.txt"):
                for result in (
                    await storage.stat(path=Path(target), authority=authority),
                    await storage.read(path=Path(target), authority=authority),
                    await storage.ls(path=Path(target), authority=authority),
                    await storage.tree(path=Path(target), authority=authority),
                    await storage.edit(path=Path(target), edits=[EditOperation(old="a", new="b")], authority=authority),
                ):
                    assert _hinted(result).get("vfs.target") == target, (target, result)
                    assert result.errors[0].path == "/d", (target, result)
            await storage.close()

    async def test_the_view_tells_a_caller_without_rights_nothing_a_missing_row_would_not(self, tmp_path) -> None:
        # ann deletes a file bob may not see. Through the view bob's answer
        # for the deleted row is the answer for a row that never existed —
        # the first component he cannot see, never the synthesized head.
        storage = DatabaseStorage(url=_url(tmp_path))
        bob = Authority.of(Principal("bob"))
        assert (await storage.posture(path=Path("/"), posture="private", authority=None)).success is True
        assert (await storage.mkdir(path=Path("/ann"), authority=None)).success is True
        assert (await storage.grant(path=Path("/ann"), principal="ann", level="read_write", authority=None)).success
        assert (await storage.write(entries=[Entry(path=Path("/ann/secret.md"), content="s")], authority=ANN)).success
        assert (await storage.delete(path=Path("/ann/secret.md"), authority=ANN)).success is True
        answers = []
        for target in ("/.vfs/trash/ann/secret.md", "/.vfs/trash/ann/nope.md"):
            for result in (
                await storage.stat(path=Path(target), authority=bob),
                await storage.read(path=Path(target), authority=bob),
                await storage.ls(path=Path(target), authority=bob),
            ):
                [error] = result.errors
                # Beside the target, the refusal carries no fact at all — no hint, no time.
                assert set(error.data or {}) <= {"vfs.target"}, (target, error)
                answers.append((error.kind, error.path))
        assert set(answers) == {(ErrorKind.not_found, "/.vfs/trash/ann")}, answers
        # The owner sees her row at its own path and the same ladder for a ghost beside it.
        shown = await storage.stat(path=Path("/.vfs/trash/ann/secret.md"), authority=ANN)
        assert shown.success is True and str(shown.observations[0].path) == "/ann/secret.md"
        ghost = await storage.stat(path=Path("/.vfs/trash/ann/nope.md"), authority=ANN)
        assert ghost.errors[0].kind == ErrorKind.not_found and ghost.errors[0].path == "/.vfs/trash/ann"
        await storage.close()

    async def test_a_hidden_directory_on_the_road_through_the_view_is_a_step_not_an_answer(self, tmp_path) -> None:
        # bob holds rights on /d/sub alone; /d is deleted over his head. Through
        # the view /d is hidden to him, but it is the road to a row he may see,
        # so a ghost beneath /d/sub is named at the ghost, not at /d.
        storage = DatabaseStorage(url=_url(tmp_path))
        bob = Authority.of(Principal("bob"))
        assert (await storage.posture(path=Path("/"), posture="private", authority=None)).success is True
        assert (await storage.mkdir(path=Path("/d"), authority=None)).success is True
        assert (await storage.mkdir(path=Path("/d/sub"), authority=None)).success is True
        assert (await storage.grant(path=Path("/d/sub"), principal="bob", level="read_write", authority=None)).success
        assert (await storage.write(entries=[Entry(path=Path("/d/sub/f.md"), content="f")], authority=None)).success
        assert (await storage.delete(path=Path("/d"), authority=None)).success is True
        shown = await storage.stat(path=Path("/.vfs/trash/d/sub/f.md"), authority=bob)
        assert shown.success is True, shown.errors
        ghost = await storage.stat(path=Path("/.vfs/trash/d/sub/nope.md"), authority=bob)
        [error] = ghost.errors
        assert error.kind == ErrorKind.not_found and error.path == "/.vfs/trash/d/sub/nope.md", error
        await storage.close()


# ---------------------------------------------------------------------------
# Edges survive
# ---------------------------------------------------------------------------


class TestEdges:
    async def test_authored_edges_hide_with_a_tombstoned_endpoint_and_return_with_it(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await _tree(storage)
        edge = Edge(source=Path("/keep.txt"), target=Path("/d/a.txt"), edge_type="ref")
        assert (await storage.mkedge(edges=[edge])).success is True
        assert (await storage.delete(path=Path("/d/a.txt"))).success is True
        assert await _count(storage, "edges") == 6  # five fs rows and the authored edge, all kept

        async def graph_edges() -> int:
            async with storage._host.session_factory() as session:
                return len((await collect_graph(session, storage._host.tables)).sources)

        assert await graph_edges() == 0
        assert (await storage.restore(path=Path("/d/a.txt"))).success is True
        assert await graph_edges() == 1
        assert (await storage.delete(path=Path("/d/a.txt"))).success is True
        assert (await storage.write(entries=[Entry(path=Path("/d/a.txt"), content="revived")])).success is True
        assert await graph_edges() == 1
        # The reindex reclaims nothing: a tombstoned endpoint is an entry like any other.
        assert (await storage.delete(path=Path("/d/a.txt"))).success is True
        reindexed = await storage.reindex()
        assert reindexed.success is True and all("edge" not in e.message for e in reindexed.errors)
        assert await _count(storage, "edges") == 6
        await storage.close()


# ---------------------------------------------------------------------------
# Scale — statements counted, never timed
# ---------------------------------------------------------------------------


def _spy(storage: DatabaseStorage, statements: list[str]):
    def record(conn, cursor, statement, parameters, context, executemany) -> None:
        if not statement.lstrip().upper().startswith(_CONTROL):
            statements.append(statement)

    return record


SIZES = [pytest.param(1_000, id="1k"), pytest.param(2_000, id="2k", marks=pytest.mark.slow)]


class TestScale:
    @pytest.mark.parametrize("count", SIZES)
    async def test_delete_and_restore_issue_a_flat_number_of_statements(self, tmp_path, count: int) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        entries = [Entry(path=Path(f"/d/f{i:04}.txt"), content="x") for i in range(count)]
        assert (await storage.write(entries=entries, parents=True)).success is True
        postings = await _count(storage, "segments")
        statements: list[str] = []
        record = _spy(storage, statements)
        event.listen(storage._host.engine.sync_engine, "before_cursor_execute", record)
        try:
            assert (await storage.delete(path=Path("/d"))).success is True
            deleted = len(statements)
            statements.clear()
            assert (await storage.restore(path=Path("/d"))).success is True
            restored = len(statements)
        finally:
            event.remove(storage._host.engine.sync_engine, "before_cursor_execute", record)
        # Flat in the batch size and far under the move's 45 and 29; the postings never move.
        assert deleted <= 10 and restored <= 10, (deleted, restored)
        assert not any("vfs_segments" in s for s in statements)
        assert await _count(storage, "segments") == postings
        rows = await _rows(storage)
        assert len(rows) == count + 2 and all(r.deleted_at is None for r in rows.values())
        await storage.close()

    async def test_a_batch_of_targets_deletes_and_restores_in_a_flat_number_of_statements(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        engine = storage._host.engine.sync_engine

        async def statements_for(count: int) -> tuple[int, int]:
            paths = [Path(f"/d{count}/f{i:04}.txt") for i in range(count)]
            assert (await storage.write(entries=[Entry(path=p, content="x") for p in paths], parents=True)).success
            targets = [Observation(path=p) for p in paths]
            seen: list[str] = []
            record = _spy(storage, seen)
            event.listen(engine, "before_cursor_execute", record)
            try:
                assert (await storage.delete(observations=targets)).success is True
                deleted = len(seen)
                seen.clear()
                assert (await storage.restore(observations=targets)).success is True
                restored = len(seen)
            finally:
                event.remove(engine, "before_cursor_execute", record)
            return deleted, restored

        # One chunk either way on this engine: the counts are identical, not merely bounded.
        assert await statements_for(1_000) == await statements_for(10)
        await storage.close()

    async def test_a_retention_sweep_issues_a_flat_number_of_statements_in_roots(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path), trash_days=0)
        engine = storage._host.engine.sync_engine

        async def statements_for(count: int) -> int:
            paths = [Path(f"/d{count}/f{i:04}.txt") for i in range(count)]
            assert (await storage.write(entries=[Entry(path=p, content="x") for p in paths], parents=True)).success
            assert (await storage.delete(observations=[Observation(path=p) for p in paths])).success is True
            seen: list[str] = []
            record = _spy(storage, seen)
            event.listen(engine, "before_cursor_execute", record)
            try:
                result = await storage.sweep(path=Path("/.vfs/trash"))
            finally:
                event.remove(engine, "before_cursor_execute", record)
            assert result.success is True and len(result.observations) == count
            return len(seen)

        assert await statements_for(1_000) == await statements_for(10)
        await storage.close()

    async def test_the_covered_check_walks_each_target_once(self, tmp_path, monkeypatch) -> None:
        # One ancestor-chain walk per target: linear in the batch, never a rescan of the whole set.
        storage = DatabaseStorage(url=_url(tmp_path))
        count = 500
        paths = [Path(f"/d/f{i:04}.txt") for i in range(count)]
        assert (await storage.write(entries=[Entry(path=p, content="x") for p in paths], parents=True)).success
        walks: list[Path] = []
        chain = trash_module.ancestor_chain

        def counting(path: Path) -> list[Path]:
            walks.append(path)
            return chain(path)

        monkeypatch.setattr(trash_module, "ancestor_chain", counting)
        assert (await storage.delete(observations=[Observation(path=p) for p in paths])).success is True
        assert len(walks) == count
        await storage.close()

    @pytest.mark.slow
    async def test_a_read_of_tombstoned_paths_issues_the_same_statements_as_one_of_live(self, tmp_path) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        count = 10_000
        paths = [Path(f"/d/f{i:05}.txt") for i in range(count)]
        assert (await storage.write(entries=[Entry(path=p, content="x") for p in paths], parents=True)).success

        async def statements_for(targets: list[Path]) -> int:
            seen: list[str] = []
            record = _spy(storage, seen)
            event.listen(storage._host.engine.sync_engine, "before_cursor_execute", record)
            try:
                result = await storage.read(observations=[Observation(path=p) for p in targets])
            finally:
                event.remove(storage._host.engine.sync_engine, "before_cursor_execute", record)
            assert all(e.kind == ErrorKind.not_found for e in result.errors)
            return len(seen)

        live = await statements_for(paths)
        half = [Observation(path=p) for p in paths[::2]]
        assert (await storage.delete(observations=half)).success is True
        assert await statements_for(paths) == live
        await storage.close()

    async def test_the_live_visible_read_seeks_an_index(self, tmp_path) -> None:
        # The liveness term rides as a residual beside the seek: a partial
        # caller's subtree read still seeks the entries table by index and
        # never scans it. (SQLite cannot seek ``IS NOT NULL``, so the view's
        # own listing is a bounded walk there; the engine legs pin it under
        # db_test.)
        storage = DatabaseStorage(url=_url(tmp_path))
        await _tree(storage)
        crowd = [Entry(path=Path(f"/crowd/f{i:04}.txt"), content="x") for i in range(500)]
        assert (await storage.write(entries=crowd, parents=True)).success is True
        assert (await storage.posture(path=Path("/"), posture="shared", authority=Authority.system())).success is True
        assert (await storage.delete(path=Path("/d"))).success is True
        async with storage._host.engine.begin() as conn:
            await conn.execute(text("ANALYZE"))
        statements: list[tuple[str, Any]] = []

        def record(conn, cursor, statement, parameters, context, executemany) -> None:
            statements.append((statement, parameters))

        event.listen(storage._host.engine.sync_engine, "before_cursor_execute", record)
        try:
            walked = await storage.tree(path=Path("/"), authority=ANN)
        finally:
            event.remove(storage._host.engine.sync_engine, "before_cursor_execute", record)
        assert walked.success is True and "/d/a.txt" not in {str(o.path) for o in walked.observations}
        [(subtree, params)] = [(s, p) for s, p in statements if "deleted_at IS NULL" in s and "LIKE" in s]
        literal = subtree
        for value in params or ():
            literal = literal.replace("?", f"'{value}'", 1)
        async with storage._host.session_factory() as session:
            plan = (await session.execute(text("EXPLAIN QUERY PLAN " + literal))).all()
        details = [row[-1] for row in plan]
        assert any(d.startswith("SEARCH vfs_entries USING INDEX") for d in details), details
        assert not any(d.startswith("SCAN vfs_entries") for d in details), details
        # The view's listing carries the flipped term and the root test, and nothing else narrows it.
        listing: list[tuple[str, Any]] = []

        def record_listing(conn, cursor, statement, parameters, context, executemany) -> None:
            listing.append((statement, parameters))

        event.listen(storage._host.engine.sync_engine, "before_cursor_execute", record_listing)
        try:
            assert (await storage.ls(path=Path("/.vfs/trash"))).success is True
        finally:
            event.remove(storage._host.engine.sync_engine, "before_cursor_execute", record_listing)
        [roots] = [s for s, _ in listing if "trash_root_id" in s and s.startswith("SELECT")]
        assert "deleted_at IS NOT NULL" in roots and "trash_root_id = vfs_entries.entry_id" in roots
        await storage.close()


# ---------------------------------------------------------------------------
# Purge hardening and the options stamp
# ---------------------------------------------------------------------------


class TestClaimRows:
    """The guarded claim set's evidence ladder: VALUES join, aggregate rowcount, per-row floor, refusal.

    The default suite drives the aggregate arm on every delete and
    restore; the VALUES arm runs through the session double SQLite
    cannot execute, and the postgres and mssql legs prove it live.
    """

    @staticmethod
    def _claim(double: _ReturningSession, claims: list[Claim]):
        entry = build_vfs_tables().entry
        return claim_rows(
            cast("AsyncSession", double),
            entry,
            POSTGRESQL,
            32_000,
            900,
            claims,
            side=entry.c.deleted_at.is_(None),
            assign={"version": entry.c.version + 1},
            miss="stale",
        )

    async def test_the_values_arm_is_a_guarded_join_returning_the_ids_it_matched(self) -> None:
        claims = [Claim(str(ULID()), 3), Claim(str(ULID()), 1)]
        double = _ReturningSession([{"entry_id": claim.entry_id} for claim in claims])
        assert await self._claim(double, claims) is None
        [stmt] = double.statements  # both rows rode one chunk
        sql = str(stmt.compile(dialect=postgresql.dialect()))
        assert "VALUES" in sql and "RETURNING" in sql and "deleted_at IS NULL" in sql

    async def test_the_values_arm_raises_on_a_shortfall(self) -> None:
        claims = [Claim(str(ULID()), 3), Claim(str(ULID()), 1)]
        double = _ReturningSession([{"entry_id": claims[0].entry_id}])
        with pytest.raises(StaleSnapshot, match="stale"):
            await self._claim(double, claims)

    async def test_no_claims_issue_no_statement(self) -> None:
        double = _ReturningSession([])
        assert await self._claim(double, []) is None and double.statements == []

    async def test_the_per_row_floor_proves_each_claim(self, tmp_path, monkeypatch) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="a"), Entry(path=Path("/b.txt"), content="b")])
        host = storage._host
        # No sane aggregate: the ladder must land on per-row rowcounts.
        monkeypatch.setattr(host.engine.sync_engine.dialect, "supports_sane_multi_rowcount", False)
        both = [Observation(path=Path("/a.txt")), Observation(path=Path("/b.txt"))]
        assert (await storage.delete(observations=both)).success is True
        rows = await _rows(storage)
        assert rows["/a.txt"].deleted_at is not None and rows["/b.txt"].deleted_at is not None
        entry = host.tables.entry
        async with host.session_factory() as session:
            await session.connection(execution_options=op_execution_options(host.profile, writer=True))
            stale = [Claim(rows["/a.txt"].id, rows["/a.txt"].version + 7)]
            with pytest.raises(StaleSnapshot, match="moved"):
                await claim_rows(
                    session,
                    entry,
                    host.profile,
                    host.parameter_budget,
                    host.membership_budget,
                    stale,
                    side=entry.c.deleted_at.is_not(None),
                    assign={"version": entry.c.version + 1},
                    miss="moved",
                )
            await session.rollback()
        await storage.close()

    async def test_an_unverifiable_claim_classifies_instead_of_guessing(self, tmp_path, monkeypatch) -> None:
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="a")])
        dialect = storage._host.engine.sync_engine.dialect
        monkeypatch.setattr(dialect, "supports_sane_multi_rowcount", False)
        monkeypatch.setattr(dialect, "supports_sane_rowcount", False)
        result = await storage.delete(path=Path("/a.txt"))
        assert result.success is False and result.errors[0].kind == ErrorKind.unsupported
        assert (await _rows(storage))["/a.txt"].deleted_at is None
        await storage.close()


class TestPurgeHardening:
    """The purge re-collects until empty and never doubles a chunk's binds."""

    async def test_purge_recollects_rows_committed_after_the_first_collection(self, tmp_path) -> None:
        # The stale-id-list orphan window: a row appearing between the
        # collect and the deletes must be swept by the second pass.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.mkdir(path=Path("/d"))
        await storage.write(entries=[Entry(path=Path("/d/base.txt"), content="x")])
        host = storage._host
        tables = host.tables
        entry = tables.entry
        async with host.session_factory() as session:
            await session.connection(execution_options=op_execution_options(host.profile, writer=True))
            parent_id = (await session.execute(select(entry.c.entry_id).where(entry.c.path == "/d"))).scalar_one()

            async def straggler() -> None:
                clear("purge:post-collect")
                now = datetime.now(UTC)
                await session.execute(
                    insert(entry).values(
                        entry_id=str(ULID()),
                        parent_id=parent_id,
                        path="/d/straggler.txt",
                        name="straggler.txt",
                        kind="file",
                        version=1,
                        everyone_level=2,
                        created_at=now,
                        updated_at=now,
                    )
                )

            with installed("purge:post-collect", straggler):
                await _purge(session, tables, host.profile, 1_000, subtree_filter(entry, "/d", host.profile))
            subtree = (entry.c.path == "/d") | entry.c.path.like("/d/%")
            remaining = (await session.execute(select(entry.c.path).where(subtree))).all()
            assert remaining == []
            await session.rollback()
        await storage.close()

    async def test_a_root_revived_mid_purge_misses_the_tombstone_proof(self, tmp_path) -> None:
        # The lost-update window: a rival write revives the root between the
        # collect and the delete; the delete misses, the sweep redrives.
        storage = DatabaseStorage(url=_url(tmp_path), trash_days=0)
        await storage.write(entries=[Entry(path=Path("/d/f.txt"), content="x")], parents=True)
        assert (await storage.delete(path=Path("/d/f.txt"))).success is True
        host = storage._host
        tables = host.tables
        entry = tables.entry
        root_id = (await _rows(storage))["/d/f.txt"].id
        async with host.session_factory() as session:
            await session.connection(execution_options=op_execution_options(host.profile, writer=True))

            async def revive() -> None:
                clear("purge:post-collect")
                stmt = (
                    update(entry)
                    .where(entry.c.entry_id == root_id)
                    .values(deleted_at=None, trash_root_id=None, version=entry.c.version + 1)
                )
                await session.execute(stmt)

            scope = entry.c.trash_root_id == root_id
            with installed("purge:post-collect", revive), pytest.raises(StaleSnapshot):
                await _purge(session, tables, host.profile, 1_000, scope, proof=entry.c.deleted_at.is_not(None))
            await session.rollback()
        assert (await _rows(storage))["/d/f.txt"].deleted_at is not None
        assert await _count(storage, "content") == 1
        await storage.close()

    async def test_purge_statements_never_double_the_membership_chunk(self, tmp_path, monkeypatch) -> None:
        # Tiny budget → membership 16. Every purge DELETE must carry at
        # most one chunk of binds — the edges statement used to OR two
        # lists together, doubling past the tightest engine's cap.
        monkeypatch.setattr(EngineHost, "parameter_budget", property(lambda self: 48))
        storage = DatabaseStorage(url=_url(tmp_path))
        paths = [Path(f"/d/f{i:02}.txt") for i in range(40)]
        written = await storage.write(entries=[Entry(path=p, content="x") for p in paths], parents=True)
        assert written.success is True, written.errors
        tables = storage._host.tables
        entry = tables.entry
        async with storage._host.session_factory() as session:
            found = await session.execute(select(entry.c.entry_id).where(entry.c.path.like("/d/%")))
            ids = [row.entry_id for row in found]
            for eid in ids[:20]:
                await session.execute(
                    insert(tables.edges).values(
                        source_id=eid, target_id=str(ULID()), edge_type="ref", provenance="user"
                    )
                )
                await session.execute(
                    insert(tables.edges).values(
                        source_id=str(ULID()), target_id=eid, edge_type="ref", provenance="user"
                    )
                )
            await session.commit()
        counts: list[int] = []

        def record(conn, cursor, statement, parameters, context, executemany) -> None:
            if statement.lstrip().upper().startswith("DELETE"):
                counts.append(statement.count("?"))

        event.listen(storage._host.engine.sync_engine, "before_cursor_execute", record)
        try:
            assert (await storage.sweep(path=Path("/d"))).success
        finally:
            event.remove(storage._host.engine.sync_engine, "before_cursor_execute", record)
        budget = membership_budget(storage._host.profile, 48)
        assert counts and max(counts) <= budget
        # 41 rows at chunk size 16 → three chunks through all six deletes.
        assert len(counts) >= 18
        await storage.close()


class TestTransferObservations:
    async def test_chained_moves_fall_back_to_the_pair_time_observation(self, tmp_path) -> None:
        # Pair 2 moves pair 1's destination away: the re-read finds no row
        # at /b, so pair 1's observation falls back to its captured values.
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])
        result = await storage.move(
            operations=[
                ResolvedPair(src=Path("/a.txt"), dest=Path("/b.txt")),
                ResolvedPair(src=Path("/b.txt"), dest=Path("/c.txt")),
            ]
        )
        assert result.success is True
        first, second = result.observations
        assert str(first.path) == "/b.txt" and first.status == "created"
        assert str(second.path) == "/c.txt" and second.status == "created"
        assert (await storage.stat(path=Path("/b.txt"))).success is False
        assert (await storage.read(path=Path("/c.txt"))).observations[0].content == "x"
        await storage.close()


class TestTopologyOptionsStamping:
    """Every topology verb stamps the topology options, never the op pin."""

    async def test_topology_verbs_stamp_the_topology_execution_options(self, tmp_path, monkeypatch) -> None:
        calls: list[object] = []
        real = backend_module.topology_execution_options

        def spy(profile):
            calls.append(profile)
            return real(profile)

        monkeypatch.setattr(backend_module, "topology_execution_options", spy)
        storage = DatabaseStorage(url=_url(tmp_path))
        await storage.write(entries=[Entry(path=Path("/a.txt"), content="x")])
        assert (await storage.delete(path=Path("/a.txt"))).success
        await storage.write(entries=[Entry(path=Path("/b.txt"), content="x")])
        assert (await storage.move(operations=[ResolvedPair(src=Path("/b.txt"), dest=Path("/c.txt"))])).success
        assert (await storage.copy(operations=[ResolvedPair(src=Path("/c.txt"), dest=Path("/d.txt"))])).success
        assert calls == [storage._host.profile] * 3
        await storage.close()
