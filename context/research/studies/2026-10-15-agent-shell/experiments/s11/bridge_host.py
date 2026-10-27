"""S11 candidate C, host side: the vfs process spawns a native CPython guest that sandboxes
itself, and serves its filesystem calls with vfs verbs under one Authority.

Two spawn shapes:
  local  — socketpair(); the child inherits one end as fd 3 (macOS: Seatbelt; Linux: Landlock).
  docker — listen on TCP; `docker run --user 1000 --cap-drop=ALL --security-opt=no-new-privileges`
           starts the guest, which connects BEFORE applying Landlock + seccomp (the only way
           to emulate an unprivileged PaaS process from this Mac; the socket it keeps is the
           bridge, and seccomp then denies any new socket()).

usage: uv run --with numpy --with pandas --with matplotlib python -I bridge_host.py
           [--docker IMAGE] [--sandbox seatbelt|landlock|none] [--json out.json]
"""

from __future__ import annotations

import asyncio
import json
import os
import posixpath
import socket
import struct
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

from sqlalchemy import event

from vfs import VirtualFileSystem
from vfs.authority import Authority, Principal
from vfs.storage.backends import InMemoryStorage

HERE = Path(__file__).resolve().parent
READ_COLUMNS = frozenset({"content", "data", "kind", "size_bytes", "mime_type", "version", "updated_at"})
ERRNO = {
    "vfs.not_found": 2, "vfs.exists": 17, "vfs.wrong_kind": 20, "vfs.not_empty": 39,
    "vfs.permission_denied": 13, "vfs.unauthenticated": 13, "vfs.read_only": 30, "vfs.invalid": 22,
}
CSV = "region,month,sales\n" + "\n".join(
    f"{r},{m},{(i * 37) % 100 + 10}"
    for i, (r, m) in enumerate((r, m) for r in ("north", "south", "east", "west") for m in range(1, 13))
) + "\n"


class Host:
    def __init__(self, fs: VirtualFileSystem, authority: Authority) -> None:
        self.fs, self.authority = fs, authority
        self.verbs: Counter[str] = Counter()
        self.ops: Counter[str] = Counter()
        self.sql_total = 0
        self.sql_per_op: Counter[str] = Counter()
        self.in_flight: list[str] = []
        self.trace: list[str] = []
        self.done: dict | None = None

    def count_sql(self, conn, cursor, statement, parameters, context, executemany):
        self.sql_total += 1
        if self.in_flight:
            self.sql_per_op[self.in_flight[-1]] += 1

    def fail(self, result) -> tuple[dict, bytes]:
        kind = str(getattr(result.errors[0].kind, "value", result.errors[0].kind))
        return {"ok": False, "errno": ERRNO.get(kind, 5), "kind": kind}, b""

    async def handle(self, req: dict, body: bytes) -> tuple[dict, bytes]:
        op, path = req["op"], req.get("path", "/")
        self.ops[op] += 1
        self.in_flight.append(op)
        try:
            return await self._dispatch(op, path, req, body)
        finally:
            self.in_flight.pop()

    async def _dispatch(self, op: str, path: str, req: dict, body: bytes) -> tuple[dict, bytes]:
        fs, a = self.fs, self.authority
        if op == "stat":
            self.verbs["stat"] += 1
            r = await fs.stat(path=path, authority=a)
            if r.errors:
                return self.fail(r)
            o = r.observations[0]
            return {"ok": True, "kind": o.kind, "size": o.size_bytes or 0,
                    "mtime": o.updated_at.timestamp() if o.updated_at else 0}, b""
        if op == "readdir":
            self.verbs["ls"] += 1
            r = await fs.ls(path=path, authority=a)
            if r.errors:
                return self.fail(r)
            return {"ok": True, "entries": sorted(posixpath.basename(o.path) for o in r.observations)}, b""
        if op == "read":
            self.verbs["read"] += 1
            r = await fs.read(path=path, columns=READ_COLUMNS, authority=a)
            if r.errors:
                return self.fail(r)
            o = r.observations[0]
            data = o.data if o.data is not None else (o.content or "").encode()
            return {"ok": True, "body_len": len(data)}, data
        if op == "write":
            self.verbs["write"] += 1
            try:
                text = body.decode("utf-8")
                r = await fs.write(path=path, content=text, parents=False, authority=a)
            except UnicodeDecodeError:
                r = await fs.write(path=path, data=body, parents=False, authority=a)
            if r.errors:
                return self.fail(r)
            o = r.observations[0]
            self.trace.append(f"write {path} {len(body)}B -> version {o.version} mime {o.mime_type}")
            return {"ok": True}, b""
        if op == "mkdir":
            self.verbs["mkdir"] += 1
            r = await fs.mkdir(path, authority=a)
            return ({"ok": True}, b"") if not r.errors else self.fail(r)
        if op == "unlink":
            self.verbs["delete"] += 1
            r = await fs.delete(path=path, cascade=False, authority=a)
            return ({"ok": True}, b"") if not r.errors else self.fail(r)
        if op == "rename":
            self.verbs["move"] += 1
            r = await fs.move(src=path, dest=req["to"], authority=a)
            return ({"ok": True}, b"") if not r.errors else self.fail(r)
        if op == "done":
            self.done = json.loads(body)
            return {"ok": True}, b""
        return {"ok": False, "errno": 38, "kind": "unsupported"}, b""


