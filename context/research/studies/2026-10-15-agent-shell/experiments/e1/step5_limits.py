"""Step 5 — a spinning guest is killed by the epoch deadline; a greedy guest hits the memory limit.

Three trap classes must be distinguishable: INTERRUPT (our timeout), UNREACHABLE (the guest
aborted — Rust's alloc-failure handler), MEMORY_OUT_OF_BOUNDS (a raw guest bug).
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "shim"))

from host import Host  # noqa: E402
from wasmtime import Module, Store, Trap, TrapCode  # noqa: E402

from vfs import VirtualFileSystem  # noqa: E402

E1 = Path(__file__).parent
GUEST = E1 / "guest/target/wasm32-wasip1/release"

# A raw guest bug: grow memory by one page then store past the end of it.
OOB_WAT = """
(module
  (memory (export "memory") 1)
  (func (export "_start")
    (drop (memory.grow (i32.const 1)))
    (i32.store (i32.const 200000) (i32.const 1))))
"""


async def main() -> None:
    fs = VirtualFileSystem()
    for name in ("spin", "alloc"):
        await fs.write(path=f"/bin/{name}.wasm", data=(GUEST / f"{name}.wasm").read_bytes(), parents=True)
    host = Host(E1 / "outputs/cache", tick_s=0.02)

    print("### timeout: spin with timeout_s=0.5")
    t0 = time.perf_counter()
    r = await host.run(fs, "spin", ["spin"], timeout_s=0.5)
    print(f"  wall={time.perf_counter() - t0:.2f}s exit={r.exit_code} trap_code={r.trap_code} timed_out={r.timed_out}")
    print(f"  message={r.trap_message!r}")
    assert r.trap_code is TrapCode.INTERRUPT and r.timed_out

    print("\n### memory limit: alloc with memory_bytes=32 MiB (Rust aborts when memory.grow fails)")
    r = await host.run(fs, "alloc", ["alloc"], timeout_s=5.0, memory_bytes=32 * 1024 * 1024)
    print(f"  exit={r.exit_code} trap_code={r.trap_code} timed_out={r.timed_out}")
    print(f"  message={r.trap_message!r}")
    print(f"  stderr={r.stderr!r}")
    assert r.trap_code is TrapCode.UNREACHABLE and not r.timed_out

    print("\n### memory limit: alloc with no limit but a 1s timeout (what happens without set_limits)")
    r = await host.run(fs, "alloc", ["alloc"], timeout_s=1.0)
    print(f"  exit={r.exit_code} trap_code={r.trap_code} timed_out={r.timed_out} message={r.trap_message!r}")
    print(f"  stderr tail={r.stderr[-60:]!r}")

    print("\n### raw guest bug: a WAT module storing out of bounds")
    module = Module(host.engine, OOB_WAT)
    store = Store(host.engine)
    store.set_epoch_deadline(1000)
    try:
        from wasmtime import Linker
        inst = Linker(host.engine).instantiate(store, module)
        inst.exports(store)["_start"](store)
    except Trap as t:
        print(f"  trap_code={t.trap_code} message={t.message.splitlines()[0]!r}")
        assert t.trap_code is TrapCode.MEMORY_OUT_OF_BOUNDS

    print("\n### the engine epoch is global: a second store on the same engine, run after the kill, still works")
    r = await host.run(fs, "spin", ["spin"], timeout_s=0.2)
    print(f"  second spin: trap_code={r.trap_code} timed_out={r.timed_out}")
    host.close()
    await fs.close()
    print("\nSTEP 5 OK")


if __name__ == "__main__":
    asyncio.run(main())
