"""Probe J: isolate the two remaining differences between the losing insert
(probe H, Core-compiled statement + Core-processed params) and the intact
one (probe I, hand SQL + bytes): the SQL text and bytearray-vs-bytes."""
from __future__ import annotations

import pyodbc
from sqlalchemy import create_engine

import rl_common as C

N = 300
REQUIRED = ("entry_id", "path", "name", "kind")


def run(conn, table, sql, params, mode):
    cur = conn.cursor()
    cur.fast_executemany = True
    error, nextsets = None, 0
    try:
        cur.executemany(sql, params)
        if mode == "drain":
            while cur.nextset():
                nextsets += 1
    except Exception as exc:
        error = f"{type(exc).__name__}: {str(exc)[:160]}"
    cur.close()
    conn.commit()
    return nextsets, error


def main() -> None:
    engine = create_engine(C.URL_SYNC, use_setinputsizes=False)
    t = C.tables()
    t.metadata.drop_all(engine)
    t.metadata.create_all(engine)
    conn = pyodbc.connect(C.ODBC, autocommit=False)
    hand_sql = f"INSERT INTO {t.entry.name} (entry_id, path, name, kind, lines, size_bytes, chunked, encoded, indexable) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
    for case in ("core_sql+bytearray", "core_sql+bytes", "hand_sql+bytearray", "hand_sql+bytes", "core_sql+bytes+bool", "hand_sql+bytes+bool"):
        outcome = {}
        for mode in ("close", "drain"):
            prefix = f"/j-{case}-{mode}"
            rows = [{k: v for k, v in C.entry_row(i, False, prefix=prefix).items() if k in REQUIRED} for i in range(N)]
            for r in rows:
                r["name"] = prefix + r["name"]
            sql, params, _, names = C.compiled(engine.dialect, t.entry, rows)
            if case == "core_sql+bytearray" and mode == "close":
                print("SQL:", repr(sql))
                print("types:", C.describe_types(params), params[0])
            if "bytes" in case:
                params = [(bytes(p[0]),) + tuple(p[1:]) for p in params]
            if "bool" in case:
                params = [tuple(p[:6]) + (False, False, False) for p in params]
            if case.startswith("hand"):
                sql = hand_sql
            nextsets, error = run(conn, t.entry.name, sql, params, mode)
            landed = conn.cursor().execute(f"SELECT COUNT(*) FROM {t.entry.name} WHERE path LIKE '{prefix}/%'").fetchval()
            conn.commit()
            outcome[mode] = (landed, nextsets, error)
        C.record(probe="J-sql-vs-params", case=case, n=N, landed_on_close=outcome["close"][0], landed_on_drain=outcome["drain"][0],
                 pending_results=outcome["drain"][1], error=outcome["close"][2] or outcome["drain"][2])
    conn.close()
    t.metadata.drop_all(engine)
    engine.dispose()


if __name__ == "__main__":
    main()
