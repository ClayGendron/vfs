import gc, sys, types
import pytest
from sqlalchemy.sql.schema import MetaData
from sqlalchemy.dialects.sqlite.aiosqlite import SQLiteDialect_aiosqlite
pytest.main(sys.argv[1:])
gc.collect()
def describe(o):
    t = type(o)
    name = f"{t.__module__}.{t.__name__}"
    if isinstance(o, dict):
        keys = list(o)[:3]
        return f"dict(len={len(o)}, keys~{[str(k)[:40] for k in keys]})"
    if isinstance(o, types.FrameType): return f"frame {o.f_code.co_filename}:{o.f_lineno}"
    if isinstance(o, types.FunctionType): return f"function {o.__module__}.{o.__qualname__}"
    if isinstance(o, types.CellType): return "cell"
    return name
def walk(obj, depth, seen, indent="  "):
    if depth == 0: return
    for r in gc.get_referrers(obj):
        if id(r) in seen or r is seen or isinstance(r, types.FrameType) and 'referrers.py' in r.f_code.co_filename: continue
        if type(r).__name__ in ("list",) and len(r) > 1000: continue
        seen.add(id(r))
        print(f"{indent}<- {describe(r)}", flush=True)
        walk(r, depth-1, seen, indent + "    ")
for cls in (MetaData, SQLiteDialect_aiosqlite):
    alive = [o for o in gc.get_objects() if isinstance(o, cls)]
    print(f"\n=== {cls.__name__}: {len(alive)} alive; referrer chain from the last one ===", flush=True)
    if alive:
        seen = {id(alive)}
        walk(alive[-1], 4, seen)
