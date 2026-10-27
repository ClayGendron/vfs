"""Steps 3 and 4 — store the binaries in vfs, resolve from the bin dir, run them over vfs verbs."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "shim"))

from host import Host, StatementSpy, VerbSpy  # noqa: E402

from vfs import VirtualFileSystem  # noqa: E402
from vfs.storage.backends import InMemoryStorage  # noqa: E402

E1 = Path(__file__).parent
GUEST = E1 / "guest/target/wasm32-wasip1/release"
BINARIES = {name: GUEST / f"{name}.wasm" for name in ("upper", "spin", "echo-stdin", "alloc", "fsops")}
BINARIES["jaq"] = E1 / "downloads/jaq/bin/jaq.wasm"


def show(title: str, res) -> None:
    print(f"\n[{title}] success={res.success} rows={len(res)}")
    for err in res.errors:
        print(f"  error kind={err.kind} severity={err.severity} path={err.path} message={err.message!r}")
    for row in res:
        print(f"  row path={row.path} kind={row.kind} version={row.version} populated={sorted(row.populated)}"
              f" size={row.size_bytes} mime={row.mime_type} source={row.source} data={None if row.data is None else len(row.data)}B"
              f" content={None if row.content is None else repr(row.content[:40])}")


def report(label: str, r, stmts: StatementSpy, verbs: VerbSpy) -> None:
    print(f"\n=== {label}")
    print(f"  exit={r.exit_code} trap={r.trap_code} timed_out={r.timed_out} {r.trap_message}")
    print(f"  stdout={r.stdout!r}")
    print(f"  stderr={r.stderr!r}")
    print(f"  module={r.compile} ({r.compile_s*1000:.1f} ms)  run={r.run_s*1000:.1f} ms")
    print(f"  shim verbs per guest path: {json.dumps(r.per_path)}")
    print(f"  all vfs verb calls this run (incl. resolve+load): {dict(sorted(verbs.counts.items()))}")
    print(f"  SQL statements this run: {stmts.count}")
    print(f"  preview1 calls: {dict(sorted(r.preview1_calls.items()))}")
    if r.stubbed:
        print(f"  STUBBED calls hit: {r.stubbed}")


async def main() -> None:
    storage = InMemoryStorage()
    fs = VirtualFileSystem(storage=storage)
    spy = VerbSpy(fs)
    stmts = StatementSpy(storage)
    host = Host(E1 / "outputs/cache")

    print("### Step 3a: the /.agents/bin namespace")
    upper_bytes = BINARIES["upper"].read_bytes()
    show("write /.agents/bin/upper.wasm parents=True", await fs.write(path="/.agents/bin/upper.wasm", data=upper_bytes, parents=True))
    show("mkdir /.agents/bin parents=True", await fs.mkdir("/.agents/bin", parents=True))
    show("write /.agents/tools/upper/upper.wasm parents=True", await fs.write(path="/.agents/tools/upper/upper.wasm", data=upper_bytes, parents=True))
    show("ls /.agents", await fs.ls("/.agents"))

    print("\n### Step 3b: install = write into /bin")
    for name, path in BINARIES.items():
        res = await fs.write(path=f"/bin/{name}.wasm", data=path.read_bytes(), parents=True)
        row = res.first()
        print(f"  write /bin/{name}.wasm: success={res.success} status={row.status} version={row.version} "
              f"size={row.size_bytes} mime={row.mime_type} source={row.source} render={row.render_status}")
    await fs.write(path="/data/in.txt", content="alpha\nbeta\ngamma\n", parents=True)
    await fs.write(path="/data/users.json", content=json.dumps({"users": [{"name": "ada"}, {"name": "grace"}]}))
    await fs.write(path="/data/blob.bin", data=bytes(range(256)))

    print("\n### Step 3c: resolve 'upper' from the bin directory")
    show("ls /bin", await fs.ls("/bin"))
    show("glob /bin/upper.*", await fs.glob("/bin/upper.*"))
    row = await host.resolve(fs, "upper")
    print(f"  resolved -> {row.path} version={row.version}")

    print("\n### Step 3d: reading the bytes back")
    show("read /bin/upper.wasm (no projection)", await fs.read("/bin/upper.wasm"))
    show("read /bin/upper.wasm columns={data}", await fs.read("/bin/upper.wasm", columns=frozenset({"data"})))
    show("read /data/in.txt columns={data,content}", await fs.read("/data/in.txt", columns=frozenset({"data", "content"})))
    show("read /data/blob.bin columns={data,content}", await fs.read("/data/blob.bin", columns=frozenset({"data", "content"})))

    print("\n### Step 4: run")
    spy.reset(); stmts.reset()
    r = await host.run(spy, "upper", ["upper", "/data/in.txt", "/data/out.txt"])
    report("upper /data/in.txt /data/out.txt (first run: compile)", r, stmts, spy)
    show("stat /data/out.txt", await fs.stat("/data/out.txt"))
    show("read /data/out.txt", await fs.read("/data/out.txt"))

    spy.reset(); stmts.reset()
    r = await host.run(spy, "upper", ["upper", "/data/in.txt", "/data/out.txt"])
    report("upper again (second run: cache hit; out.txt gets a new version)", r, stmts, spy)
    show("stat /data/out.txt", await fs.stat("/data/out.txt"))

    spy.reset(); stmts.reset()
    r = await host.run(spy, "upper", ["upper", "/data/missing.txt", "/data/out2.txt"])
    report("upper /data/missing.txt (guest's own error path)", r, stmts, spy)

    spy.reset(); stmts.reset()
    r = await host.run(spy, "upper", ["upper"])
    report("upper with no args (usage -> exit 2)", r, stmts, spy)

    spy.reset(); stmts.reset()
    r = await host.run(spy, "upper", ["upper", "/data/blob.bin", "/data/blob.out"])
    report("upper on a bytes body (invalid UTF-8 -> guest error)", r, stmts, spy)

    spy.reset(); stmts.reset()
    r = await host.run(spy, "upper", ["upper", "/data/in.txt", "/data/out.bin"], text_writeback=False)
    report("upper with bytes writeback (data=) instead of text", r, stmts, spy)
    show("stat /data/out.bin", await fs.stat("/data/out.bin"))
    show("read /data/out.bin", await fs.read("/data/out.bin"))

    print("\n### Step 4b: the directory and mutation calls (fsops)")
    for argv in (
        ["fsops", "ls", "/data"], ["fsops", "stat", "/data/in.txt"], ["fsops", "stat", "/data"],
        ["fsops", "mkdir", "/data/sub"], ["fsops", "mv", "/data/out.txt", "/data/sub/moved.txt"],
        ["fsops", "ls", "/data/sub"], ["fsops", "append", "/data/sub/moved.txt", "delta"],
        ["fsops", "seek", "/data/sub/moved.txt"], ["fsops", "rm", "/data/sub/moved.txt"],
        ["fsops", "rmdir", "/data/sub"], ["fsops", "rmdir", "/data"], ["fsops", "ls", "/nope"],
        ["fsops", "ls", "/"], ["fsops", "stat", "../../etc/passwd"],
    ):
        spy.reset(); stmts.reset()
        r = await host.run(spy, "fsops", argv)
        report(" ".join(argv), r, stmts, spy)
    show("ls /.vfs/trash", await fs.ls("/.vfs/trash"))

    print("\n### Step 4c: a real-world binary — jaq (jq clone, crates.io 1.6.0, MIT) built for wasm32-wasip1")
    users = (await fs.read("/data/users.json")).first().content.encode()
    spy.reset(); stmts.reset()
    r = await host.run(spy, "jaq", ["jaq", ".users[].name"], stdin=users)
    report("cat /data/users.json | jaq '.users[].name'", r, stmts, spy)
    spy.reset(); stmts.reset()
    r = await host.run(spy, "jaq", ["jaq", "-c", "[.users[].name]", "/data/users.json"])
    report("jaq -c '[.users[].name]' /data/users.json (file arg)", r, stmts, spy)
    spy.reset(); stmts.reset()
    r = await host.run(spy, "jaq", ["jaq", ".["], stdin=users)
    report("jaq '.[' (syntax error -> jaq's own exit code)", r, stmts, spy)

    host.close()
    await fs.close()


if __name__ == "__main__":
    asyncio.run(main())
