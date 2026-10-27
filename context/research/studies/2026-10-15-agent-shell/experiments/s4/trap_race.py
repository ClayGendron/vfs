"""Does wasmtime-py's module-global LAST_EXCEPTION cross-contaminate concurrent guests?

Two guests run on two threads, each calling proc_exit with its own code
(fsops exit 11 / exit 22), N rounds. A mismatch means thread A received
thread B's GuestExit.

    uv run --with wasmtime python context/research/studies/2026-10-15-agent-shell/experiments/s4/trap_race.py
"""

from __future__ import annotations

import sys
import threading
from collections import Counter
from pathlib import Path

from wasmtime import Engine, FuncType, Linker, Module, Store, ValType

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shim import ENOSYS, GuestExit  # noqa: E402

SETUP_LOCK = threading.Lock()
WASM = Path(__file__).resolve().parent / "fsops" / "target" / "wasm32-wasip1" / "release" / "fsops.wasm"
ROUNDS = int(sys.argv[1]) if len(sys.argv) > 1 else 300


def make_runner(engine: Engine, module: Module, code: int):
    argv = ["fsops", "exit", str(code)]

    def build():
        linker = Linker(engine)
        for imp in module.imports:
            name = imp.name
            ty = imp.type
            if name == "proc_exit":
                def proc_exit(caller, rval):
                    raise GuestExit(rval)
                linker.define_func("wasi_snapshot_preview1", name, ty, proc_exit, access_caller=True)
            elif name == "args_sizes_get":
                def args_sizes_get(caller, argc_ptr, size_ptr):
                    mem = caller.get("memory")
                    mem.write(caller, bytearray(len(argv).to_bytes(4, "little")), argc_ptr)
                    mem.write(caller, bytearray(sum(len(a) + 1 for a in argv).to_bytes(4, "little")), size_ptr)
                    return 0
                linker.define_func("wasi_snapshot_preview1", name, ty, args_sizes_get, access_caller=True)
            elif name == "args_get":
                def args_get(caller, argv_ptr, buf_ptr):
                    mem = caller.get("memory")
                    off = buf_ptr
                    for i, a in enumerate(argv):
                        mem.write(caller, bytearray(off.to_bytes(4, "little")), argv_ptr + 4 * i)
                        b = a.encode() + b"\0"
                        mem.write(caller, bytearray(b), off)
                        off += len(b)
                    return 0
                linker.define_func("wasi_snapshot_preview1", name, ty, args_get, access_caller=True)
            else:
                has_result = len(ty.results) == 1
                def stub(caller, *a, _r=has_result):
                    return 0 if _r else None
                linker.define_func("wasi_snapshot_preview1", name, ty, stub, access_caller=True)
        return linker.instantiate_pre(module)

    pre = None

    def run_once() -> int:
        nonlocal pre
        with SETUP_LOCK:  # define_func mutates wasmtime-py's module-global Slab: serialize setup
            if pre is None:
                pre = build()
        store = Store(engine)
        inst = pre.instantiate(store)
        try:
            inst.exports(store)["_start"](store)
        except GuestExit as e:
            return e.code
        except Exception as e:  # noqa: BLE001
            return -1
        return 0

    return run_once


def main() -> None:
    engine = Engine()
    module = Module.from_file(engine, str(WASM))
    results: dict[int, Counter[int]] = {11: Counter(), 22: Counter()}

    def worker(code: int) -> None:
        run_once = make_runner(engine, module, code)
        for _ in range(ROUNDS):
            results[code][run_once()] += 1

    threads = [threading.Thread(target=worker, args=(c,)) for c in (11, 22)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    print("rounds per thread:", ROUNDS)
    for code, seen in results.items():
        print(f"thread expecting {code}: observed {dict(seen)}")
    mism = sum(n for code, seen in results.items() for got, n in seen.items() if got != code)
    print("mismatches:", mism)


if __name__ == "__main__":
    main()
