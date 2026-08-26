"""Spec 102 Q2–Q4: a set-based scattered-delete prototype, measured against the live arm.

Same corpus in two namespaces on one engine: the live per-target arm in
one, this prototype in the other. The prototype holds the same topology
serialization point and produces the same end state (a parity referee
diffs both namespaces' entry and segment tables), but replaces the
per-target statement quartet with, per chunk: one guarded set-based
reparent, one fused descendant select + rewrite, one set-based parent
bump, one posting delta. A rival move measures the lock hold on both.

Spellings per engine: ``values`` (Postgres/MSSQL — VALUES join with
RETURNING), ``union`` (MySQL family — multi-table UPDATE over a UNION ALL
derived table, aggregate rowcount), ``arraydml`` (Oracle — the driver's
true array DML, aggregate rowcount; a MERGE cannot update its ON columns).

    uv run python context/research/studies/2026-08-25-set-based-topology-statements/prototype_set_based_delete.py 1000 10000
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
import time
from collections import Counter
from datetime import UTC, datetime

from common import ENGINE_ENV, StatementProfile, minted, save, scattered_corpus, sibling
from sqlalchemy import Integer, bindparam, column, func, literal, select, text, union_all, update, values

from vfs.models import Observation
from vfs.paths import Path
from vfs.storage import ResolvedPair
from vfs.storage.backends.database.descent import rows_by_path
from vfs.storage.backends.database.dialects import chunked, topology_execution_options
from vfs.storage.backends.database.segments import move_postings
from vfs.storage.backends.database.topology import _serialize, _trash_name, _TrashChain

SPELLING = {"postgresql": "values", "mssql": "values", "mysql": "union", "mariadb": "union", "oracle": "arraydml"}
REPARENT_COLS = ("v_id", "v_ver", "v_bucket", "v_name", "v_path", "v_oparent", "v_oname")


def derived(entry, spelling, name, cols, rows):
    """A derived table of *rows* in the engine's spelling: VALUES or UNION ALL."""
    types = {
        "v_id": entry.c.entry_id.type, "v_ver": entry.c.version.type, "v_bucket": entry.c.parent_id.type,
        "v_name": entry.c.name.type, "v_path": entry.c.path.type, "v_oparent": entry.c.original_parent_id.type,
        "v_oname": entry.c.original_name.type, "v_old": entry.c.path.type, "v_new": entry.c.path.type,
        "v_len": Integer(), "v_n": Integer(),
    }
    if spelling == "values":
        return values(*(column(c, types[c]) for c in cols), name=name).data(rows)
    selects = [select(*(literal(v, types[c]).label(c) for c, v in zip(cols, row, strict=True))) for row in rows]
    return union_all(*selects).subquery(name)


async def reparent(session, entry, profile, spelling, plan, now, chunk_rows):
    """Guarded set-based reparent of every target; returns the matched count."""
    matched = 0
    if spelling == "arraydml":
        stmt = (
            update(entry)
            .where(entry.c.entry_id == bindparam("b_id"), entry.c.version == bindparam("b_ver"))
            .values(
                parent_id=bindparam("b_bucket"), name=bindparam("b_name"), path=bindparam("b_path"),
                original_parent_id=bindparam("b_oparent"), original_name=bindparam("b_oname"),
                deleted_at=now, encoded=False, version=entry.c.version + 1,
            )
        )
        for chunk in chunked(plan, chunk_rows):
            params = [dict(zip(("b_id", "b_ver", "b_bucket", "b_name", "b_path", "b_oparent", "b_oname"), row, strict=True)) for row in chunk]
            matched += (await session.execute(stmt, params)).rowcount
        return matched
    for chunk in chunked(plan, chunk_rows):
        v = derived(entry, spelling, "incoming", REPARENT_COLS, chunk)
        stmt = (
            update(entry)
            .where(entry.c.entry_id == v.c.v_id, entry.c.version == v.c.v_ver)
            .values(
                parent_id=v.c.v_bucket, name=v.c.v_name, path=v.c.v_path, original_parent_id=v.c.v_oparent,
                original_name=v.c.v_oname, deleted_at=now, encoded=False, version=entry.c.version + 1,
            )
        )
        if spelling == "values":
            matched += len((await session.execute(stmt.returning(entry.c.entry_id))).all())
        else:
            matched += (await session.execute(stmt)).rowcount
    return matched


def _range(entry, v):
    """The sargable descendant predicate: a half-open byte range under ``old + '/'``."""
    return (entry.c.path > v.c.v_old + literal("/", entry.c.path.type)) & (entry.c.path < v.c.v_old + literal("0", entry.c.path.type))


def _rewritten(entry, profile, v):
    tail = func.substr(entry.c.path, v.c.v_len + 1) if profile.name == "oracle" else func.substring(entry.c.path, v.c.v_len + 1, 4096)
    return v.c.v_new + tail


