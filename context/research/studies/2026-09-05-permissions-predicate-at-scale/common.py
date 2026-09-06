"""Shared plumbing for the permissions-predicate probes.

A `Bench` opens one async SQLAlchemy engine on a study URL, mints a
`vfs_s1_<hex>` table namespace holding a lean copy of the vfs entry
table (only the columns the grant predicate reads, with the same index
shape: unique `path`, index `owner_id`, index `(ext, kind)`), the grant
tables, the membership table and a materialised-visibility sample,
loads the deterministic corpus through Core's executemany pages,
refreshes statistics, and exposes `timeit` (warm, n reps, median) and
`plan` (the engine's own plan text, summarised). Everything is dropped
on exit, and any `vfs_s1_%` leftovers from a crashed run are dropped
on entry.
"""

from __future__ import annotations

import os
import re
import statistics
import time
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    event,
    insert,
    text,
)
from sqlalchemy.dialects.mysql import VARBINARY
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from sqlalchemy.types import TypeDecorator

from vfs.storage.backends.database.dialects import DialectProfile, membership_budget, profile_for

from corpus import Corpus

MSSQL_COLLATION = "Latin1_General_100_BIN2_UTF8"
PATH_LEN = 1024
ENGINE_ENV = {
    "postgres": "VFS_TEST_POSTGRES_URL",
    "mssql": "VFS_TEST_MSSQL_URL",
    "oracle": "VFS_TEST_ORACLE_URL",
    "mariadb": "VFS_TEST_MARIADB_URL",
}
SQLITE_PRAGMAS = (
    "PRAGMA journal_mode = WAL",
    "PRAGMA synchronous = OFF",
    "PRAGMA case_sensitive_like = ON",
    "PRAGMA cache_size = -262144",
    "PRAGMA mmap_size = 8589934592",
)


def url_for(engine: str, study_dir: str) -> str:
    if engine == "sqlite":
        return f"sqlite+aiosqlite:///{os.path.join(study_dir, 'vfs_s1_corpus.sqlite')}"
    return os.environ[ENGINE_ENV[engine]]


@dataclass
class Timing:
    median_ms: float
    min_ms: float
    max_ms: float
    rows: int
    reps: int
    statements: int = 1
    note: str = ""

    def __str__(self) -> str:
        s = f"{self.median_ms:.1f} ms (min {self.min_ms:.1f}, rows {self.rows}"
        if self.statements != 1:
            s += f", {self.statements} stmts"
        return s + (f", {self.note})" if self.note else ")")


class _BinaryPath(TypeDecorator[str]):
    """VARBINARY path key on the MySQL family (vfs's BytewiseString choice): str in, str out."""

    impl = VARBINARY
    cache_ok = True

    def process_bind_param(self, value, dialect):  # noqa: ANN001, ANN201
        return None if value is None else value.encode("utf-8")

    def process_result_value(self, value, dialect):  # noqa: ANN001, ANN201
        return None if value is None else bytes(value).decode("utf-8")