async def serve(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, host: Host) -> None:
    while True:
        try:
            n = struct.unpack(">I", await reader.readexactly(4))[0]
        except (asyncio.IncompleteReadError, ConnectionError):
            return
        req = json.loads(await reader.readexactly(n))
        body = await reader.readexactly(req.get("body_len", 0)) if req.get("body_len") else b""
        reply, rbody = await host.handle(req, body)
        if rbody:
            reply["body_len"] = len(rbody)
        h = json.dumps(reply).encode()
        writer.write(struct.pack(">I", len(h)) + h + rbody)
        await writer.drain()
        if req["op"] == "done":
            return


async def main() -> None:
    args = sys.argv[1:]
    out = None
    docker = None
    sandbox = "seatbelt" if sys.platform == "darwin" else "landlock"
    if "--json" in args:
        i = args.index("--json"); out = Path(args[i + 1]); del args[i:i + 2]
    if "--docker" in args:
        i = args.index("--docker"); docker = args[i + 1]; del args[i:i + 2]
    if "--sandbox" in args:
        i = args.index("--sandbox"); sandbox = args[i + 1]; del args[i:i + 2]

    storage = InMemoryStorage()
    fs = VirtualFileSystem(storage=storage)
    authority = Authority.of(Principal("agent-7", kind="agent"))
    await fs.write(path="/data/sales.csv", content=CSV, parents=True, authority=authority)
    await fs.mkdir("/out", authority=authority)
    await fs.mkdir("/scripts", authority=authority)
    await fs.write(path="/scripts/job.py", content=(HERE.parent / "s10" / "guest_job.py").read_text(), authority=authority)
    host = Host(fs, authority)
    event.listen(storage._host.engine.sync_engine, "before_cursor_execute", host.count_sql)

    guest_args = ["--sandbox", sandbox, "--preimport", "numpy,pandas,matplotlib,matplotlib.pyplot", "/vfs/scripts/job.py"]
    t0 = time.perf_counter()
    if docker:
        server = await asyncio.start_server(lambda r, w: asyncio.ensure_future(serve(r, w, host)), "0.0.0.0", 0)
        port = server.sockets[0].getsockname()[1]
        tmp = Path("/private/tmp/claude-501/s11-guest-tmp"); tmp.mkdir(parents=True, exist_ok=True)
        cmd = ["docker", "run", "--rm", "-i", "--user", "1000:1000", "--cap-drop=ALL", "--security-opt=no-new-privileges",
               "-v", f"{HERE}:/s:ro", "-e", "MPLCONFIGDIR=/tmp/mpl", docker,
               "python", "-I", "/s/bridge_guest.py", "--connect", f"host.docker.internal:{port}",
               "--ro", "/usr", "--ro", "/lib", "--rw", "/tmp", *guest_args]
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await proc.communicate()
        server.close()
    else:
        a, b = socket.socketpair()
        rw = Path("/private/tmp/claude-501/s11-guest-tmp"); rw.mkdir(parents=True, exist_ok=True)
        b.set_inheritable(True)
        cmd = [sys.executable, "-I", str(HERE / "bridge_guest.py"), "--fd", str(b.fileno()), "--rw", str(rw), *guest_args]
        env = {"PATH": os.environ.get("PATH", ""), "HOME": str(rw), "MPLCONFIGDIR": str(rw)}
        proc = await asyncio.create_subprocess_exec(*cmd, pass_fds=(b.fileno(),), stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.PIPE, env=env)
        b.close()
        reader, writer = await asyncio.open_connection(sock=a)
        serve_task = asyncio.ensure_future(serve(reader, writer, host))
        stdout, stderr = await proc.communicate()
        await serve_task
    wall = time.perf_counter() - t0

    after = await fs.read(path="/out/plot.png", columns=READ_COLUMNS, authority=authority)
    png_row = None
    if not after.errors:
        o = after.observations[0]
        png_row = {"path": o.path, "kind": o.kind, "mime_type": o.mime_type, "size_bytes": o.size_bytes, "version": o.version,
                   "data_is_png": bool(o.data and o.data[:8] == b"\x89PNG\r\n\x1a\n"), "content_is_none": o.content is None}
    summary = await fs.read(path="/out/summary.csv", columns=READ_COLUMNS, authority=authority)
    report = {
        "spawn": "docker" if docker else "local", "sandbox": sandbox, "wall_s": round(wall, 2),
        "child_exit": proc.returncode, "guest": host.done,
        "ops": dict(host.ops), "verbs": dict(host.verbs), "sql_total": host.sql_total, "sql_per_op": dict(host.sql_per_op),
        "trace": host.trace, "png_row": png_row,
        "summary_row": None if summary.errors else {"mime_type": summary.observations[0].mime_type,
                                                    "content_head": (summary.observations[0].content or "")[:100]},
        "guest_stdout": stdout.decode(errors="replace")[-1500:], "guest_stderr": stderr.decode(errors="replace")[-1200:],
    }
    text = json.dumps(report, indent=2)
    print(text)
    if out:
        out.write_text(text)


if __name__ == "__main__":
    asyncio.run(main())
