"""Shared pieces for the SQL Server fast_executemany row-loss probes.

Builds the tree's own entry/lex_postings tables (build_vfs_tables), the
same row shapes the spec-139 probes used, and the exact positional
parameter tuples the removed "array" bulk mode would have sent (the
tree's compiled statement + Core bind processors + scalar defaults).
"""
from __future__ import annotations

import datetime
import json
import os
import sys
from typing import Any

from sqlalchemy import text
from sqlalchemy.dialects import mssql
from sqlalchemy.schema import CreateTable
from ulid import ULID

from vfs.models.rows import build_vfs_tables
from vfs.storage.backends.database.dialects import _bulk_statement, _bulk_values, chunked, rows_per_statement

URL_ASYNC = "mssql+aioodbc://sa:vfsStr0ngPassw0rd@localhost:14330/master?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"
URL_SYNC = URL_ASYNC.replace("mssql+aioodbc", "mssql+pyodbc")
ODBC = "DRIVER={ODBC Driver 18 for SQL Server};SERVER=localhost,14330;UID=sa;PWD=vfsStr0ngPassw0rd;DATABASE=master;TrustServerCertificate=yes"
NOW = datetime.datetime(2026, 8, 26, 12, 0, 0, 123456, tzinfo=datetime.UTC)
RESULTS = os.environ.get("RL_RESULTS", "results.jsonl")


def entry_row(i: int, with_nulls: bool, *, prefix: str = "/p") -> dict[str, Any]:
    """The spec-139 probe5 entry row: twelve keys, null-free or with NULLs."""
    return {
        "entry_id": str(ULID()),
        "parent_id": None if (with_nulls and i % 3 == 0) else str(ULID()),
        "path": f"{prefix}/{i}",
        "name": str(i),
        "kind": "file",
        "version": 1,
        "content_hash": None if with_nulls else "h",
        "mime_type": "text/plain",
        "chunked": False,
        "created_at": NOW,
        "updated_at": NOW,
        "deleted_at": None if with_nulls else NOW,
    }


def block_row(i: int, *, epoch: int = 1) -> dict[str, Any]:
    return {"epoch": epoch, "term": f"t{i:05d}", "block_no": 0, "doc_count": 1, "doc_ids": b"\x01", "tfs": b"\x01", "dls": b"\x02"}


def tables(name: str | None = None):
    name = name or os.environ.get("RL_TABLE", "rl_probe")
    return build_vfs_tables(table_name=name)


def compiled(dialect, table, rows):
    """(sql, positional tuples) exactly as the removed array mode sent them."""
    keys = frozenset(rows[0])
    statement = _bulk_statement(dialect, table, tuple(rows[0]))
    processed = [_bulk_values(statement, row, keys) for row in rows]
    assert statement.positional is not None
    params = [tuple(values[n] for n in statement.positional) for values in processed]
    page = rows_per_statement(dialect.insertmanyvalues_max_parameters, [dict.fromkeys(statement.names)])
    return statement.sql, params, page, statement.names


def ddl(table) -> str:
    return str(CreateTable(table).compile(dialect=mssql.dialect()))


def record(**fields) -> None:
    """Append one probe outcome to the results file and echo it."""
    line = json.dumps(fields, default=str)
    print(line)
    with open(RESULTS, "a") as fh:
        fh.write(line + "\n")


def describe_types(params) -> list[str]:
    return [type(v).__name__ for v in params[0]]
