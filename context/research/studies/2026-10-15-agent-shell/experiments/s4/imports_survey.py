"""Which preview1 imports do real wasm32-wasi binaries declare? (read-only survey of reference clones)

    uv run --with wasmtime python context/research/studies/2026-10-15-agent-shell/experiments/s4/imports_survey.py
"""

from __future__ import annotations

import json
from pathlib import Path

from wasmtime import Engine, Module

HERE = Path(__file__).resolve().parent
HOME = Path.home()
CANDIDATES = {
    "catfile (Rust, this study)": HERE / "catfile/target/wasm32-wasip1/release/catfile.wasm",
    "fsops (Rust, this study)": HERE / "fsops/target/wasm32-wasip1/release/fsops.wasm",
    "python.wasm (llm-wasm-sandbox, CPython)": HOME / "Git/Repos/llm-wasm-sandbox/bin/python.wasm",
    "quickjs.wasm (llm-wasm-sandbox, qjs-wasi)": HOME / "Git/Repos/llm-wasm-sandbox/bin/quickjs.wasm",
    "_guest.wasm (quickjs-rs)": HOME / "Git/Repos/quickjs-rs/quickjs_rs/_guest.wasm",
    "_transform.wasm (quickjs-rs)": HOME / "Git/Repos/quickjs-rs/quickjs_rs/_transform.wasm",
}
engine = Engine()
out = {}
for label, path in CANDIDATES.items():
    if not path.exists():
        out[label] = {"missing": str(path)}
        continue
    m = Module.from_file(engine, str(path))
    by_module: dict[str, list[str]] = {}
    for imp in m.imports:
        by_module.setdefault(imp.module, []).append(imp.name)
    out[label] = {"bytes": path.stat().st_size, "imports": {k: sorted(v) for k, v in by_module.items()}, "exports": [e.name for e in m.exports][:12]}
(HERE / "imports.json").write_text(json.dumps(out, indent=2))
for label, info in out.items():
    if "missing" in info:
        print(label, "MISSING")
        continue
    p1 = info["imports"].get("wasi_snapshot_preview1", [])
    print(f"{label}: {info['bytes']} bytes, preview1 imports={len(p1)} other modules={[k for k in info['imports'] if k != 'wasi_snapshot_preview1']}")
    print("   ", " ".join(p1))
