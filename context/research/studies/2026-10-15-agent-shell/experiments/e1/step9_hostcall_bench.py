"""Step 9 — the cost of one host call: Python shim vs wasmtime's built-in (Rust) preview1.

A WAT guest calls fd_write on a 1-byte iovec N times. (a) our Python fd_write through
define_func; (b) wasmtime's own `linker.define_wasi()` with stdout sent to a file, so the
host function is Rust and Python is never entered. The difference is the Python trampoline
cost per host call — the number that decides Python-host vs Rust-host for the shim.
"""

from __future__ import annotations

import os
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "shim"))

from wasmtime import Engine, FuncType, Linker, Module, Store, ValType, WasiConfig  # noqa: E402

E1 = Path(__file__).parent

WAT = """
(module
  (import "wasi_snapshot_preview1" "fd_write" (func $fd_write (param i32 i32 i32 i32) (result i32)))
  (memory (export "memory") 1)
  (data (i32.const 100) "x")
  (func (export "_start")
    (local $i i32)
    (i32.store (i32.const 300) (i32.const 100))
    (i32.store (i32.const 304) (i32.const 1))
    (local.set $i (i32.const {n}))
    (loop $l
      (drop (call $fd_write (i32.const 1) (i32.const 300) (i32.const 1) (i32.const 400)))
      (local.set $i (i32.sub (local.get $i) (i32.const 1)))
      (br_if $l (local.get $i)))))
"""
N = 200_000


def main() -> None:
    engine = Engine()
    module = Module(engine, WAT.replace("{n}", str(N)))
    sink = bytearray()

    def fd_write(caller, fd, iovs, iovs_len, nwritten_ptr):
        mem = caller.get("memory")
        base, length = struct.unpack_from("<II", mem.read(caller, iovs, iovs + 8))
        sink.extend(mem.read(caller, base, base + length))
        mem.write(caller, struct.pack("<I", length), nwritten_ptr)
        return 0

    def fd_write_noop(caller, fd, iovs, iovs_len, nwritten_ptr):
        return 0

    i32 = ValType.i32()
    results = {}
    for label, impl in (("python fd_write (decode iovec + copy)", fd_write), ("python no-op host call", fd_write_noop)):
        linker = Linker(engine)
        linker.define_func("wasi_snapshot_preview1", "fd_write", FuncType([i32] * 4, [i32]), impl, access_caller=True)
        store = Store(engine)
        inst = linker.instantiate(store, module)
        t0 = time.perf_counter()
        inst.exports(store)["_start"](store)
        results[label] = time.perf_counter() - t0

    linker = Linker(engine)
    linker.define_wasi()
    wasi = WasiConfig()
    out = E1 / "outputs/bench-stdout.bin"
    wasi.stdout_file = str(out)
    store = Store(engine)
    store.set_wasi(wasi)
    inst = linker.instantiate(store, module)
    t0 = time.perf_counter()
    inst.exports(store)["_start"](store)
    results["wasmtime built-in Rust fd_write (to a host file)"] = time.perf_counter() - t0
    assert len(sink) == N and out.stat().st_size == N
    os.unlink(out)

    print(f"{N} host calls each:")
    for label, secs in results.items():
        print(f"  {label:48} {secs*1000:8.1f} ms total  {secs/N*1e6:7.2f} us/call")
    py = results["python no-op host call"] / N * 1e6
    rs = results["wasmtime built-in Rust fd_write (to a host file)"] / N * 1e6
    print(f"\n  Python trampoline floor ~{py:.2f} us/call vs Rust host ~{rs:.2f} us/call -> {py/rs:.0f}x")


if __name__ == "__main__":
    main()
