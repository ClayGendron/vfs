"""Probe 1: how /.vfs/... paths route and answer today (spec 169 review)."""

from __future__ import annotations

import asyncio

from vfs.base import VirtualFileSystem
from vfs.storage.backends.memory import InMemoryStorage

WASM = b"\x00asm\x01\x00\x00\x00" + b"\x00" * 24


def show(label, r):
    print(f"[{label}] success={r.success}")
    for o in r.observations:
        print(f"    row path={o.path} kind={o.kind} mime={o.mime_type} source={o.source} populated={sorted(o.populated)}")
    for e in r.errors:
        print(f"    error kind={e.kind} sev={e.severity} path={e.path} msg={e.message!r} data={e.data}")


async def main() -> None:
    fs = VirtualFileSystem()
    await fs.add_mount(InMemoryStorage(name="data"), "/data")
    await fs.write(path="/data/a.txt", content="hi")
    await fs.write(path="/notes.txt", content="root note")
    await fs.delete("/notes.txt")
    await fs.delete("/data/a.txt")

    print("== locate: which binding owns each view path")
    for p in ["/.vfs", "/.vfs/bin/jq", "/.vfs/trash", "/data/.vfs/trash", "/data/.vfs/bin"]:
        loc = await fs.locate(p)
        print(f"  {p} -> mount={loc.mount} storage_path={loc.storage_path}")

    print("\n== reads at view paths")
    show("ls /.vfs", await fs.ls("/.vfs"))
    show("stat /.vfs", await fs.stat("/.vfs"))
    show("ls /.vfs/trash", await fs.ls("/.vfs/trash"))
    show("ls /data/.vfs", await fs.ls("/data/.vfs"))
    show("ls /data/.vfs/trash", await fs.ls("/data/.vfs/trash"))
    show("stat /.vfs/bin", await fs.stat("/.vfs/bin"))
    show("ls /.vfs/bin", await fs.ls("/.vfs/bin"))
    show("stat /.vfs/bin/jq", await fs.stat("/.vfs/bin/jq"))

    print("\n== writes into would-be views")
    show("write /.vfs/bin/x.wasm data", await fs.write(path="/.vfs/bin/x.wasm", data=WASM, parents=True))
    show("ls /.vfs (after)", await fs.ls("/.vfs"))
    show("ls /.vfs/bin (after)", await fs.ls("/.vfs/bin"))
    show("write /.vfs/trash/y.txt", await fs.write(path="/.vfs/trash/y.txt", content="y", parents=True))
    show("write /.vfs", await fs.write(path="/.vfs", content="y"))
    show("mkdir /.vfs/skills", await fs.mkdir("/.vfs/skills", parents=True))
    show("write /data/.vfs/bin/z.wasm", await fs.write(path="/data/.vfs/bin/z.wasm", data=WASM, parents=True))

    print("\n== the meta-scoped search rule")
    show("glob **/*.wasm (unscoped)", await fs.glob("**/*.wasm"))
    show("glob /.vfs/**", await fs.glob("/.vfs/**"))

    print("\n== a mount at /.vfs/bin (the ViewStorage alternative)")
    try:
        await fs.bind(InMemoryStorage(name="v"), "/.vfs/bin")
    except Exception as exc:  # noqa: BLE001
        print(f"  bind /.vfs/bin -> {type(exc).__name__}: {exc}")

    print("\n== deny_ops with a program name")
    try:
        VirtualFileSystem(deny_ops=["jq"])
        print("  VirtualFileSystem(deny_ops=['jq']) accepted (mask stored, no effect)")
    except Exception as exc:  # noqa: BLE001
        print(f"  deny_ops=['jq'] -> {type(exc).__name__}: {exc}")
    try:
        VirtualFileSystem(deny_ops=["grep"])
    except Exception as exc:  # noqa: BLE001
        print(f"  deny_ops=['grep'] -> {type(exc).__name__}: {exc}")
    await fs.close()


asyncio.run(main())
