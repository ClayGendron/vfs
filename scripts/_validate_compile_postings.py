"""Throwaway validation harness for DatabaseFileSystem.compile_postings.

Covers correctness cases 1-6 plus the doc_count invariant and a codec
round-trip re-confirmation. Builds its own in-memory SQLite filesystem rather
than running the (partly-broken) full test suite.

Run: uv run python scripts/_validate_compile_postings.py
"""

from __future__ import annotations

import asyncio
import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

from sqlalchemy import func, insert, select

from tests.conftest import make_sqlite_db
from vfs.code_grams import unique_code_grams
from vfs.models import GRAM_ACTION_ADD, ENCODING_DELTA_GAMMA
from vfs.postings import decode_postings, encode_postings

USER = "u1"
results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


async def committed_chunks(fs, session) -> list:
    """Return live indexed chunk rows (kind=chunk, not soft-deleted)."""
    stmt = select(fs._model).where(
        fs._model.kind == "chunk",
        fs._model.deleted_at.is_(None),
        fs._model.index_content == True,  # noqa: E712
    )
    return list((await session.execute(stmt)).scalars().all())


async def ground_truth(fs, session) -> dict[int, set[int]]:
    """Brute-force per-gram doc_id set from live committed chunk content."""
    truth: dict[int, set[int]] = {}
    for chunk in await committed_chunks(fs, session):
        for g in unique_code_grams(chunk.content or "", folded=True):
            truth.setdefault(g, set()).add(chunk.id)
    return truth


async def load_postings(fs, session) -> dict[int, set[int]]:
    """Decode every posting row into a gram_key -> doc_id set map."""
    posting = fs._posting_table
    rows = (
        await session.execute(
            select(posting.c.gram_key, posting.c.postings, posting.c.doc_count, posting.c.byte_size)
        )
    ).all()
    out: dict[int, set[int]] = {}
    for gram_key, blob, doc_count, byte_size in rows:
        decoded = decode_postings(bytes(blob), doc_count)
        out[gram_key] = set(decoded)
        # doc_count + byte_size invariants (case 6)
        assert doc_count == len(decoded), f"doc_count {doc_count} != decoded {len(decoded)} for gram {gram_key}"
        assert byte_size == len(bytes(blob)), f"byte_size {byte_size} != blob len for gram {gram_key}"
        assert len(decoded) > 0, f"empty posting row left for gram {gram_key}"
    return out


async def assert_matches_truth(fs, session, label: str) -> tuple[bool, str]:
    truth = await ground_truth(fs, session)
    stored = await load_postings(fs, session)
    truth_keys = set(truth)
    stored_keys = set(stored)
    if truth_keys != stored_keys:
        missing = truth_keys - stored_keys
        extra = stored_keys - truth_keys
        return False, f"{label}: key mismatch missing={len(missing)} extra={len(extra)}"
    for g in truth_keys:
        if truth[g] != stored[g]:
            return False, f"{label}: gram {g} truth={sorted(truth[g])} stored={sorted(stored[g])}"
    return True, f"{label}: {len(truth_keys)} grams, all decode to exact doc_id sets (brute-force matched)"


