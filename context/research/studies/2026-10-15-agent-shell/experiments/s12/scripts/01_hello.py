"""Step 1: run the wasi-sdk hello world under wasmtime-py.  uv run --with wasmtime python scripts/01_hello.py build/hello/hello.wasm"""
import sys
from wasmtime import Engine, Linker, Module, Store, WasiConfig
engine = Engine(); linker = Linker(engine); linker.define_wasi()
store = Store(engine); w = WasiConfig(); w.argv = ["hello", "x"]; w.inherit_stdout(); store.set_wasi(w)
inst = linker.instantiate(store, Module.from_file(engine, sys.argv[1]))
inst.exports(store)["_start"](store)
