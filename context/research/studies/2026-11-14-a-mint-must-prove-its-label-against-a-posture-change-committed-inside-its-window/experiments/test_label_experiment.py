"""The label-mint experiment: which windows are open, per engine, seam, shape and minter.

Scratch research code, never committed. Each node stages a posture
change, driven to the end of its relabel, inside a mint's window, then
compares every minted row's stored label with the label the standing
posture rows give it.
"""

from __future__ import annotations

import asyncio
import json
import os
from concurrent.futures import ThreadPoolExecutor
from typing import NamedTuple

import pytest
from sqlalchemy import event, func, select, text

from tests.support.commit_worlds import ANONYMOUS, BOB, CAROL, SYSTEM, label_world, row_at
from tests.support.server_schemas import ENGINE_LEGS, server_storage, sibling
from vfs.authority import Authority
from vfs.models import Entry
from vfs.paths import Path
from vfs.results import ErrorKind, Result
from vfs.storage import ResolvedPair
from vfs.storage.backends.database import DatabaseStorage, seams
from vfs.storage.backends.database.labels import labels_for
from vfs.storage.grants import LEVEL_RANK

OUT = os.environ.get("LABEL_EXPERIMENT_OUT")


def record(kind: str, **fields: object) -> None:
    """Append one measured fact to the experiment's JSON-lines file."""
    if OUT:
        with open(OUT, "a") as handle:
            handle.write(json.dumps({"kind": kind, **fields}) + "\n")


class Shape(NamedTuple):
    posture: str
    target: str
    minted: tuple[str, ...]


SHAPES = {
    "at-path": Shape("/p/new.txt", "/p/new.txt", ("/p/new.txt",)),
    "at-minted-parent": Shape("/p/n", "/p/n/new.txt", ("/p/n", "/p/n/new.txt")),
    "at-existing-parent": Shape("/p", "/p/new.txt", ("/p/new.txt",)),
}
MINTERS: dict[str, Authority | None] = {"granted": BOB, "system": None}
WRITE_SEAMS = ("write:before-apply", "write:after-labels")
# The no-lock candidate's copy carries a seam after its re-read; a rival there would wait on a real lock for ever.
if os.environ.get("LABEL_EXPERIMENT_NOLOCK"):
    WRITE_SEAMS = (*WRITE_SEAMS, "mint:after-hold")


async def marks(storage: DatabaseStorage) -> int:
    relabels = storage._host.tables.relabels
    async with storage._host.session_factory() as session:
        return int((await session.execute(select(func.count()).select_from(relabels))).scalar_one())


async def standing(storage: DatabaseStorage, paths: tuple[str, ...]) -> dict[str, int]:
    host = storage._host
    async with host.session_factory() as session:
        return await labels_for(session, host.tables, host.profile, host.membership_budget, paths)


async def stored(storage: DatabaseStorage, paths: tuple[str, ...]) -> dict[str, int | None]:
    rows = {path: await row_at(storage, path) for path in paths}
    return {path: None if row is None else row["everyone_level"] for path, row in rows.items()}


def self_clearing(name: str, call):
    results: list[Result] = []

    async def handler() -> None:
        seams.clear(name)
        results.append(await call())

    return handler, results


def counted(storage: DatabaseStorage) -> tuple[list[str], object]:
    """Every statement *storage*'s engine issues from now on, and the listener to remove."""
    seen: list[str] = []

    def listen(conn, cursor, statement, parameters, context, executemany) -> None:
        seen.append(statement)

    engine = storage._host.engine.sync_engine
    event.listen(engine, "before_cursor_execute", listen)
    return seen, listen


def attempts_of(storage: DatabaseStorage) -> list[int]:
    """Counts each attempt the storage's retry layer starts, by wrapping its session factory."""
    count = [0]
    factory = storage._host.session_factory

    def wrapped(*args, **kwargs):
        count[0] += 1
        return factory(*args, **kwargs)

    storage._host.session_factory = wrapped
    return count


async def check(storage, name, result, minted, target, want_level, leg) -> None:
    """Assert the property and record the outcome whichever way it falls."""
    assert await marks(storage) == 0
    want = await standing(storage, minted)
    assert want == dict.fromkeys(minted, want_level), want
    have = await stored(storage, minted)
    if have[target] is None:
        lawful = {(ErrorKind.permission_denied, False), (ErrorKind.conflict, True)}
        outcome = "refused" if {(e.kind, e.retryable) for e in result.errors} <= lawful else "UNLAWFUL"
        record(name, leg=leg, outcome=outcome, errors=[str(e.kind) for e in result.errors])
        assert result.success is False and outcome == "refused", result.errors
        assert all(level is None for level in have.values()), have
        return
    outcome = "closed" if have == want else "OPEN"
    record(name, leg=leg, outcome=outcome, stored=have, standing=want)
    assert result.success is True, result.errors
    assert have == want, f"{leg}: stored {have}, standing {want}"


