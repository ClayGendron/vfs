"""The three-seek visibility predicate and the posture relabel, on all five engines.

Slice D of spec 150. The 2026-10-02 row-label spike measured the shape
on SQLite and Postgres; this study runs it on SQL Server, MariaDB and
Oracle too, with the statement shapes the spec left open, and records
the chosen shape per dialect. It imports the spike's world, compiler,
truth function and relabel algebra unchanged.

Read mode (``--n``): load the spike's seeded world at N users, compile
the five callers, and time four statements (visible entries; the same
under one shared folder; the visible chunk count through a derived
table; the top 10 chunks by score) in each predicate shape:

- ``union``       (a) plain ``UNION`` of the three branches
- ``unionall``    (b) ``UNION ALL`` of branches 1 and 2, ``UNION`` onto 3
- ``literal``     (c) the inline-predicate form, bound piece by piece
- ``fenced``      (d) Postgres only: (b) with the range branch behind
                      ``OFFSET 0`` and ``SET LOCAL jit = off``
- ``disjoint``    (e) every branch disjoint, ``UNION ALL`` throughout:
                      the owner branch excludes the caller's own ranges
                      with ``NOT EXISTS`` (an extra probe, not in the brief)

Every cell is checked against the spike's Python truth; the sibling
traps are counted separately. Plans are captured per shape. The scoped
read is also timed with branch 1 spelled ``everyone_level IN (...)``
instead of ``>=``, to see which planners seek the composite index.

Writes mode (``--writes``): a 1,000-user world plus ``/mid`` (1,000
rows), ``/mv`` (10,000) and ``/big`` (200,000). The relabel ``UPDATE``
in three forms per dialect (join through the range source; literal OR
of ranges; ``id IN (subquery)``), each chunk of at most 500 pieces its
own transaction, keyset chunks for the big range, the root change
across 1,102 deeper postures, and a 10,001-row move with the
destination label in the same statement. Labels are checked against
the Python labeller after every operation.

    uv run --no-sync python bench.py --engine mssql --n 10000
    uv run --no-sync python bench.py --engine oracle --writes

The spelling each engine needs (``CROSS JOIN`` on SQLite, ``STRAIGHT_JOIN``
+ ``FORCE INDEX`` on MariaDB, ``INNER LOOP JOIN`` on SQL Server, the
``CARDINALITY`` and index hints on Oracle) is the default; ``probe.py``
flips each one through the ``TS_*`` environment knobs on ``Dialect``.

Every table is prefixed ``ts_<hex>_`` and dropped at the end. Study
code only: nothing here is imported by vfs.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import pickle
import random
import statistics
import sys
import time
import xml.etree.ElementTree as ET
from typing import Any
from uuid import uuid4

from sqlalchemy import CLOB, BigInteger, Column, Index, Integer, MetaData, SmallInteger, String, Table, bindparam, event, insert, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from vfs.models.rows import MSSQL_UTF8_COLLATION, BytewiseString

HERE = os.path.dirname(os.path.abspath(__file__))
SPIKE = os.path.join(HERE, "..", "2026-10-02-row-label-grants-spike")
sys.path.insert(0, SPIKE)

from prototype import (  # noqa: E402
    NEXT,
    Compiled,
    Pieces,
    Span,
    compile_rights,
    public_level,
    relabel_spans,
    split,
    truth,
)
from world import NONE, READ, READ_WRITE, World, build, callers  # noqa: E402

SCRATCH = os.environ.get("TS_SCRATCH", "/Users/claygendron/.claude/jobs/b627c391/tmp/sliceD")
SPIKE_SCRATCH = "/Users/claygendron/.claude/jobs/b627c391/tmp/research/rowlabel"
URLS = {
    "postgres": os.environ.get("TS_PG_URL", "postgresql+asyncpg://vfs:vfs@localhost:54320/vfs"),
    "mariadb": os.environ.get("TS_MARIADB_URL", "mariadb+aiomysql://vfs:vfs@localhost:33062/vfs?charset=utf8mb4"),
    "mssql": os.environ.get(
        "TS_MSSQL_URL",
        "mssql+aioodbc://sa:vfsStr0ngPassw0rd@localhost:14330/master"
        "?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes",
    ),
    "oracle": os.environ.get("TS_ORACLE_URL", "oracle+oracledb_async://vfs:vfs@localhost:15210/?service_name=FREEPDB1"),
}
STATEMENTS = ("entries", "scoped", "count", "top10")
SHAPES = ("union", "unionall", "literal", "fenced", "disjoint")
LITERAL_MAX_PIECES = 600  # the inline form is for small rights; the heavy caller at 100k is past this
PIECES_PER_STATEMENT = 500
SQLITE_PRAGMAS = (
    "PRAGMA busy_timeout = 5000",
    "PRAGMA synchronous = FULL",
    "PRAGMA case_sensitive_like = ON",
    "PRAGMA mmap_size = 8589934592",
    "PRAGMA cache_size = -262144",
)
LEVEL_NAME = {0: "none", 1: "read", 2: "read_write"}
PATH_LEN = 1024


# ---------------------------------------------------------------------------
# Dialect spellings
# ---------------------------------------------------------------------------


class Dialect:
    """What each engine needs: path binds, range sources, update-with-join, top-k, plans, sizes."""

    def __init__(self, name: str) -> None:
        self.name = name  # sqlite, postgresql, mssql, mariadb, oracle
        # Spelling knobs the probe flips; the defaults are the chosen spelling per engine.
        self.apply = os.environ.get("TS_MSSQL_APPLY") == "1"  # CROSS APPLY per range (measured: no help)
        self.loop_join = name == "mssql" and os.environ.get("TS_MSSQL_LOOP", "1") == "1"  # INNER LOOP JOIN
        self.force_order = os.environ.get("TS_MSSQL_FORCE") == "1"  # OPTION (FORCE ORDER)
        self.oracle_cardinality = name == "oracle" and os.environ.get("TS_ORACLE_CARD", "1") == "1"  # CARDINALITY(src n)
        self.oracle_one_index = name == "oracle" and os.environ.get("TS_ORACLE_ONE", "1") == "1"  # INDEX on branch 1
        self.oracle_derived_nl = name == "oracle" and os.environ.get("TS_ORACLE_NL", "1") == "1"  # visible set drives chunks
        self.oracle_leading = os.environ.get("TS_ORACLE_LEADING") == "1"  # LEADING/USE_NL/INDEX(path): measured worse
        self.plus_zero = os.environ.get("TS_PLUS_ZERO") == "1"  # ``everyone_level + 0 < :r``: no planner seeks it
        self.pg_nudge = os.environ.get("TS_PG_NUDGE") == "1"  # Postgres: ``AND path LIKE lo || '%'`` to cut the range estimate
        self.mariadb_force = name == "mariadb" and os.environ.get("TS_MARIADB_FORCE", "1") == "1"  # STRAIGHT_JOIN + FORCE INDEX

    def below(self) -> str:
        """The disjointness term on branches 2 and 3."""
        return " AND e.everyone_level + 0 < :lvl" if self.plus_zero else " AND e.everyone_level < :lvl"

    def entry_from(self, t: str) -> str:
        """The entry table in a range branch, with MariaDB pinned to the path index when asked."""
        return f"{t} e FORCE INDEX ({t}_path)" if self.name == "mariadb" and self.mariadb_force else f"{t} e"

    def branch_hint(self, key: str, count: int) -> str:
        """Oracle: drive the range branch from the unpacked pieces and seek the path index per piece."""
        if self.name != "oracle":
            return ""
        parts = []
        if self.oracle_leading:
            parts.append(f"LEADING({key}) USE_NL(e) INDEX(e (path))")
        if self.oracle_cardinality:
            parts.append(f"CARDINALITY({key} {count})")
        return f"/*+ {' '.join(parts)} */ " if parts else ""

    def one_hint(self) -> str:
        """Oracle: branch 1 through the composite index rather than a full scan."""
        return "/*+ INDEX(e (everyone_level path)) */ " if self.name == "oracle" and self.oracle_one_index else ""

    def derived_hint(self) -> str:
        """Oracle: the visible set first, then the chunk index — never the chunks driving the view."""
        return "/*+ NO_MERGE(v) LEADING(v) USE_NL(c) INDEX(c (entry_id)) */ " if self.name == "oracle" and self.oracle_derived_nl else ""

    def tail(self) -> str:
        return " OPTION (FORCE ORDER)" if self.name == "mssql" and self.force_order else ""

    # -- binds --------------------------------------------------------------

    def path(self, value: str) -> Any:
        """A path bound value; MariaDB's path column is VARBINARY."""
        return value.encode() if self.name == "mariadb" else value

    def path_expr(self, key: str) -> str:
        """The bind *key* as an expression comparable to the path column with an index seek."""
        if self.name == "mssql":
            return f"CAST(:{key} COLLATE {MSSQL_UTF8_COLLATION} AS varchar({PATH_LEN}))"
        return f":{key}"

    @property
    def join(self) -> str:
        """SQLite otherwise seeks ``everyone_level < :r`` on the composite and scans the ranges per row."""
        if self.name == "mssql" and self.loop_join:
            return "INNER LOOP JOIN"
        if self.name == "mariadb" and self.mariadb_force:
            return "STRAIGHT_JOIN"
        return "CROSS JOIN" if self.name == "sqlite" else "JOIN"

    def owner_expr(self, key: str) -> str:
        return f"CAST(:{key} AS varchar(255))" if self.name == "mssql" else f":{key}"

    def points(self, key: str, values: list[str]) -> tuple[str, str, dict[str, Any]]:
        """``(FROM fragment, value expr, binds)`` unpacking a list of exact paths."""
        if self.name == "postgresql":
            return f"unnest(CAST(:{key} AS text[])) AS {key}(value)", f'{key}.value COLLATE "C"', {key: values}
        if self.name == "sqlite":
            return f"json_each(:{key}) AS {key}", f"{key}.value", {key: json.dumps(values)}
        if self.name == "mssql":
            frag = f"OPENJSON(:{key}) AS {key}"
            return frag, f"CAST({key}.value COLLATE {MSSQL_UTF8_COLLATION} AS varchar({PATH_LEN}))", {key: json.dumps(values)}
        if self.name == "mariadb":
            frag = f"JSON_TABLE(:{key}, '$[*]' COLUMNS (v VARCHAR({PATH_LEN}) PATH '$')) AS {key}"
            return frag, f"CAST({key}.v AS BINARY)", {key: json.dumps(values)}
        frag = f"JSON_TABLE(:{key}, '$[*]' COLUMNS (v VARCHAR2({PATH_LEN}) PATH '$')) {key}"
        return frag, f"{key}.v", {key: json.dumps(values)}

    def opens(self, key: str, spans: list[Span]) -> tuple[str, str, str, dict[str, Any]]:
        """``(FROM fragment, lo expr, hi expr, binds)`` unpacking a list of open ranges."""
        if self.name == "postgresql":
            frag = f"unnest(CAST(:{key}_lo AS text[]), CAST(:{key}_hi AS text[])) AS {key}(lo, hi)"
            binds = {f"{key}_lo": [lo for lo, _ in spans], f"{key}_hi": [hi for _, hi in spans]}
            return frag, f'{key}.lo COLLATE "C"', f'{key}.hi COLLATE "C"', binds
        pairs = json.dumps([list(s) for s in spans])
        if self.name == "sqlite":
            return f"json_each(:{key}) AS {key}", f"{key}.value ->> 0", f"{key}.value ->> 1", {key: pairs}
        if self.name == "mssql":
            frag = f"OPENJSON(:{key}) WITH (lo nvarchar(max) '$[0]', hi nvarchar(max) '$[1]') AS {key}"
            utf8 = f"COLLATE {MSSQL_UTF8_COLLATION} AS varchar({PATH_LEN}))"
            return frag, f"CAST({key}.lo {utf8}", f"CAST({key}.hi {utf8}", {key: pairs}
        if self.name == "mariadb":
            cols = f"COLUMNS (lo VARCHAR({PATH_LEN}) PATH '$[0]', hi VARCHAR({PATH_LEN}) PATH '$[1]')"
            return f"JSON_TABLE(:{key}, '$[*]' {cols}) AS {key}", f"CAST({key}.lo AS BINARY)", f"CAST({key}.hi AS BINARY)", {key: pairs}
        cols = f"COLUMNS (lo VARCHAR2({PATH_LEN}) PATH '$[0]', hi VARCHAR2({PATH_LEN}) PATH '$[1]')"
        return f"JSON_TABLE(:{key}, '$[*]' {cols}) {key}", f"{key}.lo", f"{key}.hi", {key: pairs}

    def literal_points(self, col: str, key: str, values: list[str]) -> tuple[str, dict[str, Any]]:
        """``col IN (:k0, :k1, ...)`` one bind per path."""
        binds = {f"{key}{i}": self.path(v) for i, v in enumerate(values)}
        return f"{col} IN ({', '.join(self.path_expr(k) for k in binds)})", binds

    def literal_opens(self, col: str, key: str, spans: list[Span]) -> tuple[str, dict[str, Any]]:
        """``(col > :lo AND col < :hi) OR ...`` two binds per range."""
        binds: dict[str, Any] = {}
        terms: list[str] = []
        for i, (lo, hi) in enumerate(spans):
            binds[f"{key}l{i}"] = self.path(lo)
            binds[f"{key}h{i}"] = self.path(hi)
            terms.append(f"({col} > {self.path_expr(f'{key}l{i}')} AND {col} < {self.path_expr(f'{key}h{i}')})")
        return " OR ".join(terms), binds

    def stmt(self, sql: str, params: dict[str, Any]) -> Any:
        """A ``text()`` statement; Oracle's JSON binds are typed CLOB so any size travels."""
        s = text(sql)
        if self.name == "oracle" and os.environ.get("TS_ORACLE_VARCHAR") != "1":
            json_keys = [k for k, v in params.items() if isinstance(v, str) and v[:1] == "["]
            if json_keys:
                s = s.bindparams(*(bindparam(k, type_=CLOB) for k in json_keys))
        return s

    # -- statement shapes -------------------------------------------------------

    def top(self, cols: str, from_where: str, order: str, k: int) -> str:
        if self.name == "mssql":
            return f"SELECT TOP {k} {cols} {from_where} ORDER BY {order}"
        if self.name == "oracle":
            return f"SELECT {cols} {from_where} ORDER BY {order} FETCH FIRST {k} ROWS ONLY"
        return f"SELECT {cols} {from_where} ORDER BY {order} LIMIT {k}"

    def offset_one(self, cols: str, from_where: str, order: str, key: str) -> str:
        """The row at offset *key* in *order*: the keyset boundary probe."""
        if self.name in ("mssql", "oracle"):
            return f"SELECT {cols} {from_where} ORDER BY {order} OFFSET :{key} ROWS FETCH NEXT 1 ROWS ONLY"
        return f"SELECT {cols} {from_where} ORDER BY {order} LIMIT 1 OFFSET :{key}"

    def move_set(self, cut_key: str, dst_key: str) -> str:
        """``path = dst || substr(path, cut)`` per engine."""
        if self.name == "mssql":
            return f"path = CAST(:{dst_key} COLLATE {MSSQL_UTF8_COLLATION} AS varchar({PATH_LEN})) + SUBSTRING(path, :{cut_key}, {PATH_LEN})"
        if self.name == "mariadb":
            return f"path = CONCAT(:{dst_key}, SUBSTRING(path, :{cut_key}))"
        return f"path = :{dst_key} || substr(path, :{cut_key})"

    def update_join_opens(self, table: str, key: str, spans: list[Span], level_key: str) -> tuple[str, dict[str, Any]]:
        """The relabel through the range source, each range an index seek: the ``UPDATE … FROM`` family."""
        frag, lo, hi, binds = self.opens(key, spans)
        on = f"e.path > {lo} AND e.path < {hi}"
        if self.name == "postgresql":
            sql = f"UPDATE {table} e SET everyone_level = :{level_key} FROM {frag} WHERE {on}"
        elif self.name == "sqlite":
            sql = f"UPDATE {table} AS e SET everyone_level = :{level_key} FROM {frag} WHERE {on}"
        elif self.name == "mssql":
            # The plain JOIN plans a scan of e with the ranges as the inner (rows x ranges, measured: minutes).
            sql = f"UPDATE e SET everyone_level = :{level_key} FROM {frag} {self.join} {table} e ON {on}"
        elif self.name == "mariadb":
            sql = f"UPDATE {table} e JOIN {frag} ON {on} SET e.everyone_level = :{level_key}"
        else:
            # Without the cardinality hint Oracle plans a merge join over a full scan (measured: 5.9 s for the root).
            hint = f"/*+ CARDINALITY({key} {len(spans)}) */ " if self.oracle_cardinality else ""
            sql = (
                f"MERGE INTO {table} e USING (SELECT {hint}lo, hi FROM {frag}) r ON ({on.replace(key + '.', 'r.')}) "
                f"WHEN MATCHED THEN UPDATE SET e.everyone_level = :{level_key}"
            )
        return sql, binds

    def update_in_opens(self, table: str, key: str, spans: list[Span], level_key: str) -> tuple[str, dict[str, Any]]:
        """The spike's form: ``id IN (SELECT … FROM source JOIN e)``."""
        frag, lo, hi, binds = self.opens(key, spans)
        hint = self.branch_hint(key, len(spans))
        sql = (
            f"UPDATE {table} SET everyone_level = :{level_key} WHERE id IN "
            f"(SELECT {hint}e.id FROM {frag} JOIN {table} e ON e.path > {lo} AND e.path < {hi})"
        )
        return sql, binds

    def update_literal_opens(self, table: str, key: str, spans: list[Span], level_key: str) -> tuple[str, dict[str, Any]]:
        pred, binds = self.literal_opens("path", key, spans)
        # Oracle does not expand hundreds of OR'd ranges into index range scans unless told to.
        hint = "/*+ USE_CONCAT */ " if self.name == "oracle" and self.oracle_cardinality else ""
        return f"UPDATE {hint}{table} SET everyone_level = :{level_key} WHERE {pred}", binds

    # -- maintenance ------------------------------------------------------------

    def analyze(self, name: str) -> str:
        return {
            "postgresql": f"ANALYZE {name}",
            "mssql": f"UPDATE STATISTICS {name} WITH FULLSCAN",
            "oracle": f"BEGIN DBMS_STATS.GATHER_TABLE_STATS(USER, '{name.upper()}', cascade => TRUE, method_opt => 'FOR ALL COLUMNS SIZE SKEWONLY'); END;",
            "mariadb": f"ANALYZE TABLE {name}",
            "sqlite": f"ANALYZE {name}",
        }[self.name]

    async def size(self, conn, name: str, index: bool, table: str = "") -> int:
        """Bytes used by a table or an index."""
        if self.name == "sqlite":
            return int((await conn.execute(text("SELECT coalesce(sum(pgsize), 0) FROM dbstat WHERE name = :n"), {"n": name})).scalar())
        if self.name == "postgresql":
            return int((await conn.execute(text("SELECT pg_relation_size(CAST(:n AS regclass))"), {"n": name})).scalar())
        if self.name == "mssql":
            sql = (
                "SELECT coalesce(sum(ps.used_page_count), 0) * 8192 FROM sys.indexes i "
                "JOIN sys.dm_db_partition_stats ps ON ps.object_id = i.object_id AND ps.index_id = i.index_id "
                "WHERE i.object_id = OBJECT_ID(:t) AND " + ("i.name = :n" if index else "i.index_id IN (0, 1)")
            )
            return int((await conn.execute(text(sql), {"t": table or name, "n": name})).scalar())
        if self.name == "mariadb":
            if not index:
                sql = "SELECT data_length FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = :n"
                return int((await conn.execute(text(sql), {"n": name})).scalar() or 0)
            # No per-index size view is readable here: measure the index_length delta around a drop and re-add.
            cols = {"path": "UNIQUE (path)", "owner": "(owner_id)", "lvlpath": "(everyone_level, path)"}[name.rsplit("_", 1)[1]]
            sql = "SELECT index_length FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = :n"
            before = int((await conn.execute(text(sql), {"n": table})).scalar() or 0)
            await conn.execute(text(f"ALTER TABLE {table} DROP INDEX {name}"))
            await conn.execute(text(f"ANALYZE TABLE {table}"))
            after = int((await conn.execute(text(sql), {"n": table})).scalar() or 0)
            await conn.execute(text(f"ALTER TABLE {table} ADD {'UNIQUE INDEX' if 'UNIQUE' in cols else 'INDEX'} {name} {cols.replace('UNIQUE ', '')}"))
            await conn.execute(text(f"ANALYZE TABLE {table}"))
            return before - after
        sql = "SELECT coalesce(sum(bytes), 0) FROM user_segments WHERE segment_name = :n"
        return int((await conn.execute(text(sql), {"n": name.upper()})).scalar())

    async def plan(self, conn, sql: str, params: dict[str, Any], *, pre: list[str] = ()) -> str:
        """The engine's plan for *sql*, as text. Writes are run inside a rolled-back transaction."""
        try:
            for p in pre:
                await conn.execute(text(p))
            if self.name == "sqlite":
                rows = (await conn.execute(self.stmt("EXPLAIN QUERY PLAN " + sql, params), params)).all()
                return "\n".join(str(r[-1]) for r in rows)
            if self.name == "postgresql":
                rows = (await conn.execute(self.stmt("EXPLAIN (ANALYZE, BUFFERS) " + sql, params), params)).all()
                return "\n".join(r[0] for r in rows)
            if self.name == "mariadb":
                rows = (await conn.execute(self.stmt("EXPLAIN " + sql, params), params)).mappings().all()
                return "\n".join(
                    f"{r['select_type']} {r['table']} type={r['type']} key={r['key']} rows={r['rows']} {r['Extra'] or ''}".rstrip()
                    for r in rows
                )
            if self.name == "oracle":
                sid = uuid4().hex[:12]
                await conn.execute(self.stmt(f"EXPLAIN PLAN SET STATEMENT_ID = '{sid}' FOR " + sql, params), params)
                rows = (
                    await conn.execute(text(f"SELECT plan_table_output FROM TABLE(DBMS_XPLAN.DISPLAY('PLAN_TABLE', '{sid}', 'BASIC ROWS'))"))
                ).all()
                return "\n".join(r[0] for r in rows if r[0] and not r[0].startswith("Plan hash"))
            tag = uuid4().hex[:10]
            tagged = f"/* plan:{tag} */ " + sql
            res = await conn.execute(self.stmt(tagged, params), params)
            if res.returns_rows:
                res.all()
            found = (
                await conn.execute(
                    text(
                        "SELECT TOP 1 CAST(qp.query_plan AS nvarchar(max)) FROM sys.dm_exec_cached_plans cp "
                        "CROSS APPLY sys.dm_exec_sql_text(cp.plan_handle) st CROSS APPLY sys.dm_exec_query_plan(cp.plan_handle) qp "
                        "WHERE st.text LIKE :t AND st.text NOT LIKE '%dm_exec_cached_plans%'"
                    ),
                    {"t": f"%plan:{tag}%"},
                )
            ).scalar()
            return _showplan_text(found) if found else "plan not found in cache"
        except Exception as exc:  # noqa: BLE001 — a missing plan must not sink the run
            return f"plan unavailable: {type(exc).__name__}: {str(exc)[:300]}"
        finally:
            await conn.rollback()


