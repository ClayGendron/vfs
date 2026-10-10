import asyncio, time, collections, pytest
acc=collections.Counter(); cnt=collections.Counter(); per_test=collections.Counter(); per_file=collections.Counter()
current=[None]
_orig=asyncio.sleep
async def spy(d, *a, **k):
    t=time.perf_counter()
    try:
        return await _orig(d, *a, **k)
    finally:
        if d and d>0:
            e=time.perf_counter()-t; acc["asyncio.sleep"]+=e; cnt["asyncio.sleep"]+=1; per_test[current[0]]+=e; per_file[current[0].split("::")[0]]+=e
asyncio.sleep=spy
_ts=time.sleep
def tspy(d):
    t=time.perf_counter(); _ts(d); e=time.perf_counter()-t
    acc["time.sleep"]+=e; cnt["time.sleep"]+=1; per_test[current[0]]+=e; per_file[current[0].split("::")[0]]+=e
time.sleep=tspy
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    current[0]=item.nodeid; yield
def pytest_sessionfinish(session, exitstatus):
    print("\n=== elapsed sleep accounting ===")
    for k in acc: print(f"  {k:14} n={cnt[k]:5} elapsed={acc[k]:6.2f}s")
    print("  by file:")
    for k,v in per_file.most_common(12): print(f"    {v:5.2f}s  {k}")
    print("  top sleepers:")
    for k,v in per_test.most_common(20): print(f"    {v:5.2f}s  {k}")