async def main() -> None:
    # ---- Codec round-trip re-confirmation -------------------------------
    rng = random.Random(42)
    rt_ok = True
    for _ in range(2000):
        n = rng.randint(0, 40)
        ids = sorted(rng.sample(range(0, 100000), n))
        if decode_postings(encode_postings(ids), len(ids)) != ids:
            rt_ok = False
            break
    record("codec-roundtrip", rt_ok, "2000 random sorted-set encodings round-trip exactly")

    # ---- Case 1: basic add ----------------------------------------------
    fs = await make_sqlite_db(auto_chunk=True, auto_index=True, user_scoped=True)
    await fs.setup()
    await fs.write(path=f"/{USER}/a.py", content="def foo():\n    return 1\n", user_id=USER)
    await fs.write(path=f"/{USER}/b.py", content="def bar():\n    return 2\n", user_id=USER)
    await fs.write(path=f"/{USER}/c.py", content="x = foo() + bar()\n", user_id=USER)

    async with fs._session_factory() as session:
        folded = await fs.compile_postings(session)
        await session.commit()
    async with fs._session_factory() as session:
        ok, detail = await assert_matches_truth(fs, session, "case1-basic-add")
    record("case1-basic-add", ok, f"folded {folded} staged rows; {detail}")

    # ---- Case 2: edit / re-chunk ----------------------------------------
    # Capture a gram unique to the old content of a.py to prove it disappears.
    async with fs._session_factory() as session:
        chunks = await committed_chunks(fs, session)
        old_a_grams: set[int] = set()
        for c in chunks:
            if c.path.startswith(f"/{USER}/.vfs/a.py") or "a.py" in c.path:
                old_a_grams |= unique_code_grams(c.content or "", folded=True)

    await fs.write(path=f"/{USER}/a.py", content="def renamed_func():\n    return 99\n", user_id=USER)
    async with fs._session_factory() as session:
        folded2 = await fs.compile_postings(session)
        await session.commit()
    async with fs._session_factory() as session:
        ok2, detail2 = await assert_matches_truth(fs, session, "case2-edit")
        # Grams that existed ONLY in old a.py content must be gone or doc set changed.
        truth = await ground_truth(fs, session)
        stored = await load_postings(fs, session)
        # find a gram that was in old content but not in any current chunk
        gone_grams = old_a_grams - set(truth)
        for g in gone_grams:
            if g in stored:
                ok2 = False
                detail2 += f" | stale gram {g} still has a posting row"
    record(
        "case2-edit-rechunk",
        ok2,
        f"folded {folded2} rows; {detail2}; {len(gone_grams)} old-only grams confirmed removed",
    )

    # ---- Case 3: delete -------------------------------------------------
    # Find grams that live ONLY in c.py so we can prove zero-doc rows are deleted.
    async with fs._session_factory() as session:
        truth_before = await ground_truth(fs, session)
        c_chunks = [
            ch for ch in await committed_chunks(fs, session) if "c.py" in ch.path
        ]
        c_doc_ids = {ch.id for ch in c_chunks}
        c_grams: set[int] = set()
        for ch in c_chunks:
            c_grams |= unique_code_grams(ch.content or "", folded=True)
        # grams whose ONLY doc is a c.py chunk
        c_exclusive = {g for g in c_grams if truth_before.get(g, set()) <= c_doc_ids}

    # NOTE: fs.delete() is broken on main (unrelated pre-existing bug), so we
    # drive a delete through the same staging machinery compile_postings
    # consumes: stage DELETE deltas for c.py's chunks (carrying doc_id), soft-
    # delete the chunk rows, then compile. This is exactly what the write
    # pipeline's de-index path produces for a removed/de-indexed file.
    from datetime import UTC, datetime

    async with fs._session_factory() as session:
        live_c = [ch for ch in await committed_chunks(fs, session) if "c.py" in ch.path]
        await fs._stage_gram_deltas([], {}, live_c, session=session)
        for ch in live_c:
            ch.deleted_at = datetime.now(UTC)
            ch.index_content = False
            session.add(ch)
        await session.commit()
    async with fs._session_factory() as session:
        folded3 = await fs.compile_postings(session)
        await session.commit()
    async with fs._session_factory() as session:
        ok3, detail3 = await assert_matches_truth(fs, session, "case3-delete")
        stored = await load_postings(fs, session)
        zero_rows_left = [g for g in c_exclusive if g in stored]
        if zero_rows_left:
            ok3 = False
            detail3 += f" | {len(zero_rows_left)} zero-doc grams kept a row (should be DELETEd)"
    record(
        "case3-delete",
        ok3,
        f"folded {folded3} rows; {detail3}; {len(c_exclusive)} c.py-exclusive grams checked for row removal",
    )

    # ---- Case 4: idempotent / crash re-run ------------------------------
    async with fs._session_factory() as session:
        before = await load_postings(fs, session)
    async with fs._session_factory() as session:
        n_empty = await fs.compile_postings(session)
        await session.commit()
    # crash-style: another write+compile, then immediate second compile no-op
    await fs.write(path=f"/{USER}/d.py", content="z = 7\n", user_id=USER)
    async with fs._session_factory() as session:
        n_first = await fs.compile_postings(session)
        await session.commit()
    async with fs._session_factory() as session:
        n_second = await fs.compile_postings(session)
        await session.commit()
    async with fs._session_factory() as session:
        after = await load_postings(fs, session)
    # Empty-staging compile must return 0 and leave posting rows unchanged
    # (snapshot `before` taken right after case 3, `after` after re-runs+d.py).
    empty_ok = n_empty == 0 and all(before[k] == after.get(k) for k in before)
    second_ok = n_second == 0
    record("case4a-empty-staging-returns-0", empty_ok, f"compile_postings on empty staging returned {n_empty}")
    record("case4b-crash-rerun-noop", second_ok, f"first compile folded {n_first}, immediate re-run folded {n_second}")

    # ---- Case 5: join-miss drop (hard-deleted entry) --------------------
    # Stage an ADD for an entry_id that does not exist in vfs_entries.
    gram = fs._gram_table
    bogus_gram_key = 0x515151  # 'QQQ' — almost certainly absent from corpus
    async with fs._session_factory() as session:
        before_rows = (await session.execute(select(func.count()).select_from(fs._posting_table))).scalar()
        await session.execute(
            insert(gram),
            [
                {
                    "gram_key": bogus_gram_key,
                    "entry_id": "ffffffff-ffff-ffff-ffff-ffffffffffff",
                    "doc_id": None,
                    "action": GRAM_ACTION_ADD,
                }
            ],
        )
        await session.commit()
    join_miss_err = None
    try:
        async with fs._session_factory() as session:
            folded5 = await fs.compile_postings(session)
            await session.commit()
    except Exception as exc:  # noqa: BLE001
        join_miss_err = exc
        folded5 = -1
    async with fs._session_factory() as session:
        after_rows = (await session.execute(select(func.count()).select_from(fs._posting_table))).scalar()
        bogus = (
            await session.execute(
                select(fs._posting_table.c.gram_key).where(fs._posting_table.c.gram_key == bogus_gram_key)
            )
        ).first()
        staging_left = (await session.execute(select(func.count()).select_from(gram))).scalar()
    case5_ok = join_miss_err is None and bogus is None and after_rows == before_rows and staging_left == 0
    record(
        "case5-join-miss-drop",
        case5_ok,
        (
            f"err={join_miss_err}; bogus posting row present={bogus is not None}; "
            f"posting count {before_rows}->{after_rows}; staging cleared={staging_left == 0}"
        ),
    )

    # ---- Case 6: doc_count / byte_size invariant (already asserted in load) ----
    async with fs._session_factory() as session:
        try:
            await load_postings(fs, session)
            record("case6-doc_count-byte_size-invariant", True, "all rows: doc_count==len(decode) and byte_size==len(blob), no empty rows")
        except AssertionError as e:
            record("case6-doc_count-byte_size-invariant", False, str(e))

    print("\n==== SUMMARY ====")
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL':4} {name}")
    failed = [n for n, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    if failed:
        print("FAILED:", failed)


if __name__ == "__main__":
    asyncio.run(main())