# ---------------------------------------------------------------------------
# The write family, tightening and loosening, at both seams
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("minter", list(MINTERS))
@pytest.mark.parametrize("shape", list(SHAPES))
@pytest.mark.parametrize("seam", WRITE_SEAMS)
@pytest.mark.parametrize("env_var", ENGINE_LEGS)
async def test_write_across_a_tightening(env_var: str, seam: str, shape: str, minter: str) -> None:
    async with server_storage(env_var, posture="none") as storage:
        await label_world(storage)
        assert (await storage.grant(path=Path("/p"), principal="bob", level="read_write")).success is True
        at = SHAPES[shape]
        second = sibling(env_var, storage)
        tries = attempts_of(storage)

        async def rival() -> Result:
            tightened = await second.posture(path=Path(at.posture), posture="none")
            assert await marks(second) == 0
            return tightened

        handler, rivals = self_clearing(seam, rival)
        try:
            with seams.installed(seam, handler):
                entries = [Entry(path=Path(at.target), content="minted probe\n")]
                result = await storage.write(entries=entries, parents=True, authority=MINTERS[minter])
        finally:
            await second.close()
        assert rivals and rivals[0].success is True, rivals[0].errors if rivals else "the rival never ran"
        leg = f"{storage._host.profile.name}/{seam}/{shape}/{minter}"
        record("attempts", leg=leg, attempts=tries[0])
        await check(storage, "tighten", result, at.minted, at.target, LEVEL_RANK["none"], leg)


@pytest.mark.parametrize("minter", list(MINTERS))
@pytest.mark.parametrize("shape", list(SHAPES))
@pytest.mark.parametrize("seam", WRITE_SEAMS)
@pytest.mark.parametrize("env_var", ENGINE_LEGS)
async def test_write_across_a_loosening(env_var: str, seam: str, shape: str, minter: str) -> None:
    async with server_storage(env_var, posture="none") as storage:
        await label_world(storage)
        assert (await storage.posture(path=Path("/p"), posture="none")).success is True
        assert (await storage.grant(path=Path("/p"), principal="bob", level="read_write")).success is True
        at = SHAPES[shape]
        second = sibling(env_var, storage)

        async def rival() -> Result:
            loosened = await second.posture(path=Path(at.posture), posture="read_write")
            assert await marks(second) == 0
            return loosened

        handler, rivals = self_clearing(seam, rival)
        try:
            with seams.installed(seam, handler):
                entries = [Entry(path=Path(at.target), content="minted probe\n")]
                result = await storage.write(entries=entries, parents=True, authority=MINTERS[minter])
        finally:
            await second.close()
        assert rivals and rivals[0].success is True, rivals[0].errors if rivals else "the rival never ran"
        leg = f"{storage._host.profile.name}/{seam}/{shape}/{minter}"
        await check(storage, "loosen", result, at.minted, at.target, LEVEL_RANK["read_write"], leg)
        read = await storage.read(path=Path(at.target), authority=CAROL)
        record("loosen-read", leg=leg, carol_reads=read.success)
        assert read.success is True, read.errors


# ---------------------------------------------------------------------------
# The transfer path
# ---------------------------------------------------------------------------

TRANSFER_SEAMS = ("transfer:post-collect", "transfer:after-postures")


@pytest.mark.parametrize("minter", list(MINTERS))
@pytest.mark.parametrize("verb", ["move", "copy"])
@pytest.mark.parametrize("seam", TRANSFER_SEAMS)
@pytest.mark.parametrize("env_var", ENGINE_LEGS)
async def test_transfer_across_a_tightening(env_var: str, seam: str, verb: str, minter: str) -> None:
    async with server_storage(env_var, posture="none") as storage:
        await label_world(storage)
        assert (await storage.mkdir(path=Path("/p/q"), authority=SYSTEM)).success is True
        assert (await storage.grant(path=Path("/p"), principal="bob", level="read_write")).success is True
        second = sibling(env_var, storage)

        async def rival() -> Result:
            tightened = await second.posture(path=Path("/p/q"), posture="none")
            assert await marks(second) == 0
            return tightened

        handler, rivals = self_clearing(seam, rival)
        pair = ResolvedPair(src=Path("/p/d"), dest=Path("/p/q/d"))
        minted = ("/p/q/d", "/p/q/d/f.txt", "/p/q/d/sub", "/p/q/d/sub/g.txt")
        try:
            with seams.installed(seam, handler):
                call = storage.move if verb == "move" else storage.copy
                result = await call(operations=[pair], authority=MINTERS[minter])
        finally:
            await second.close()
        assert rivals and rivals[0].success is True, rivals[0].errors if rivals else "the rival never ran"
        leg = f"{storage._host.profile.name}/{seam}/{verb}/{minter}"
        await check(storage, "transfer", result, minted, "/p/q/d", LEVEL_RANK["none"], leg)


