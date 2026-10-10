import gc, time, sys
_t = {}; _tot = {0:0.0,1:0.0,2:0.0}; _n = {0:0,1:0,2:0}
def _cb(phase, info):
    g = info["generation"]
    if phase == "start": _t[g] = time.perf_counter()
    else: _tot[g] += time.perf_counter() - _t[g]; _n[g] += 1
gc.callbacks.append(_cb)
def pytest_unconfigure(config):
    print(f"\nGC: gen0 {_n[0]}x {_tot[0]:.2f}s | gen1 {_n[1]}x {_tot[1]:.2f}s | gen2 {_n[2]}x {_tot[2]:.2f}s | tracked {len(gc.get_objects())}", file=sys.stderr, flush=True)
