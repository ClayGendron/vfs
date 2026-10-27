"""Probe: is wasmtime-py's module-global LAST_EXCEPTION a cross-thread hazard?

Run from the vfs repo root:
    uv run --with wasmtime python context/research/studies/2026-10-15-agent-shell/experiments/s5/probe_wasmtime_trap_global.py

Each thread owns its own Store and instance of a tiny module whose export calls
a host import that raises an exception tagged with the calling thread's id. If
the exception that surfaces at the embedder boundary carries another thread's
tag (or none), the global leaked across threads. ctypes releases the GIL for the
foreign call, so threads really do run guest code concurrently.
"""

from __future__ import annotations

import threading
from collections import Counter

import wasmtime

WAT = """
(module
  (import "env" "boom" (func $boom))
  (func (export "run") (call $boom)))
"""


class Tagged(Exception):
    def __init__(self, tag: int) -> None:
        super().__init__(str(tag))
        self.tag = tag


def worker(engine: wasmtime.Engine, module: wasmtime.Module, tag: int, n: int, results: Counter, lock: threading.Lock) -> None:
    store = wasmtime.Store(engine)
    linker = wasmtime.Linker(engine)

    def boom() -> None:
        raise Tagged(tag)

    linker.define_func("env", "boom", wasmtime.FuncType([], []), boom)
    inst = linker.instantiate(store, module)
    run = inst.exports(store)["run"]
    local = Counter()
    for _ in range(n):
        try:
            run(store)
            local["no exception"] += 1
        except Tagged as e:
            local["own tag" if e.tag == tag else "FOREIGN tag"] += 1
        except wasmtime.Trap:
            local["bare Trap (exception lost)"] += 1
        except Exception as e:  # noqa: BLE001
            local[f"other: {type(e).__name__}"] += 1
    with lock:
        results.update(local)


def main() -> None:
    engine = wasmtime.Engine()
    module = wasmtime.Module(engine, WAT)
    results: Counter = Counter()
    lock = threading.Lock()
    threads = [threading.Thread(target=worker, args=(engine, module, i, 2000, results, lock)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    print("8 threads x 2000 raising host calls, one Store per thread:")
    for k, v in sorted(results.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
