"""Probe 2: install by write, the mime, and the list/read gates a resolver relies on (spec 169 review)."""

from __future__ import annotations

import asyncio

from vfs.authority import Authority, Principal
from vfs.base import VirtualFileSystem
from vfs.models.media import sniff_mime
from vfs.storage.backends.memory import InMemoryStorage

SYSTEM = Authority.system()
BOB = Authority.of(Principal("bob"))
ZED = Authority.of(Principal("zed"))
WASM = b"\x00asm\x01\x00\x00\x00" + b"\x00" * 24
COMPONENT = b"\x00asm\x0d\x00\x01\x00" + b"\x00" * 24


def show(label, r):
    print(f"[{label}] success={r.success}")
    for o in r.observations:
        print(
            f"    row path={o.path} kind={o.kind} mime={o.mime_type} source={o.source} "
            f"hash={(o.content_hash or '')[:12]} v={o.version} populated={sorted(o.populated)}"
        )
    for e in r.errors:
        print(f"    error kind={e.kind} sev={e.severity} path={e.path} msg={e.message!r}")


async def main() -> None:
    print("== sniff_mime on wasm magic")
    print(f"  core module   -> {sniff_mime(WASM[:16], ext='wasm')}")
    print(f"  component     -> {sniff_mime(COMPONENT[:16], ext='wasm')}")

    fs = VirtualFileSystem(storage=InMemoryStorage(), default_authority=SYSTEM)
    show("write /opt/bin/upper.wasm data=", await fs.write(path="/opt/bin/upper.wasm", data=WASM, parents=True))
    show("stat /opt/bin/upper.wasm", await fs.stat("/opt/bin/upper.wasm"))
    show("write /opt/bin/fake.wasm content=", await fs.write(path="/opt/bin/fake.wasm", content="echo hi"))
    show("stat /opt/bin/fake.wasm", await fs.stat("/opt/bin/fake.wasm"))
    show("same-bytes reinstall", await fs.write(path="/opt/bin/upper.wasm", data=WASM))

    print("\n== the gates a resolver relies on (posture none at /, bob list on upper, zed nothing)")
    show("posture / none", await fs.posture("/", "none"))
    show("grant bob list /opt/bin", await fs.grant("/opt/bin", "bob", "list"))
    show("bob stat upper.wasm", await fs.stat("/opt/bin/upper.wasm", authority=BOB))
    show("bob ls /opt/bin", await fs.ls("/opt/bin", authority=BOB))
    show(
        "bob read columns={content_hash,version}",
        await fs.read("/opt/bin/upper.wasm", columns=frozenset({"content_hash", "version"}), authority=BOB),
    )
    show("bob read columns={data}", await fs.read("/opt/bin/upper.wasm", columns=frozenset({"data"}), authority=BOB))
    show("zed stat upper.wasm", await fs.stat("/opt/bin/upper.wasm", authority=ZED))
    show("grant bob read upper.wasm", await fs.grant("/opt/bin/upper.wasm", "bob", "read"))
    show(
        "bob read columns={content_hash,version} (now read)",
        await fs.read("/opt/bin/upper.wasm", columns=frozenset({"content_hash", "version"}), authority=BOB),
    )

    print("\n== who owns /opt/bin when an agent mints it (open posture, default)")
    fs2 = VirtualFileSystem(storage=InMemoryStorage())
    ann = Authority.of(Principal("ann"))
    await fs2.write(path="/opt/bin/x.wasm", data=WASM, parents=True, authority=ann)
    show(
        "stat /opt/bin columns owner?",
        await fs2.stat("/opt/bin", authority=ann),
    )
    show("bob overwrites ann's x.wasm (open default)", await fs2.write(path="/opt/bin/x.wasm", data=WASM + b"\x01", authority=BOB))
    await fs.close()
    await fs2.close()


asyncio.run(main())