# ---------------------------------------------------------------------------
# Restore keeps the relabelled label
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("env_var", ENGINE_LEGS)
async def test_restore_after_a_tightening(env_var: str) -> None:
    async with server_storage(env_var, posture="none") as storage:
        await label_world(storage)
        assert (await storage.delete(path=Path("/p/d/f.txt"), authority=SYSTEM)).success is True
        assert (await storage.posture(path=Path("/p/d"), posture="none")).success is True
        restored = await storage.restore(path=Path("/p/d/f.txt"), authority=SYSTEM)
        assert restored.success is True, restored.errors
        leg = storage._host.profile.name
        await check(storage, "restore", restored, ("/p/d/f.txt",), "/p/d/f.txt", LEVEL_RANK["none"], leg)


# ---------------------------------------------------------------------------
# Counts: statements per call
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("env_var", ENGINE_LEGS)
async def test_statement_counts(env_var: str) -> None:
    async with server_storage(env_var, posture="none") as storage:
        await label_world(storage)
        assert (await storage.grant(path=Path("/p"), principal="bob", level="read_write")).success is True
        engine = storage._host.profile.name
        # Warm the rights cache and the first-touch statements out of the counts.
        assert (await storage.write(entries=[Entry(path=Path("/p/warm.txt"), content="w")], authority=BOB)).success
        assert (await storage.write(entries=[Entry(path=Path("/p/warm2.txt"), content="w")])).success
        seen, listener = counted(storage)
        try:
            for who, minter in MINTERS.items():
                seen.clear()
                one = [Entry(path=Path(f"/p/one-{who}.txt"), content="x")]
                assert (await storage.write(entries=one, authority=minter)).success is True
                record("statements", engine=engine, call="new file", minter=who, statements=len(seen))
                seen.clear()
                assert (await storage.write(entries=one, authority=minter)).success is True
                record("statements", engine=engine, call="rewrite, no mint", minter=who, statements=len(seen))
                seen.clear()
                batch = [Entry(path=Path(f"/p/b-{who}/d{i % 100}/f{i}.txt"), content="x") for i in range(10_000)]
                written = await storage.write(entries=batch, parents=True, authority=minter)
                assert written.success is True, written.errors
                record("statements", engine=engine, call="10,000 files with parents", minter=who, statements=len(seen))
                seen.clear()
                pair = ResolvedPair(src=Path(f"/p/one-{who}.txt"), dest=Path(f"/p/moved-{who}.txt"))
                assert (await storage.move(operations=[pair], authority=minter)).success is True
                record("statements", engine=engine, call="move one file", minter=who, statements=len(seen))
                seen.clear()
                pair = ResolvedPair(src=Path(f"/p/moved-{who}.txt"), dest=Path(f"/p/copied-{who}.txt"))
                assert (await storage.copy(operations=[pair], authority=minter)).success is True
                record("statements", engine=engine, call="copy one file", minter=who, statements=len(seen))
        finally:
            event.remove(storage._host.engine.sync_engine, "before_cursor_execute", listener)


# ---------------------------------------------------------------------------
# Contention: writers, a posture change with its relabel, and a purge, side by side
# ---------------------------------------------------------------------------


async def multixact(storage: DatabaseStorage) -> int | None:
    """Postgres's next multixact id, read after a checkpoint; ``None`` on every other engine."""
    if storage._host.profile.name != "postgresql":
        return None
    async with storage._host.engine.connect() as conn:
        auto = await conn.execution_options(isolation_level="AUTOCOMMIT")
        await auto.execute(text("CHECKPOINT"))
        found = await auto.execute(text("SELECT next_multixact_id FROM pg_control_checkpoint()"))
        return int(found.scalar_one())


# ---------------------------------------------------------------------------
# Who waits while a posture write is open: every row written, nothing committed
# ---------------------------------------------------------------------------

# How long a call may take before it is recorded as waiting on the open posture write.
WAITS_AFTER = 2.5


