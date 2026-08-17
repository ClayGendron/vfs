"""Cold experiment: fresh APFS clone per run (new vnode defeats the page
cache), one subprocess per run, scan overlay excluded (mode-independent)."""
import json, statistics, subprocess, os, sys

ROWS = [
    ("scoped-01 EXPORT_SYMBOL_GPL @ drivers/**", ["file:25000", "chunk:none"]),
    ("scoped-02 kzalloc @ drivers/net/**", ["file:25000", "chunk:none"]),
    ("scoped-03 mutex_lock @ drivers/gpu/drm/**", ["file:25000", "chunk:none"]),
    ("unscoped copyright -i", ["file:25000", "chunk:25000", "chunk:none"]),
    ("unscoped kfree -w", ["file:25000", "chunk:none"]),
    ("unscoped randomize_kstack_offset", ["file:25000", "chunk:none"]),
]
RUNS = 5
SRC = "linux-chunk.sqlite"

out = {}
for key, legs in ROWS:
    out[key] = {}
    for leg in legs:
        mode, budget = leg.split(":")
        totals, last = [], None
        for i in range(RUNS):
            clone = f"cold-{os.getpid()}-{i}.sqlite"
            subprocess.run(["cp", "-c", SRC, clone], check=True)
            try:
                p = subprocess.run(
                    [sys.executable, "cold_one.py", clone, mode, key, budget],
                    capture_output=True, text=True, check=True)
                last = json.loads(p.stdout.strip().splitlines()[-1])
                totals.append(last["total_ms"])
            finally:
                for suf in ("", "-wal", "-shm"):
                    try: os.remove(clone + suf)
                    except FileNotFoundError: pass
        out[key][leg] = {"median_ms": statistics.median(totals), "all_ms": totals, "last": last}
        print(f"{key:44s} {leg:12s} median {statistics.median(totals):8.1f} ms  {['%.0f' % t for t in totals]}", flush=True)
json.dump(out, open("cold_results.json", "w"), indent=2)
print("written cold_results.json")