def _showplan_text(xml: str) -> str:
    """A SQL Server showplan XML as one line per operator: physical op, object, estimate."""
    ns = {"p": "http://schemas.microsoft.com/sqlserver/2004/07/showplan"}
    root = ET.fromstring(xml)
    out: list[str] = []

    def walk(rel: ET.Element, depth: int) -> None:
        obj = rel.find(".//p:Object", ns)
        name = ""
        if obj is not None:
            name = obj.get("Index") or obj.get("Table") or ""
        seek = " seek" if rel.find("./*/p:SeekPredicates", ns) is not None or rel.find("./*/p:SeekPredicateNew", ns) is not None else ""
        out.append(f"{'  ' * depth}{rel.get('PhysicalOp')} ({rel.get('LogicalOp')}){seek} {name} est={float(rel.get('EstimateRows', 0)):,.0f}")
        for child in rel.findall("./*/p:RelOp", ns):
            walk(child, depth + 1)

    for stmt in root.iter(f"{{{ns['p']}}}QueryPlan"):
        for rel in stmt.findall("./p:RelOp", ns):
            walk(rel, 0)
    return "\n".join(out) or xml[:2000]


# ---------------------------------------------------------------------------
# Schema and loading
# ---------------------------------------------------------------------------


def schema(ns: str) -> tuple[MetaData, Table, Table]:
    md = MetaData()
    ident = BigInteger().with_variant(Integer, "sqlite")
    owner_type = String(255).with_variant(String(255, collation=MSSQL_UTF8_COLLATION), "mssql")
    entry = Table(
        f"{ns}e",
        md,
        Column("id", ident, primary_key=True, autoincrement=False),
        Column("path", BytewiseString(PATH_LEN), nullable=False),
        Column("owner_id", owner_type),
        Column("everyone_level", SmallInteger, nullable=False),
    )
    chunk = Table(
        f"{ns}c",
        md,
        Column("id", ident, primary_key=True, autoincrement=False),
        Column("entry_id", ident, nullable=False),
        Column("score", Integer, nullable=False),
    )
    Index(f"{ns}e_path", entry.c.path, unique=True)
    Index(f"{ns}e_owner", entry.c.owner_id)
    Index(f"{ns}e_lvlpath", entry.c.everyone_level, entry.c.path)
    Index(f"{ns}c_entry", chunk.c.entry_id)
    Index(f"{ns}c_score", chunk.c.score)
    return md, entry, chunk


