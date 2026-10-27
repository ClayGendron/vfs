"""Step 1 — the floor: wasmtime-py's own fd_write WAT fixture under OUR preview1 fd_write.

The fixture is wasmtime-py tests/test_wasi.py::test_custom_print (the WAT text is
reproduced here as a test fixture, not as library code). The upstream test runs it
through the built-in WasiConfig; here `wasi_snapshot_preview1.fd_write` is a Python
function registered with Linker.define_func, decoding the iovec array from guest memory.
"""

from __future__ import annotations

import struct

from wasmtime import Engine, FuncType, Linker, Module, Store, ValType

WAT = """
(module
    (import "wasi_snapshot_preview1" "fd_write"
        (func $write (param i32 i32 i32 i32) (result i32)))
    (memory (export "memory") 1)
    (func $print
        (i32.store (i32.const 300) (i32.const 100))
        (i32.store (i32.const 304) (i32.const 14))
        (call $write (i32.const 1) (i32.const 300) (i32.const 1) (i32.const 400))
        if unreachable end
        (i32.store (i32.const 300) (i32.const 200))
        (i32.store (i32.const 304) (i32.const 14))
        (call $write (i32.const 2) (i32.const 300) (i32.const 1) (i32.const 400))
        if unreachable end
    )
    (start $print)
    (data (i32.const 100) "Hello, stdout!")
    (data (i32.const 200) "Hello, stderr!")
)
"""

captured: dict[int, bytearray] = {1: bytearray(), 2: bytearray()}


def fd_write(caller, fd: int, iovs: int, iovs_len: int, nwritten_ptr: int) -> int:
    mem = caller.get("memory")
    total = 0
    for i in range(iovs_len):
        base, length = struct.unpack_from("<II", mem.read(caller, iovs + i * 8, iovs + i * 8 + 8))
        captured[fd] += mem.read(caller, base, base + length)
        total += length
    mem.write(caller, struct.pack("<I", total), nwritten_ptr)
    return 0


def main() -> None:
    engine = Engine()
    linker = Linker(engine)
    i32 = ValType.i32()
    linker.define_func("wasi_snapshot_preview1", "fd_write", FuncType([i32] * 4, [i32]), fd_write, access_caller=True)
    linker.define_unknown_imports_as_traps(Module(engine, WAT))
    store = Store(engine)
    linker.instantiate(store, Module(engine, WAT))
    print("stdout:", captured[1].decode())
    print("stderr:", captured[2].decode())
    assert captured[1] == b"Hello, stdout!" and captured[2] == b"Hello, stderr!"
    print("STEP 1 OK: guest fd_write landed in the host's own buffers (no WasiConfig used)")


if __name__ == "__main__":
    main()
