"""Probe H: bisect inside the real entry table (build_vfs_tables DDL) — which
key subsets leave pending results / lose rows. Bare pyodbc, one 300-row
fast_executemany call, close vs drain. Also prints the mssql DDL and the
exact first parameter tuple Core's bind processors produce."""
from __future__ import annotations

import datetime

import pyodbc
from sqlalchemy import create_engine

import rl_common as C

N = 300
REQUIRED = ("entry_id", "path", "name", "kind")
SUBSETS = {
    "full12": None,
    "no_datetimes": ("entry_id", "parent_id", "path", "name", "kind", "version", "content_hash", "mime_type", "chunked"),
    "required_only": REQUIRED,
    "required+parent_id": REQUIRED + ("parent_id",),
    "required+created_at": REQUIRED + ("created_at",),
    "required+3datetimes": REQUIRED + ("created_at", "updated_at", "deleted_at"),
    "required+version": REQUIRED + ("version",),
    "required+content_hash+mime": REQUIRED + ("content_hash", "mime_type"),
    "required+chunked": REQUIRED + ("chunked",),
}


def run(conn, table, sql, params, mode, prefix):
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
    landed = conn.cursor().execute(f"SELECT COUNT(*) FROM {table} WHERE path LIKE '{prefix}/%'").fetchval()
    conn.commit()
    return landed, nextsets, error


def main() -> None:
    engine = create_engine(C.URL_SYNC, use_setinputsizes=False)
    t = C.tables()
    t.metadata.drop_all(engine)
    t.metadata.create_all(engine)
    print(C.ddl(t.entry))
    conn = pyodbc.connect(C.ODBC, autocommit=False)
    for name, keys in SUBSETS.items():
        for variant in ("core", "raw_datetimes"):
            prefix = f"/h-{name}-{variant}"
            rows = [C.entry_row(i, False, prefix=prefix) for i in range(N)]
            if keys is not None:
                rows = [{k: r[k] for k in keys} for r in rows]
            if variant == "raw_datetimes" and not any(k.endswith("_at") for k in rows[0]):
                continue
            sql, params, _, names = C.compiled(engine.dialect, t.entry, rows)
            if variant == "raw_datetimes":
                idx = [i for i, n in enumerate(names) if n.endswith("_at")]
                # bypass Core's DateTime bind processor: send naive datetime objects
                params = [tuple(C.NOW.replace(tzinfo=None) if i in idx else v for i, v in enumerate(p)) for p in params]
            if name == "full12" and variant == "core":
                print("names:", names)
                print("first row:", params[0])
            landed_close, _, e1 = run(conn, t.entry.name, sql, params, "close", prefix)
            rows2 = [C.entry_row(i, False, prefix=prefix + "d") for i in range(N)]
            if keys is not None:
                rows2 = [{k: r[k] for k in keys} for r in rows2]
            sql2, params2, _, _ = C.compiled(engine.dialect, t.entry, rows2)
            if variant == "raw_datetimes":
                params2 = [tuple(C.NOW.replace(tzinfo=None) if i in idx else v for i, v in enumerate(p)) for p in params2]
            landed_drain, nextsets, e2 = run(conn, t.entry.name, sql2, params2, "drain", prefix + "d")
            C.record(probe="H-entry-bisect", case=name, variant=variant, ncols=len(names), n=N, landed_on_close=landed_close,
                     landed_on_drain=landed_drain, pending_results=nextsets, error=e1 or e2)
    conn.close()
    t.metadata.drop_all(engine)
    engine.dispose()


if __name__ == "__main__":
    main()