@pytest.mark.parametrize("env_var", ENGINE_LEGS)
async def test_who_waits_while_a_posture_write_is_open(env_var: str) -> None:
    from vfs.storage.backends.database import rights as rights_module

    if "posture:before-commit" not in open(rights_module.__file__).read():
        pytest.skip("this copy has no seam at the end of the posture write")
    async with server_storage(env_var, posture="none") as storage:
        await label_world(storage)
        assert (await storage.grant(path=Path("/p"), principal="bob", level="read_write")).success is True
        asyncio.get_running_loop().set_default_executor(ThreadPoolExecutor(64))
        engine = storage._host.profile.name
        admin, callers = sibling(env_var, storage), sibling(env_var, storage)
        f, g = Path("/p/d/f.txt"), Path("/p/d/sub/g.txt")
        calls = {
            "read, system": lambda: callers.read(path=f),
            "read, granted caller": lambda: callers.read(path=f, authority=BOB),
            "read, caller with the posture only": lambda: callers.read(path=f, authority=CAROL),
            "read, anonymous": lambda: callers.read(path=f, authority=ANONYMOUS),
            "glob, granted caller": lambda: callers.glob(patterns=("/p/**",), authority=BOB),
            "grep, granted caller": lambda: callers.grep(pattern="f", allow_scan=True, authority=BOB),
            "rewrite an existing file, system": lambda: callers.write(entries=[Entry(path=f, content="f2")]),
            "rewrite an existing file, granted caller": lambda: callers.write(
                entries=[Entry(path=Path("/p/d/sub/g.txt"), content="g2")], authority=BOB
            ),
            "create a file, system": lambda: callers.write(entries=[Entry(path=Path("/p/new-s.txt"), content="n")]),
            "create a file, granted caller": lambda: callers.write(
                entries=[Entry(path=Path("/p/new-b.txt"), content="n")], authority=BOB
            ),
            "grant, system": lambda: callers.grant(path=Path("/p/d"), principal="dave", level="read"),
        }
        found: dict[str, str] = {}
        pending: list[asyncio.Future[Result]] = []

        async def probe() -> Result:
            for name, call in calls.items():
                task = asyncio.ensure_future(call())
                done, _ = await asyncio.wait({task}, timeout=WAITS_AFTER)
                found[name] = "returns" if done else "waits"
                pending.append(task)
            return Result(ops=("posture",))

        handler, _ = self_clearing("posture:before-commit", probe)
        try:
            with seams.installed("posture:before-commit", handler):
                changed = await admin.posture(path=g.parent_dir, posture="read")
            after = await asyncio.wait_for(asyncio.gather(*pending, return_exceptions=True), timeout=60)
        finally:
            await admin.close()
            await callers.close()
        finished = {
            name: ("success" if getattr(result, "success", False) else f"failed: {str(result)[:80]}")
            for name, result in zip(calls, after, strict=True)
        }
        record("who-waits", engine=engine, while_open=found, once_committed=finished, posture=changed.success)


# The posture write's stamp statement, in each engine's no-wait form: it must fail while a mint shares the lock.
_NO_WAIT = {
    "postgresql": ["SET LOCAL lock_timeout = '300ms'", "UPDATE {t} SET revision = revision WHERE principal_id = '*'"],
    "mariadb": ["SET SESSION innodb_lock_wait_timeout = 1", "UPDATE {t} SET revision = revision WHERE principal_id = '*'"],
    "mssql": ["SET LOCK_TIMEOUT 300", "UPDATE {t} SET revision = revision WHERE principal_id = '*'"],
    "oracle": ["SELECT revision FROM {t} WHERE principal_id = '*' FOR UPDATE NOWAIT"],
}


@pytest.mark.parametrize("env_var", ENGINE_LEGS)
async def test_lock_probes(env_var: str) -> None:
    from vfs.storage.backends.database import labels as labels_module

    if not hasattr(labels_module, "everyone_stamp"):
        pytest.skip("the unfixed tree takes no lock")
    async with server_storage(env_var, posture="none") as storage:
        await label_world(storage)
        host = storage._host
        engine = host.profile.name
        revisions = host.tables.principal_revisions
        async with host.session_factory() as first, host.session_factory() as second, host.session_factory() as admin:
            name = first.get_bind().dialect.identifier_preparer.format_table(revisions)
            await labels_module.everyone_stamp(first, host.tables, host.profile)
            # A second mint's shared lock beside the first: it must be granted, and at once.
            try:
                await asyncio.wait_for(labels_module.everyone_stamp(second, host.tables, host.profile), timeout=5)
                sharers = "share"
            except TimeoutError:
                sharers = "BLOCK"
            # A posture write's stamp behind two sharers: it must not be granted.
            try:
                for statement in _NO_WAIT[engine]:
                    await admin.execute(text(statement.format(t=name)))
                posture = "GRANTED"
            except Exception as exc:
                posture = f"waits ({' '.join(str(getattr(exc, 'orig', exc)).split())[:110]})"
            await admin.rollback()
            await first.rollback()
            await second.rollback()
        record("locks", engine=engine, sharer_beside_sharer=sharers, posture_behind_sharers=posture)
        assert sharers == "share" and posture.startswith("waits"), (sharers, posture)


