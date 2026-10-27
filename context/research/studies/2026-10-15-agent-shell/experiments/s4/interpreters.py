"""Run real interpreter binaries (CPython python.wasm, qjs-wasi quickjs.wasm from the
llm-wasm-sandbox clone, read-only) under the vfs preview1 shim.

    uv run --with wasmtime python context/research/studies/2026-10-15-agent-shell/experiments/s4/interpreters.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from shim import HERE, run_scenario  # noqa: E402

from vfs import VirtualFileSystem  # noqa: E402
from vfs.storage.backends import InMemoryStorage  # noqa: E402

BIN = Path.home() / "Git/Repos/llm-wasm-sandbox/bin"
PY_CODE = (
    "import os, sys, json\n"
    "print('python', sys.version.split()[0], sys.platform)\n"
    "print(open('/data/hello.txt').read(), end='')\n"
    "with open('/data/py.out', 'w') as f: f.write('written by cpython\\n')\n"
    "print(sorted(os.listdir('/data')))\n"
    "print(os.stat('/data/hello.txt').st_size, oct(os.stat('/data/hello.txt').st_mode))\n"
    "os.mkdir('/data/pydir'); os.rename('/data/py.out', '/data/pydir/moved.out'); os.remove('/data/pydir/moved.out'); os.rmdir('/data/pydir')\n"
    "print(json.dumps({'ok': True}))\n"
)
JS_CODE = (
    "import * as std from 'qjs:std'; import * as os from 'qjs:os';\n"
    "const t = std.loadFile('/data/hello.txt'); std.out.puts(t);\n"
    "const f = std.open('/data/js.out', 'w'); f.puts('written by quickjs\\n'); f.close();\n"
    "const [names, err] = os.readdir('/data'); std.out.puts(JSON.stringify(names.sort()) + '\\n');\n"
    "const [st, e2] = os.stat('/data/hello.txt'); std.out.puts('size ' + st.size + ' mode ' + st.mode.toString(8) + '\\n');\n"
)


async def main() -> None:
    results = {}
    for name, wasm, argv, env, stdin in (
        ("cpython", BIN / "python.wasm", ["python", "-I", "-X", "utf8", "-c", PY_CODE], ["PYTHONUTF8=1", "PYTHONHASHSEED=0", "LC_ALL=C.UTF-8"], b""),
        ("quickjs", BIN / "quickjs.wasm", ["qjs", "--std", "-m", "/data/main.mjs"], [], b""),
    ):
        storage = InMemoryStorage()
        fs = VirtualFileSystem(storage=storage)
        await fs.write(path="/data/hello.txt", content="hello from vfs\nsecond line\n", parents=True)
        await fs.write(path="/data/main.mjs", content=JS_CODE)
        rep = await run_scenario(fs, storage, wasm, argv, stdin, env)
        after = await fs.ls(path="/data")
        rep["ls_after"] = sorted((o.path, o.kind) for o in after.observations)
        out = await fs.read(path="/data/js.out")
        rep["js_out"] = [o.content for o in out.observations]
        trash = await fs.ls(path="/.vfs/trash")
        rep["trash"] = sorted(o.path for o in trash.observations)
        results[name] = rep
        print(f"== {name}: exit={rep['exit_code']} trapped={rep['trapped']} compile={rep['compile_seconds']}s run={rep['run_seconds']}s")
        print("stdout:", rep["stdout"])
        print("stderr:", rep["stderr"][:400])
        print("syscalls:", rep["syscalls"])
        print("unimplemented called:", rep["unimplemented_called"])
        print("verbs:", rep["verbs"], "sql:", rep["sql_statements"], rep["sql_statements_per_verb"])
        print("ls_after:", rep["ls_after"], "trash:", rep["trash"])
        print("trace:", rep["trace"][:12])
        await fs.close()
    (HERE / "interpreters.json").write_text(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
