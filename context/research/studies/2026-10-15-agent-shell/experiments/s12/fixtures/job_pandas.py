# Stretch job: pandas read_csv from a vfs row, groupby, to_csv back into a row (study 11's job minus the PNG).
import os, time
import numpy as np, pandas as pd
os.makedirs('/out', exist_ok=True)
df = pd.read_csv('/data/sales.csv')
summary = df.groupby('region')['sales'].agg(['sum', 'mean', 'max'])
print('rows:', len(df), 'regions:', list(summary.index))
print(summary.round(2).to_string())
summary.to_csv('/out/summary.csv')
print(open('/out/summary.csv').read(), end='')
rng = np.random.default_rng(0)
n = 1_000_000
t0 = time.perf_counter(); big = pd.DataFrame({'k': rng.integers(0, 100, n), 'v': rng.random(n)}); t1 = time.perf_counter()
r = big.groupby('k')['v'].sum(); t2 = time.perf_counter()
r2 = big.groupby('k')['v'].agg(['mean', 'max', 'count']); t3 = time.perf_counter()
print(f"BENCH pandas={pd.__version__} build1e6_s={t1-t0:.4f} groupby_sum1e6_s={t2-t1:.4f} groupby_agg3_1e6_s={t3-t2:.4f} nkeys={len(r)} total={r.sum():.3f}")