@pytest.mark.parametrize("env_var", ENGINE_LEGS)
async def test_contention(env_var: str) -> None:
    async with server_storage(env_var, posture="none") as storage:
        await label_world(storage)
        assert (await storage.grant(path=Path("/p"), principal="bob", level="read_write")).success is True
        doomed = [Entry(path=Path(f"/p/doomed/f{i}.txt"), content="x") for i in range(200)]
        assert (await storage.write(entries=doomed, parents=True)).success is True
        assert (await storage.delete(path=Path("/p/doomed"))).success is True
        engine = storage._host.profile.name
        writers = int(os.environ.get("LABEL_EXPERIMENT_WRITERS", "16"))
        handles = [sibling(env_var, storage) for _ in range(writers + 2)]
        outcomes: dict[str, int] = {}
        before = await multixact(storage)

        def tally(result: Result) -> None:
            if result.success:
                key = "success"
            else:
                key = "|".join(sorted({f"{e.kind}{'/retryable' if e.retryable else ''}" for e in result.errors}))
                if key != f"{ErrorKind.conflict}/retryable":
                    details = [" ".join(str(getattr(e, "detail", e)).split())[:400] for e in result.errors]
                    record("contention-error", engine=engine, ops=list(result.ops), outcome=key, details=details)
            outcomes[key] = outcomes.get(key, 0) + 1

        async def writer(index: int) -> None:
            handle = handles[index]
            minter = BOB if index % 2 else None
            for n in range(50):
                entries = [Entry(path=Path(f"/p/w{index}/f{n}.txt"), content="x")]
                tally(await handle.write(entries=entries, parents=True, authority=minter))

        async def admin() -> None:
            for level in ("none", "read_write", "none"):
                await asyncio.sleep(0.05)
                tally(await handles[writers].posture(path=Path("/p"), posture=level))

        async def purger() -> None:
            await asyncio.sleep(0.05)
            tally(await handles[writers + 1].sweep(path=Path("/.vfs/trash")))

        # aioodbc runs each call on the loop's default executor; THREADS caps it (the default is cpus + 4).
        threads = int(os.environ.get("LABEL_EXPERIMENT_THREADS", "64"))
        asyncio.get_running_loop().set_default_executor(ThreadPoolExecutor(threads))
        hung = False
        try:
            work = asyncio.gather(*(writer(i) for i in range(writers)), admin(), purger())
            await asyncio.wait_for(work, timeout=150)
        except TimeoutError:
            hung = True
            # Written before anything else touches the engine: on a starved executor nothing else returns.
            record("contention", engine=engine, threads=threads, writers=writers, hung=True, outcomes=outcomes)
        finally:
            if not hung:
                for handle in handles:
                    await handle.close()
        assert not hung, f"{engine}: the run did not finish in 150 s on {threads} threads"
        after = await multixact(storage)
        created = None if before is None or after is None else after - before
        left = await marks(storage)
        record(
            "contention", engine=engine, threads=threads, writers=writers, hung=False, outcomes=outcomes,
            multixacts_created=created, marks_left=left,
        )
        # A posture call that lost a chunk leaves its mark for the next call; run what that call would.
        if left:
            assert (await storage._settled(Result(ops=("posture",)))).success is True
        assert await marks(storage) == 0
        entry = storage._host.tables.entry
        async with storage._host.session_factory() as session:
            rows = await session.execute(
                select(entry.c.path, entry.c.everyone_level).where(entry.c.path.like("/p/w%"))
            )
            have = {row.path: row.everyone_level for row in rows}
        want = await standing(storage, tuple(have))
        wrong = {path: (have[path], want[path]) for path in have if have[path] != want[path]}
        record("contention-labels", engine=engine, rows=len(have), wrong=len(wrong), sample=dict(list(wrong.items())[:3]))
        assert not wrong, f"{engine}: {len(wrong)} of {len(have)} rows carry a stale label"
        lawful = {"success", f"{ErrorKind.conflict}/retryable"}
        assert set(outcomes) <= lawful, outcomes
