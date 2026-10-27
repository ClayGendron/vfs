# Step 7 guest benchmark: arange(1e6).sum() and a few numpy kernels, timed inside the guest with time.perf_counter.
import time, numpy as np
t0 = time.perf_counter(); a = np.arange(1_000_000); s = a.sum(); t1 = time.perf_counter()
reps = 20
t2 = time.perf_counter()
for _ in range(reps): s = np.arange(1_000_000).sum()
t3 = time.perf_counter()
x = np.random.default_rng(0).random(1_000_000)
t4 = time.perf_counter(); y = np.sort(x); t5 = time.perf_counter()
t6 = time.perf_counter(); m = (x * 2.0 + 1.0).mean(); t7 = time.perf_counter()
print(f"BENCH arange_sum_first_s={t1-t0:.6f} arange_sum_mean_s={(t3-t2)/reps:.6f} sort1e6_s={t5-t4:.6f} axpy_mean1e6_s={t7-t6:.6f} sum={int(s)} m={m:.6f}")
