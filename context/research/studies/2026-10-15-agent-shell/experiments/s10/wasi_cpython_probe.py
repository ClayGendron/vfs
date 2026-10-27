"""S10 probe: what can CPython-on-WASI import, and why does numpy fail?

Runs Brett Cannon's prebuilt CPython 3.14.7 (wasm32-wasip1, WASI SDK 24)
under wasmtime-py with the unpacked release directory preopened at "/".
This probe is about the *interpreter's* capabilities (C extensions, dlopen,
threads, sockets), so a host directory is fine here; the vfs mapping of file
calls was already proven by study 04.

usage: uv run --with wasmtime python -I wasi_cpython_probe.py <py314 dir> [extra sys.path dir ...]

Each extra directory is preopened at /ext<i> and appended to sys.path, so a
native numpy wheel or the wasi-wheels numpy tarball can be put in front of
the interpreter to see the exact failure.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from wasmtime import Config, Engine, Linker, Module, Store, WasiConfig

PROBE = r"""
import sys, json, importlib, os
sys.path[:0] = [f"/ext{i}" for i in range(4) if os.path.isdir(f"/ext{i}")]
out = {"version": sys.version, "platform": sys.platform, "path": sys.path}
mods = ["json","csv","re","decimal","dataclasses","enum","sqlite3","_sqlite3","zlib","bz2","lzma",
        "hashlib","_hashlib","ssl","ctypes","socket","select","selectors","threading","_thread",
        "multiprocessing","subprocess","signal","mmap","asyncio","uuid","datetime","zoneinfo",
        "pyexpat","xml.etree.ElementTree","array","struct","math","statistics","fractions",
        "tomllib","tarfile","zipfile","gzip","io","tempfile","shutil","glob","fnmatch","argparse",
        "numpy","pandas","scipy","matplotlib","PIL","yaml","openpyxl","docx","bs4","dateutil","pydantic"]
res = {}
for m in mods:
    try:
        importlib.import_module(m)
        res[m] = "ok"
    except BaseException as e:
        res[m] = f"{type(e).__name__}: {str(e)[:160]}"
out["imports"] = res
import _imp, traceback
out["imp_create_dynamic"] = hasattr(_imp, "create_dynamic")
try:
    importlib.import_module("numpy._core._multiarray_umath")
    out["numpy_core_direct"] = "ok"
except BaseException as e:
    chain = []
    x = e
    while x is not None:
        chain.append(f"{type(x).__name__}: {str(x)[:300]}")
        x = x.__cause__ or x.__context__
    out["numpy_core_direct"] = chain
# threads
try:
    import threading
    t = threading.Thread(target=lambda: None); t.start(); t.join()
    out["thread_start"] = "ok"
except BaseException as e:
    out["thread_start"] = f"{type(e).__name__}: {e}"
# dlopen-shaped probe: does the import system have an extension loader at all?
import importlib.machinery as im
out["extension_suffixes"] = im.EXTENSION_SUFFIXES
try:
    import os
    out["cpu_count"] = os.cpu_count()
    out["fork"] = hasattr(os, "fork")
except BaseException as e:
    out["os"] = str(e)
print("PROBE_JSON " + json.dumps(out))
"""


def run(py_dir: Path, extras: list[Path]) -> None:
    cfg = Config()
    cfg.cache = True
    engine = Engine(cfg)
    t0 = time.perf_counter()
    module = Module.from_file(engine, str(py_dir / "python.wasm"))
    t1 = time.perf_counter()
    linker = Linker(engine)
    linker.define_wasi()
    store = Store(engine)
    wasi = WasiConfig()
    argv = ["/usr/local/bin/python.wasm", "-I", "-X", "utf8", "-c", PROBE]
    wasi.argv = argv
    env = [("PYTHONHOME", "/"), ("PYTHONUTF8", "1"), ("PYTHONHASHSEED", "0"), ("LC_ALL", "C.UTF-8")]
    if extras:
        env.append(("PYTHONPATH", ":".join(f"/ext{i}" for i in range(len(extras)))))
    wasi.env = env
    wasi.preopen_dir(str(py_dir), "/usr/local")
    for i, p in enumerate(extras):
        wasi.preopen_dir(str(p), f"/ext{i}")
    out_path = Path("/tmp/s10_wasi_stdout.txt")
    err_path = Path("/tmp/s10_wasi_stderr.txt")
    wasi.stdout_file = str(out_path)
    wasi.stderr_file = str(err_path)
    store.set_wasi(wasi)
    inst = linker.instantiate(store, module)
    start = inst.exports(store)["_start"]
    t2 = time.perf_counter()
    code = 0
    try:
        start(store)
    except Exception as e:  # ExitTrap or Trap
        code = getattr(e, "code", repr(e))
    t3 = time.perf_counter()
    stdout = out_path.read_text(errors="replace")
    stderr = err_path.read_text(errors="replace")
    print(f"compile {t1 - t0:.3f}s  instantiate {t2 - t1:.3f}s  run {t3 - t2:.3f}s  exit {code}")
    for line in stdout.splitlines():
        if line.startswith("PROBE_JSON "):
            data = json.loads(line[len("PROBE_JSON "):])
            print("version:", data["version"].split("\n")[0], "platform:", data["platform"])
            print("extension_suffixes:", data["extension_suffixes"])
            print("thread_start:", data.get("thread_start"))
            print("cpu_count:", data.get("cpu_count"), "has fork:", data.get("fork"))
            print("_imp.create_dynamic present:", data.get("imp_create_dynamic"))
            print("numpy core direct import:", data.get("numpy_core_direct"))
            for m, r in data["imports"].items():
                print(f"  {m:28s} {r}")
        else:
            print("stdout:", line[:300])
    if stderr.strip():
        print("stderr:", stderr[-2000:])


if __name__ == "__main__":
    run(Path(sys.argv[1]), [Path(p) for p in sys.argv[2:]])
