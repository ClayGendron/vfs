"""Probe N2: mid-batch failure x statement kind x close/drain, capturing
cursor.messages (pyodbc's copy of the diagnostic records) and cursor.rowcount."""
from __future__ import annotations

import pyodbc
from sqlalchemy import bindparam, create_engine, insert

import rl_common as C

N = 300


def main() -> None:
    engine = create_engine(C.URL_SYNC, use_setinputsizes=False)
    t = C.tables()
    t.metadata.drop_all(engine)
    t.metadata.create_all(engine)
    conn = pyodbc.connect(C.ODBC, autocommit=False)
    for stmt_kind in ("output", "inline"):
        for dup_at in (0, 150):
            for mode in ("close", "drain"):
                prefix = f"/n2-{stmt_kind}-{dup_at}-{mode}"
                rows = [C.entry_row(i, False, prefix=prefix) for i in range(N)]
                rows[dup_at]["path"] = rows[10]["path"]
                sql, params, _, names = C.compiled(engine.dialect, t.entry, rows)
                if stmt_kind == "inline":
                    sql = str(insert(t.entry).values({n: bindparam(n) for n in names}).inline().compile(dialect=engine.dialect))
                error, messages, rowcount, nextsets = None, [], None, 0
                cur = conn.cursor()
                cur.fast_executemany = True
                try:
                    cur.executemany(sql, params)
                    rowcount = cur.rowcount
                    messages = [str(m)[:160] for m in (cur.messages or [])]
                    if mode == "drain":
                        while cur.nextset():
                            nextsets += 1
                except Exception as exc:
                    error = f"{type(exc).__name__}: {str(exc)[:100]}"
                    messages = [str(m)[:160] for m in (cur.messages or [])]
                cur.close()
                conn.commit()
                landed = conn.cursor().execute(f"SELECT COUNT(*) FROM {t.entry.name} WHERE path LIKE '{prefix}/%'").fetchval()
                conn.commit()
                C.record(probe="N2-midbatch", statement=stmt_kind, duplicate_row=dup_at, mode=mode, n=N, landed=landed, error=error,
                         rowcount=rowcount, nextsets=nextsets, messages=messages[:3])
    conn.close()
    t.metadata.drop_all(engine)
    engine.dispose()


if __name__ == "__main__":
    main()
