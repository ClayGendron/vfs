"""Probe G: which table/column shapes leave one pending result per parameter
set (and so lose rows on cursor close)? Plain tables, bare pyodbc, 300 rows in
one fast_executemany call. For each case: run 1 closes the cursor right away
and counts landed rows; run 2 drains with nextset() and counts the pending
result sets."""
from __future__ import annotations

import datetime
import os

import pyodbc

import rl_common as C

N = 300
DT_STR = "2026-08-26 12:00:00.123456"
DT = datetime.datetime(2026, 8, 26, 12, 0, 0, 123456)

CASES = {
    "identity_pk+varchar": ("id INT IDENTITY PRIMARY KEY, a VARCHAR(50)", "(a)", lambda i: (f"v{i}",)),
    "varchar_pk": ("a VARCHAR(50) PRIMARY KEY", "(a)", lambda i: (f"v{i}",)),
    "heap_varchar": ("a VARCHAR(50)", "(a)", lambda i: (f"v{i}",)),
    "heap_int": ("a INT", "(a)", lambda i: (i,)),
    "heap_binary16": ("a BINARY(16)", "(a)", lambda i: (bytes([i % 256]) * 16,)),
    "heap_datetime_str": ("a DATETIME", "(a)", lambda i: (DT_STR,)),
    "heap_datetime_obj": ("a DATETIME", "(a)", lambda i: (DT,)),
    "heap_datetime2_str": ("a DATETIME2", "(a)", lambda i: (DT_STR,)),
    "heap_bit_int": ("a BIT", "(a)", lambda i: (0,)),
    "heap_bigint": ("a BIGINT", "(a)", lambda i: (1,)),
    "heap_varchar1024_utf8": ("a VARCHAR(1024) COLLATE Latin1_General_100_BIN2_UTF8", "(a)", lambda i: (f"/p/{i}",)),
    "heap_nvarchar": ("a NVARCHAR(50)", "(a)", lambda i: (f"v{i}",)),
    "heap_16int": (", ".join(f"c{k} INT" for k in range(16)), "(" + ", ".join(f"c{k}" for k in range(16)) + ")", lambda i: tuple(range(16))),
    "heap_3varchar": ("a VARCHAR(50), b VARCHAR(50), c VARCHAR(50)", "(a, b, c)", lambda i: (f"v{i}", f"w{i}", f"x{i}")),
    "identity+unique_varchar": ("id INT IDENTITY PRIMARY KEY, a VARCHAR(50) UNIQUE", "(a)", lambda i: (f"v{i}",)),
    "identity+2varchar+datetime_str": ("id INT IDENTITY PRIMARY KEY, a VARCHAR(50), b VARCHAR(50), d DATETIME", "(a, b, d)", lambda i: (f"v{i}", f"w{i}", DT_STR)),
    "heap_varchar+binary16": ("a VARCHAR(50), b BINARY(16)", "(a, b)", lambda i: (f"v{i}", bytes(16))),
    "heap_varchar+bytearray16": ("a VARCHAR(50), b BINARY(16)", "(a, b)", lambda i: (f"v{i}", bytearray(16))),
    "heap_bytes_varbinary": ("a VARBINARY(64)", "(a)", lambda i: (b"\x01",)),
}


def run(conn, name, ddl, cols, make, mode):
    table = f"rl_b_{name}".replace("+", "_")
    cur = conn.cursor()
    cur.execute(f"IF OBJECT_ID('{table}') IS NOT NULL DROP TABLE {table}")
    cur.execute(f"CREATE TABLE {table} ({ddl})")
    conn.commit()
    placeholders = ", ".join("?" for _ in make(0))
    cur = conn.cursor()
    cur.fast_executemany = True
    error, nextsets = None, 0
    try:
        cur.executemany(f"INSERT INTO {table} {cols} VALUES ({placeholders})", [make(i) for i in range(N)])
        if mode == "drain":
            while cur.nextset():
                nextsets += 1
    except Exception as exc:
        error = f"{type(exc).__name__}: {str(exc)[:160]}"
    cur.close()
    conn.commit()
    landed = conn.cursor().execute(f"SELECT COUNT(*) FROM {table}").fetchval()
    conn.commit()
    conn.cursor().execute(f"DROP TABLE {table}")
    conn.commit()
    return landed, nextsets, error


def main() -> None:
    conn = pyodbc.connect(C.ODBC, autocommit=False)
    for name, (ddl, cols, make) in CASES.items():
        landed_close, _, err1 = run(conn, name, ddl, cols, make, "close")
        landed_drain, nextsets, err2 = run(conn, name, ddl, cols, make, "drain")
        C.record(probe="G-bisect", case=name, ddl=ddl, n=N, landed_on_close=landed_close, landed_on_drain=landed_drain,
                 pending_results=nextsets, error=err1 or err2)
    conn.close()


if __name__ == "__main__":
    main()
