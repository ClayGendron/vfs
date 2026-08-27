"""Probe N: two things the safe form must survive.
 1. A row that fails mid-batch (unique-index duplicate at row 0 / 150 / 299)
    under fast_executemany, with the OUTPUT statement and with the inline
    (no OUTPUT) statement: is an error raised, and what landed?
 2. The content table (VARCHAR(max) bodies, data-at-execution territory):
    300 x 20 KB bodies plus one 400 KB body, inline statement."""
from __future__ import annotations

import datetime

import pyodbc
from sqlalchemy import bindparam, create_engine, insert
from ulid import ULID

import rl_common as C

N = 300


def inline_sql(dialect, table, names):
    return str(insert(table).values({n: bindparam(n) for n in names}).inline().compile(dialect=dialect))


def main() -> None:
    engine = create_engine(C.URL_SYNC, use_setinputsizes=False)
    t = C.tables()
    t.metadata.drop_all(engine)
    t.metadata.create_all(engine)
    conn = pyodbc.connect(C.ODBC, autocommit=False)
    for stmt_kind in ("output", "inline"):
        for dup_at in (0, 150, 299):
            prefix = f"/n-{stmt_kind}-{dup_at}"
            rows = [C.entry_row(i, False, prefix=prefix) for i in range(N)]
            rows[dup_at]["path"] = rows[10]["path"] if dup_at != 10 else rows[11]["path"]
            if dup_at == 0:
                rows[0]["path"] = rows[10]["path"]
            sql, params, _, names = C.compiled(engine.dialect, t.entry, rows)
            if stmt_kind == "inline":
                sql = inline_sql(engine.dialect, t.entry, names)
            error = None
            try:
                cur = conn.cursor()
                cur.fast_executemany = True
                cur.executemany(sql, params)
                cur.close()
            except Exception as exc:
                error = f"{type(exc).__name__}: {str(exc)[:120]}"
            conn.commit()
            landed = conn.cursor().execute(f"SELECT COUNT(*) FROM {t.entry.name} WHERE path LIKE '{prefix}/%'").fetchval()
            conn.commit()
            C.record(probe="N-midbatch", statement=stmt_kind, duplicate_row=dup_at, n=N, landed=landed, error=error)
    # content table: VARCHAR(max) bodies
    now = datetime.datetime(2026, 8, 26, 12, 0, 0, tzinfo=datetime.UTC)
    bodies = [("x" * 20_000) for _ in range(N)]
    bodies[7] = "y" * 400_000
    rows = [{"entry_id": str(ULID()), "created_at": now, "content": b} for b in bodies]
    sql, params, page, names = C.compiled(engine.dialect, t.content, rows)
    sql = inline_sql(engine.dialect, t.content, names)
    error = None
    try:
        cur = conn.cursor()
        cur.fast_executemany = True
        cur.executemany(sql, params)
        cur.close()
    except Exception as exc:
        error = f"{type(exc).__name__}: {str(exc)[:200]}"
    conn.commit()
    landed, total = conn.cursor().execute(f"SELECT COUNT(*), SUM(LEN(content)) FROM {t.content.name}").fetchone()
    conn.commit()
    C.record(probe="N-content-max", n=N, landed=landed, bytes_expected=sum(len(b) for b in bodies), bytes_landed=total, error=error, sql_tail=sql.split("VALUES")[0][-30:])
    conn.close()
    t.metadata.drop_all(engine)
    engine.dispose()


if __name__ == "__main__":
    main()
