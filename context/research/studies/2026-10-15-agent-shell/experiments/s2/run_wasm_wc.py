"""Run the uutils `wc` wasm32-wasip1 module under wasmtime with piped stdin.

Usage (from the vfs repo root):

    uv run --with wasmtime python experiments/s2/run_wasm_wc.py <wc.wasm> [args...]

Writes a small text to a temp file, hands it to the module as stdin, and prints
what the module wrote to stdout plus its exit status. Proves the module is a
runnable WASI command, not just a build artefact.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from wasmtime import Config, Engine, Linker, Module, Store, WasiConfig


def main(argv: list[str]) -> int:
    wasm_path = Path(argv[1])
    extra = argv[2:] or ["-l", "-w", "-c"]
    sample = "alpha beta\ngamma\n\ndelta epsilon zeta\n"
    with tempfile.TemporaryDirectory() as tmp:
        stdin = Path(tmp) / "stdin.txt"
        stdout = Path(tmp) / "stdout.txt"
        stderr = Path(tmp) / "stderr.txt"
        stdin.write_text(sample)
        stdout.touch()
        stderr.touch()

        config = Config()
        config.consume_fuel = True
        engine = Engine(config)
        store = Store(engine)
        store.set_fuel(2_000_000_000)
        argv_in = ["wc", *extra]
        wasi = WasiConfig()
        wasi.argv = argv_in
        wasi.stdin_file = str(stdin)
        wasi.stdout_file = str(stdout)
        wasi.stderr_file = str(stderr)
        store.set_wasi(wasi)

        linker = Linker(engine)
        linker.define_wasi()
        module = Module.from_file(engine, str(wasm_path))
        instance = linker.instantiate(store, module)
        start = instance.exports(store)["_start"]
        status = "exit 0"
        try:
            start(store)
        except Exception as exc:  # wasmtime raises on non-zero _exit
            status = f"trap/exit: {exc}"[:200]
        print("argv:", argv_in)
        print("stdin bytes:", len(sample.encode()))
        print("stdout:", stdout.read_text().rstrip())
        print("stderr:", stderr.read_text().rstrip())
        print("fuel used:", 2_000_000_000 - store.get_fuel())
        print("status:", status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
