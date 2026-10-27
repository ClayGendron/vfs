"""Probe 5: can the host tell "hit the memory budget" from "the guest aborted", and does fuel give a count-based kill? (spec 169 review)"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
E1 = HERE.parent / "e1"
sys.path.insert(0, str(E1 / "shim"))

from vfs_wasi import GuestExit, VfsWasi  # noqa: E402
from wasmtime import Config, Engine, Linker, Module, Store, Trap, TrapCode, wat2wasm  # noqa: E402

from vfs.base import VirtualFileSystem  # noqa: E402

LIMIT = 32 * 1024 * 1024
ALLOC = (E1 / "guest/target/wasm32-wasip1/release/alloc.wasm").read_bytes()
PANIC_WAT = '(module (memory (export "memory") 1) (func (export "_start") unreachable))'
SPIN_WAT = '(module (memory (export "memory") 1) (func (export "_start") (loop (br 0))))'


def run(engine, module, *, fuel=None, loop=None):
    fs = VirtualFileSystem()
    shim = VfsWasi(fs, loop, argv=["g"])
    linker = Linker(engine)
    shim.define(linker)
    linker.define_unknown_imports_as_traps(module)
    store = Store(engine)
    store.set_limits(memory_size=LIMIT)
    if fuel is not None:
        store.set_fuel(fuel)
    instance = linker.instantiate(store, module)
    try:
        instance.exports(store)["_start"](store)
        outcome = "returned"
    except GuestExit as e:
        outcome = f"exit {e.code}"
    except Trap as t:
        outcome = f"trap {t.trap_code}"
    mem = instance.exports(store)["memory"]
    size = mem.data_len(store)
    consumed = None
    if fuel is not None:
        consumed = fuel - store.get_fuel()
    return outcome, size, consumed, shim.stderr[:60]


async def main() -> None:
    loop = asyncio.get_running_loop()
    print("TrapCode members:", sorted(m.name for m in TrapCode))
    plain = Engine(Config())
    for label, wasm in [("alloc (Rust, grows until refused)", ALLOC), ("WAT unreachable at 64 KiB", wat2wasm(PANIC_WAT))]:
        outcome, size, _, err = await loop.run_in_executor(None, run, plain, Module(plain, wasm), )
        at_cap = size + 65536 > LIMIT
        print(f"  {label}: {outcome}; memory at trap = {size} B; within one page of the cap = {at_cap}; stderr={err!r}")

    cfg = Config()
    cfg.consume_fuel = True
    fueled = Engine(cfg)
    spin = Module(fueled, wat2wasm(SPIN_WAT))
    for budget in (1_000_000, 2_000_000):
        outcome, _, consumed, _ = await loop.run_in_executor(None, lambda b=budget: run(fueled, spin, fuel=b, loop=loop))
        print(f"  spin under fuel {budget:,}: {outcome}; fuel consumed = {consumed:,}")
    try:
        Module.deserialize(fueled, Module(plain, wat2wasm(SPIN_WAT)).serialize())
        print("  a module compiled without fuel deserialized into a fuel engine (cache key must carry the flag)")
    except Exception as exc:  # noqa: BLE001
        print(f"  cross-config deserialize refused: {str(exc).splitlines()[0]}")


asyncio.run(main())