def make_engine(engine_name: str, path: str | None) -> AsyncEngine:
    if engine_name == "sqlite":
        engine = create_async_engine(f"sqlite+aiosqlite:///{path}")

        def on_connect(dbapi, _):
            for p in SQLITE_PRAGMAS:
                dbapi.execute(p)

        event.listen(engine.sync_engine, "connect", on_connect)
        return engine
    kw = {"use_setinputsizes": False} if engine_name == "mssql" else {}
    return create_async_engine(URLS[engine_name], **kw)


async def load(engine: AsyncEngine, d: Dialect, entry: Table, chunk: Table, rows: list, chunks: list) -> float:
    """Create the tables, bulk-insert, build the indexes with the tables, gather statistics."""
    t0 = time.perf_counter()
    md = entry.metadata
    async with engine.begin() as conn:
        await conn.run_sync(md.create_all)
    batch = 20_000 if d.name != "mssql" else 10_000
    for i in range(0, len(rows), batch):
        async with engine.begin() as conn:
            await conn.execute(insert(entry), [{"id": a, "path": p, "owner_id": o, "everyone_level": lvl} for a, p, o, lvl in rows[i : i + batch]])
    for i in range(0, len(chunks), batch):
        async with engine.begin() as conn:
            await conn.execute(insert(chunk), [{"id": a, "entry_id": b, "score": s} for a, b, s in chunks[i : i + batch]])
    async with engine.begin() as conn:
        for name in (entry.name, chunk.name):
            await conn.execute(text(d.analyze(name)))
    return time.perf_counter() - t0


