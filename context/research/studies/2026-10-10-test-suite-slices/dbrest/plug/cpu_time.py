import resource, time
t0=[0.0]
def pytest_sessionstart(session): t0[0]=time.perf_counter()
def pytest_sessionfinish(session, exitstatus):
    r=resource.getrusage(resource.RUSAGE_SELF)
    print(f"\n=== CPU: user={r.ru_utime:.1f}s sys={r.ru_stime:.1f}s total={r.ru_utime+r.ru_stime:.1f}s wall={time.perf_counter()-t0[0]:.1f}s")
