"""S10 experiment: Pyodide (in a node child process) reads and writes vfs rows.

The shape under test:

    Python host (this file)            node main thread              node Worker
    VirtualFileSystem + Authority  <--JSON lines over stdio-->  relay  <--SharedArrayBuffer + Atomics-->  Pyodide + VFSFS

Every file call the guest makes (pandas.read_csv, matplotlib savefig, open())
reaches an Emscripten filesystem object (VFSFS, in pyodide_bridge_worker.mjs)
whose node_ops/stream_ops block on a SharedArrayBuffer until the node main
thread has relayed the request to this process and this process has answered
it with a vfs verb carried under the caller's Authority. Whole-file staging:
one `read` per open, one `write` per close of a dirty buffer.

usage: uv run python -I pyodide_vfs_host.py <guest script.py> [--json out.json]
"""

from __future__ import annotations

import asyncio
import base64
import json
import posixpath
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
    "vfs.not_found": 44,
    "vfs.exists": 20,
    "vfs.wrong_kind": 54,
    "vfs.not_empty": 55,
    "vfs.permission_denied": 2,
    "vfs.unauthenticated": 2,
    "vfs.read_only": 69,
    "vfs.invalid": 28,
    "vfs.cross_mount": 75,
}

CSV = "region,month,sales\n" + "\n".join(
    f"{r},{m},{(i * 37) % 100 + 10}"
    for i, (r, m) in enumerate((r, m) for r in ("north", "south", "east", "west") for m in range(1, 13))
) + "\n"


class Host:
    def __init__(self, fs: VirtualFileSystem, authority: Authority) -> None:
        self.fs = fs
        self.authority = authority
        self.verbs: Counter[str] = Counter()
        self.ops: Counter[str] = Counter()
        self.sql_per_op: Counter[str] = Counter()
        self.sql_total = 0
        self.in_flight: list[str] = []
        self.trace: list[str] = []
        self.bridge_round_trips = 0
        self.by_path: Counter[str] = Counter()

    def count_sql(self, conn, cursor, statement, parameters, context, executemany):
        self.sql_total += 1
        if self.in_flight:
            self.sql_per_op[self.in_flight[-1]] += 1

    @staticmethod
    def err_kind(result) -> str | None:
        if not result.errors:
            return None
        return str(getattr(result.errors[0].kind, "value", result.errors[0].kind))

    def fail(self, result) -> dict:
        kind = self.err_kind(result)
        return {"ok": False, "errno": ERRNO.get(kind, 29), "kind": kind}

    async def handle(self, req: dict) -> dict:
        op, path = req["op"], req.get("path", "/")
        self.ops[op] += 1
        self.by_path[f"{op} {path}"] += 1
        self.bridge_round_trips += 1
        self.in_flight.append(op)
        try:
            return await self._dispatch(op, path, req)
        finally:
            self.in_flight.pop()

    async def _dispatch(self, op: str, path: str, req: dict) -> dict:
        fs, a = self.fs, self.authority
        if op == "stat":
            self.verbs["stat"] += 1
            r = await fs.stat(path=path, authority=a)
            if r.errors:
                return self.fail(r)
            o = r.observations[0]
            return {"ok": True, "kind": o.kind, "size": o.size_bytes or 0,
                    "mtime": o.updated_at.timestamp() if o.updated_at else 0, "version": o.version}
        if op == "readdir":
            self.verbs["ls"] += 1
            r = await fs.ls(path=path, authority=a)
            if r.errors:
                return self.fail(r)
            return {"ok": True, "entries": sorted(posixpath.basename(o.path) for o in r.observations)}
        if op == "read":
            self.verbs["read"] += 1
            r = await fs.read(path=path, columns=READ_COLUMNS, authority=a)
            if r.errors:
                return self.fail(r)
            o = r.observations[0]
            body = o.data if o.data is not None else (o.content or "").encode()
            return {"ok": True, "data": base64.b64encode(body).decode(), "mime": o.mime_type, "version": o.version}
        if op == "write":
            self.verbs["write"] += 1
            body = base64.b64decode(req["data"])
            try:
                text = body.decode("utf-8")
                r = await fs.write(path=path, content=text, parents=False, authority=a)
            except UnicodeDecodeError:
                r = await fs.write(path=path, data=body, parents=False, authority=a)
            if r.errors:
                return self.fail(r)
            o = r.observations[0]
            self.trace.append(f"write {path} {len(body)}B -> version {o.version} mime {o.mime_type}")
            return {"ok": True, "version": o.version, "mime": o.mime_type}
        if op == "mkdir":
            self.verbs["mkdir"] += 1
            r = await fs.mkdir(path, authority=a)
            return {"ok": True} if not r.errors else self.fail(r)
        if op == "unlink":
            self.verbs["delete"] += 1
            r = await fs.delete(path=path, cascade=False, authority=a)
            return {"ok": True} if not r.errors else self.fail(r)
        if op == "rename":
            self.verbs["move"] += 1
            r = await fs.move(src=path, dest=req["to"], authority=a)
            return {"ok": True} if not r.errors else self.fail(r)
        return {"ok": False, "errno": 52, "kind": "unsupported"}


