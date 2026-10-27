"""S4 scenarios: one guest run per POSIX operation, over a shared vfs.

    uv run --with wasmtime python context/research/studies/2026-10-15-agent-shell/experiments/s4/scenarios.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from shim import HERE, run_scenario  # noqa: E402

from vfs import VirtualFileSystem  # noqa: E402
from vfs.models.entry import Entry  # noqa: E402
from vfs.storage.backends import InMemoryStorage  # noqa: E402

FSOPS = HERE / "fsops" / "target" / "wasm32-wasip1" / "release" / "fsops.wasm"
BIG = 8 * 1024 * 1024


async def main() -> None:
    storage = InMemoryStorage()
    fs = VirtualFileSystem(storage=storage)
    await fs.write(path="/data/hello.txt", content="hello from vfs\nsecond line\n", parents=True)
    await fs.write(path="/data/bytes.bin", data=bytes(range(256)) * 4)
    await fs.mkdir("/data/sub")
    big_text = ("x" * 99 + "\n") * (BIG // 100)
    await fs.write(path="/data/big.txt", content=big_text)
    await fs.write(entries=[Entry(path=f"/many/f{i:05d}.txt", content=str(i)) for i in range(2000)], parents=True)

    async def after(label: str, path: str) -> dict:
        r = await fs.read(path=path)
        if r.errors:
            return {label: [str(getattr(e.kind, 'value', e.kind)) for e in r.errors]}
        o = r.observations[0]
        return {label: {"version": o.version, "content": (o.content or "")[:80], "bytes": None if o.data is None else len(o.data)}}

    runs: list[dict] = []

    async def run(name: str, argv: list[str], stdin: bytes = b"", env: list[str] | None = None, check=None) -> None:
        rep = await run_scenario(fs, storage, FSOPS, ["fsops", *argv], stdin, env)
        rep["name"] = name
        if check is not None:
            rep["after"] = await check()
        runs.append(rep)
        print(f"{name:28s} exit={rep['exit_code']:>3} verbs={rep['verbs']} sql={rep['sql_statements']} per_verb={rep['sql_statements_per_verb']} out={rep['stdout'][:60]!r} err={rep['stderr'][:90]!r}")

    await run("cat", ["cat", "/data/hello.txt"])
    await run("cat relative (no cwd)", ["cat", "data/hello.txt"])
    await run("cwd", ["cwd"])
    await run("cat missing -> ENOENT", ["cat", "/data/nope.txt"])
    await run("cat directory -> EISDIR", ["cat", "/data/sub"])
    await run("stat file", ["stat", "/data/hello.txt"])
    await run("stat dir", ["stat", "/data"])
    await run("write new", ["write", "/data/new.txt", "fresh\n"], check=lambda: after("new", "/data/new.txt"))
    await run("write overwrite", ["write", "/data/new.txt", "second\n"], check=lambda: after("new", "/data/new.txt"))
    await run("append", ["append", "/data/new.txt", "tail\n"], check=lambda: after("new", "/data/new.txt"))
    await run("patch at offset 2", ["patch", "/data/new.txt", "ZZ", "2"], check=lambda: after("new", "/data/new.txt"))
    await run("range read 6..12", ["range", "/data/hello.txt", "6", "6"])
    await run("truncate to 3", ["truncate", "/data/new.txt", "3"], check=lambda: after("new", "/data/new.txt"))
    await run("catbytes binary row", ["catbytes", "/data/bytes.bin"])
    await run("write binary via tee", ["tee", "/data/out.bin"], stdin=b"\x00\x01\xff\xfe", check=lambda: after("out", "/data/out.bin"))
    await run("catbytes written binary", ["catbytes", "/data/out.bin"])
    await run("tee text via stdin", ["tee", "/data/t.txt"], stdin=b"plain text\n", check=lambda: after("t", "/data/t.txt"))
    await run("mkdir", ["mkdir", "/data/made"])
    await run("mkdir exists -> EEXIST", ["mkdir", "/data/made"])
    await run("ls", ["ls", "/data"])
    await run("mv", ["mv", "/data/new.txt", "/data/moved.txt"], check=lambda: after("moved", "/data/moved.txt"))
    await run("rm -> trash", ["rm", "/data/moved.txt"], check=lambda: after("moved", "/data/moved.txt"))
    await run("rm missing -> ENOENT", ["rm", "/data/moved.txt"])
    await run("rmdir", ["rmdir", "/data/made"])
    await run("rmdir nonempty -> ENOTEMPTY", ["rmdir", "/data"])
    await run("escape ../..", ["cat", "/data/../../etc/passwd"])
    await run("escape dotdot relative", ["cat", "../etc/passwd"])
    await run("hidden /.vfs", ["ls", "/.vfs/trash"])
    await run("stdin", ["stdin"], stdin=b"piped text\n")
    await run("env", ["env"], env=["HOME=/", "TERM=dumb"])
    await run("exit 7", ["exit", "7"])
    await run("big cat 8 MiB", ["cat", "/data/big.txt"])
    await run("big range 1 byte", ["range", "/data/big.txt", "4000000", "1"])
    await run("big append", ["append", "/data/big.txt", "end\n"])
    await run("count 2000 entries", ["count", "/many"])

    trash = await fs.ls(path="/.vfs/trash")
    summary = {"trash_after": sorted(o.path for o in trash.observations), "runs": runs}
    (HERE / "scenarios.json").write_text(json.dumps(summary, indent=2, default=str))
    print("trash:", summary["trash_after"])
    await fs.close()


if __name__ == "__main__":
    asyncio.run(main())
