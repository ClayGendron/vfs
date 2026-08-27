"""Probe F: mechanism tests in bare pyodbc. Same 300-row entry page (or a
block-row page), fast_executemany on, one executemany per page, then one of:
  close     - cursor.close() right after executemany (what pyodbc/SQLAlchemy do)
  drain     - loop cursor.nextset() until it returns False, then close
  sleep     - time.sleep(1.5) before close
  noclose   - never close the cursor; commit the connection directly
  slow      - fast_executemany OFF (pyodbc's row-at-a-time executemany)
Records landed rows and the server's attention / error count for the session."""
from __future__ import annotations

import sys
import time
import xml.etree.ElementTree as ET  # noqa: N817

import pyodbc
from sqlalchemy import create_engine

import rl_common as C

SHAPE = sys.argv[1] if len(sys.argv) > 1 else "entry_nullfree"
N = int(sys.argv[2]) if len(sys.argv) > 2 else 300
PAGE = int(sys.argv[3]) if len(sys.argv) > 3 else 300
MODES = sys.argv[4].split(",") if len(sys.argv) > 4 else ["close", "drain", "sleep", "noclose", "slow"]
SESSION = "rl_mech"
XE = f"CREATE EVENT SESSION [{SESSION}] ON SERVER ADD EVENT sqlserver.rpc_completed(ACTION(sqlserver.session_id)), ADD EVENT sqlserver.error_reported(ACTION(sqlserver.session_id)), ADD EVENT sqlserver.attention(ACTION(sqlserver.session_id)) ADD TARGET package0.ring_buffer(SET max_memory = 16384) WITH (MAX_DISPATCH_LATENCY = 1 SECONDS)"


def xe_counts(admin, spid):
    time.sleep(2)
    cur = admin.cursor()
    cur.execute("SELECT CAST(t.target_data AS nvarchar(max)) FROM sys.dm_xe_session_targets t JOIN sys.dm_xe_sessions s ON s.address = t.event_session_address WHERE s.name = ?", SESSION)
    root = ET.fromstring(cur.fetchone()[0])
    counts, executes, errors = {}, 0, []
    for ev in root.iter("event"):
        act = ev.find("action[@name='session_id']/value")
        if act is None or act.text != str(spid):
            continue
        counts[ev.get("name")] = counts.get(ev.get("name"), 0) + 1
        fields = {d.get("name"): (d.find("value").text if d.find("value") is not None else None) for d in ev.findall("data")}
        if ev.get("name") == "rpc_completed" and (fields.get("statement") or "").startswith("exec sp_execute"):
            executes += 1
        if ev.get("name") == "error_reported":
            errors.append(f"{fields.get('error_number')}: {(fields.get('message') or '')[:120]}")
    return counts, executes, errors


def main() -> None:
    engine = create_engine(C.URL_SYNC, use_setinputsizes=False)
    t = C.tables()
    t.metadata.drop_all(engine)
    t.metadata.create_all(engine)
    admin = pyodbc.connect(C.ODBC, autocommit=True)
    acur = admin.cursor()
    for mode in MODES:
        conn = pyodbc.connect(C.ODBC, autocommit=False)
        spid = conn.cursor().execute("SELECT @@SPID").fetchval()
        conn.commit()
        acur.execute(f"IF EXISTS (SELECT 1 FROM sys.server_event_sessions WHERE name = '{SESSION}') DROP EVENT SESSION [{SESSION}] ON SERVER")
        acur.execute(XE)
        acur.execute(f"ALTER EVENT SESSION [{SESSION}] ON SERVER STATE = START")
        if SHAPE.startswith("entry"):
            table, key = t.entry, "path"
            rows = [C.entry_row(i, SHAPE == "entry_nulls", prefix=f"/m-{mode}") for i in range(N)]
            where = f"path LIKE '/m-{mode}/%'"
        else:
            table, key = t.lex_postings, "term"
            epoch = MODES.index(mode) + 1
            rows = [C.block_row(i, epoch=epoch) for i in range(N)]
            where = f"epoch = {epoch}"
        sql, params, _, names = C.compiled(engine.dialect, table, rows)
        error, rowcounts, nextsets, elapsed = None, [], [], []
        try:
            for chunk in C.chunked(params, PAGE):
                cur = conn.cursor()
                cur.fast_executemany = mode != "slow"
                t0 = time.perf_counter()
                cur.executemany(sql, list(chunk))
                elapsed.append(round(time.perf_counter() - t0, 3))
                rowcounts.append(cur.rowcount)
                if mode == "drain":
                    n = 0
                    while cur.nextset():
                        n += 1
                    nextsets.append(n)
                elif mode == "sleep":
                    time.sleep(1.5)
                if mode != "noclose":
                    cur.close()
        except Exception as exc:
            error = f"{type(exc).__name__}: {str(exc)[:300]}"
        conn.commit()
        landed = {r[0] for r in conn.cursor().execute(f"SELECT {key} FROM {table.name} WHERE {where}").fetchall()}
        conn.commit()
        expected = {r[key] for r in rows}
        missing = sorted(expected - landed, key=lambda s: int(s.rsplit("/", 1)[-1].lstrip("t")))
        counts, executes, errors = xe_counts(admin, spid)
        acur.execute(f"ALTER EVENT SESSION [{SESSION}] ON SERVER STATE = STOP")
        acur.execute(f"DROP EVENT SESSION [{SESSION}] ON SERVER")
        conn.close()
        C.record(probe="F-mechanism", mode=mode, shape=SHAPE, n=N, page=PAGE, landed=len(landed), expected=N, error=error,
                 rowcounts=rowcounts, nextsets=nextsets, seconds=elapsed, xe=counts, sp_execute_completed=executes, xe_errors=errors[:5],
                 missing_ranges=_ranges(missing))
    admin.close()
    t.metadata.drop_all(engine)
    engine.dispose()


def _ranges(missing):
    nums = [int(s.rsplit("/", 1)[-1].lstrip("t")) for s in missing]
    out, start, prev = [], None, None
    for n in nums:
        if start is None:
            start = prev = n
        elif n == prev + 1:
            prev = n
        else:
            out.append(f"{start}-{prev}")
            start = prev = n
    if start is not None:
        out.append(f"{start}-{prev}")
    return out


if __name__ == "__main__":
    main()