async def drop_all(engine: AsyncEngine, md: MetaData) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(md.drop_all)


# ---------------------------------------------------------------------------
# The three-seek predicate in its shapes
# ---------------------------------------------------------------------------


class Caller:
    def __init__(self, compiled: Compiled | None, anonymous: bool, system: bool) -> None:
        self.compiled = compiled
        self.anonymous = anonymous
        self.system = system

    @property
    def pieces(self) -> int:
        if self.compiled is None:
            return 0
        n = len(self.compiled.arms.points) + len(self.compiled.arms.opens)
        return n + sum(len(p.points) + len(p.opens) for _, p in self.compiled.owners if p is not None)


class Visible:
    """The visible-entries SQL for one caller and shape: ``sql``, ``params`` and ``pre`` statements."""

    def __init__(self, sql: str, params: dict[str, Any], pre: list[str] | None = None, inline: bool = False) -> None:
        self.sql = sql
        self.params = params
        self.pre = pre or []
        self.inline = inline  # True: ``sql`` is a WHERE predicate on alias ``e``, not a SELECT


def visible(d: Dialect, t: str, shape: str, caller: Caller, level: int, scope: Span | None = None, *, branch1: str = "ge") -> Visible:
    params: dict[str, Any] = {"lvl": level}
    scoped = ""
    if scope is not None:
        scoped = f" AND e.path > {d.path_expr('slo')} AND e.path < {d.path_expr('shi')}"
        params |= {"slo": d.path(scope[0]), "shi": d.path(scope[1])}
    if caller.system:
        return Visible(f"SELECT e.id FROM {t} e WHERE 1=1{scoped}", params)
    if branch1 == "in":
        levels = [lv for lv in (NONE, READ, READ_WRITE) if lv >= level]
        params |= {f"lv{i}": lv for i, lv in enumerate(levels)}
        one = f"SELECT {d.one_hint()}e.id FROM {t} e WHERE e.everyone_level IN ({', '.join(f':lv{i}' for i in range(len(levels)))}){scoped}"
    else:
        one = f"SELECT {d.one_hint()}e.id FROM {t} e WHERE e.everyone_level >= :lvl{scoped}"
    if caller.anonymous or caller.compiled is None:
        return Visible(one, params)
    c = caller.compiled
    below = d.below()

    if shape == "literal":
        terms = ["e.everyone_level >= :lvl"]

        def lit(key: str, pieces: Pieces) -> list[str]:
            out: list[str] = []
            if pieces.points:
                pred, binds = d.literal_points("e.path", f"{key}p", pieces.points)
                params.update(binds)
                out.append(pred)
            if pieces.opens:
                pred, binds = d.literal_opens("e.path", f"{key}r", pieces.opens)
                params.update(binds)
                out.append(pred)
            return out

        terms += lit("a", c.arms)
        for n, (owner, pieces) in enumerate(c.owners):
            params[f"o{n}"] = owner
            if pieces is None:
                terms.append(f"e.owner_id = {d.owner_expr(f'o{n}')}")
            else:
                inner = lit(f"o{n}", pieces)
                if inner:
                    terms.append(f"(e.owner_id = {d.owner_expr(f'o{n}')} AND ({' OR '.join(inner)}))")
        pred = "(" + " OR ".join(terms) + ")"
        if scope is not None:
            pred += scoped
        return Visible(pred, params, inline=True)

    def range_branches(key: str, pieces: Pieces, cond: str) -> list[str]:
        """One branch per piece kind; *cond* is the extra ``AND …`` on the entry row."""
        out: list[str] = []
        kinds: list[tuple[str, str, str, dict[str, Any], int]] = []
        if pieces.points:
            frag, value, binds = d.points(f"{key}p", pieces.points)
            kinds.append((f"{key}p", frag, f"e.path = {value}", binds, len(pieces.points)))
        if pieces.opens:
            frag, lo, hi, binds = d.opens(f"{key}r", pieces.opens)
            on = f"e.path > {lo} AND e.path < {hi}"
            if d.pg_nudge and d.name == "postgresql":
                on += f" AND e.path LIKE ({lo} || '%')"
            kinds.append((f"{key}r", frag, on, binds, len(pieces.opens)))
        for k, frag, on, binds, count in kinds:
            params.update(binds)
            hint = d.branch_hint(k, count)
            if d.apply:
                out.append(f"SELECT e.id FROM {frag} CROSS APPLY (SELECT e.id FROM {t} e WHERE {on}{cond}{scoped}) e")
            else:
                out.append(f"SELECT {hint}e.id FROM {frag} {d.join} {d.entry_from(t)} ON {on}{cond}{scoped}")
        return out

    def excluded(key: str, pieces: Pieces) -> str:
        """``NOT EXISTS`` over the arms' pieces: makes the owner branch disjoint from branch 2."""
        out: list[str] = []
        if pieces.points:
            frag, value, binds = d.points(f"{key}p", pieces.points)
            params.update(binds)
            out.append(f" AND NOT EXISTS (SELECT 1 FROM {frag} WHERE e.path = {value})")
        if pieces.opens:
            frag, lo, hi, binds = d.opens(f"{key}r", pieces.opens)
            params.update(binds)
            out.append(f" AND NOT EXISTS (SELECT 1 FROM {frag} WHERE e.path > {lo} AND e.path < {hi})")
        return "".join(out)

    two = range_branches("a", c.arms, below)
    if shape == "fenced":
        two = [f"SELECT f.id FROM ({b} OFFSET 0) f" for b in two]
    three: list[str] = []
    for n, (owner, pieces) in enumerate(c.owners):
        params[f"o{n}"] = owner
        cond = f" AND e.owner_id = {d.owner_expr(f'o{n}')}{below}"
        if shape == "disjoint":
            cond += excluded(f"x{n}", c.arms)
        if pieces is None:
            three.append(f"SELECT e.id FROM {t} e WHERE 1=1{cond}{scoped}")
        else:
            three += range_branches(f"o{n}", pieces, cond)
    pre = ["SET LOCAL jit = off"] if shape == "fenced" else []
    if shape == "union":
        return Visible(" UNION ".join([one, *two, *three]), params, pre)
    if shape == "disjoint":
        return Visible(" UNION ALL ".join([one, *two, *three]), params, pre)
    head = " UNION ALL ".join([one, *two])
    if not three:
        return Visible(head, params, pre)
    return Visible(f"{head} UNION " + " UNION ".join(three), params, pre)


