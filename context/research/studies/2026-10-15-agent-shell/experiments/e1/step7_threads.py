"""Step 7 — the LAST_EXCEPTION global under concurrent guests.

Part A: N threads each run a tiny guest that only calls proc_exit(code) with a distinct code,
many times; every run must report its own code. A cross-contaminated run shows up as the
wrong exit code (thread A raised B's GuestExit) or as a bare Trap("python exception")
(the global was already consumed). Part B: two real guests (upper) on distinct files,
concurrently, through the vfs loop; correctness of both outputs.
"""

from __future__ import annotations

import asyncio
import sys
import threading
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "shim"))

import wasmtime._func as wf  # noqa: E402
from host import Host  # noqa: E402
from vfs_wasi import GuestExit  # noqa: E402
from wasmtime import Engine, FuncType, Linker, Module, Store, Trap, ValType  # noqa: E402

from vfs import VirtualFileSystem  # noqa: E402

E1 = Path(__file__).parent
GUEST = E1 / "guest/target/wasm32-wasip1/release"

EXIT_WAT = """
(module
  (import "wasi_snapshot_preview1" "proc_exit" (func $exit (param i32)))
  (memory (export "memory") 1)
  (func (export "_start") (call $exit (i32.const {code}))))
"""


def part_a(threads: int = 4, reps: int = 2000) -> None:
    print(f"### Part A: LAST_EXCEPTION is {'a module global' if hasattr(wf, 'LAST_EXCEPTION') else 'NOT a module global'} "
          f"(wasmtime/_func.py); {threads} threads x {reps} proc_exit guests")
    engine = Engine()
    outcomes: Counter[str] = Counter()
    lock = threading.Lock()

    def worker(code: int) -> None:
        module = Module(engine, EXIT_WAT.replace("{code}", str(code)))
        linker = Linker(engine)

        def proc_exit(caller, c: int) -> None:
            raise GuestExit(c)

        linker.define_func("wasi_snapshot_preview1", "proc_exit", FuncType([ValType.i32()], []), proc_exit, access_caller=True)
        local: Counter[str] = Counter()
        for _ in range(reps):
            store = Store(engine)
            try:
                linker.instantiate(store, module).exports(store)["_start"](store)
                local["no exception at all"] += 1
            except GuestExit as e:
                local["own code" if e.code == code else f"WRONG code {e.code} (wanted {code})"] += 1
            except Trap as t:
                local[f"bare Trap: {t.message.splitlines()[0]}"] += 1
            except Exception as e:  # noqa: BLE001
                local[f"other: {type(e).__name__}"] += 1
        with lock:
            outcomes.update(local)

    ts = [threading.Thread(target=worker, args=(10 + i,)) for i in range(threads)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    total = sum(outcomes.values())
    for k, v in outcomes.most_common():
        print(f"  {v:6}/{total}  {k}")


async def part_b() -> None:
    print("\n### Part B: two real guests concurrently on the vfs loop (upper on two files)")
    fs = VirtualFileSystem()
    await fs.write(path="/bin/upper.wasm", data=(GUEST / "upper.wasm").read_bytes(), parents=True)
    await fs.write(path="/a/in.txt", content="one\ntwo\n", parents=True)
    await fs.write(path="/b/in.txt", content="x\ny\nz\nw\n", parents=True)
    host = Host(E1 / "outputs/cache")
    rounds = 20
    bad = 0
    for _ in range(rounds):
        ra, rb = await asyncio.gather(
            host.run(fs, "upper", ["upper", "/a/in.txt", "/a/out.txt"]),
            host.run(fs, "upper", ["upper", "/b/in.txt", "/b/out.txt"]),
        )
        if (ra.exit_code, ra.stdout) != (0, b"2\n") or (rb.exit_code, rb.stdout) != (0, b"4\n"):
            bad += 1
            print(f"  MISMATCH a=({ra.exit_code},{ra.stdout!r},{ra.trap_message}) b=({rb.exit_code},{rb.stdout!r},{rb.trap_message})")
    a = (await fs.read("/a/out.txt")).first()
    b = (await fs.read("/b/out.txt")).first()
    print(f"  {rounds} concurrent rounds, {bad} mismatches; /a/out.txt v{a.version}={a.content!r}; /b/out.txt v{b.version}={b.content!r}")
    print("  (the default executor has >1 worker, so both guests were on worker threads at once; vfs verbs serialize on the loop)")
    host.close()
    await fs.close()


if __name__ == "__main__":
    part_a()
    asyncio.run(part_b())
    print("\nSTEP 7 DONE")
