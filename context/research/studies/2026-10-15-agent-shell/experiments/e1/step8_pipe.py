"""Step 8 — a pipe between wasm stages: bytes out of one guest become the next guest's stdin.

    cat /data/users.json | jaq '.users[].name' | echo-stdin | jaq -R -r 'ascii_upcase' > /data/names.txt

The host does: one vfs read to bytes, three guest runs passing stdout->stdin, one vfs write.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "shim"))

from host import Host, VerbSpy  # noqa: E402

from vfs import VirtualFileSystem  # noqa: E402

E1 = Path(__file__).parent
GUEST = E1 / "guest/target/wasm32-wasip1/release"


async def main() -> None:
    fs = VirtualFileSystem()
    await fs.write(path="/bin/jaq.wasm", data=(E1 / "downloads/jaq/bin/jaq.wasm").read_bytes(), parents=True)
    await fs.write(path="/bin/echo-stdin.wasm", data=(GUEST / "echo-stdin.wasm").read_bytes())
    await fs.write(path="/data/users.json", content='{"users":[{"name":"ada"},{"name":"grace"},{"name":"édith"}]}', parents=True)
    spy = VerbSpy(fs)
    host = Host(E1 / "outputs/cache")

    stages = [
        ("jaq", ["jaq", ".users[].name"]),
        ("echo-stdin", ["echo-stdin"]),
        ("jaq", ["jaq", "-R", "-r", "ascii_upcase"]),
    ]
    # `cat /data/users.json`: the row's text body rendered to bytes at the pipe's entry
    src = (await spy.read("/data/users.json")).first()
    data = src.content.encode("utf-8") if src.data is None else src.data
    print(f"entry: /data/users.json -> {len(data)} bytes (body was {'text' if src.data is None else 'bytes'})")
    for name, argv in stages:
        r = await host.run(spy, name, argv, stdin=data)
        print(f"  {' '.join(argv):28} exit={r.exit_code} trap={r.trap_code} stdin={len(data)}B stdout={r.stdout!r} stderr={r.stderr!r}")
        if r.exit_code != 0:
            break
        data = r.stdout
    # `> /data/names.txt`: bytes back into a row at the pipe's exit
    res = await spy.write(path="/data/names.txt", content=data.decode("utf-8"))
    print(f"exit: write /data/names.txt v{res.first().version} status={res.first().status}")
    print(f"verb calls for the whole pipeline: {dict(sorted(spy.counts.items()))}")
    final = (await fs.read("/data/names.txt")).first()
    print(f"/data/names.txt = {final.content!r}")

    print("\n### a bytes-only stage in the middle: echo-stdin on a 1 MiB binary payload, no vfs involvement")
    blob = bytes(range(256)) * 4096
    r = await host.run(spy, "echo-stdin", ["echo-stdin"], stdin=blob)
    print(f"  exit={r.exit_code} out==in: {r.stdout == blob} ({len(r.stdout)} B) fd_read calls={r.preview1_calls.get('fd_read')} fd_write calls={r.preview1_calls.get('fd_write')} run={r.run_s*1000:.1f} ms")
    host.close()
    await fs.close()
    print("\nSTEP 8 OK")


if __name__ == "__main__":
    asyncio.run(main())
