"""DatabaseFileSystem.compile_postings — the compile phase of the index pipeline.

Folds the staging delta-log into the per-gram posting list. Each case checks the
result against a brute-force gram ground truth computed directly from the live
committed chunk content, on in-memory SQLite. Covers: basic add, edit/re-chunk
(stale grams removed), delete (zero-doc rows deleted), idempotent re-run,
join-miss drop, the doc_count/byte_size invariants, and the §4.5 read-fold
(posting | staged adds - staged deletes) across pre/post/mixed compile states.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, insert, select

from tests.conftest import make_sqlite_db
from vfs.code_grams import unique_code_grams
from vfs.models import GRAM_ACTION_ADD
from vfs.postings import decode_postings

USER = "u1"


async def _make_fs():
    fs = await make_sqlite_db(auto_chunk=True, auto_index=True, user_scoped=True)
    await fs.setup()
    return fs


async def _committed_chunks(fs, session) -> list:
    stmt = select(fs._model).where(
        fs._model.kind == "chunk",
        fs._model.deleted_at.is_(None),
        fs._model.index_content.is_(True),
    )
    return list((await session.execute(stmt)).scalars().all())


async def _ground_truth(fs, session) -> dict[int, set[int]]:
    """Brute-force per-gram doc_id set from live committed chunk content."""
    truth: dict[int, set[int]] = {}
    for chunk in await _committed_chunks(fs, session):
        for gram_key in unique_code_grams(chunk.content or "", folded=True):
            truth.setdefault(gram_key, set()).add(chunk.id)
    return truth


async def _stored_postings(fs, session) -> dict[int, set[int]]:
    """Decode every posting row, asserting the per-row invariants."""
    posting = fs._posting_table
    rows = (
        await session.execute(
            select(posting.c.gram_key, posting.c.postings, posting.c.doc_count, posting.c.byte_size)
        )
    ).all()
    out: dict[int, set[int]] = {}
    for gram_key, blob, doc_count, byte_size in rows:
        decoded = decode_postings(bytes(blob), doc_count)
        assert doc_count == len(decoded)
        assert byte_size == len(bytes(blob))
        assert decoded, f"empty posting row kept for gram {gram_key}"
        out[gram_key] = set(decoded)
    return out


async def _read_fold(fs, session) -> dict[int, set[int]]:
    """§4.5: (posting row | staged adds - staged deletes), LAW per (gram, entry)."""
    posting = fs._posting_table
    out: dict[int, set[int]] = {
        gram_key: set(decode_postings(bytes(blob), doc_count))
        for gram_key, blob, doc_count in (
            await session.execute(
                select(posting.c.gram_key, posting.c.postings, posting.c.doc_count)
            )
        ).all()
    }
    gram = fs._gram_table
    entry = fs._model.__table__
    rows = (
        await session.execute(
            select(gram.c.gram_key, gram.c.entry_id, gram.c.action, gram.c.doc_id, entry.c.id)
            .select_from(gram.outerjoin(entry, entry.c.entry_id == gram.c.entry_id))
            .order_by(gram.c.seq)
        )
    ).all()
    folded: dict[tuple[int, str], tuple[int, int | None, int | None]] = {}
    for gram_key, entry_id, action, doc_id, resolved in rows:
        folded[(gram_key, entry_id)] = (action, doc_id, resolved)
    for (gram_key, _entry_id), (action, doc_id, resolved) in folded.items():
        if action == GRAM_ACTION_ADD:
            if resolved is not None:
                out.setdefault(gram_key, set()).add(resolved)
        elif doc_id is not None and gram_key in out:
            out[gram_key].discard(doc_id)
    return {k: v for k, v in out.items() if v}


async def _compile(fs) -> int:
    async with fs._session_factory() as session:
        folded = await fs.compile_postings(session)
        await session.commit()
    return folded


async def _staging_count(fs) -> int:
    async with fs._session_factory() as session:
        return (await session.execute(select(func.count()).select_from(fs._gram_table))).scalar()


# --- cases ------------------------------------------------------------------


async def test_compile_basic_add() -> None:
    fs = await _make_fs()
    await fs.write(path=f"/{USER}/a.py", content="def foo():\n    return 1\n", user_id=USER)
    await fs.write(path=f"/{USER}/b.py", content="def bar():\n    return 2\n", user_id=USER)
    assert await _compile(fs) > 0
    async with fs._session_factory() as session:
        assert await _stored_postings(fs, session) == await _ground_truth(fs, session)
    assert await _staging_count(fs) == 0


async def test_compile_edit_rechunk_removes_stale_grams() -> None:
    fs = await _make_fs()
    await fs.write(path=f"/{USER}/a.py", content="def alpha():\n    return 1\n", user_id=USER)
    await _compile(fs)
    async with fs._session_factory() as session:
        old = await _ground_truth(fs, session)

    await fs.write(path=f"/{USER}/a.py", content="zzz = 9\n", user_id=USER)
    await _compile(fs)
    async with fs._session_factory() as session:
        truth = await _ground_truth(fs, session)
        stored = await _stored_postings(fs, session)
    assert stored == truth
    gone = set(old) - set(truth)
    assert gone, "edit should have removed some grams"
    assert not (gone & set(stored)), "stale grams must have no posting row"


async def test_compile_delete_removes_zero_doc_rows() -> None:
    fs = await _make_fs()
    await fs.write(path=f"/{USER}/a.py", content="def foo():\n    return 1\n", user_id=USER)
    await fs.write(path=f"/{USER}/c.py", content="qqqzzz_unique_token = 1\n", user_id=USER)
    await _compile(fs)

    async with fs._session_factory() as session:
        truth_before = await _ground_truth(fs, session)
        c_chunks = [ch for ch in await _committed_chunks(fs, session) if "c.py" in ch.path]
        c_ids = {ch.id for ch in c_chunks}
        c_grams: set[int] = set()
        for ch in c_chunks:
            c_grams |= unique_code_grams(ch.content or "", folded=True)
        c_exclusive = {g for g in c_grams if truth_before.get(g, set()) <= c_ids}
    assert c_exclusive, "the unique token should yield c.py-exclusive grams"

    # fs.delete() is broken on main (unrelated), so drive de-indexing through the
    # same staging path the write pipeline uses for a removed file: stage all-delete
    # deltas (carrying doc_id) and soft-delete the chunk rows, then compile.
    async with fs._session_factory() as session:
        live_c = [ch for ch in await _committed_chunks(fs, session) if "c.py" in ch.path]
        await fs._stage_gram_deltas([], {}, live_c, session=session)
        for ch in live_c:
            ch.deleted_at = datetime.now(UTC)
            ch.index_content = False
            session.add(ch)
        await session.commit()
    await _compile(fs)

    async with fs._session_factory() as session:
        stored = await _stored_postings(fs, session)
        assert stored == await _ground_truth(fs, session)
        assert not (c_exclusive & set(stored)), "zero-doc grams must be deleted, not emptied"


async def test_compile_idempotent_rerun() -> None:
    fs = await _make_fs()
    await fs.write(path=f"/{USER}/a.py", content="def foo():\n    return 1\n", user_id=USER)
    assert await _compile(fs) > 0
    async with fs._session_factory() as session:
        before = await _stored_postings(fs, session)
    assert await _compile(fs) == 0, "empty-staging compile must fold nothing"
    async with fs._session_factory() as session:
        assert await _stored_postings(fs, session) == before


async def test_compile_join_miss_drops_add() -> None:
    fs = await _make_fs()
    await fs.write(path=f"/{USER}/a.py", content="def foo():\n    return 1\n", user_id=USER)
    await _compile(fs)

    gram = fs._gram_table
    posting = fs._posting_table
    bogus_gram = 0x515151  # 'QQQ' — an add for an entry that does not exist
    async with fs._session_factory() as session:
        before = (await session.execute(select(func.count()).select_from(posting))).scalar()
        await session.execute(
            insert(gram),
            [
                {
                    "gram_key": bogus_gram,
                    "entry_id": "ffffffff-ffff-ffff-ffff-ffffffffffff",
                    "doc_id": None,
                    "action": GRAM_ACTION_ADD,
                }
            ],
        )
        await session.commit()

    assert await _compile(fs) == 1  # the bogus row is folded (and dropped), not errored
    async with fs._session_factory() as session:
        after = (await session.execute(select(func.count()).select_from(posting))).scalar()
        bogus_row = (
            await session.execute(select(posting.c.gram_key).where(posting.c.gram_key == bogus_gram))
        ).first()
    assert bogus_row is None, "join-miss add must not create a posting row"
    assert after == before
    assert await _staging_count(fs) == 0


async def test_read_fold_matches_truth_pre_post_and_mixed() -> None:
    fs = await _make_fs()
    await fs.write(path=f"/{USER}/a.py", content="def foo():\n    return 1\n", user_id=USER)
    await fs.write(path=f"/{USER}/b.py", content="bar = foo\n", user_id=USER)

    # Pre-compile: posting list empty, staging holds the deltas. §4.5 fold == truth.
    async with fs._session_factory() as session:
        truth = await _ground_truth(fs, session)
        assert await _read_fold(fs, session) == truth

    # Post-compile: posting list alone == truth, staging cleared.
    await _compile(fs)
    async with fs._session_factory() as session:
        assert await _stored_postings(fs, session) == truth
        assert await _read_fold(fs, session) == truth
    assert await _staging_count(fs) == 0

    # Mixed: a new write stages more; the fold (posting | new staging) still == truth.
    await fs.write(path=f"/{USER}/c.py", content="baz = bar + foo\n", user_id=USER)
    async with fs._session_factory() as session:
        assert await _read_fold(fs, session) == await _ground_truth(fs, session)