def statements(d: Dialect, t_e: str, t_c: str, shape: str, caller: Caller, level: int, scope: Span) -> dict[str, Visible]:
    v = visible(d, t_e, shape, caller, level)
    s = visible(d, t_e, shape, caller, level, scope)
    if v.inline:
        joined = f"FROM {t_c} c JOIN {t_e} e ON e.id = c.entry_id WHERE {v.sql}"
        return {
            "entries": Visible(f"SELECT e.id FROM {t_e} e WHERE {v.sql}", v.params),
            "scoped": Visible(f"SELECT e.id FROM {t_e} e WHERE {s.sql}", s.params),
            "count": Visible(f"SELECT count(*) {joined}", v.params),
            "top10": Visible(d.top("c.id", joined, "c.score", 10), v.params),
        }
    derived = f"FROM ({v.sql}) v JOIN {t_c} c ON c.entry_id = v.id"
    return {
        "entries": Visible(v.sql + d.tail(), v.params, v.pre),
        "scoped": Visible(s.sql + d.tail(), s.params, s.pre),
        "count": Visible(f"SELECT {d.derived_hint()}count(*) {derived}{d.tail()}", v.params, v.pre),
        "top10": Visible(d.top(d.derived_hint() + "c.id", derived, "c.score", 10) + d.tail(), v.params, v.pre),
    }


# ---------------------------------------------------------------------------
# Timing and recall
# ---------------------------------------------------------------------------


async def timed(engine: AsyncEngine, d: Dialect, v: Visible, reps: int, *, cap_s: float = 20.0) -> tuple[float, float, Any]:
    """Cold ms (fresh connection, first run), warm median ms, and the first answer. Errors return the message."""
    await engine.dispose()
    stmt = d.stmt(v.sql, v.params)
    async with engine.connect() as conn:
        t0 = time.perf_counter()
        try:
            for p in v.pre:
                await conn.execute(text(p))
            answer = (await conn.execute(stmt, v.params)).all()
        except Exception as exc:  # noqa: BLE001 — one failing spelling must not sink the run
            await conn.rollback()
            return float("nan"), float("nan"), f"error: {type(exc).__name__}: {str(exc).splitlines()[0][:160]}"
        cold = (time.perf_counter() - t0) * 1000
        await conn.rollback()
        if cold / 1000 > cap_s:
            return cold, float("nan"), answer
        warm: list[float] = []
        for _ in range(reps):
            t0 = time.perf_counter()
            for p in v.pre:
                await conn.execute(text(p))
            (await conn.execute(stmt, v.params)).all()
            warm.append((time.perf_counter() - t0) * 1000)
            await conn.rollback()
    return cold, statistics.median(warm), answer


