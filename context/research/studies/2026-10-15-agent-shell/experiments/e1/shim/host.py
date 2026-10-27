"""The host side of the E1 spike: engine, compiled-module cache, resolve, run, spies.

    host = Host(cache_dir=..., tick_s=0.05)
    result = await host.run(fs, "upper", ["upper", "/data/in.txt", "/data/out.txt"], timeout_s=2.0)
    result.exit_code, result.stdout, result.stderr, result.trap_code, result.timed_out

Resolution walks one bin directory in vfs; the binary bytes come from fs.read with the
``data`` projection; the compiled module is cached by (wasmtime version, config
fingerprint, entry path, entry version) as serialized bytes on the host disk.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib.metadata
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import event
from wasmtime import Config, Engine, Linker, Module, Store, Trap, TrapCode, WasmtimeError

from vfs_wasi import GuestExit, VfsWasi

WASMTIME_VERSION = importlib.metadata.version("wasmtime")


@dataclass
class RunResult:
    exit_code: int | None
    stdout: bytes
    stderr: bytes
    trap_code: TrapCode | None = None
    trap_message: str = ""
    timed_out: bool = False
    verbs: dict[str, int] = field(default_factory=dict)
    per_path: dict[str, list[str]] = field(default_factory=dict)
    preview1_calls: dict[str, int] = field(default_factory=dict)
    stubbed: dict[str, int] = field(default_factory=dict)
    statements: int = 0
    compile: str = ""
    compile_s: float = 0.0
    run_s: float = 0.0


class VerbSpy:
    """Wraps the VirtualFileSystem verbs the shim and the host call, counting each."""

    VERBS = ("read", "write", "stat", "ls", "glob", "delete", "move", "mkdir")

    def __init__(self, fs: Any) -> None:
        self.fs = fs
        self.counts: dict[str, int] = {}
        self.log: list[tuple[str, tuple, dict]] = []

    def __getattr__(self, name: str) -> Any:
        target = getattr(self.fs, name)
        if name not in self.VERBS:
            return target

        async def spy(*args: Any, **kwargs: Any) -> Any:
            self.counts[name] = self.counts.get(name, 0) + 1
            self.log.append((name, args, kwargs))
            return await target(*args, **kwargs)

        return spy

    def reset(self) -> None:
        self.counts.clear()
        self.log.clear()


class StatementSpy:
    """Counts SQL statements on the storage's engine via SQLAlchemy's cursor event."""

    def __init__(self, storage: Any) -> None:
        self.count = 0
        self.statements: list[str] = []
        engine = storage._host._engine
        event.listen(engine.sync_engine, "before_cursor_execute", self._on_execute)

    def _on_execute(self, conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool) -> None:
        self.count += 1
        self.statements.append(statement.split("\n", 1)[0][:80])

    def reset(self) -> None:
        self.count = 0
        self.statements.clear()


class Host:
    def __init__(self, cache_dir: Path, *, tick_s: float = 0.05, bin_dir: str = "/bin") -> None:
        self.config = Config()
        self.config.epoch_interruption = True
        self.config_fingerprint = f"epoch=1;cranelift=default;wasmtime={WASMTIME_VERSION}"
        self.engine = Engine(self.config)
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.tick_s = tick_s
        self.bin_dir = bin_dir
        self._stop = threading.Event()
        self._ticker = threading.Thread(target=self._tick, daemon=True)
        self._ticker.start()

    def _tick(self) -> None:
        while not self._stop.is_set():
            time.sleep(self.tick_s)
            self.engine.increment_epoch()

    def close(self) -> None:
        self._stop.set()

    # ---- resolve and load ---------------------------------------------------

    async def resolve(self, fs: Any, name: str, *, authority: Any = None) -> Any:
        """Find ``<bin_dir>/<name>.wasm`` with one ls of the bin directory; return its stat row."""
        listing = await fs.ls(self.bin_dir, authority=authority)
        if not listing.success:
            raise FileNotFoundError(listing.error_message)
        wanted = f"{self.bin_dir}/{name}.wasm"
        for row in listing:
            if str(row.path) == wanted:
                return row
        raise FileNotFoundError(f"{name}: not found in {self.bin_dir} ({[str(r.path) for r in listing]})")

    def cache_key(self, path: str, version: int) -> str:
        return hashlib.sha256(f"{WASMTIME_VERSION}|{self.config_fingerprint}|{path}|{version}".encode()).hexdigest()

    async def load(self, fs: Any, row: Any, *, authority: Any = None) -> tuple[Module, str, float]:
        key = self.cache_dir / (self.cache_key(str(row.path), row.version) + ".cwasm")
        t0 = time.perf_counter()
        if key.exists():
            module = Module.deserialize_file(self.engine, str(key))
            return module, "deserialized", time.perf_counter() - t0
        res = await fs.read(str(row.path), columns=frozenset({"data"}), authority=authority)
        if not res.success:
            raise RuntimeError(res.error_message)
        body = res.first()
        if body.data is None:
            raise RuntimeError(f"{row.path}: read returned no bytes; populated={sorted(body.populated)}")
        module = Module(self.engine, bytes(body.data))
        key.write_bytes(bytes(module.serialize()))
        return module, "compiled", time.perf_counter() - t0

    # ---- run ---------------------------------------------------------------

    async def run(
        self,
        fs: Any,
        name: str,
        argv: list[str],
        *,
        stdin: bytes = b"",
        env: dict[str, str] | None = None,
        timeout_s: float = 5.0,
        memory_bytes: int | None = None,
        authority: Any = None,
        module: Module | None = None,
        text_writeback: bool = True,
    ) -> RunResult:
        loop = asyncio.get_running_loop()
        compile_mode, compile_s = "supplied", 0.0
        if module is None:
            row = await self.resolve(fs, name, authority=authority)
            module, compile_mode, compile_s = await self.load(fs, row, authority=authority)
        shim = VfsWasi(fs, loop, argv=argv, env=env, stdin=stdin, authority=authority, text_writeback=text_writeback)
        linker = Linker(self.engine)
        shim.define(linker)
        linker.define_unknown_imports_as_traps(module)
        store = Store(self.engine)
        store.set_epoch_deadline(max(1, int(timeout_s / self.tick_s)))
        if memory_bytes is not None:
            store.set_limits(memory_size=memory_bytes)

        def guest() -> RunResult:
            t0 = time.perf_counter()
            exit_code: int | None = None
            trap_code, trap_message, timed_out = None, "", False
            try:
                instance = linker.instantiate(store, module)
                instance.exports(store)["_start"](store)
                exit_code = 0
            except GuestExit as e:
                exit_code = e.code
            except Trap as t:
                trap_code, trap_message = t.trap_code, t.message.split("\n", 1)[0]
                timed_out = trap_code is TrapCode.INTERRUPT
            except WasmtimeError as e:
                trap_message = f"WasmtimeError: {e}".split("\n", 1)[0]
            # a guest that exits without closing its files: flush every open handle
            for fd in list(shim.fds):
                if fd > 3:
                    shim._flush(fd)
            return RunResult(
                exit_code, shim.stdout, shim.stderr, trap_code, trap_message, timed_out,
                dict(shim.counts.verbs), dict(shim.counts.per_path), dict(shim.counts.calls), dict(shim.stubbed),
                compile=compile_mode, compile_s=compile_s, run_s=time.perf_counter() - t0,
            )

        return await loop.run_in_executor(None, guest)
