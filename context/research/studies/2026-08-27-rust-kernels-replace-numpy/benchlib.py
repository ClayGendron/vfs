"""Shared helpers: the store, timing, memory, machine facts."""

from __future__ import annotations

import json
import os
import platform
import statistics
import subprocess
import sys
import time
import tracemalloc
from pathlib import Path

DB = Path(
    os.environ.get(
        "VFS_BENCH_DB",
        "/private/tmp/claude-501/-Users-claygendron-Git-Repos-vfs/"
        "9aca8a65-866f-4cbb-bc2b-685f1963370c/scratchpad/landing_full.sqlite",
    )
)
OUT = Path(os.environ.get("VFS_BENCH_OUT", Path(__file__).resolve().parent / "results"))
OUT.mkdir(exist_ok=True)
REPEATS = int(os.environ.get("REPEATS", "7"))


def timed_ms(fn, reps: int = REPEATS) -> float:
    times = []
    for _ in range(reps):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000.0)
    return statistics.median(times)


def peak_kb(fn) -> float:
    """tracemalloc peak (KiB) of one call — Python-side allocations, numpy included."""
    tracemalloc.start()
    tracemalloc.reset_peak()
    fn()
    _cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return peak / 1024.0


def machine() -> dict:
    cpu = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True).stdout.strip()
    rustc = subprocess.run(["rustc", "--version"], capture_output=True, text=True).stdout.strip()
    import numpy

    return {
        "python": sys.version.split()[0],
        "numpy": numpy.__version__,
        "rustc": rustc,
        "platform": platform.platform(),
        "cpu": cpu,
        "db": str(DB),
        "db_bytes": DB.stat().st_size,
        "date": time.strftime("%Y-%m-%d"),
    }


def dump(name: str, payload: dict) -> Path:
    path = OUT / name
    path.write_text(json.dumps(payload, indent=1))
    print(f"-> {path}")
    return path