def recall(statement: str, answer: Any, exact: Any, traps: set[int]) -> str:
    if isinstance(answer, str):
        return answer
    if statement == "count":
        got = answer[0][0]
        return "exact" if got == exact else f"{got} != {exact}"
    got = {r[0] for r in answer}
    hit = len(got & exact) / len(exact) if exact else 1.0
    extra = len(got - exact)
    leaked = len(got & traps)
    out = "exact" if hit == 1.0 and not extra else f"{hit:.4f}"
    if extra:
        out += f" (+{extra} extra, {leaked} traps)"
    return out


def ms(v: float) -> str:
    return "n/a" if v != v else (f"{v:,.1f}" if v < 100 else f"{v:,.0f}")


def mb(b: int) -> str:
    return f"{b / 1e6:,.1f} MB"


def write_lines(filename: str, lines: list[str]) -> None:
    os.makedirs(os.path.join(HERE, "runs"), exist_ok=True)
    out = os.path.join(HERE, "runs", filename)
    with open(out, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"→ {out}", flush=True)


# ---------------------------------------------------------------------------
# The read run
# ---------------------------------------------------------------------------


async def read_run(engine_name: str, n: int, reps: int, chunks_per_file: int, shapes: tuple[str, ...]) -> None:
    started = time.perf_counter()
    lines: list[str] = []

    def say(s: str = "") -> None:
        print(s, flush=True)
        lines.append(s)

    w = build(n)
    lab = [public_level(w.star, p) for _, p, _ in w.rows]
    rows = [(rid, p, o, lvl) for (rid, p, o), lvl in zip(w.rows, lab)]
    traps = {rid for rid, p, _ in w.rows if p.endswith("-x")}
    rng = random.Random(7)
    files = [rid for rid, p, _ in w.rows if p.endswith(".md")]
    scores = rng.sample(range(len(files) * chunks_per_file * 4), len(files) * chunks_per_file)
    chunks = [(i, fid, scores[i]) for i, fid in enumerate(f for f in files for _ in range(chunks_per_file))]
    score_of = {i: s for i, _, s in chunks}
    say(
        f"## {engine_name} — N={n:,} users: {len(w.rows):,} entries, {len(chunks):,} chunks ({chunks_per_file}/file), "
        f"{len(w.grants):,} grant rows, {len(w.star):,} posture rows, {len(traps)} sibling traps"
    )
    say()
    os.makedirs(SCRATCH, exist_ok=True)
    path = os.path.join(SCRATCH, f"ts-n{n}-{uuid4().hex[:6]}.sqlite") if engine_name == "sqlite" else None
    ns = f"ts_{uuid4().hex[:8]}_"
    md, entry, chunk = schema(ns)
    engine = make_engine(engine_name, path)
    d = Dialect(engine.dialect.name)
    if d.name != "postgresql":
        shapes = tuple(s for s in shapes if s != "fenced")
    try:
        secs = await load(engine, d, entry, chunk, rows, chunks)
        say(f"Load (tables, rows, indexes, statistics): {secs:.0f}s.")
        say()
        say("### Indexes")
        say()
        say("| index | size |")
        say("|---|---|")
        async with engine.connect() as conn:
            for name in (f"{ns}e_path", f"{ns}e_owner", f"{ns}e_lvlpath"):
                say(f"| `{name[len(ns) + 2 :]}` | {mb(await d.size(conn, name, True, entry.name))} |")
            say(f"| (entries table) | {mb(await d.size(conn, entry.name, False))} |")
        say()

        specs = callers(w)
        exact: dict[str, set[int]] = {}
        cache = next((p for p in (os.path.join(SCRATCH, f"truth-{n}.pkl"), os.path.join(SPIKE_SCRATCH, f"truth-{n}.pkl")) if os.path.exists(p)), None)
        if cache:
            with open(cache, "rb") as f:
                exact = pickle.load(f)
        else:
            t0 = time.perf_counter()
            for label, spec in specs.items():
                exact[label] = truth(w, spec["subjects"], READ, anonymous=spec.get("anonymous", False), system=spec.get("system", False))
            with open(os.path.join(SCRATCH, f"truth-{n}.pkl"), "wb") as f:
                pickle.dump(exact, f)
            say(f"Truth computed in Python in {time.perf_counter() - t0:.1f}s.")
        scope = ("/shared/s0001/", "/shared/s00010")
        in_scope = {rid for rid, p, _ in w.rows if scope[0] < p < scope[1]}

        say("### Callers")
        say()
        say("| caller | subjects | pieces (arms + owner) | bind bytes | compile us | visible entries |")
        say("|---|---|---|---|---|---|")
        caller_objs: dict[str, Caller] = {}
        for label, spec in specs.items():
            if spec.get("system"):
                caller_objs[label] = Caller(None, False, True)
            elif spec.get("anonymous"):
                caller_objs[label] = Caller(None, True, False)
            else:
                caller_objs[label] = Caller(compile_rights(w, spec["subjects"], READ), False, False)
            c = caller_objs[label]
            say(
                f"| {label} | {', '.join(spec['subjects']) or '—'} | {c.pieces} | {c.compiled.bind_bytes if c.compiled else 0:,} | "
                f"{c.compiled.compile_us if c.compiled else 0:,.0f} | {len(exact[label]):,} |"
            )
        say()

        say(f"### Statements — cold = fresh connection, warm = median of {reps} (ms); recall against the Python truth")
        say()
        say("Shapes: " + ", ".join(shapes) + ". A blank cell is a shape that does not apply to that caller.")
        say()
        say("| caller | statement | " + " | ".join(f"{s}: cold / warm / recall" for s in shapes) + " |")
        say("|---|---|" + "---|" * len(shapes))
        plans: list[tuple[str, str, str, str]] = []
        for label, spec in specs.items():
            caller = caller_objs[label]
            vis = exact[label]
            visible_chunks = [i for i, eid, _ in chunks if eid in vis]
            top = set(sorted(visible_chunks, key=score_of.__getitem__)[:10])
            truths = {"entries": vis, "scoped": vis & in_scope, "count": len(visible_chunks), "top10": top}
            applicable = list(shapes)
            if caller.compiled is None:
                applicable = [s for s in shapes if s in ("union", "literal")][:1] or list(shapes)[:1]
            elif caller.pieces > LITERAL_MAX_PIECES:
                applicable = [s for s in shapes if s != "literal"]
            for statement in STATEMENTS:
                cells = []
                for shape in shapes:
                    if shape not in applicable:
                        cells.append("")
                        continue
                    v = statements(d, entry.name, chunk.name, shape, caller, READ, scope)[statement]
                    cold, warm, answer = await timed(engine, d, v, reps)
                    cells.append(f"{ms(cold)} / {ms(warm)} / {recall(statement, answer, truths[statement], traps)}")
                    if label in ("ordinary", "two subjects") and statement in ("entries", "scoped", "count", "top10"):
                        if label == "two subjects" and statement != "entries":
                            continue
                        async with engine.connect() as conn:
                            plans.append((label, shape, statement, await d.plan(conn, v.sql, v.params, pre=v.pre)))
                say(f"| {label} | {statement} | " + " | ".join(cells) + " |")
        say()

        # The scoped read: branch 1 as ``>=`` against ``IN`` — does the planner seek (everyone_level, path)?
        say("### Scoped read, branch 1 spelled `everyone_level >= :r` against `everyone_level IN (...)`")
        say()
        say("| caller | shape | `>=` cold / warm | `IN` cold / warm | recall |")
        say("|---|---|---|---|---|")
        spelled_plans: list[tuple[str, str, str]] = []
        for label in ("anonymous", "ordinary"):
            caller = caller_objs[label]
            for shape in (s for s in shapes if s in ("union", "unionall", "disjoint", "literal")):
                if caller.compiled is None and shape != shapes[0]:
                    continue
                ge = visible(d, entry.name, shape, caller, READ, scope, branch1="ge")
                inn = visible(d, entry.name, shape, caller, READ, scope, branch1="in")
                if ge.inline:
                    ge = Visible(f"SELECT e.id FROM {entry.name} e WHERE {ge.sql}", ge.params)
                    inn = Visible(f"SELECT e.id FROM {entry.name} e WHERE {inn.sql}", inn.params)
                a = await timed(engine, d, ge, reps)
                b = await timed(engine, d, inn, reps)
                say(f"| {label} | {shape} | {ms(a[0])} / {ms(a[1])} | {ms(b[0])} / {ms(b[1])} | {recall('scoped', b[2], exact[label] & in_scope, traps)} |")
                async with engine.connect() as conn:
                    spelled_plans.append((label, f"{shape} / IN", await d.plan(conn, inn.sql, inn.params)))
                if caller.compiled is None:
                    async with engine.connect() as conn:
                        spelled_plans.append((label, f"{shape} / >=", await d.plan(conn, ge.sql, ge.params)))
        say()

        say("### Plans")
        say()
        for label, shape, statement, p in plans:
            say(f"**{label} / {shape} / {statement}**")
            say()
            say("```")
            say(p)
            say("```")
            say()
        for label, shape, p in spelled_plans:
            say(f"**scoped / {label} / {shape}**")
            say()
            say("```")
            say(p)
            say("```")
            say()
    finally:
        await drop_all(engine, md)
        await engine.dispose()
        if path:
            for suffix in ("", "-wal", "-shm"):
                if os.path.exists(path + suffix):
                    os.remove(path + suffix)
    say(f"Total wall time {time.perf_counter() - started:.0f}s.")
    write_lines(f"{engine_name}-{n}.md", lines)


