"""Native comparison for the pandas groupby: uv run --with pandas --with numpy python scripts/bench_native_pandas.py"""
import time, sys, numpy as np, pandas as pd
rng = np.random.default_rng(0); n = 1_000_000
t0 = time.perf_counter(); big = pd.DataFrame({'k': rng.integers(0, 100, n), 'v': rng.random(n)}); t1 = time.perf_counter()
r = big.groupby('k')['v'].sum(); t2 = time.perf_counter()
r2 = big.groupby('k')['v'].agg(['mean', 'max', 'count']); t3 = time.perf_counter()
print(f"NATIVE python={sys.version.split()[0]} pandas={pd.__version__} numpy={np.__version__} build1e6_s={t1-t0:.4f} groupby_sum1e6_s={t2-t1:.4f} groupby_agg3_1e6_s={t3-t2:.4f} nkeys={len(r)} total={r.sum():.3f}")