async def fused_descendants(session, entry, profile, spelling, dir_plan, chunk_rows):
    """One select per chunk of directory targets: every descendant's (id, old, new)."""
    found = []
    for chunk in chunked(dir_plan, chunk_rows):
        v = derived(entry, spelling, "prefixes", ("v_old", "v_new", "v_len"), chunk)
        stmt = select(entry.c.entry_id, entry.c.path, _rewritten(entry, profile, v).label("new_path")).select_from(entry.join(v, _range(entry, v)))
        found.extend((r.entry_id, r.path, r.new_path) for r in await session.execute(stmt))
    return found


async def fused_rewrite(session, entry, profile, spelling, dir_plan, rewrites, chunk_rows):
    """Apply the descendant path rewrites: one fused UPDATE per chunk, or array DML on Oracle."""
    if spelling == "arraydml":
        stmt = update(entry).where(entry.c.entry_id == bindparam("b_id")).values(path=bindparam("b_path"))
        for chunk in chunked(rewrites, chunk_rows):
            await session.execute(stmt, [{"b_id": i, "b_path": new} for i, _old, new in chunk])
        return
    for chunk in chunked(dir_plan, chunk_rows):
        v = derived(entry, spelling, "prefixes", ("v_old", "v_new", "v_len"), chunk)
        await session.execute(update(entry).where(_range(entry, v)).values(path=_rewritten(entry, profile, v)))


async def bump_parents(session, entry, spelling, counts, chunk_rows):
    rows = list(counts.items())
    if spelling == "arraydml":
        stmt = update(entry).where(entry.c.entry_id == bindparam("b_id")).values(version=entry.c.version + bindparam("b_n"))
        for chunk in chunked(rows, chunk_rows):
            await session.execute(stmt, [{"b_id": i, "b_n": n} for i, n in chunk])
        return
    for chunk in chunked(rows, chunk_rows):
        v = derived(entry, spelling, "bumps", ("v_id", "v_n"), chunk)
        await session.execute(update(entry).where(entry.c.entry_id == v.c.v_id).values(version=entry.c.version + v.c.v_n))


