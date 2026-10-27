"""Probe 6: can a suffixless program file exist, and what does `jq.wasm` vs `jq` look like in one directory? (spec 169 review)"""

from __future__ import annotations

import asyncio

from vfs.base import VirtualFileSystem

WASM = b"\x00asm\x01\x00\x00\x00" + b"\x00" * 24


async def main() -> None:
    fs = VirtualFileSystem()
    for p in ["/opt/bin/jq", "/opt/bin/jq.wasm", "/opt/bin/jq.py"]:
        r = await fs.write(path=p, data=WASM, parents=True)
        e = r.errors[0] if r.errors else None
        print(f"write {p:18} success={r.success} kind={r.observations[0].kind if r.observations else None} err={e.kind if e else None} {e.message if e else ''}")
    ls = await fs.ls("/opt/bin")
    print("ls /opt/bin:", [(str(o.path), o.kind) for o in ls.observations])
    await fs.close()


asyncio.run(main())