async def main(script: Path, json_out: Path | None) -> None:
    storage = InMemoryStorage()
    fs = VirtualFileSystem(storage=storage)
    # The caller: identity is a value on the call, never a string in the guest.
    authority = Authority.of(Principal("agent-7", kind="agent"))
    await fs.write(path="/data/sales.csv", content=CSV, parents=True, authority=authority)
    await fs.mkdir("/out", authority=authority)
    await fs.mkdir("/scripts", authority=authority)
    await fs.write(path="/scripts/job.py", content=script.read_text(), authority=authority)

    host = Host(fs, authority)
    sync_engine = storage._host.engine.sync_engine
    event.listen(sync_engine, "before_cursor_execute", host.count_sql)

    t0 = time.perf_counter()
    proc = await asyncio.create_subprocess_exec(
        "node", str(HERE / "pyodide_bridge_main.mjs"), "/vfs/scripts/job.py",
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, limit=64 * 1024 * 1024,
    )
    assert proc.stdin and proc.stdout and proc.stderr
    guest_stdout: list[str] = []
    guest_stderr: list[str] = []
    done: dict = {}
    timings: dict = {}
    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        msg = json.loads(line)
        kind = msg.get("type")
        if kind == "req":
            reply = await host.handle(msg["req"])
            reply["id"] = msg["id"]
            proc.stdin.write((json.dumps(reply) + "\n").encode())
            await proc.stdin.drain()
        elif kind == "stdout":
            guest_stdout.append(msg["text"])
        elif kind == "stderr":
            guest_stderr.append(msg["text"])
        elif kind == "timing":
            timings.update(msg["data"])
        elif kind == "done":
            done = msg
            break
    stderr_tail = (await proc.stderr.read()).decode(errors="replace")[-1500:]
    await proc.wait()
    wall = time.perf_counter() - t0
    event.remove(sync_engine, "before_cursor_execute", host.count_sql)

    # The media round trip: the PNG is a bytes row; its MCP projection is an image block.
    after = await fs.read(path="/out/plot.png", columns=READ_COLUMNS, authority=authority)
    png_row = None
    mcp_block = None
    if not after.errors:
        o = after.observations[0]
        png_row = {"path": o.path, "kind": o.kind, "mime_type": o.mime_type, "size_bytes": o.size_bytes,
                   "version": o.version, "data_is_png": bool(o.data and o.data[:8] == b"\x89PNG\r\n\x1a\n"),
                   "content_is_none": o.content is None}
        if o.data:
            # base64 appears here and only here: at the MCP boundary, in an ImageContent block.
            mcp_block = {"type": "image", "mimeType": o.mime_type or "image/png",
                         "data": base64.b64encode(o.data).decode()[:40] + "...",
                         "_data_b64_len": len(base64.b64encode(o.data))}
    summary = await fs.read(path="/out/summary.csv", columns=READ_COLUMNS, authority=authority)
    summary_row = None if summary.errors else {"path": "/out/summary.csv", "kind": summary.observations[0].kind,
                                              "mime_type": summary.observations[0].mime_type,
                                              "content_head": (summary.observations[0].content or "")[:120]}
    report = {
        "exit": done.get("exit"), "error": done.get("error"), "wall_s": round(wall, 3),
        "timings_ms": timings,
        "guest_stdout": "".join(guest_stdout)[-1500:], "guest_stderr": "".join(guest_stderr)[-800:],
        "node_stderr_tail": stderr_tail,
        "bridge_round_trips": host.bridge_round_trips,
        "ops": dict(host.ops), "verbs": dict(host.verbs),
        "sql_total": host.sql_total, "sql_per_op": dict(host.sql_per_op),
        "trace": host.trace[-20:],
        "ops_by_path": dict(host.by_path.most_common(25)),
        "png_row": png_row, "mcp_image_block": mcp_block, "summary_row": summary_row,
        "trash": sorted(posixpath.basename(o.path) for o in (await fs.ls(path="/.vfs/trash", authority=authority)).observations),
    }
    text = json.dumps(report, indent=2)
    print(text)
    if json_out:
        json_out.write_text(text)


if __name__ == "__main__":
    args = sys.argv[1:]
    out = None
    if "--json" in args:
        i = args.index("--json")
        out = Path(args[i + 1])
        del args[i:i + 2]
    asyncio.run(main(Path(args[0]), out))
