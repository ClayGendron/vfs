"""The worlds and rivals the commit-point rights rows share.

A mutation is judged at its gate and again where it finds the rows it
acts on, and its caller's rights are read once more just before it
commits. The rows that pin that stage a rival's effect on the attempt's
own session at a named seam — the SQLite and in-memory idiom, since a
genuine second writer cannot commit inside an attempt there — or commit
a genuine rival on a server engine. Five small worlds hold the shapes:

- ``drop_world``: posture ``none`` at ``/`` and ``add`` at ``/drop``;
  ``eve`` owns the four rows under ``/drop/e`` and ``bob`` owns
  ``/drop/b.txt``.
- ``copy_world``: posture ``read`` at ``/s`` and ``none`` at ``/s/priv``,
  a directory ``eve`` owns; ``alice`` may add under it and ``eve`` under
  ``/t``.
- ``dest_world``: posture ``read_write`` at ``/src``, ``add`` at ``/dst``
  and ``none`` at ``/dst/c/sub``, so a direct write of
  ``/dst/c/sub/f.txt`` is refused at ``/dst/c/sub``.
- ``grant_world``: ``bob`` holds ``read_write`` on ``/g`` by the mount's
  latest admin write, over two files, an edge between them and a
  deleted file.
- ``label_world``: ``eve`` reaches ``/p`` by the posture ``read_write``.

``attempts`` records the session of every gate call, so its length is
the attempt count and its last item the live attempt's session; ``land``,
``replace`` and ``stamp`` model a rival's committed create, its sweep
and write, and its admin write, each run on a session it is handed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, func, insert, select
from ulid import ULID

from vfs.authority import Authority, Principal
from vfs.models import Edge, Entry, measure_text
from vfs.models.edge import RESERVED_EDGE_TYPE
from vfs.paths import Path
from vfs.storage.backends.database import seams
from vfs.storage.backends.database.edges import insert_fs_rows
from vfs.storage.backends.database.revision import bump_revision, stamp_principals
from vfs.storage.backends.database.segments import insert_postings
from vfs.storage.grants import LEVEL_RANK

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import pytest
    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.models.rows import VFSTables
    from vfs.storage.backends.database import DatabaseStorage
    from vfs.storage.grants import GrantLevel

SYSTEM = Authority.system()
ALICE = Authority.of(Principal("alice"))
BOB = Authority.of(Principal("bob"))
CAROL = Authority.of(Principal("carol"))
EVE = Authority.of(Principal("eve"))
ANONYMOUS = Authority.anonymous()

LANDED_BODY = "landed text\n"
"""The body every landed row carries, so an edit's old text matches it as it matches the world's own rows."""


# ---------------------------------------------------------------------------
# Worlds
# ---------------------------------------------------------------------------


async def drop_world(storage: DatabaseStorage) -> None:
    """``add`` at ``/drop`` under ``none``: eve's tree at ``/drop/e`` and bob's file at ``/drop/b.txt``."""
    assert (await storage.mkdir(path=Path("/drop"), authority=SYSTEM)).success is True
    await _postures(storage, [("/", "none"), ("/drop", "add")])
    eves = [Entry(path=Path("/drop/e/f.txt"), content="eve text\n"), Entry(path=Path("/drop/e/sub/g.txt"), content="g")]
    assert (await storage.write(entries=eves, parents=True, authority=EVE)).success is True
    bobs = [Entry(path=Path("/drop/b.txt"), content="bob text\n")]
    assert (await storage.write(entries=bobs, authority=BOB)).success is True


async def copy_world(storage: DatabaseStorage) -> None:
    """``read`` at ``/s``, ``none`` at ``/s/priv`` (eve's directory), alice adding there and eve under ``/t``."""
    entries = [Entry(path=Path("/s/a.txt"), content="a"), Entry(path=Path("/t"), kind="directory")]
    assert (await storage.write(entries=entries, parents=True, authority=SYSTEM)).success is True
    # Made by eve while the mount is open: a directory's declared owner is not stored.
    await _postures(storage, [("/", "read_write")])
    assert (await storage.mkdir(path=Path("/s/priv"), authority=EVE)).success is True
    await _postures(storage, [("/", "none"), ("/s", "read"), ("/s/priv", "none")])
    await _grants(storage, [("/s/priv", "alice", "add"), ("/t", "eve", "add")])


async def dest_world(storage: DatabaseStorage) -> None:
    """``read_write`` at ``/src``, ``add`` at ``/dst`` and ``none`` at ``/dst/c/sub``."""
    entries = [Entry(path=Path("/src/sub/f.txt"), content="f"), Entry(path=Path("/dst"), kind="directory")]
    assert (await storage.write(entries=entries, parents=True, authority=SYSTEM)).success is True
    await _postures(storage, [("/", "none"), ("/src", "read_write"), ("/dst", "add"), ("/dst/c/sub", "none")])


async def grant_world(storage: DatabaseStorage) -> None:
    """bob's ``read_write`` on ``/g``, granted last, over two files, an edge and the deleted ``/g/old.txt``."""
    entries = [
        Entry(path=Path("/g/d/f.txt"), content="alpha\n"),
        Entry(path=Path("/g/d/sub/g.txt"), content="gamma\n"),
        Entry(path=Path("/g/old.txt"), content="old\n"),
    ]
    assert (await storage.write(entries=entries, parents=True, authority=SYSTEM)).success is True
    edge = Edge(source=Path("/g/d/sub/g.txt"), target=Path("/g/d/f.txt"), edge_type="ref")
    assert (await storage.mkedge(edges=[edge], authority=SYSTEM)).success is True
    assert (await storage.delete(path=Path("/g/old.txt"), authority=SYSTEM)).success is True
    await _postures(storage, [("/", "none")])
    await _grants(storage, [("/g", "bob", "read_write")])


async def label_world(storage: DatabaseStorage) -> None:
    """``read_write`` by the posture at ``/p`` under ``none``, over ``/p/d``'s two files."""
    entries = [Entry(path=Path("/p/d/f.txt"), content="f"), Entry(path=Path("/p/d/sub/g.txt"), content="g")]
    assert (await storage.write(entries=entries, parents=True, authority=SYSTEM)).success is True
    await _postures(storage, [("/", "none"), ("/p", "read_write")])


# ---------------------------------------------------------------------------
# Attempts and rivals
# ---------------------------------------------------------------------------


def attempts(monkeypatch: pytest.MonkeyPatch, storage: DatabaseStorage) -> list[Any]:
    """The session of every gate call *storage* makes from now on: one per attempt of a gated verb."""
    sessions: list[Any] = []
    gate = storage._gate

    async def recorded(session: AsyncSession, *args: Any, **kwargs: Any) -> Any:
        sessions.append(session)
        return await gate(session, *args, **kwargs)

    monkeypatch.setattr(storage, "_gate", recorded)
    return sessions


async def land(
    session: AsyncSession,
    tables: VFSTables,
    path: str,
    owner: str,
    level: GrantLevel,
    *,
    deleted: bool = False,
    body: str = LANDED_BODY,
) -> str:
    """Insert one file row at *path* under its parent, owned by *owner* and labelled *level*: a rival's create.

    The row carries a measured body, so an edit can match it and a body
    it loses is kept as a version; it bumps no parent, as a rival's
    insert seen before its own bump would not. Tombstoned when *deleted*.
    """
    entry = tables.entry
    target = Path(path)
    parent = (await session.execute(select(entry.c.entry_id).where(entry.c.path == target.parent_dir))).scalar_one()
    entry_id, now = str(ULID()), datetime.now(UTC)
    metrics = measure_text(body)
    values: dict[str, Any] = {
        "entry_id": entry_id,
        "parent_id": parent,
        "path": path,
        "name": target.name,
        "kind": "file",
        "version": 1,
        "content_hash": metrics.content_hash,
        "ext": target.ext,
        "size_bytes": metrics.size_bytes,
        "lines": metrics.lines,
        "owner_id": owner,
        "everyone_level": LEVEL_RANK[level],
        "created_at": now,
        "updated_at": now,
        "deleted_at": now if deleted else None,
        "trash_root_id": entry_id if deleted else None,
    }
    await session.execute(insert(entry).values(**values))
    await session.execute(insert(tables.content).values(entry_id=entry_id, created_at=now, content=body))
    # The side rows a create writes beside a fresh row: its fs mirror row and its segment postings.
    await insert_fs_rows(session, tables.edges, [(parent, entry_id)])
    await insert_postings(session, tables.segments, [(entry_id, path)])
    return entry_id


async def replace(
    session: AsyncSession, tables: VFSTables, path: str, owner: str, level: GrantLevel, *, body: str = LANDED_BODY
) -> str:
    """Remove the row at *path* and land another there: a rival's committed sweep and write."""
    entry = tables.entry
    gone = (await session.execute(select(entry.c.entry_id).where(entry.c.path == path))).scalar_one()
    edges, segments = tables.edges, tables.segments
    await session.execute(delete(entry).where(entry.c.entry_id == gone))
    await session.execute(delete(tables.content).where(tables.content.c.entry_id == gone))
    await session.execute(delete(segments).where(segments.c.entry_id == gone))
    await session.execute(delete(edges).where((edges.c.source_id == gone) | (edges.c.target_id == gone)))
    return await land(session, tables, path, owner, level, body=body)


async def stamp(session: AsyncSession, tables: VFSTables, principal: str) -> None:
    """Bump the mount revision and stamp *principal* with it: a committed admin write naming *principal*."""
    revision = await bump_revision(session, tables)
    await stamp_principals(session, tables, [principal], revision)


def clearing(name: str, act: Callable[[], Awaitable[object]]) -> Callable[[], Awaitable[None]]:
    """A seam handler that uninstalls itself from *name*, then runs *act*: the rival fires on the first attempt only."""

    async def handler() -> None:
        seams.clear(name)
        await act()

    return handler


# ---------------------------------------------------------------------------
# Reads as the system actor
# ---------------------------------------------------------------------------


async def row_at(storage: DatabaseStorage, path: str) -> dict[str, Any] | None:
    """The entry row at *path*, live or tombstoned, with its text body, read on a session of its own."""
    tables = storage._host.tables
    entry, content = tables.entry, tables.content
    stmt = select(entry, content.c.content).select_from(tables.content_joined()).where(entry.c.path == path)
    async with storage._host.session_factory() as session:
        found = (await session.execute(stmt)).mappings().one_or_none()
    return None if found is None else dict(found)


async def paths_under(storage: DatabaseStorage, root: str) -> set[str]:
    """Every row's path at *root* or beneath it, live or tombstoned."""
    entry = storage._host.tables.entry
    stmt = select(entry.c.path).where((entry.c.path == root) | entry.c.path.startswith(root + "/"))
    async with storage._host.session_factory() as session:
        return set((await session.execute(stmt)).scalars())


async def version_count(storage: DatabaseStorage, entry_id: str) -> int:
    """How many version rows name *entry_id*."""
    versions = storage._host.tables.versions
    stmt = select(func.count()).select_from(versions).where(versions.c.entry_id == entry_id)
    async with storage._host.session_factory() as session:
        return int((await session.execute(stmt)).scalar_one())


async def authored_edges(storage: DatabaseStorage) -> list[tuple[str, str]]:
    """Every authored edge as ``(source_id, target_id)``; the fs mirror rows are left out."""
    edges = storage._host.tables.edges
    stmt = select(edges.c.source_id, edges.c.target_id).where(edges.c.edge_type != RESERVED_EDGE_TYPE)
    async with storage._host.session_factory() as session:
        return [(row.source_id, row.target_id) for row in await session.execute(stmt)]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _postures(storage: DatabaseStorage, rows: list[tuple[str, GrantLevel]]) -> None:
    for path, level in rows:
        assert (await storage.posture(path=Path(path), posture=level, authority=SYSTEM)).success is True


async def _grants(storage: DatabaseStorage, rows: list[tuple[str, str, GrantLevel]]) -> None:
    for path, principal, level in rows:
        granted = await storage.grant(path=Path(path), principal=principal, level=level, authority=SYSTEM)
        assert granted.success is True
