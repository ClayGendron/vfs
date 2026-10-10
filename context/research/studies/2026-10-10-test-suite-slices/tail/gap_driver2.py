import gc, sys, time, threading, collections
import pytest
rc = pytest.main(sys.argv[1:])
T = time.perf_counter()
objs = gc.get_objects()
kinds = collections.Counter(f"{type(o).__module__}.{type(o).__name__}" for o in objs)
want = [k for k in kinds if any(s in k for s in ("AsyncEngine", "engine.base.Engine", "aiosqlite", "BaseEventLoop", "_UnixSelectorEventLoop", "ThreadPoolExecutor", "StaticPool", "VFSTables", "VirtualFileSystem", "InMemoryStorage", "DatabaseStorage", "MetaData", "Table"))]
print(f"\nGAP2: {len(objs)} tracked objects; threads={threading.active_count()}", flush=True)
for k in sorted(want): print(f"GAP2:   {kinds[k]:6d} {k}", flush=True)
t0 = time.perf_counter(); n = gc.collect(); print(f"GAP2: explicit gc.collect() freed {n} in {time.perf_counter()-t0:.2f}s", flush=True)
objs2 = gc.get_objects(); print(f"GAP2: {len(objs2)} tracked after collect; {time.perf_counter()-T:.2f}s since main returned", flush=True)