class Bench:
    def __init__(self, engine: str, study_dir: str) -> None:
        self.engine_name = engine
        self.url = url_for(engine, study_dir)
        self.study_dir = study_dir
        self.ns = f"vfs_s1_{uuid4().hex[:8]}"
        kwargs: dict[str, Any] = {}
        if engine == "mssql":
            kwargs["use_setinputsizes"] = False
        self.engine: AsyncEngine = create_async_engine(self.url, **kwargs)
        if engine == "sqlite":
            @event.listens_for(self.engine.sync_engine, "connect")
            def _pragmas(dbapi_conn, _record):  # noqa: ANN001
                for p in SQLITE_PRAGMAS:
                    dbapi_conn.execute(p)
        self.dialect = self.engine.dialect
        self.profile: DialectProfile = profile_for(self.dialect.name)
        self.parameter_budget: int = self.dialect.insertmanyvalues_max_parameters
        self.membership_budget: int = membership_budget(self.profile, self.parameter_budget)
        self.metadata = MetaData()
        self.t = self._tables()
        self.conn: AsyncConnection | None = None
        self.last_plan_raw = ""

    # -- schema ---------------------------------------------------------------
    def _path_type(self):  # noqa: ANN202
        if self.dialect.name == "mssql":
            return String(PATH_LEN, collation=MSSQL_COLLATION)
        if self.dialect.name == "postgresql":
            return String(PATH_LEN, collation="C")
        if self.dialect.name in ("mysql", "mariadb"):
            return _BinaryPath(PATH_LEN)
        return String(PATH_LEN)

    def _id_type(self):  # noqa: ANN202
        if self.dialect.name == "mssql":
            return String(255, collation=MSSQL_COLLATION)
        return String(255)

    def _tables(self) -> dict[str, Table]:
        ns, md = self.ns, self.metadata
        entry = Table(
            f"{ns}_entry", md,
            Column("id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=False),
            Column("path", self._path_type(), nullable=False),
            Column("owner_id", self._id_type()),
            Column("kind", String(32), nullable=False),
            Column("ext", String(32)),
            Column("size_bytes", Integer, nullable=False),
            Column("deleted_at", DateTime(timezone=True)),
        )
        def grants(name: str) -> Table:
            return Table(
                f"{ns}_{name}", md,
                Column("principal_id", self._id_type(), nullable=False),
                Column("path_prefix", self._path_type(), nullable=False),
                Column("lvl", String(16), nullable=False),
            )
        member = Table(
            f"{ns}_member", md,
            Column("principal_id", self._id_type(), nullable=False),
            Column("group_id", self._id_type(), nullable=False),
        )
        vis = Table(
            f"{ns}_vis", md,
            Column("principal_id", self._id_type(), nullable=False),
            Column("entry_id", BigInteger().with_variant(Integer, "sqlite"), nullable=False),
        )
        return {"entry": entry, "grant": grants("grant"), "grantg": grants("grantg"), "grantgx": grants("grantgx"), "member": member, "vis": vis}

    def _indexes(self) -> list[Index]:
        ns, t = self.ns, self.t
        ix = [
            Index(f"ux_{ns}_entry_path", t["entry"].c.path, unique=True),
            Index(f"ix_{ns}_entry_owner", t["entry"].c.owner_id),
            Index(f"ix_{ns}_entry_ext_kind", t["entry"].c.ext, t["entry"].c.kind),
            Index(f"ix_{ns}_member_p", t["member"].c.principal_id, t["member"].c.group_id),
            Index(f"ux_{ns}_vis", t["vis"].c.principal_id, t["vis"].c.entry_id, unique=True),
        ]
        for g in ("grant", "grantg", "grantgx"):
            ix.append(Index(f"ix_{ns}_{g}_pp", t[g].c.principal_id, t[g].c.path_prefix))
        return ix

    # -- lifecycle ------------------------------------------------------------
    async def __aenter__(self) -> Bench:
        await self.drop_stale()
        self.conn = await self.engine.connect()
        await self.conn.run_sync(self.metadata.create_all)
        await self.conn.commit()
        return self

    async def __aexit__(self, *exc: object) -> None:
        try:
            if self.conn is not None:
                await self.conn.rollback()
                await self.conn.run_sync(self.metadata.drop_all)
                await self.conn.commit()
                await self.conn.close()
        finally:
            await self.engine.dispose()
            if self.engine_name == "sqlite":
                for suffix in ("", "-wal", "-shm"):
                    p = os.path.join(self.study_dir, "vfs_s1_corpus.sqlite" + suffix)
                    if os.path.exists(p):
                        os.remove(p)

    async def drop_stale(self) -> None:
        """Drop any vfs_s1_% table a crashed run left behind."""
        q = {
            "postgresql": "SELECT tablename FROM pg_tables WHERE schemaname = current_schema() AND tablename LIKE 'vfs_s1_%'",
            "mssql": "SELECT name FROM sys.tables WHERE name LIKE 'vfs_s1_%'",
            "oracle": "SELECT table_name FROM user_tables WHERE LOWER(table_name) LIKE 'vfs_s1_%'",
            "mariadb": "SELECT table_name FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name LIKE 'vfs_s1_%'",
            "mysql": "SELECT table_name FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name LIKE 'vfs_s1_%'",
            "sqlite": "SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'vfs_s1_%'",
        }[self.dialect.name]
        async with self.engine.begin() as c:
            names = [r[0] for r in await c.execute(text(q))]
            for n in names:
                await c.execute(text(f"DROP TABLE {n}"))
        if names:
            print(f"  dropped {len(names)} stale vfs_s1_* tables")

    # -- loading --------------------------------------------------------------
    async def load(self, corpus: Corpus, vis_principals: list[str]) -> dict[str, float]:
        assert self.conn is not None
        c = self.conn
        t = self.t
        times: dict[str, float] = {}
        t0 = time.perf_counter()
        rows = [
            {"id": i, "path": p, "owner_id": o, "kind": k, "ext": x, "size_bytes": s, "deleted_at": None if d is None else _DELETED}
            for i, p, o, k, x, s, d in corpus.entries
        ]
        await self._bulk(t["entry"], rows)
        times["entry"] = time.perf_counter() - t0
        for name, data in (("grant", corpus.grant_flat), ("grantg", corpus.grant_g), ("grantgx", corpus.grant_gx)):
            t0 = time.perf_counter()
            await self._bulk(t[name], [{"principal_id": p, "path_prefix": pf, "lvl": lv} for p, pf, lv in data])
            times[name] = time.perf_counter() - t0
        t0 = time.perf_counter()
        await self._bulk(t["member"], [{"principal_id": p, "group_id": g} for p, g in corpus.member])
        times["member"] = time.perf_counter() - t0
        t0 = time.perf_counter()
        vis_rows: list[dict[str, Any]] = []
        for p in vis_principals:
            ids: set[int] = set()
            for pf in corpus.prefixes_of(p):
                ids.update(corpus.subtree_ids(pf))
            vis_rows.extend({"principal_id": p, "entry_id": i} for i in sorted(ids))
        await self._bulk(t["vis"], vis_rows)
        times["vis"] = time.perf_counter() - t0
        times["vis_rows"] = len(vis_rows)
        t0 = time.perf_counter()
        for ix in self._indexes():
            await c.run_sync(ix.create)
        await c.commit()
        await self.analyze()
        times["index+stats"] = time.perf_counter() - t0
        return times

    async def _bulk(self, table: Table, rows: list[dict[str, Any]], page: int = 20_000) -> None:
        assert self.conn is not None
        for i in range(0, len(rows), page):
            await self.conn.execute(insert(table), rows[i : i + page])
        await self.conn.commit()

    async def analyze(self) -> None:
        assert self.conn is not None
        d = self.dialect.name
        stmts: list[str] = []
        for tb in self.t.values():
            n = tb.name
            if d == "postgresql":
                stmts.append(f"ANALYZE {n}")
            elif d == "mssql":
                stmts.append(f"UPDATE STATISTICS {n} WITH FULLSCAN")
            elif d == "oracle":
                stmts.append(f"BEGIN DBMS_STATS.GATHER_TABLE_STATS(USER, '{n.upper()}', cascade => TRUE); END;")
            elif d in ("mysql", "mariadb"):
                stmts.append(f"ANALYZE TABLE {n}")
            elif d == "sqlite":
                stmts.append(f"ANALYZE {n}")
        for s in stmts:
            await self.conn.execute(text(s))
        await self.conn.commit()
        if d == "mssql":
            await self.conn.execute(text("DBCC FREEPROCCACHE WITH NO_INFOMSGS"))
            await self.conn.commit()

    # -- SQL dialect helpers ----------------------------------------------------
    def concat(self, a: str, b: str) -> str:
        return f"CONCAT({a}, {b})" if self.dialect.name in ("mssql", "mysql", "mariadb") else f"({a} || {b})"

    def pbind(self, name: str) -> str:
        """A path-typed bind: cast through the UTF-8 collation on SQL Server so the seek survives."""
        if self.dialect.name == "mssql":
            return f"CAST(:{name} COLLATE {MSSQL_COLLATION} AS varchar({PATH_LEN}))"
        return f":{name}"

    def sbind(self, name: str) -> str:
        """A principal-id bind, cast through the column's collation and length on SQL Server."""
        if self.dialect.name == "mssql":
            return f"CAST(:{name} COLLATE {MSSQL_COLLATION} AS varchar(255))"
        return f":{name}"

    def values_table(self, n: int, prefix: str) -> tuple[str, str] | None:
        """(FROM-clause fragment, column ref) for a VALUES join of *n* integer ids, or None."""
        vals = ", ".join(f"(:{prefix}{i})" for i in range(n))
        d = self.dialect.name
        if d == "postgresql":
            vals = ", ".join(f"(CAST(:{prefix}{i} AS bigint))" for i in range(n))
            return f"(VALUES {vals}) AS cand (id)", "cand.id"
        if d == "mssql":
            return f"(VALUES {vals}) AS cand (id)", "cand.id"
        if d == "oracle":
            return f"(VALUES {vals}) cand (id)", "cand.id"
        if d in ("sqlite", "mariadb", "mysql"):
            return f"(WITH cte (id) AS (VALUES {vals}) SELECT id FROM cte) AS cand", "cand.id"
        return None

    # -- measurement ------------------------------------------------------------
    async def timeit(self, sql: str | list[tuple[str, dict[str, Any]]], params: dict[str, Any] | None = None, reps: int = 5, cap_s: float = 60.0) -> Timing:
        """Median wall time over *reps* warm runs; a list of (sql, params) is one logical query of several statements."""
        assert self.conn is not None
        stmts = [(sql, params or {})] if isinstance(sql, str) else sql
        await self.conn.rollback()
        samples: list[float] = []
        rows = 0
        note = ""
        for r in range(reps + 1):
            t0 = time.perf_counter()
            n = 0
            for s, p in stmts:
                res = await self.conn.execute(text(s), p)
                n += len(res.fetchall())
            dt = (time.perf_counter() - t0) * 1000
            await self.conn.rollback()
            if r == 0:
                rows = n
                first = dt
                if dt > cap_s * 1000:
                    note = f"capped after first run {dt / 1000:.0f}s"
                    samples.append(dt)
                    break
                continue
            samples.append(dt)
        return Timing(statistics.median(samples), min(samples), max(samples), rows, len(samples), len(stmts), note or (f"first {first:.0f}" if first > 2 * statistics.median(samples) and first > 50 else ""))

    async def plan(self, sql: str, params: dict[str, Any] | None = None) -> str:
        """The engine's plan for *sql*, compressed to its operator skeleton."""
        assert self.conn is not None
        params = params or {}
        d = self.dialect.name
        try:
            if d == "postgresql":
                res = await self.conn.execute(text("EXPLAIN (ANALYZE, FORMAT TEXT) " + sql), params)
                lines = [r[0] for r in res.fetchall()]
                self.last_plan_raw = "\n".join(lines)
                return _pg_summary(lines)
            if d == "sqlite":
                res = await self.conn.execute(text("EXPLAIN QUERY PLAN " + sql), params)
                return " | ".join(str(r[-1]) for r in res.fetchall())[:400]
            if d in ("mysql", "mariadb"):
                res = await self.conn.execute(text("EXPLAIN " + sql), params)
                rows = res.mappings().all()
                return " | ".join(f"{r['select_type']}:{r['table']}:{r['type']}:{r['key']}:{r['rows']}" for r in rows)[:400]
            if d == "oracle":
                sid = uuid4().hex[:12]
                await self.conn.execute(text(f"EXPLAIN PLAN SET STATEMENT_ID = '{sid}' FOR " + sql), params)
                res = await self.conn.execute(text(f"SELECT plan_table_output FROM TABLE(DBMS_XPLAN.DISPLAY('PLAN_TABLE', '{sid}', 'BASIC ROWS'))"))
                lines = [r[0] for r in res.fetchall()]
                self.last_plan_raw = "\n".join(lines)
                await self.conn.execute(text(f"DELETE FROM plan_table WHERE statement_id = '{sid}'"))
                return _oracle_summary(lines)
            if d == "mssql":
                marker = f"S1PLAN{uuid4().hex[:8]}"
                res = await self.conn.execute(text(f"/* {marker} */ " + sql), params)
                res.fetchall()
                res = await self.conn.execute(
                    text(
                        "SELECT TOP 1 CAST(qp.query_plan AS nvarchar(max)) FROM sys.dm_exec_query_stats qs "
                        "CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) st CROSS APPLY sys.dm_exec_query_plan(qs.plan_handle) qp "
                        f"WHERE st.text LIKE '%{marker}%' AND st.text NOT LIKE '%dm_exec_query_stats%' ORDER BY qs.last_execution_time DESC"
                    )
                )
                xml = res.scalar()
                return _mssql_summary(xml or "")
        except Exception as exc:  # noqa: BLE001 — a plan failure must not sink the timing row
            await self.conn.rollback()
            return f"plan unavailable: {type(exc).__name__}: {str(exc)[:120]}"
        finally:
            await self.conn.rollback()
        return "?"


_DELETED = __import__("datetime").datetime(2026, 1, 1, tzinfo=__import__("datetime").timezone.utc)


def _pg_summary(lines: list[str]) -> str:
    ops: list[str] = []
    total = ""
    for ln in lines:
        m = re.match(r"\s*(?:->\s*)?([A-Z][A-Za-z ]+?)(?: using (\S+))?(?: on (\S+))?(?: \w+)?\s+\(cost", ln)
        if m:
            op = m.group(1).strip()
            tgt = m.group(3) or ""
            tgt = re.sub(r"vfs_s1_[0-9a-f]+_", "", tgt)
            ix = m.group(2) or ""
            ix = re.sub(r"[iu]x_vfs_s1_[0-9a-f]+_", "", ix)
            loops = re.search(r"loops=(\d+)", ln)
            ops.append(op + (f"[{tgt}]" if tgt else "") + (f"({ix})" if ix else "") + (f"x{loops.group(1)}" if loops and int(loops.group(1)) > 1 else ""))
        if ln.startswith("Execution Time"):
            total = ln.split(":")[1].strip()
    return " > ".join(ops)[:300] + (f" [{total}]" if total else "")


def _oracle_summary(lines: list[str]) -> str:
    ops: list[str] = []
    for ln in lines:
        m = re.match(r"\|\s*\d+\s*\|\s*([A-Z][A-Z ()]+?)\s*\|\s*(\S*)\s*\|\s*(\S*)\s*\|", ln)
        if m:
            op = m.group(1).strip()
            name = re.sub(r"(?i)[IU]X_VFS_S1_[0-9A-F]+_|VFS_S1_[0-9A-F]+_", "", m.group(2))
            ops.append(op + (f"[{name}]" if name else "") + (f"~{m.group(3)}" if m.group(3) else ""))
    return " > ".join(ops)[:300]


def _mssql_summary(xml: str) -> str:
    if not xml:
        return "plan not in cache"
    ops = re.findall(r'PhysicalOp="([^"]+)"', xml)
    abort = re.search(r'StatementOptmEarlyAbortReason="([^"]+)"', xml)
    convert = "CONVERT_IMPLICIT" in xml
    objs = re.findall(r'<Object Database=[^>]*?Table="\[([^\]]+)\]"[^>]*?(?:Index="\[([^\]]+)\]")?', xml)
    tbl = " ".join(sorted({re.sub(r"vfs_s1_[0-9a-f]+_", "", (ix or tb)) for tb, ix in objs}))
    est = re.search(r'StatementEstRows="([^"]+)"', xml)
    return ">".join(dict.fromkeys(ops))[:200] + f" | objs: {tbl}" + (f" | abort={abort.group(1)}" if abort else "") + (" | CONVERT_IMPLICIT" if convert else "") + (f" | est={float(est.group(1)):.0f}" if est else "")
