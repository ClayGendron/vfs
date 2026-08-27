"""Probe M: what the live ODBC driver declares for parameter arrays
(SQLGetInfo SQL_PARAM_ARRAY_ROW_COUNTS=153, SQL_PARAM_ARRAY_SELECTS=154), the
driver/server versions, and whether SET NOCOUNT ON changes the OUTPUT loss."""
import pyodbc
from sqlalchemy import create_engine

import rl_common as C

conn = pyodbc.connect(C.ODBC, autocommit=False)
info = {
    "driver_name": conn.getinfo(pyodbc.SQL_DRIVER_NAME),
    "driver_ver": conn.getinfo(pyodbc.SQL_DRIVER_VER),
    "driver_odbc_ver": conn.getinfo(pyodbc.SQL_DRIVER_ODBC_VER),
    "dbms": conn.getinfo(pyodbc.SQL_DBMS_NAME),
    "dbms_ver": conn.getinfo(pyodbc.SQL_DBMS_VER),
    "SQL_PARAM_ARRAY_ROW_COUNTS(153)": conn.getinfo(153),
    "SQL_PARAM_ARRAY_SELECTS(154)": conn.getinfo(154),
    "pyodbc": pyodbc.version,
}
# ODBC: SQL_PARC_BATCH=1, SQL_PARC_NO_BATCH=2; SQL_PAS_BATCH=1, SQL_PAS_NO_BATCH=2, SQL_PAS_NO_SELECT=3
engine = create_engine(C.URL_SYNC, use_setinputsizes=False)
t = C.tables()
t.metadata.drop_all(engine)
t.metadata.create_all(engine)
out = {}
for nocount in (False, True):
    prefix = f"/m-nocount-{nocount}"
    rows = [C.entry_row(i, False, prefix=prefix) for i in range(300)]
    sql, params, _, _ = C.compiled(engine.dialect, t.entry, rows)
    cur = conn.cursor()
    if nocount:
        cur.execute("SET NOCOUNT ON")
    cur.fast_executemany = True
    cur.executemany(sql, params)
    cur.close()
    conn.commit()
    out[f"output_stmt_landed_nocount={nocount}"] = conn.cursor().execute(f"SELECT COUNT(*) FROM {t.entry.name} WHERE path LIKE '{prefix}/%'").fetchval()
    conn.commit()
C.record(probe="M-driverinfo", **info, **out)
conn.close()
t.metadata.drop_all(engine)
engine.dispose()