async def set_based_delete(storage, targets):
    host = storage._host
    tables, entry, profile = host.tables, host.tables.entry, host.profile
    spelling = SPELLING[profile.name]
    width = len(REPARENT_COLS)
    chunk_rows = max(1, min(host.membership_budget, host.parameter_budget // width))
    async with host.session_factory() as session:
        await session.connection(execution_options=topology_execution_options(profile))
        await _serialize(session, profile, tables.meta, host.topology_key)
        now = datetime.now(UTC)
        root_id = (await session.execute(select(entry.c.entry_id).where(entry.c.path == "/"))).scalar_one()
        trash = _TrashChain(entry, tables.segments, root_id=root_id, user_id=None, now=now)
        bucket_id = await trash.ensure(session, targets[0])
        assert isinstance(bucket_id, str), bucket_id
        cols = [entry.c.entry_id, entry.c.parent_id, entry.c.name, entry.c.path, entry.c.version, entry.c.kind]
        snapshot = await rows_by_path(session, entry, [str(t) for t in targets], cols, host.membership_budget)
        plan, dir_plan, moves, parents = [], [], [], Counter()
        for target in targets:
            row = snapshot[str(target)]
            trash_name = _trash_name(row["entry_id"], row["name"])
            trash_path = f"{trash.bucket_path}/{trash_name}"
            plan.append((row["entry_id"], row["version"], bucket_id, trash_name, trash_path, row["parent_id"], row["name"]))
            moves.append((row["entry_id"], row["path"], trash_path))
            parents[row["parent_id"]] += 1
            if row["kind"] == "directory":
                dir_plan.append((row["path"], trash_path, len(row["path"])))
        matched = await reparent(session, entry, profile, spelling, plan, now, chunk_rows)
        assert matched == len(plan), (matched, len(plan))
        rewrites = await fused_descendants(session, entry, profile, spelling, dir_plan, chunk_rows) if dir_plan else []
        if rewrites:
            await fused_rewrite(session, entry, profile, spelling, dir_plan, rewrites, chunk_rows)
        parents[bucket_id] += len(plan)
        await bump_parents(session, entry, spelling, parents, chunk_rows)
        await move_postings(session, tables.segments, host.membership_budget, moves + rewrites)
        await session.commit()
    return {"spelling": spelling, "chunk_rows": chunk_rows, "targets": len(plan), "descendants": len(rewrites)}


async def dump(storage):
    """The namespace's observable end state, ids resolved to paths."""
    host = storage._host
    entry, segments = host.tables.entry, host.tables.segments
    async with host.session_factory() as session:
        rows = (await session.execute(select(entry.c.entry_id, entry.c.parent_id, entry.c.path, entry.c.name, entry.c.kind, entry.c.version, entry.c.deleted_at, entry.c.original_parent_id, entry.c.original_name, entry.c.encoded))).all()
        posts = (await session.execute(select(segments.c.segment, segments.c.entry_id))).all()
    # Trash names embed each namespace's own ULIDs; normalize them so the
    # two namespaces compare on shape, not identity.
    norm = lambda text: re.sub(r"01[0-9A-HJKMNP-TV-Z]{24}-", "<ulid>-", text) if text else text
    by_id = {r.entry_id: norm(r.path) for r in rows}
    state = sorted((by_id[r.entry_id], by_id.get(r.parent_id), norm(r.name), r.kind, r.version, r.deleted_at is not None, by_id.get(r.original_parent_id), r.original_name, bool(r.encoded)) for r in rows)
    postings = sorted((norm(p.segment), by_id[p.entry_id]) for p in posts)
    return state, postings


async def explain_postgres(storage, dir_plan):
    """Q3: is the fused rewrite's range predicate sargable? EXPLAIN on Postgres."""
    host = storage._host
    entry = host.tables.entry
    v = derived(entry, "values", "prefixes", ("v_old", "v_new", "v_len"), dir_plan[:50])
    stmt = select(entry.c.entry_id).select_from(entry.join(v, _range(entry, v)))
    like = select(entry.c.entry_id).select_from(entry.join(v, entry.c.path.like(v.c.v_old + literal("/%", entry.c.path.type))))
    out = {}
    async with host.session_factory() as session:
        for name, s in (("range", stmt), ("like", like)):
            sql = str(s.compile(dialect=host.engine.sync_engine.dialect, compile_kwargs={"literal_binds": True}))
            plan = (await session.execute(text("EXPLAIN " + sql))).scalars().all()
            out[name] = plan[:8]
    return out


async def run_arm(engine, url, size, dirs, *, prototype):
    async with minted(url) as storage:
        entries, targets = scattered_corpus(size, dirs_with_children=dirs)
        assert (await storage.write(entries=entries, parents=True)).success
        profile = StatementProfile(storage)
        rival = sibling(url, storage)
        try:
            profile.enabled = True
            t0 = time.perf_counter()
            if prototype:
                work = asyncio.ensure_future(set_based_delete(storage, targets))
            else:
                work = asyncio.ensure_future(storage.delete(observations=[Observation(path=t) for t in targets]))
            await asyncio.sleep(0.5)
            t_rival = time.perf_counter()
            moved = await rival.move(operations=[ResolvedPair(src=Path("/rival"), dest=Path("/rival2"))])
            rival_s = time.perf_counter() - t_rival
            outcome = await work
            elapsed = time.perf_counter() - t0
            profile.enabled = False
        finally:
            await rival.close()
        assert moved.success, moved.errors[:2]
        if not prototype:
            assert outcome.success, outcome.errors[:2]
            outcome = {"observations": len(outcome.observations)}
        explain = await explain_postgres(storage, [(f"/t{j:04}", f"/x{j:04}", 6) for j in range(dirs)]) if engine == "postgres" and prototype and dirs else None
        state = await dump(storage)
        return {"seconds": round(elapsed, 3), "rival_move_blocked_seconds": round(rival_s, 3), "statement_total": sum(v["count"] for v in profile.shapes.values()), "statements": profile.report(8), "outcome": outcome, "explain": explain}, state


async def run(engine, url, size):
    dirs = size // 100
    live, live_state = await run_arm(engine, url, size, dirs, prototype=False)
    proto, proto_state = await run_arm(engine, url, size, dirs, prototype=True)
    entry_diff = [x for x in live_state[0] if x not in set(proto_state[0])][:5] + [x for x in proto_state[0] if x not in set(live_state[0])][:5]
    posting_diff = len(set(live_state[1]) ^ set(proto_state[1]))
    payload = {"engine": engine, "size": size, "directory_targets": dirs, "live": live, "prototype": proto, "parity": {"entries_equal": live_state[0] == proto_state[0], "postings_equal": live_state[1] == proto_state[1], "entry_diff_sample": entry_diff, "posting_diff_count": posting_diff}}
    save(f"prototype-{engine}-{size}", payload)
    print(f"{engine} {size}: live {live['seconds']}s (rival {live['rival_move_blocked_seconds']}s, {live['statement_total']} stmts) → prototype {proto['seconds']}s (rival {proto['rival_move_blocked_seconds']}s, {proto['statement_total']} stmts) parity entries={payload['parity']['entries_equal']} postings={payload['parity']['postings_equal']}")


async def main():
    sizes = [int(a) for a in sys.argv[1:]] or [1000, 10000]
    for engine, env in ENGINE_ENV.items():
        url = os.environ.get(env)
        if not url:
            continue
        for size in sizes:
            await run(engine, url, size)


if __name__ == "__main__":
    asyncio.run(main())
