"""Extra checks the report needs: the step-7 WasmtimeError text, the statement list of one
upper run, how far alloc gets with no memory limit, and the stdout-isatty switch on jaq."""

from __future__ import annotations

import asyncio
import sys
import threading
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "shim"))

from host import Host, StatementSpy, VerbSpy  # noqa: E402
from vfs_wasi import GuestExit  # noqa: E402
from wasmtime import Engine, FuncType, Linker, Module, Store, Trap, ValType, WasmtimeError  # noqa: E402

from vfs import VirtualFileSystem  # noqa: E402
from vfs.storage.backends import InMemoryStorage  # noqa: E402

E1 = Path(__file__).parent
GUEST = E1 / "guest/target/wasm32-wasip1/release"
EXIT_WAT = """
(module
  (import "wasi_snapshot_preview1" "proc_exit" (func $exit (param i32)))
  (memory (export "memory") 1)
  (func (export "_start") (call $exit (i32.const {code}))))
"""


def step7_message() -> None:
    print("### what the step-7 'other: WasmtimeError' outcomes say")
    engine = Engine()
    msgs: Counter[str] = Counter()
    lock = threading.Lock()

    def worker(code: int) -> None:
        module = Module(engine, EXIT_WAT.replace("{code}", str(code)))
        linker = Linker(engine)
        linker.define_func("wasi_snapshot_preview1", "proc_exit", FuncType([ValType.i32()], []),
                           lambda caller, c: (_ for _ in ()).throw(GuestExit(c)), access_caller=True)
        for _ in range(1500):
            store = Store(engine)
            try:
                linker.instantiate(store, module).exports(store)["_start"](store)
            except GuestExit:
                pass
            except (WasmtimeError, Trap) as e:
                with lock:
                    msgs[f"{type(e).__name__}: {str(e).splitlines()[0]}"] += 1

    ts = [threading.Thread(target=worker, args=(10 + i,)) for i in range(4)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    for k, v in msgs.most_common(5):
        print(f"  {v:5}  {k}")


async def statements_and_alloc() -> None:
    storage = InMemoryStorage()
    fs = VirtualFileSystem(storage=storage)
    spy, stmts = VerbSpy(fs), StatementSpy(storage)
    for name in ("upper", "alloc", "jaq"):
        src = GUEST / f"{name}.wasm" if name != "jaq" else E1 / "downloads/jaq/bin/jaq.wasm"
        await fs.write(path=f"/bin/{name}.wasm", data=src.read_bytes(), parents=True)
    await fs.write(path="/data/in.txt", content="a\nb\n", parents=True)
    host = Host(E1 / "outputs/cache")
    await host.run(spy, "upper", ["upper", "/data/in.txt", "/data/out.txt"])  # warm the cache and the row

    print("\n### the SQL statements of one warm `upper /data/in.txt /data/out.txt` run, grouped by verb")
    stmts.reset(); spy.reset()
    marks: list[tuple[str, int]] = []
    orig = spy.__class__.__getattr__

    r = await host.run(spy, "upper", ["upper", "/data/in.txt", "/data/out.txt"])
    print(f"  verbs={dict(sorted(spy.counts.items()))} statements={stmts.count}")
    counts = Counter(s.split(" ")[0] + " " + (s.split(" FROM ")[1].split(" ")[0] if " FROM " in s else s.split(" ")[2] if len(s.split(" ")) > 2 else "") for s in stmts.statements)
    for k, v in counts.most_common():
        print(f"    {v:3}  {k}")
    print("  first 12 statements verbatim (truncated):")
    for s in stmts.statements[:12]:
        print(f"    {s}")

    print("\n### alloc with no memory limit: how far does it get before wasm32's own ceiling?")
    r = await host.run(spy, "alloc", ["alloc"], timeout_s=5.0)
    lines = r.stderr.decode().splitlines()
    print(f"  trap={r.trap_code} last progress line={[l for l in lines if l.startswith('alloc:')][-1:]} abort={[l for l in lines if 'failed' in l]}")

    print("\n### jaq decides colour from fd_fdstat_get on stdout: tty vs pipe")
    users = b'{"a":1}'
    for tty in (False, True):
        from vfs_wasi import VfsWasi
        import host as h
        # run with the shim's stdout_is_tty flag flipped
        loop = asyncio.get_running_loop()
        row = await host.resolve(fs, "jaq")
        module, _, _ = await host.load(fs, row)
        shim = VfsWasi(fs, loop, argv=["jaq", "."], stdin=users, stdout_is_tty=tty)
        linker = Linker(host.engine); shim.define(linker); linker.define_unknown_imports_as_traps(module)
        store = Store(host.engine); store.set_epoch_deadline(1000)

        def go():
            try:
                linker.instantiate(store, module).exports(store)["_start"](store)
            except GuestExit:
                pass
        await loop.run_in_executor(None, go)
        print(f"  stdout_is_tty={tty}: stdout={shim.stdout!r}")
    host.close()
    await fs.close()


if __name__ == "__main__":
    step7_message()
    asyncio.run(statements_and_alloc())
