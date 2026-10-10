"""DDL cost per fresh :memory: mount: create_all(checkfirst) vs checkfirst=False vs one executescript of precompiled DDL."""
from __future__ import annotations
import sqlite3, sys, time
sys.path.insert(0, "/Users/claygendron/Git/Repos/vfs")
from sqlalchemy import create_engine
from sqlalchemy.schema import CreateTable, CreateIndex
from vfs.models.rows import build_vfs_tables

tables = build_vfs_tables()
md = tables.metadata
N = 30

def bench(label, fn):
    t0 = time.perf_counter()
    for _ in range(N):
        fn()
    dt = (time.perf_counter() - t0) / N
    print(f"{label:48s} {1000*dt:6.1f} ms/mount")

def create_all_checkfirst():
    e = create_engine("sqlite://")
    with e.begin() as c:
        md.create_all(c, checkfirst=True)
    e.dispose()

def create_all_nocheck():
    e = create_engine("sqlite://")
    with e.begin() as c:
        md.create_all(c, checkfirst=False)
    e.dispose()

e0 = create_engine("sqlite://")
ddl = []
for t in md.sorted_tables:
    ddl.append(str(CreateTable(t).compile(e0)))
    for ix in t.indexes:
        ddl.append(str(CreateIndex(ix).compile(e0)))
script = ";\n".join(ddl) + ";"
print(f"{len(ddl)} DDL statements, {len(script)} chars")

def executescript_sqlalchemy():
    e = create_engine("sqlite://")
    with e.begin() as c:
        raw = c.connection.dbapi_connection
        raw.executescript(script)
    e.dispose()

def executescript_raw():
    c = sqlite3.connect(":memory:")
    c.executescript(script)
    c.close()

def engine_only():
    e = create_engine("sqlite://")
    with e.begin() as c:
        pass
    e.dispose()

bench("engine create+dispose only", engine_only)
bench("create_all(checkfirst=True)  [live]", create_all_checkfirst)
bench("create_all(checkfirst=False)", create_all_nocheck)
bench("executescript(precompiled DDL) via engine", executescript_sqlalchemy)
bench("executescript(precompiled DDL) raw sqlite3", executescript_raw)
