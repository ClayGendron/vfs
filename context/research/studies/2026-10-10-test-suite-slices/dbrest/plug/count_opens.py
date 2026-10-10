"""pytest plugin: count mount opens and time first-touch / create_all / __init__."""
import time, functools, collections
import pytest
from sqlalchemy import MetaData
from vfs.storage.backends.database.engine import EngineHost
from vfs.storage.backends.database import DatabaseStorage

acc = collections.Counter(); cnt = collections.Counter()
def wrap_sync(cls, name):
    orig = getattr(cls, name)
    @functools.wraps(orig)
    def w(*a, **k):
        t=time.perf_counter()
        try: return orig(*a, **k)
        finally: acc[name]+=time.perf_counter()-t; cnt[name]+=1
    setattr(cls, name, w)
def wrap_async(cls, name):
    orig = getattr(cls, name)
    @functools.wraps(orig)
    async def w(*a, **k):
        t=time.perf_counter()
        try: return await orig(*a, **k)
        finally: acc[name]+=time.perf_counter()-t; cnt[name]+=1
    setattr(cls, name, w)
wrap_sync(MetaData, "create_all")
wrap_sync(DatabaseStorage, "__init__")
wrap_async(EngineHost, "_first_touch")
wrap_async(EngineHost, "_verify_or_provision")
wrap_async(EngineHost, "_probe_sqlite_vec")
wrap_async(EngineHost, "_apply_file_settings")
wrap_async(EngineHost, "close")

def pytest_sessionfinish(session, exitstatus):
    print("\n=== mount accounting ===")
    for k in acc: print(f"  {k:22} n={cnt[k]:5} total={acc[k]:6.2f}s mean={acc[k]/cnt[k]*1000:6.1f}ms")
