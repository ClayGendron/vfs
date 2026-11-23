"""Probe what the live tree does today for tools-as-files: run, /.agents, /.vfs, search, grep, posture, payload."""

from __future__ import annotations

import asyncio
import json

from vfs import AsyncVirtualFileSystem, Authority, InMemoryStorage, Principal

MANIFEST = """---
name: deploy
description: Deploy a service to production. Use when the user asks to ship or roll out a release.
readOnlyHint: false
destructiveHint: true
---
inputSchema: {"type": "object", "properties": {"service": {"type": "string"}}, "required": ["service"]}
"""


def show(label: str, result) -> None:
    errs = [(e.kind, e.severity, e.path, e.message) for e in result.errors]
    paths = [o.path for o in result.observations]
    print(f"{label}: success={result.success} rows={paths} errors={errs}")


async def main() -> None:
    storage = InMemoryStorage()
    fs = AsyncVirtualFileSystem(storage=storage)
    system = Authority.system()
    alice = Authority.of(Principal("alice"))
    print("capabilities has run:", "run" in fs.capabilities())

    show("P1 run on a stored path", await fs.run("/.agents/tools/deploy", arguments={"service": "x"}, authority=system))
    show("P1b run with bad arguments", await fs.run("/.agents/tools/deploy", arguments="x", authority=system))  # type: ignore[arg-type]

    show("P2 write /.agents TOOL.md", await fs.write(path="/.agents/tools/deploy/TOOL.md", content=MANIFEST, parents=True, authority=system))
    show("P2b write ordinary file", await fs.write(path="/docs/release.md", content="How to roll out a release safely.\n", parents=True, authority=system))
    show("P3 write /.vfs/tools manifest", await fs.write(path="/.vfs/tools/deploy/TOOL.md", content=MANIFEST, parents=True, authority=system))
    show("P3b write /.vfs/bin/jq.wasm", await fs.write(path="/.vfs/bin/jq.wasm", data=b"\0asm\x01\x00\x00\x00", parents=True, authority=system))
    show("P3c write /.vfs/run/1/stdout", await fs.write(path="/.vfs/run/1/stdout", content="out\n", parents=True, authority=system))

    rebuilt = await storage.rebuild()
    print("rebuild success:", rebuilt.success)

    show("P4 unscoped search 'deploy production release'", await fs.search("deploy production release", authority=system))
    show("P4b search scoped to /.vfs/tools", await fs.search("deploy production release", paths=("/.vfs/tools",), authority=system))
    show("P4c unscoped grep 'destructiveHint'", await fs.grep("destructiveHint", authority=system))
    show("P4d grep scoped to /.vfs/tools", await fs.grep("destructiveHint", paths=("/.vfs/tools",), authority=system))
    show("P4e unscoped glob **/TOOL.md", await fs.glob("**/TOOL.md", authority=system))
    show("P4f ls /.vfs", await fs.ls("/.vfs", authority=system))

    show("P5 posture /.agents/tools none", await fs.posture("/.agents/tools", "none", authority=system))
    show("P5b grant alice read /.agents/tools/deploy", await fs.grant("/.agents/tools/deploy", "alice", "read", authority=system))
    bob = Authority.of(Principal("bob"))
    show("P5c search as alice", await fs.search("deploy production release", authority=alice))
    show("P5d search as bob", await fs.search("deploy production release", authority=bob))
    show("P5e read manifest as bob", await fs.read("/.agents/tools/deploy/TOOL.md", authority=bob))
    show("P5f run as bob", await fs.run("/.agents/tools/deploy", arguments={"service": "x"}, authority=bob))

    read = await fs.read("/.agents/tools/deploy/TOOL.md", authority=alice)
    payload = read.to_payload()
    print("P6 payload keys:", sorted(payload), "row keys:", sorted(payload["observations"][0]))
    print("P6 payload chars:", len(json.dumps(payload)))
    print("P6 to_str first line:", read.to_str().splitlines()[0] if read.to_str() else "")
    await fs.close()


asyncio.run(main())
