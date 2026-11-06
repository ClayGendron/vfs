"""Count the INSERT statements pandas.to_sql sends for 10,000 rows, per chunksize and method.

Run from /home/user/vfs: uv run python <this file>
"""

import pandas as pd
import sqlalchemy as sa
from sqlalchemy import event

eng = sa.create_engine("sqlite://")
seen: list[tuple[bool, int]] = []


@event.listens_for(eng, "before_cursor_execute")
def record(conn, cursor, statement, parameters, context, executemany):
    if statement.lstrip().upper().startswith("INSERT"):
        rows = len(parameters) if executemany else 1
        seen.append((executemany, rows if executemany else statement.count("(?") or 1))


df = pd.DataFrame({"path": [f"/f{i}" for i in range(10_000)], "body": ["x"] * 10_000})
print("pandas", pd.__version__, "sqlalchemy", sa.__version__)
print("insertmanyvalues_max_parameters:", eng.dialect.insertmanyvalues_max_parameters)
for chunksize, method in ((None, None), (1000, None), (None, "multi"), (1000, "multi")):
    seen.clear()
    try:
        n = df.to_sql("t", eng, if_exists="replace", index=False, chunksize=chunksize, method=method)
        print(f"chunksize={chunksize} method={method}: rows={n} INSERT executes={len(seen)} executemany={sorted({m for m, _ in seen})}")
    except Exception as exc:
        print(f"chunksize={chunksize} method={method}: {type(exc).__name__}: {str(exc)[:110]}")
