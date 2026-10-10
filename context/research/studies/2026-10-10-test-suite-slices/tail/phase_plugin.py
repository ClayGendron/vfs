import time, atexit, sys
T0 = time.perf_counter()
def _stamp(name): print(f"\nPHASE {name:16s} +{time.perf_counter()-T0:6.2f}s", file=sys.stderr, flush=True)
def pytest_configure(config): _stamp("configure")
def pytest_sessionstart(session): _stamp("sessionstart")
def pytest_collection_finish(session): _stamp("collection_done")
def pytest_sessionfinish(session, exitstatus): _stamp("sessionfinish")
def pytest_unconfigure(config): _stamp("unconfigure"); atexit.register(lambda: _stamp("atexit"))
