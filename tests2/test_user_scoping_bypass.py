"""Adversarial pytest coverage for user-scoped filesystem isolation."""

from __future__ import annotations

import pytest
from sqlmodel import select

from tests.conftest import _create_schema
from vfs.backends.database import DatabaseFileSystem
from vfs.models import VFSEntry
from vfs.paths import edge_out_path
from vfs.results import Candidate, VFSResult

ALICE = "alice"
BOB = "bob"
BOB_SECRET = "bob-only-secret"
ALICE_PAYLOAD = "alice-payload"


@pytest.fixture
async def scoped_db(engine):
    fs = DatabaseFileSystem(engine=engine, user_scoped=True)
    await _create_schema(engine, fs._model)
    return fs


async def seed(scoped_db: DatabaseFileSystem) -> DatabaseFileSystem:
    await scoped_db.write(path="/notes/private.txt", content="alice-private", user_id=ALICE)
    await scoped_db.write(path="/move-me.txt", content=ALICE_PAYLOAD, user_id=ALICE)
    await scoped_db.write(path="/src/entry.py", content="import helper", user_id=ALICE)
    await scoped_db.write(path="/src/helper.py", content="def alice_helper():\n    return 'alice'", user_id=ALICE)
    await scoped_db.mkedge("/src/entry.py", "/src/helper.py", "imports", user_id=ALICE)

    await scoped_db.write(path="/notes/private.txt", content="bob-private", user_id=BOB)
    await scoped_db.write(path="/top-secret.txt", content=BOB_SECRET, user_id=BOB)
    await scoped_db.write(path="/src/main.py", content="import auth", user_id=BOB)
    await scoped_db.write(path="/src/auth.py", content="def bob_auth():\n    return 'bob'", user_id=BOB)
    await scoped_db.mkedge("/src/main.py", "/src/auth.py", "imports", user_id=BOB)
    return scoped_db


@pytest.fixture
async def seeded_scoped_db(scoped_db):
    return await seed(scoped_db)


def candidate_paths(result: VFSResult) -> set[str]:
    return {entry.path for entry in result.candidates}


async def raw_object(fs: DatabaseFileSystem, path: str) -> VFSEntry | None:
    assert fs._session_factory is not None
    async with fs._session_factory() as session:
        stmt = select(fs._model).where(fs._model.path == path)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


async def read_content(fs: DatabaseFileSystem, path: str, *, user_id: str) -> str | None:
    result = await fs.read(path=path, user_id=user_id)
    return result.file.content if result.file is not None else None


async def test_read_parent_traversal_cannot_escape(seeded_scoped_db):
    result = await seeded_scoped_db.read(path="/../bob/top-secret.txt", user_id=ALICE)

    assert result.file is None
    assert all(entry.content != BOB_SECRET for entry in result.candidates)


async def test_candidate_smuggling_cannot_read_other_user(seeded_scoped_db):
    smuggled = VFSResult(function="read", candidates=[Candidate(path="/bob/top-secret.txt")])

    result = await seeded_scoped_db.read(candidates=smuggled, user_id=ALICE)

    assert result.file is None
    assert all(entry.content != BOB_SECRET for entry in result.candidates)


async def test_copy_from_other_user_prefixed_source_fails_closed(seeded_scoped_db):
    result = await seeded_scoped_db.copy(src="/bob/top-secret.txt", dest="/loot.txt", user_id=ALICE)

    assert not result.success
    assert await read_content(seeded_scoped_db, "/loot.txt", user_id=ALICE) is None
    assert await read_content(seeded_scoped_db, "/top-secret.txt", user_id=BOB) == BOB_SECRET


async def test_move_into_other_user_prefix_stays_local(seeded_scoped_db):
    result = await seeded_scoped_db.move(src="/move-me.txt", dest="/bob/top-secret.txt", user_id=ALICE)

    assert result.success
    assert await read_content(seeded_scoped_db, "/bob/top-secret.txt", user_id=ALICE) == ALICE_PAYLOAD
    assert await read_content(seeded_scoped_db, "/top-secret.txt", user_id=BOB) == BOB_SECRET

    moved = await raw_object(seeded_scoped_db, "/alice/bob/top-secret.txt")
    assert moved is not None
    assert moved.owner_id == ALICE


async def test_delete_other_user_prefixed_path_cannot_touch_other_user_row(seeded_scoped_db):
    result = await seeded_scoped_db.delete(path="/bob/top-secret.txt", user_id=ALICE)

    assert not result.success
    assert await read_content(seeded_scoped_db, "/top-secret.txt", user_id=BOB) == BOB_SECRET


async def test_batch_write_cannot_override_owner_or_prefix(seeded_scoped_db):
    smuggled = VFSEntry(path="/bob/stolen.txt", content="smuggled", owner_id=BOB)

    result = await seeded_scoped_db.write(entries=[smuggled], user_id=ALICE)

    assert result.success

    obj = await raw_object(seeded_scoped_db, "/alice/bob/stolen.txt")
    assert obj is not None
    assert obj.owner_id == ALICE
    assert await read_content(seeded_scoped_db, "/stolen.txt", user_id=BOB) is None


async def test_mkedge_target_smuggling_is_rehomed(seeded_scoped_db):
    result = await seeded_scoped_db.mkedge("/src/entry.py", "/bob/top-secret.txt", "imports", user_id=ALICE)

    assert result.success

    stored_path = edge_out_path(
        "/alice/src/entry.py",
        "/alice/bob/top-secret.txt",
        "imports",
    )
    conn = await raw_object(seeded_scoped_db, stored_path)
    assert conn is not None
    assert conn.source_path == "/alice/src/entry.py"
    assert conn.target_path == "/alice/bob/top-secret.txt"
    assert conn.owner_id == ALICE


async def test_glob_parent_traversal_does_not_discover_other_user_data(seeded_scoped_db):
    result = await seeded_scoped_db.glob(pattern="/../bob/*.txt", user_id=ALICE)

    assert "/top-secret.txt" not in candidate_paths(result)


async def test_grep_does_not_leak_other_user_contents(seeded_scoped_db):
    result = await seeded_scoped_db.grep(pattern=BOB_SECRET, user_id=ALICE)

    assert not result.candidates


async def test_graph_parent_traversal_does_not_discover_other_user_nodes(seeded_scoped_db):
    result = await seeded_scoped_db.predecessors(path="/../bob/src/auth.py", user_id=ALICE)

    assert not result.candidates


async def test_pagerank_remains_scoped_with_other_user_graph_present(seeded_scoped_db):
    result = await seeded_scoped_db.pagerank(user_id=ALICE)

    assert not candidate_paths(result) & {"/src/main.py", "/src/auth.py"}
