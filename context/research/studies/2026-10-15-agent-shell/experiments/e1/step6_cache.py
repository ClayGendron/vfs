"""Step 6 — the compiled-module cache keyed on (wasmtime version, config fingerprint, entry path, entry version).

Cold: compile + serialize. Warm: deserialize_file. Rewrite the entry (version 2): the key
changes and the module recompiles. Times are a bench fact for the memo, never a test.
"""

from __future__ import annotations

import asyncio
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "shim"))

from host import WASMTIME_VERSION, Host  # noqa: E402
from wasmtime import Module  # noqa: E402

from vfs import VirtualFileSystem  # noqa: E402

E1 = Path(__file__).parent
GUEST = E1 / "guest/target/wasm32-wasip1/release"
CACHE = E1 / "outputs/cache-step6"


async def main() -> None:
    shutil.rmtree(CACHE, ignore_errors=True)
    fs = VirtualFileSystem()
    jaq = (E1 / "downloads/jaq/bin/jaq.wasm").read_bytes()
    upper = (GUEST / "upper.wasm").read_bytes()
    await fs.write(path="/bin/jaq.wasm", data=jaq, parents=True)
    await fs.write(path="/bin/upper.wasm", data=upper, parents=True)
    host = Host(CACHE)
    print(f"wasmtime {WASMTIME_VERSION}; config fingerprint {host.config_fingerprint!r}")

    for name, size in (("jaq", len(jaq)), ("upper", len(upper))):
        row = await host.resolve(fs, name)
        for label in ("cold", "warm", "warm2"):
            module, mode, secs = await host.load(fs, row)
            key = host.cache_key(str(row.path), row.version)
            cw = (CACHE / f"{key}.cwasm").stat().st_size
            print(f"  {name:6} v{row.version} {label:5}: {mode:12} {secs*1000:8.1f} ms  wasm={size} B  cwasm={cw} B  key={key[:12]}")

    print("\n### rewrite /bin/upper.wasm (same bytes, overwrite=True) -> does the version advance?")
    res = await fs.write(path="/bin/upper.wasm", data=upper)
    print(f"  write: status={res.first().status} version={res.first().version}")
    row = await host.resolve(fs, "upper")
    module, mode, secs = await host.load(fs, row)
    print(f"  load after same-bytes rewrite: version={row.version} {mode} {secs*1000:.1f} ms key={host.cache_key(str(row.path), row.version)[:12]}")

    print("\n### rewrite /bin/upper.wasm with different bytes (the fsops binary) -> new version, new key, recompile")
    res = await fs.write(path="/bin/upper.wasm", data=(GUEST / "fsops.wasm").read_bytes())
    row = await host.resolve(fs, "upper")
    module, mode, secs = await host.load(fs, row)
    print(f"  write status={res.first().status} version={row.version}; load: {mode} {secs*1000:.1f} ms key={host.cache_key(str(row.path), row.version)[:12]}")

    print("\n### deserialize(bytes) vs deserialize_file (mmap) vs compile, jaq, 5 reps each")
    key = CACHE / (host.cache_key("/bin/jaq.wasm", 1) + ".cwasm")
    blob = key.read_bytes()
    for label, fn in (
        ("compile", lambda: Module(host.engine, jaq)),
        ("deserialize(bytes)", lambda: Module.deserialize(host.engine, blob)),
        ("deserialize_file", lambda: Module.deserialize_file(host.engine, str(key))),
    ):
        times = []
        for _ in range(5):
            t0 = time.perf_counter(); fn(); times.append(time.perf_counter() - t0)
        print(f"  {label:20} min={min(times)*1000:8.1f} ms  max={max(times)*1000:8.1f} ms")

    print("\n### cache poisoning check: a cwasm from a different engine config is refused")
    from wasmtime import Config, Engine, WasmtimeError
    cfg = Config(); cfg.epoch_interruption = False
    try:
        Module.deserialize(Engine(cfg), blob)
        print("  deserialized under a different config: ACCEPTED (key must carry the config fingerprint ourselves)")
    except WasmtimeError as e:
        print(f"  refused: {str(e).splitlines()[0]!r}")
    host.close()
    await fs.close()
    print("\nSTEP 6 OK")


if __name__ == "__main__":
    asyncio.run(main())
