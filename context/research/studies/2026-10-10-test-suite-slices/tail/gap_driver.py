import atexit, sys, time, threading
T0 = time.perf_counter()
import pytest
T1 = time.perf_counter()
rc = pytest.main(sys.argv[1:])
T2 = time.perf_counter()
alive = [t for t in threading.enumerate() if t is not threading.main_thread()]
print(f"\nGAP: import pytest {T1-T0:.2f}s | pytest.main {T2-T1:.2f}s | threads alive at return: {len(alive)} ({sum(1 for t in alive if t.daemon)} daemon)", flush=True)
atexit.register(lambda: print(f"GAP: atexit reached at +{time.perf_counter()-T2:.2f}s after main returned", flush=True))
