"""Shared plumbing for the SQL Server membership-read probes.

A `Probe` mints a vfs table namespace on the live SQL Server container
(`VFS_TEST_MSSQL_URL`), writes three non-ASCII "canary" paths through the
vfs write verb, grows the entry table with a raw set-based INSERT (rows
are minimal but lawful: unique entry_id, path, name under /n), and
exposes helpers to time a statement, read the locks it holds, pull the
executed plan from the plan cache by a marker comment, and read the
table's lock-promotion counters. Everything is dropped on exit.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from ulid import ULID

from vfs.models import Entry
from vfs.models.rows import build_vfs_tables
from vfs.paths import Path
from vfs.storage.backends.database import DatabaseStorage

UTF8_BIN2 = "Latin1_General_100_BIN2_UTF8"
# Code-page canaries: a varchar bind squeezed through CP-1252 keeps the
# first, mangles the other two to '?', and then matches nothing.
CANARIES = ["/n/café.py", "/n/日本語.py", "/n/emoji-\U0001f600.py"]

LOCKS_SQL = text(
    "SELECT resource_type, request_mode, COUNT(*) AS n FROM sys.dm_tran_locks "
    "WHERE request_session_id = @@SPID GROUP BY resource_type, request_mode"
)


def synthetic_path(i: int) -> str:
    return f"/n/{i:07d}.py"


def synthetic_ulid(i: int) -> str:
    return str(ULID.from_bytes(i.to_bytes(16, "big")))


@dataclass
class PlanFacts:
    ops: list[str]
    param_types: list[str]
    convert_implicit: bool
    early_abort: str | None
    compile_ms: int | None
    est_rows: float | None
    shape: str

    def __str__(self) -> str:
        return f"{self.shape} params={self.param_types} convert={self.convert_implicit} abort={self.early_abort} compile={self.compile_ms}ms est={self.est_rows}"


def plan_facts(plan: str) -> PlanFacts:
    ops = re.findall(r'PhysicalOp="([^"]+)"', plan)
    params = sorted({p for _, p in re.findall(r'<ColumnReference Column="(@P\d+)" ParameterDataType="([^"]+)"', plan)})
    abort = re.search(r'StatementOptmEarlyAbortReason="([^"]+)"', plan)
    compile_ms = re.search(r'CompileTime="(\d+)"', plan)
    est = re.search(r'StatementEstRows="([^"]+)"', plan)
    key = [o for o in ops if o in ("Index Seek", "Clustered Index Seek", "Clustered Index Scan", "Index Scan", "Filter", "Merge Interval", "Table Scan", "Hash Match", "Merge Join", "Sort", "Table-valued function", "Table Insert")]
    if "Clustered Index Scan" in ops or "Index Scan" in ops or "Table Scan" in ops:
        shape = "SCAN"
    elif "Index Seek" in ops or "Clustered Index Seek" in ops:
        shape = "SEEK"
    else:
        shape = "?"
    return PlanFacts(ops, params, "CONVERT_IMPLICIT" in plan, abort.group(1) if abort else None, int(compile_ms.group(1)) if compile_ms else None, float(est.group(1)) if est else None, shape + ":" + ">".join(dict.fromkeys(key)))


class Probe:
    def __init__(self, url: str | None = None) -> None:
        self.url = url or os.environ["VFS_TEST_MSSQL_URL"]
        self.tn = f"vfs_{uuid4().hex[:10]}"
        self.storage = DatabaseStorage(url=self.url, table_name=self.tn)
        self.rows = 0
        self.parent_id: bytes = b""

    async def __aenter__(self) -> Probe:
        await self.storage.mkdir(path=Path("/n"))
        assert (await self.storage.write(entries=[Entry(path=Path(p), content="x") for p in CANARIES])).success
        async with self.session() as s:
            self.parent_id = (await s.execute(text(f"SELECT entry_id FROM {self.tn} WHERE path = '/n'"))).scalar_one()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.storage.close()
        eng = create_async_engine(self.url)
        async with eng.begin() as c:
            await c.run_sync(build_vfs_tables(table_name=self.tn).metadata.drop_all)
        await eng.dispose()

    @property
    def tables(self):
        return self.storage._host.tables

    @property
    def host(self):
        return self.storage._host

    def session(self) -> AsyncSession:
        return self.storage._host.session_factory()

    async def grow(self, total: int, slice_size: int = 100_000) -> float:
        """Add synthetic file rows until the table holds *total* of them; returns seconds."""
        t0 = time.perf_counter()
        eng = create_async_engine(self.url, isolation_level="AUTOCOMMIT")
        async with eng.connect() as c:
            while self.rows < total:
                lo, hi = self.rows, min(total, self.rows + slice_size)
                await c.execute(
                    text(
                        f"INSERT INTO {self.tn} (entry_id, parent_id, path, name, kind, version, ext, lines, size_bytes, chunked, encoded, indexable) "
                        f"SELECT CAST(value AS binary(16)), :parent, '/n/' + RIGHT('0000000' + CAST(value AS varchar(10)), 7) + '.py', "
                        f"RIGHT('0000000' + CAST(value AS varchar(10)), 7) + '.py', 'file', 1, 'py', 1, 1, 0, 0, 0 "
                        f"FROM GENERATE_SERIES(:lo, :hi)"
                    ),
                    {"parent": self.parent_id, "lo": lo, "hi": hi - 1},
                )
                self.rows = hi
            await c.execute(text(f"UPDATE STATISTICS {self.tn} WITH FULLSCAN"))
            await c.execute(text("DBCC FREEPROCCACHE WITH NO_INFOMSGS"))
        await eng.dispose()
        return time.perf_counter() - t0

    def paths(self, k: int, *, canaries: bool = True) -> list[str]:
        """*k* sorted synthetic paths, the canaries replacing the last three when asked."""
        base = [synthetic_path(i) for i in range(k - (3 if canaries else 0))]
        return sorted(base + (CANARIES if canaries else []))

    def ulids(self, k: int) -> list[str]:
        return sorted(synthetic_ulid(i) for i in range(k))

    async def locks(self, session: AsyncSession) -> dict[str, int]:
        return {f"{r.resource_type}:{r.request_mode}": r.n for r in await session.execute(LOCKS_SQL)}

    async def promotions(self, session: AsyncSession | None = None) -> tuple[int, int]:
        """(attempts, successes) of lock escalation on the entry table, cumulative.

        Read on its own autocommit connection: inside the probe's transaction the
        DMV answered inconsistently (deltas went negative), outside it is monotone.
        """
        sql = text(
            "SELECT ISNULL(SUM(index_lock_promotion_attempt_count),0), ISNULL(SUM(index_lock_promotion_count),0) "
            f"FROM sys.dm_db_index_operational_stats(DB_ID(), OBJECT_ID('{self.tn}'), NULL, NULL)"
        )
        eng = create_async_engine(self.url, isolation_level="AUTOCOMMIT")
        try:
            async with eng.connect() as c:
                row = (await c.execute(sql)).one()
        finally:
            await eng.dispose()
        return int(row[0]), int(row[1])

    async def plan(self, session: AsyncSession, marker: str) -> PlanFacts | None:
        plan = (
            await session.execute(
                text(
                    "SELECT TOP 1 CAST(qp.query_plan AS nvarchar(max)) FROM sys.dm_exec_query_stats qs "
                    "CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) st CROSS APPLY sys.dm_exec_query_plan(qs.plan_handle) qp "
                    f"WHERE st.text LIKE '%{marker}%' AND st.text NOT LIKE '%dm_exec_query_stats%' ORDER BY qs.last_execution_time DESC"
                )
            )
        ).scalar()
        return plan_facts(plan) if plan else None


def canary_hits(rows: list[Any]) -> int:
    got = {r[0] for r in rows}
    return sum(1 for c in CANARIES if c in got)
