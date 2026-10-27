"""Step 7b — defuse the LAST_EXCEPTION race: record the exit code in per-run state BEFORE raising,
and have the embedder read that state on any exception, never the exception's identity."""

from __future__ import annotations

import threading
from collections import Counter

from wasmtime import Engine, FuncType, Linker, Module, Store, ValType

EXIT_WAT = """
(module
  (import "wasi_snapshot_preview1" "proc_exit" (func $exit (param i32)))
  (memory (export "memory") 1)
  (func (export "_start") (call $exit (i32.const {code}))))
"""


class Exit(Exception):
    pass


def main(threads: int = 4, reps: int = 2000) -> None:
    engine = Engine()
    outcomes: Counter[str] = Counter()
    lock = threading.Lock()

    def worker(code: int) -> None:
        module = Module(engine, EXIT_WAT.replace("{code}", str(code)))
        linker = Linker(engine)
        state = {"exit": None}  # per-run shim state (one dict per run in the real shim)

        def proc_exit(caller, c: int) -> None:
            state["exit"] = c
            raise Exit()

        linker.define_func("wasi_snapshot_preview1", "proc_exit", FuncType([ValType.i32()], []), proc_exit, access_caller=True)
        local: Counter[str] = Counter()
        for _ in range(reps):
            state["exit"] = None
            store = Store(engine)
            try:
                linker.instantiate(store, module).exports(store)["_start"](store)
                local["returned normally (exit 0)"] += 1
            except BaseException:  # noqa: BLE001 — whichever exception object arrived
                local["own code via recorded state" if state["exit"] == code else f"WRONG recorded {state['exit']}"] += 1
        with lock:
            outcomes.update(local)

    ts = [threading.Thread(target=worker, args=(10 + i,)) for i in range(threads)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    total = sum(outcomes.values())
    for k, v in outcomes.most_common():
        print(f"  {v:6}/{total}  {k}")


if __name__ == "__main__":
    main()
