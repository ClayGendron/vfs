"""Probe C: bare pyodbc (sync, no SQLAlchemy execution path) with an Extended
Events trace of the probe's own session — SQL Server's view of every RPC and
every error raised while the parameter array executes. Also reads
cursor.rowcount, cursor.messages, and the pre-commit vs post-commit count."""
from __future__ import annotations

import sys
import time
import xml.etree.ElementTree as ET  # noqa: N817

import pyodbc
from sqlalchemy import create_engine

import rl_common as C

PAGES = [int(p) for p in sys.argv[1].split(",") if p] if len(sys.argv) > 1 and sys.argv[1] else [None]
SHAPE = sys.argv[2] if len(sys.argv) > 2 else "entry_nullfree"
N = int(sys.argv[3]) if len(sys.argv) > 3 else 300
FAST = (sys.argv[4] if len(sys.argv) > 4 else "1") == "1"
SESSION = "rl_trace"

XE_CREATE = f"""
CREATE EVENT SESSION [{SESSION}] ON SERVER
ADD EVENT sqlserver.rpc_completed(ACTION(sqlserver.session_id)),
ADD EVENT sqlserver.sql_batch_completed(ACTION(sqlserver.session_id)),
ADD EVENT sqlserver.error_reported(ACTION(sqlserver.session_id)),
ADD EVENT sqlserver.attention(ACTION(sqlserver.session_id))
ADD TARGET package0.ring_buffer(SET max_memory = 8192)
WITH (STARTUP_STATE = OFF, MAX_DISPATCH_LATENCY = 1 SECONDS)
"""


def xe_events(admin) -> list[dict]:
    cur = admin.cursor()
    cur.execute(
        "SELECT CAST(t.target_data AS xml) FROM sys.dm_xe_session_targets t JOIN sys.dm_xe_sessions s ON s.address = t.event_session_address WHERE s.name = ?",
        SESSION,
    )
    row = cur.fetchone()
    if row is None:
        return []
    root = ET.fromstring(row[0])
    out = []
    for ev in root.iter("event"):
        fields = {d.get("name"): (d.find("value").text if d.find("value") is not None else None) for d in ev.findall("data")}
        act = ev.find("action[@name='session_id']/value")
        rec = {"event": ev.get("name"), "t": ev.get("timestamp")[11:23], "spid": act.text if act is not None else None}
        if ev.get("name") in ("rpc_completed", "sql_batch_completed"):
            stmt = fields.get("statement") or fields.get("batch_text") or ""
            rec.update(rows=fields.get("row_count"), result=fields.get("result"), stmt=stmt[:110].replace("\n", " "))
        elif ev.get("name") == "error_reported":
            rec.update(error=fields.get("error_number"), sev=fields.get("severity"), state=fields.get("state"), msg=(fields.get("message") or "")[:200])
        out.append(rec)
    return out


def main() -> None:
    engine = create_engine(C.URL_SYNC, use_setinputsizes=False)
    t = C.tables()
    t.metadata.drop_all(engine)
    t.metadata.create_all(engine)
    admin = pyodbc.connect(C.ODBC, autocommit=True)
    conn = pyodbc.connect(C.ODBC, autocommit=False)
    spid = conn.cursor().execute("SELECT @@SPID").fetchval()
    conn.commit()
    acur = admin.cursor()
    acur.execute(f"IF EXISTS (SELECT 1 FROM sys.server_event_sessions WHERE name = '{SESSION}') DROP EVENT SESSION [{SESSION}] ON SERVER")
    acur.execute(XE_CREATE.format(spid=spid))
    acur.execute(f"ALTER EVENT SESSION [{SESSION}] ON SERVER STATE = START")
    for page_override in PAGES:
        if SHAPE.startswith("entry"):
            table = t.entry
            rows = [C.entry_row(i, SHAPE == "entry_nulls", prefix=f"/c{page_override}") for i in range(N)]
        else:
            table = t.lex_postings
            rows = [C.block_row(i, epoch=page_override or 0) for i in range(N)]
        sql, params, page, names = C.compiled(engine.dialect, table, rows)
        page = page_override or page
        calls, error = [], None
        try:
            for chunk in C.chunked(params, page):
                cur = conn.cursor()
                cur.fast_executemany = FAST
                cur.executemany(sql, list(chunk))
                calls.append({"n": len(chunk), "rowcount": cur.rowcount, "messages": [str(m)[:200] for m in (cur.messages or [])]})
                cur.close()
        except Exception as exc:
            error = f"{type(exc).__name__}: {str(exc)[:300]}"
        if SHAPE.startswith("entry"):
            where, key = f"path LIKE '/c{page_override}/%'", "path"
        else:
            where, key = f"epoch = {page_override or 0}", "term"
        pre = conn.cursor().execute(f"SELECT COUNT(*) FROM {table.name} WHERE {where}").fetchval()
        conn.commit()
        post = conn.cursor().execute(f"SELECT COUNT(*) FROM {table.name} WHERE {where}").fetchval()
        conn.commit()
        landed = {r[0] for r in conn.cursor().execute(f"SELECT {key} FROM {table.name} WHERE {where}").fetchall()}
        conn.commit()
        expected = {r[key] for r in rows}
        missing = sorted(expected - landed, key=lambda s: int(s.rsplit("/", 1)[-1].lstrip("t")))
        time.sleep(2)
        events = [e for e in xe_events(admin) if e.get("spid") == str(spid)]
        acur.execute(f"ALTER EVENT SESSION [{SESSION}] ON SERVER STATE = STOP")
        acur.execute(f"DROP EVENT SESSION [{SESSION}] ON SERVER")
        acur.execute(XE_CREATE.format(spid=spid))
        acur.execute(f"ALTER EVENT SESSION [{SESSION}] ON SERVER STATE = START")
        C.record(probe="C-bare-pyodbc", fast=FAST, shape=SHAPE, n=N, page=page, landed=len(landed), expected=N, pre_commit=pre, post_commit=post,
                 error=error, calls=calls, missing=missing[:400], ncols=len(names), types=C.describe_types(params),
                 xe_summary={k: sum(1 for e in events if e["event"] == k) for k in ("rpc_completed", "sql_batch_completed", "error_reported", "attention")},
                 xe_errors=[e for e in events if e["event"] in ("error_reported", "attention")][:20],
                 xe_rpc_sample=[e for e in events if e["event"] == "rpc_completed"][:3] + [e for e in events if e["event"] == "rpc_completed"][-3:])
    acur.execute(f"ALTER EVENT SESSION [{SESSION}] ON SERVER STATE = STOP")
    acur.execute(f"DROP EVENT SESSION [{SESSION}] ON SERVER")
    conn.close()
    admin.close()
    t.metadata.drop_all(engine)
    engine.dispose()


if __name__ == "__main__":
    main()