# ---------------------------------------------------------------------------
# The writes run: the relabel per dialect, chunked, and a move
# ---------------------------------------------------------------------------


async def writes_run(engine_name: str, reps: int, big: int, forms: tuple[str, ...]) -> None:
    started = time.perf_counter()
    lines: list[str] = []

    def say(s: str = "") -> None:
        print(s, flush=True)
        lines.append(s)

    w = build(1_000)
    extra = {"/mid": 1_000, "/mv": 10_000, "/big": big - 1}
    for folder, count in extra.items():
        w.add_row(folder)
        for i in range(count):
            w.add_row(f"{folder}/f{i:07d}.md", "u000000")
    lab = [public_level(w.star, p) for _, p, _ in w.rows]
    rows = [(rid, p, o, lvl) for (rid, p, o), lvl in zip(w.rows, lab)]
    say(
        f"## {engine_name} — writes: 1,000-user world plus /mid ({extra['/mid'] + 1:,} rows), /mv ({extra['/mv'] + 1:,}), "
        f"/big ({big:,}); {len(w.rows):,} entries"
    )
    say()
    os.makedirs(SCRATCH, exist_ok=True)
    path = os.path.join(SCRATCH, f"ts-writes-{uuid4().hex[:6]}.sqlite") if engine_name == "sqlite" else None
    ns = f"ts_{uuid4().hex[:8]}_"
    md, entry, chunk = schema(ns)
    engine = make_engine(engine_name, path)
    d = Dialect(engine.dialect.name)
    t = entry.name
    star = dict(w.star)
    plans: list[tuple[str, str]] = []
    try:
        secs = await load(engine, d, entry, chunk, rows, [])
        say(f"Load: {secs:.0f}s.")
        say()
        say("Forms: `join` = the UPDATE through the range source (`UPDATE … FROM unnest` / `UPDATE … FROM … JOIN OPENJSON` / "
            "`UPDATE … JOIN JSON_TABLE` / `MERGE … USING JSON_TABLE`); `literal` = `WHERE (path > :lo AND path < :hi) OR …`; "
            "`in_sub` = `WHERE id IN (SELECT … FROM source JOIN e)`. Points always travel as `path IN (…)`. "
            f"At most {PIECES_PER_STATEMENT} pieces per statement; every statement is its own transaction.")
        say()
        say("| operation | form | statements | rows touched | total ms (median of runs) | labels after |")
        say("|---|---|---|---|---|---|")

        async def check() -> str:
            expect = {rid: public_level(star, p) for rid, p, _ in w.rows}
            async with engine.connect() as conn:
                got = (await conn.execute(text(f"SELECT id, everyone_level FROM {t}"))).all()
            wrong = sum(1 for rid, lvl in got if expect[rid] != lvl)
            return "all correct" if wrong == 0 else f"{wrong:,} wrong"

        async def relabel(level: int, pieces: Pieces, form: str, chunk_rows: int | None, want_plan: str | None) -> tuple[int, int]:
            """Relabel the rows *pieces* name; each statement its own transaction. Returns (statements, rows)."""
            stmts = touched = 0
            for i in range(0, len(pieces.points), PIECES_PER_STATEMENT):
                pred, binds = d.literal_points("path", "p", pieces.points[i : i + PIECES_PER_STATEMENT])
                async with engine.begin() as conn:
                    res = await conn.execute(d.stmt(f"UPDATE {t} SET everyone_level = :lvl WHERE {pred}", binds), {"lvl": level, **binds})
                stmts += 1
                touched += res.rowcount
            if chunk_rows is None:
                for i in range(0, len(pieces.opens), PIECES_PER_STATEMENT):
                    spans = pieces.opens[i : i + PIECES_PER_STATEMENT]
                    sql, binds = {
                        "join": d.update_join_opens,
                        "in_sub": d.update_in_opens,
                        "literal": d.update_literal_opens,
                    }[form](t, "r", spans, "lvl")
                    params = {"lvl": level, **binds}
                    if want_plan and i == 0:
                        async with engine.connect() as conn:
                            plans.append((f"{want_plan} / {form} ({len(spans)} ranges)", await d.plan(conn, sql, params)))
                    async with engine.begin() as conn:
                        res = await conn.execute(d.stmt(sql, params), params)
                    stmts += 1
                    touched += res.rowcount
                return stmts, touched
            for lo, hi in pieces.opens:
                cur = lo
                while True:
                    probe = d.offset_one("path", f"FROM {t} WHERE path > {d.path_expr('cur')} AND path < {d.path_expr('hi')}", "path", "k")
                    async with engine.connect() as conn:
                        bound = (await conn.execute(text(probe), {"cur": d.path(cur), "hi": d.path(hi), "k": chunk_rows - 1})).scalar()
                    stmts += 1
                    if bound is None:
                        sql = f"UPDATE {t} SET everyone_level = :lvl WHERE path > {d.path_expr('cur')} AND path < {d.path_expr('hi')}"
                        async with engine.begin() as conn:
                            res = await conn.execute(text(sql), {"lvl": level, "cur": d.path(cur), "hi": d.path(hi)})
                        stmts += 1
                        touched += res.rowcount
                        break
                    if isinstance(bound, (bytes, bytearray, memoryview)):
                        bound = bytes(bound).decode()
                    sql = f"UPDATE {t} SET everyone_level = :lvl WHERE path > {d.path_expr('cur')} AND path <= {d.path_expr('b')}"
                    async with engine.begin() as conn:
                        res = await conn.execute(text(sql), {"lvl": level, "cur": d.path(cur), "b": d.path(bound)})
                    stmts += 1
                    touched += res.rowcount
                    cur = bound
            return stmts, touched

        async def run_posture(prefix: str, new_level: int, form: str, chunk_rows: int | None, label: str, want_plan: bool = False) -> None:
            deeper = [p for p in star if p != prefix and p.startswith(prefix.rstrip("/") + "/")]
            pieces = split(relabel_spans(prefix, deeper))
            samples: list[float] = []
            stmts = touched = 0
            for r in range(reps):
                level = new_level if r % 2 == 0 else (NONE if new_level != NONE else READ)
                star[prefix] = level
                t0 = time.perf_counter()
                try:
                    stmts, touched = await relabel(level, pieces, form, chunk_rows, label if want_plan and r == 0 else None)
                except Exception as exc:  # noqa: BLE001 — record the failing form, re-sync the labels, move on
                    say(f"| {label} | {form} | error | | {type(exc).__name__}: {str(exc).splitlines()[0][:160]} | |")
                    await relabel(level, pieces, "literal", None, None)
                    return
                samples.append((time.perf_counter() - t0) * 1000)
            shape = f"{form}; {len(pieces.points)} points + {len(pieces.opens)} ranges ({len(deeper):,} deeper postures cut)"
            if chunk_rows:
                shape += f"; keyset chunks of {chunk_rows:,} rows"
            say(f"| {label} | {shape} | {stmts:,} | {touched:,} | {statistics.median(samples):,.0f} | {await check()} |")

        for form in forms:
            await run_posture("/mid", READ, form, None, "posture /mid → shared (1,000 rows)", want_plan=True)
        await run_posture("/big", READ, forms[0], None, f"posture /big → shared ({big:,} rows), one statement")
        await run_posture("/big", READ, forms[0], 50_000, f"posture /big → shared ({big:,} rows), chunked")
        for form in forms:
            await run_posture("/", READ, form, None, "posture / → shared (root minus every deeper posture)", want_plan=True)

        # Move /mv (open, under the root) into /home/u000000 (private): the destination label in the same UPDATE.
        src, dst = "/mv", "/home/u000000/mv"
        samples = []
        res = None
        for r in range(reps):
            a, b = (src, dst) if r % 2 == 0 else (dst, src)
            lvl = public_level(star, b)
            sql = (
                f"UPDATE {t} SET {d.move_set('cut', 'b')}, everyone_level = :lvl "
                f"WHERE path = {d.path_expr('a')} OR (path >= {d.path_expr('lo')} AND path < {d.path_expr('hi')})"
            )
            params = {"a": d.path(a), "b": d.path(b), "cut": len(a) + 1, "lvl": lvl, "lo": d.path(a + "/"), "hi": d.path(a + "0")}
            if r == 0:
                async with engine.connect() as conn:
                    plans.append(("move /mv → /home/u000000/mv", await d.plan(conn, sql, params)))
            t0 = time.perf_counter()
            async with engine.begin() as conn:
                res = await conn.execute(text(sql), params)
            samples.append((time.perf_counter() - t0) * 1000)
        if reps % 2 == 0:
            async with engine.begin() as conn:
                sql = (
                    f"UPDATE {t} SET {d.move_set('cut', 'b')}, everyone_level = :lvl "
                    f"WHERE path = {d.path_expr('a')} OR (path >= {d.path_expr('lo')} AND path < {d.path_expr('hi')})"
                )
                await conn.execute(text(sql), {"a": d.path(src), "b": d.path(dst), "cut": len(src) + 1, "lvl": public_level(star, dst), "lo": d.path(src + "/"), "hi": d.path(src + "0")})
        async with engine.connect() as conn:
            moved = (
                await conn.execute(
                    text(f"SELECT count(*), min(everyone_level), max(everyone_level) FROM {t} WHERE path = {d.path_expr('p')} OR (path >= {d.path_expr('lo')} AND path < {d.path_expr('hi')})"),
                    {"p": d.path(dst), "lo": d.path(dst + "/"), "hi": d.path(dst + "0")},
                )
            ).one()
            left = (
                await conn.execute(
                    text(f"SELECT count(*) FROM {t} WHERE path = {d.path_expr('p')} OR (path >= {d.path_expr('lo')} AND path < {d.path_expr('hi')})"),
                    {"p": d.path(src), "lo": d.path(src + "/"), "hi": d.path(src + "0")},
                )
            ).scalar()
        ok = moved[0] == extra["/mv"] + 1 and moved[1] == moved[2] == public_level(star, dst) and left == 0
        say(
            f"| move /mv → /home/u000000/mv ({extra['/mv'] + 1:,} rows, open → private) | one UPDATE: path rewrite + destination label | 1 | "
            f"{res.rowcount if res is not None else 0:,} | {statistics.median(samples):,.0f} | {'all take the destination label' if ok else 'WRONG: ' + str(moved)} |"
        )
        say()
        say("### Plans")
        say()
        for label, p in plans:
            say(f"**{label}**")
            say()
            say("```")
            say(p)
            say("```")
            say()
    finally:
        await drop_all(engine, md)
        await engine.dispose()
        if path:
            for suffix in ("", "-wal", "-shm"):
                if os.path.exists(path + suffix):
                    os.remove(path + suffix)
    say(f"Total wall time {time.perf_counter() - started:.0f}s.")
    write_lines(f"{engine_name}-writes.md", lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", required=True, choices=["sqlite", "postgres", "mssql", "oracle", "mariadb"])
    ap.add_argument("--n", type=int, default=1_000)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--chunks", type=int, default=3, help="chunks per file")
    ap.add_argument("--shapes", default=",".join(SHAPES))
    ap.add_argument("--forms", default="join,literal,in_sub")
    ap.add_argument("--writes", action="store_true")
    ap.add_argument("--big", type=int, default=200_000)
    a = ap.parse_args()
    if a.writes:
        asyncio.run(writes_run(a.engine, a.reps, a.big, tuple(a.forms.split(","))))
    else:
        asyncio.run(read_run(a.engine, a.n, a.reps, a.chunks, tuple(a.shapes.split(","))))
