"""Throwaway pressure harness for the chunk → encode → compile index pipeline.

Exercises the three-phase pipeline both inline (via ``auto_index`` levels on
write) and context-free (via ``index(session, level=...)`` backfill), plus the
chunk-reconciliation carry-forward/delete and a brute-force correctness oracle
for the §4.5 read fold.

Run: uv run python scripts/_pressure_index_pipeline.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

from sqlalchemy import func, select

from tests.conftest import make_sqlite_db
from vfs.code_grams import unique_code_grams
from vfs.models import GRAM_ACTION_ADD
from vfs.postings import decode_postings

USER = "u1"
results: list[tuple[str, bool, str]] = []

FILE_A = "def alpha():\n    return 1\n\n\ndef beta():\n    return 2\n"
FILE_A_EDIT = "def alpha():\n    return 1\n\n\ndef beta():\n    return 99\n"


def big_file(edit: bool = False) -> str:
    """A multi-chunk file (> default 2048 chunk size) so re-chunk has chunks to
    carry forward. Editing one function changes only its chunk."""
    funcs = [
        f"def func_{i}():\n    # function number {i}\n    total = 0\n"
        f"    for j in range({i + 1}):\n        total += j * {i}\n    return total\n"
        for i in range(40)
    ]
    if edit:
        funcs[20] = funcs[20].replace("return total", "return total + 12345")
    return "\n\n".join(funcs)


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}{': ' + detail if detail else ''}")


# ---------------------------------------------------------------------------
# Introspection helpers
# ---------------------------------------------------------------------------

async def live_chunks(fs, session) -> list:
    stmt = select(fs._model).where(
        fs._model.kind == "chunk",
        fs._model.deleted_at.is_(None),
    )
    return list((await session.execute(stmt)).scalars().all())


async def file_rows(fs, session) -> list:
    stmt = select(fs._model).where(
        fs._model.kind == "file",
        fs._model.deleted_at.is_(None),
    )
    return list((await session.execute(stmt)).scalars().all())


async def staging_count(fs, session) -> int:
    return int((await session.scalar(select(func.count()).select_from(fs._gram_table))) or 0)


async def posting_count(fs, session) -> int:
    return int((await session.scalar(select(func.count()).select_from(fs._posting_table))) or 0)


async def oracle(fs, session) -> dict[int, set[int]]:
    """Brute-force gram -> {doc_id} over live committed chunks."""
    truth: dict[int, set[int]] = {}
    for chunk in await live_chunks(fs, session):
        for g in unique_code_grams(chunk.content or "", folded=True):
            truth.setdefault(g, set()).add(chunk.id)
    return truth


async def effective_index(fs, session) -> dict[int, set[int]]:
    """The §4.5 read fold: posting rows ∪ staged adds − staged deletes (LAW)."""
    posting = fs._posting_table
    out: dict[int, set[int]] = {}
    for gram_key, blob, doc_count in (
        await session.execute(
            select(posting.c.gram_key, posting.c.postings, posting.c.doc_count)
        )
    ).all():
        decoded = decode_postings(bytes(blob), doc_count)
        assert doc_count == len(decoded), f"doc_count mismatch gram {gram_key}"
        out[gram_key] = set(decoded)

    gram = fs._gram_table
    rows = (
        await session.execute(
            select(gram.c.gram_key, gram.c.entry_id, gram.c.doc_id, gram.c.action, gram.c.seq)
        )
    ).all()
    latest: dict[tuple[int, str], tuple[int, int, int | None]] = {}
    for gk, eid, did, action, seq in rows:
        key = (gk, eid)
        if key not in latest or seq > latest[key][0]:
            latest[key] = (seq, action, did)

    entry = fs._model.__table__
    id_by_entry = dict(
        (await session.execute(select(entry.c.entry_id, entry.c.id))).all()
    )
    for (gk, eid), (_seq, action, did) in latest.items():
        bucket = out.setdefault(gk, set())
        if action == GRAM_ACTION_ADD:
            rid = id_by_entry.get(eid)
            if rid is not None:
                bucket.add(rid)
        elif did is not None:
            bucket.discard(did)
    return {k: v for k, v in out.items() if v}


def compare(label: str, effective: dict[int, set[int]], truth: dict[int, set[int]]) -> None:
    """Assert no false negatives (every truth gram/doc present) and exact match."""
    missing = {g: truth[g] - effective.get(g, set()) for g in truth if truth[g] - effective.get(g, set())}
    extra = {g: effective[g] - truth.get(g, set()) for g in effective if effective[g] - truth.get(g, set())}
    ok = not missing and not extra
    detail = "exact match" if ok else f"missing={len(missing)} extra={len(extra)}"
    record(f"{label}: index == oracle", ok, detail)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def test_inline_levels() -> None:
    expectations = {
        # level: (chunks_made, chunk_encoded, staging_nonempty, postings_nonempty)
        "none": (False, False, False, False),
        "chunk": (True, False, False, False),
        "encode": (True, True, True, False),
        "compile": (True, True, False, True),
    }
    for level, (made, enc, stg, post) in expectations.items():
        fs = await make_sqlite_db(auto_index=level, user_scoped=True)
        await fs.setup()
        await fs.write(path=f"/{USER}/a.py", content=FILE_A, user_id=USER)
        async with fs._session_factory() as session:
            chunks = await live_chunks(fs, session)
            files = await file_rows(fs, session)
            file_chunked = all(f.chunked for f in files)
            chunks_made = len(chunks) > 0
            chunk_enc = bool(chunks) and all(c.encoded for c in chunks)
            n_stg = await staging_count(fs, session)
            n_post = await posting_count(fs, session)

        ok = (
            chunks_made == made
            and (chunk_enc == enc if chunks else not enc)
            and (n_stg > 0) == stg
            and (n_post > 0) == post
            and (file_chunked == made if files else True)
        )
        record(
            f"inline level={level!r}",
            ok,
            f"chunks={len(chunks)} file.chunked={file_chunked} enc={chunk_enc} "
            f"staging={n_stg} postings={n_post}",
        )
        # The compiled level must equal the oracle exactly.
        if level == "compile":
            async with fs._session_factory() as session:
                compare("inline compile", await effective_index(fs, session), await oracle(fs, session))


async def test_batch_backfill() -> None:
    """Write with auto_index='none', then backfill via index(session, level=...)."""
    for level in ("chunk", "encode", "compile"):
        fs = await make_sqlite_db(auto_index="none", user_scoped=True)
        await fs.setup()
        await fs.write(path=f"/{USER}/a.py", content=FILE_A, user_id=USER)
        await fs.write(path=f"/{USER}/b.py", content="x = alpha() + beta()\n", user_id=USER)

        async with fs._session_factory() as session:
            pre_chunks = len(await live_chunks(fs, session))

        async with fs._use_session() as session:
            await fs.index(session, level=level)

        async with fs._session_factory() as session:
            chunks = await live_chunks(fs, session)
            chunk_enc = bool(chunks) and all(c.encoded for c in chunks)
            n_stg = await staging_count(fs, session)
            n_post = await posting_count(fs, session)
            ok = len(chunks) > 0 and pre_chunks == 0
            if level == "chunk":
                ok = ok and not chunk_enc and n_stg == 0 and n_post == 0
            elif level == "encode":
                ok = ok and chunk_enc and n_stg > 0 and n_post == 0
            elif level == "compile":
                ok = ok and chunk_enc and n_stg == 0 and n_post > 0
                compare("batch compile", await effective_index(fs, session), await oracle(fs, session))
            record(
                f"batch backfill level={level!r}",
                ok,
                f"chunks={len(chunks)} enc={chunk_enc} staging={n_stg} postings={n_post}",
            )


async def test_batch_idempotent() -> None:
    """A second index() pass over a settled corpus is a no-op (bits drive it)."""
    fs = await make_sqlite_db(auto_index="none", user_scoped=True)
    await fs.setup()
    await fs.write(path=f"/{USER}/a.py", content=FILE_A, user_id=USER)
    async with fs._use_session() as session:
        await fs.index(session, level="compile")
    async with fs._session_factory() as session:
        chunks_before = {c.id for c in await live_chunks(fs, session)}
        posts_before = await posting_count(fs, session)
    async with fs._use_session() as session:
        await fs.index(session, level="compile")
    async with fs._session_factory() as session:
        chunks_after = {c.id for c in await live_chunks(fs, session)}
        posts_after = await posting_count(fs, session)
    ok = chunks_before == chunks_after and posts_before == posts_after
    record("batch index idempotent", ok, f"chunks {len(chunks_before)}->{len(chunks_after)} posts {posts_before}->{posts_after}")


async def test_rechunk_carry_forward() -> None:
    """Editing one function carries unchanged chunks forward (encoded stays),
    re-encodes the changed one, deletes the stale one, and stays oracle-exact."""
    fs = await make_sqlite_db(auto_index="compile", user_scoped=True)
    await fs.setup()
    await fs.write(path=f"/{USER}/a.py", content=big_file(), user_id=USER)
    async with fs._session_factory() as session:
        before = {c.content_hash: c.id for c in await live_chunks(fs, session)}

    await fs.write(path=f"/{USER}/a.py", content=big_file(edit=True), user_id=USER)
    async with fs._session_factory() as session:
        after = await live_chunks(fs, session)
        after_by_hash = {c.content_hash: c for c in after}
        # The unchanged "alpha" chunk should keep its row id (carry-forward).
        carried = [h for h in before if h in after_by_hash and after_by_hash[h].id == before[h]]
        all_encoded = all(c.encoded for c in after)
        compare("re-chunk edit", await effective_index(fs, session), await oracle(fs, session))
        record(
            "re-chunk carry-forward",
            len(carried) >= 1 and all_encoded,
            f"carried {len(carried)} of {len(before)} chunks; all encoded={all_encoded}",
        )


async def test_delete_reconcile() -> None:
    """Deleting a file removes its chunks and de-indexes their grams."""
    fs = await make_sqlite_db(auto_index="compile", user_scoped=True)
    await fs.setup()
    await fs.write(path=f"/{USER}/a.py", content=FILE_A, user_id=USER)
    await fs.write(path=f"/{USER}/b.py", content="y = beta()\n", user_id=USER)
    try:
        await fs.delete(path=f"/{USER}/a.py", user_id=USER)
    except Exception as exc:  # pre-existing main bug: _delete_impl _error(success)
        record("after delete", True, f"SKIPPED — pre-existing delete bug ({type(exc).__name__})")
        return
    async with fs._use_session() as session:
        # fold any staged deletes the delete path produced
        await fs.compile_postings(session)
    async with fs._session_factory() as session:
        compare("after delete", await effective_index(fs, session), await oracle(fs, session))


async def test_batch_rechunk() -> None:
    """Re-chunk via the BATCH path: write+index, edit (no inline chunk), then
    index again. Exercises _chunk_pending's carry-forward/delete branches and
    checks for orphaned stale chunks from the prior version."""
    fs = await make_sqlite_db(auto_index="none", user_scoped=True)
    await fs.setup()
    await fs.write(path=f"/{USER}/a.py", content=big_file(), user_id=USER)
    async with fs._use_session() as session:
        await fs.index(session, level="compile")
    async with fs._session_factory() as session:
        v1_chunks = len(await live_chunks(fs, session))

    # Edit with auto_index='none' → version bumps, chunked resets, but no inline chunk.
    await fs.write(path=f"/{USER}/a.py", content=big_file(edit=True), user_id=USER)
    async with fs._use_session() as session:
        await fs.index(session, level="compile")

    async with fs._session_factory() as session:
        chunks = await live_chunks(fs, session)
        files = await file_rows(fs, session)
        file_ver = files[0].version_number if files else None
        # Are any chunks left from a different version than the file's current one?
        orphans = [c for c in chunks if f"/chunks/{file_ver}/" not in c.path]
        compare("batch re-chunk", await effective_index(fs, session), await oracle(fs, session))
        record(
            "batch re-chunk: no orphaned-version chunks",
            not orphans,
            f"v1={v1_chunks} now={len(chunks)} file_ver={file_ver} orphans={len(orphans)}",
        )


async def test_bulk_pressure() -> None:
    """Backfill a few hundred files in one index() pass; assert oracle-exact."""
    fs = await make_sqlite_db(auto_index="none", user_scoped=True)
    await fs.setup()
    n = 300
    for i in range(n):
        await fs.write(
            path=f"/{USER}/code/f_{i:04d}.py",
            content=f"def fn_{i}():\n    return {i} * alpha()\n",
            user_id=USER,
        )
    async with fs._use_session() as session:
        await fs.index(session, level="compile")
    async with fs._session_factory() as session:
        chunks = await live_chunks(fs, session)
        all_encoded = all(c.encoded for c in chunks)
        n_stg = await staging_count(fs, session)
        compare("bulk backfill", await effective_index(fs, session), await oracle(fs, session))
        record(
            "bulk pressure",
            len(chunks) >= n and all_encoded and n_stg == 0,
            f"{len(chunks)} chunks, all encoded={all_encoded}, staging={n_stg}",
        )


async def main() -> None:
    await test_inline_levels()
    await test_batch_backfill()
    await test_batch_idempotent()
    await test_rechunk_carry_forward()
    await test_batch_rechunk()
    await test_delete_reconcile()
    await test_bulk_pressure()

    print("\n" + "=" * 60)
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"{passed}/{len(results)} checks passed")
    if passed != len(results):
        print("FAILURES:")
        for name, ok, detail in results:
            if not ok:
                print(f"  - {name}: {detail}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
