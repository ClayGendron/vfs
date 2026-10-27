"""S10 experiment: a minimal 9P2000 file server over the live `VirtualFileSystem`.

9P is Plan 9's file protocol: a client sends T-messages (Tattach, Twalk, Topen,
Tread, Twrite, Tclunk, ...) and the server answers with R-messages. Anything
that speaks 9P can mount this server as a filesystem: Linux's v9fs
(`mount -t 9p -o trans=tcp,version=9p2000`), plan9port's `9p` command,
9pfuse, a microVM's virtio-9p device. The point of the experiment: native
CPython with the whole pip ecosystem sees vfs as an ordinary directory, and
every operation it makes is a vfs verb carried under the Authority minted at
Tattach from the client's `uname`.

Protocol facts (Plan 9 manual, intro(5) and the per-message pages; the Linux
client in net/9p and fs/9p was read for the legacy-mode expectations):
  size[4] type[1] tag[2] body     little-endian; strings are len[2] + UTF-8
  qid = type[1] version[4] path[8]; QTDIR 0x80, QTFILE 0
  stat = size[2] type[2] dev[4] qid[13] mode[4] atime[4] mtime[4] length[8]
         name[s] uid[s] gid[s] muid[s]; DMDIR 0x80000000 in mode
  Rstat carries stat[n] *with* an extra size[2] in front (two length prefixes)
  a directory read returns whole stat entries only; offset must be 0 or the
  previous offset + count

Staging rule: Topen of a file is one `read` and stages the whole row; Twrite
edits the staged buffer; Tclunk of a dirty buffer is one `write`. Topen of a
directory is one `ls` (whose rows carry size, version and mtime, so the whole
listing is one verb). Twalk is one `stat` per path element. Tcreate of a file
mints nothing until clunk. Tremove is one `delete` (to the trash). Twstat with
a new name is one `move`; with a new length a read + a write; other fields are
accepted and ignored (vfs has no mode bits).

usage: uv run python -I p9_server.py [--port 5640] [--seed] [--report out.json]
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import posixpath
import signal
import struct
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import event

from vfs import VirtualFileSystem
from vfs.authority import Authority, Principal
from vfs.storage.backends import InMemoryStorage

HERE = Path(__file__).resolve().parent
READ_COLUMNS = frozenset({"content", "data", "kind", "size_bytes", "mime_type", "version", "updated_at"})

NOFID = 0xFFFFFFFF
NOTAG = 0xFFFF
QTDIR, QTFILE = 0x80, 0x00
DMDIR = 0x80000000
OTRUNC, ORCLOSE = 0x10, 0x40
IOUNIT = 0  # 0 means "no limit beyond msize - 24"
MSIZE = 128 * 1024 + 24

(Tversion, Rversion, Tauth, Rauth, Tattach, Rattach, Terror, Rerror, Tflush, Rflush, Twalk, Rwalk,
 Topen, Ropen, Tcreate, Rcreate, Tread, Rread, Twrite, Rwrite, Tclunk, Rclunk, Tremove, Rremove,
 Tstat, Rstat, Twstat, Rwstat) = range(100, 128)
NAMES = {Tversion: "Tversion", Tauth: "Tauth", Tattach: "Tattach", Tflush: "Tflush", Twalk: "Twalk",
         Topen: "Topen", Tcreate: "Tcreate", Tread: "Tread", Twrite: "Twrite", Tclunk: "Tclunk",
         Tremove: "Tremove", Tstat: "Tstat", Twstat: "Twstat"}

# Plan 9 error strings; the Linux client maps these to errnos (net/9p/error.c).
E_NOENT = "file does not exist"
E_EXIST = "file already exists"
E_NOTDIR = "not a directory"
E_ISDIR = "Is a directory"
E_NOTEMPTY = "directory is not empty"
E_PERM = "permission denied"
E_ROFS = "Read-only file system"
E_INVAL = "Invalid argument"
E_IO = "i/o error"
KIND_TO_ERR = {
    "vfs.not_found": E_NOENT, "vfs.exists": E_EXIST, "vfs.wrong_kind": E_NOTDIR, "vfs.not_empty": E_NOTEMPTY,
    "vfs.permission_denied": E_PERM, "vfs.unauthenticated": E_PERM, "vfs.read_only": E_ROFS,
    "vfs.invalid": E_INVAL, "vfs.cross_mount": "cross-device link",
}


class P9Error(Exception):
    pass


# ---------------------------------------------------------------------------
# Wire encoding
# ---------------------------------------------------------------------------

def p_str(s: str) -> bytes:
    b = s.encode()
    return struct.pack("<H", len(b)) + b


def p_qid(qtype: int, version: int, path: int) -> bytes:
    return struct.pack("<BIQ", qtype, version & 0xFFFFFFFF, path)


def qid_path(path: str) -> int:
    return int.from_bytes(hashlib.sha1(path.encode()).digest()[:8], "little") & 0x7FFFFFFFFFFFFFFF


def p_stat(name: str, is_dir: bool, size: int, mtime: int, version: int, path: str, uid: str) -> bytes:
    qt = QTDIR if is_dir else QTFILE
    mode = (DMDIR | 0o755) if is_dir else 0o644
    body = (struct.pack("<HI", 0, 0) + p_qid(qt, version, qid_path(path)) + struct.pack("<IIIQ", mode, mtime, mtime, size)
            + p_str(name) + p_str(uid) + p_str(uid) + p_str(uid))
    return struct.pack("<H", len(body)) + body


class Reader:
    def __init__(self, data: bytes, pos: int = 0) -> None:
        self.d, self.p = data, pos

    def u8(self) -> int:
        v = self.d[self.p]; self.p += 1; return v

    def u16(self) -> int:
        v = struct.unpack_from("<H", self.d, self.p)[0]; self.p += 2; return v

    def u32(self) -> int:
        v = struct.unpack_from("<I", self.d, self.p)[0]; self.p += 4; return v

    def u64(self) -> int:
        v = struct.unpack_from("<Q", self.d, self.p)[0]; self.p += 8; return v

    def s(self) -> str:
        n = self.u16(); v = self.d[self.p:self.p + n].decode(errors="replace"); self.p += n; return v

    def bytes_(self, n: int) -> bytes:
        v = self.d[self.p:self.p + n]; self.p += n; return v


# ---------------------------------------------------------------------------
# Fids
# ---------------------------------------------------------------------------

@dataclass
class Fid:
    path: str
    is_dir: bool
    buf: bytearray | None = None       # staged file body while open
    dirty: bool = False
    version: int = 0
    mtime: int = 0
    dir_entries: list[bytes] = field(default_factory=list)  # encoded stats while a dir is open
    open_mode: int | None = None
    pending_create: bool = False       # Tcreate'd file not yet minted


class Session:
    """One 9P connection: one Authority (minted at Tattach), one fid table."""

    def __init__(self, fs: VirtualFileSystem, counters: Counters) -> None:
        self.fs = fs
        self.c = counters
        self.fids: dict[int, Fid] = {}
        self.authority: Authority | None = None
        self.uname = "?"
        self.msize = MSIZE
        self.pending: dict[str, Fid] = {}  # Tcreate'd files not yet minted, visible to walk/stat

    # -- verbs, counted -------------------------------------------------
    async def verb(self, name: str, coro):
        self.c.verbs[name] += 1
        self.c.in_flight.append(name)
        try:
            return await coro
        finally:
            self.c.in_flight.pop()

    @staticmethod
    def err_of(result) -> str:
        kind = str(getattr(result.errors[0].kind, "value", result.errors[0].kind))
        return KIND_TO_ERR.get(kind, f"{E_IO}: {kind}")

    async def stat_row(self, path: str) -> dict:
        pf = self.pending.get(path)
        if pf is not None:
            return {"kind": "file", "size": len(pf.buf or b""), "version": 0, "mtime": pf.mtime}
        r = await self.verb("stat", self.fs.stat(path=path, authority=self.authority))
        if r.errors:
            raise P9Error(self.err_of(r))
        o = r.observations[0]
        return {"kind": o.kind, "size": o.size_bytes or 0, "version": o.version or 0,
                "mtime": int(o.updated_at.timestamp()) if o.updated_at else int(time.time())}

    def stat_of_fid(self, f: Fid) -> bytes:
        name = "/" if f.path == "/" else posixpath.basename(f.path)
        size = len(f.buf) if f.buf is not None else f.size_hint
        return p_stat(name, f.is_dir, size, f.mtime or int(time.time()), f.version, f.path, self.uname)

    # -- message handlers --------------------------------------------------
    async def handle(self, mtype: int, tag: int, r: Reader) -> bytes:
        self.c.msgs[NAMES.get(mtype, str(mtype))] += 1
        try:
            fn = getattr(self, f"t_{mtype}", None)
            if fn is None:
                raise P9Error("unknown message type")
            body, rtype = await fn(r)
        except P9Error as e:
            body, rtype = p_str(str(e)), Rerror
        return struct.pack("<IBH", 7 + len(body), rtype, tag) + body

    async def t_100(self, r: Reader):  # Tversion
        msize, version = r.u32(), r.s()
        self.msize = min(msize, MSIZE)
        self.fids.clear()
        ver = "9P2000" if version.startswith("9P2000") else "unknown"
        return struct.pack("<I", self.msize) + p_str(ver), Rversion

    async def t_102(self, r: Reader):  # Tauth
        raise P9Error("authentication not required")

    async def t_104(self, r: Reader):  # Tattach
        fid, afid, uname, aname = r.u32(), r.u32(), r.s(), r.s()
        # Identity is a value on the call: the uname becomes the Authority for this connection.
        self.uname = uname or "anonymous"
        self.authority = Authority.of(Principal(self.uname, kind="agent"))
        st = await self.stat_row("/")
        self.fids[fid] = Fid("/", True, version=st["version"], mtime=st["mtime"])
        return p_qid(QTDIR, st["version"], qid_path("/")), Rattach

    async def t_108(self, r: Reader):  # Tflush
        return b"", Rflush

    async def t_110(self, r: Reader):  # Twalk
        fid, newfid, n = r.u32(), r.u32(), r.u16()
        names = [r.s() for _ in range(n)]
        f = self.fids.get(fid)
        if f is None:
            raise P9Error("unknown fid")
        path = f.path
        qids: list[bytes] = []
        is_dir, version, mtime, size = f.is_dir, f.version, f.mtime, 0
        for i, name in enumerate(names):
            if name == "..":
                path = posixpath.dirname(path) or "/"
            elif name == ".":
                pass
            else:
                path = "/" + name if path == "/" else f"{path}/{name}"
            try:
                st = await self.stat_row(path)
            except P9Error:
                if i == 0:
                    raise
                break
            is_dir = st["kind"] == "directory"
            version, mtime, size = st["version"], st["mtime"], st["size"]
            qids.append(p_qid(QTDIR if is_dir else QTFILE, version, qid_path(path)))
        if len(qids) == len(names):
            nf = Fid(path, is_dir, version=version, mtime=mtime)
            nf.size_hint = size
            self.fids[newfid] = nf
        return struct.pack("<H", len(qids)) + b"".join(qids), Rwalk

    async def t_112(self, r: Reader):  # Topen
        fid, mode = r.u32(), r.u8()
        f = self.fids.get(fid)
        if f is None:
            raise P9Error("unknown fid")
        if f.is_dir:
            res = await self.verb("ls", self.fs.ls(path=f.path, authority=self.authority))
            if res.errors:
                raise P9Error(self.err_of(res))
            f.dir_entries = [
                p_stat(posixpath.basename(o.path), o.kind == "directory", o.size_bytes or 0,
                       int(o.updated_at.timestamp()) if o.updated_at else 0, o.version or 0, o.path, self.uname)
                for o in sorted(res.observations, key=lambda o: o.path)
            ]
            f.open_mode = mode
            return p_qid(QTDIR, f.version, qid_path(f.path)) + struct.pack("<I", IOUNIT), Ropen
        if mode & OTRUNC:
            f.buf, f.dirty = bytearray(), True
        else:
            res = await self.verb("read", self.fs.read(path=f.path, columns=READ_COLUMNS, authority=self.authority))
            if res.errors:
                raise P9Error(self.err_of(res))
            o = res.observations[0]
            f.buf = bytearray(o.data if o.data is not None else (o.content or "").encode())
            f.version = o.version or 0
        f.open_mode = mode
        return p_qid(QTFILE, f.version, qid_path(f.path)) + struct.pack("<I", IOUNIT), Ropen

    async def t_114(self, r: Reader):  # Tcreate
        fid, name, perm, mode = r.u32(), r.s(), r.u32(), r.u8()
        f = self.fids.get(fid)
        if f is None or not f.is_dir:
            raise P9Error(E_NOTDIR)
        path = "/" + name if f.path == "/" else f"{f.path}/{name}"
        if perm & DMDIR:
            res = await self.verb("mkdir", self.fs.mkdir(path, authority=self.authority))
            if res.errors:
                raise P9Error(self.err_of(res))
            st = await self.stat_row(path)
            self.fids[fid] = Fid(path, True, version=st["version"], mtime=st["mtime"], open_mode=mode)
            return p_qid(QTDIR, st["version"], qid_path(path)) + struct.pack("<I", IOUNIT), Rcreate
        # A file: nothing is minted until clunk; the fid now names the new file, open and dirty.
        nf = Fid(path, False, buf=bytearray(), dirty=True, version=0, mtime=int(time.time()), open_mode=mode, pending_create=True)
        nf.size_hint = 0
        self.fids[fid] = nf
        self.pending[path] = nf
        return p_qid(QTFILE, 0, qid_path(path)) + struct.pack("<I", IOUNIT), Rcreate

    async def t_116(self, r: Reader):  # Tread
        fid, offset, count = r.u32(), r.u64(), r.u32()
        f = self.fids.get(fid)
        if f is None or f.open_mode is None:
            raise P9Error("fid not open")
        count = min(count, self.msize - 24)
        if f.is_dir:
            # Serve whole stat entries; the offset is a byte offset into the concatenation.
            pos, out = 0, bytearray()
            for ent in f.dir_entries:
                if pos >= offset:
                    if len(out) + len(ent) > count:
                        break
                    out += ent
                pos += len(ent)
            return struct.pack("<I", len(out)) + bytes(out), Rread
        assert f.buf is not None
        data = bytes(f.buf[offset:offset + count])
        self.c.bytes_out += len(data)
        return struct.pack("<I", len(data)) + data, Rread

    async def t_118(self, r: Reader):  # Twrite
        fid, offset, count = r.u32(), r.u64(), r.u32()
        data = r.bytes_(count)
        f = self.fids.get(fid)
        if f is None or f.open_mode is None or f.is_dir:
            raise P9Error("fid not open for writing")
        assert f.buf is not None
        if offset > len(f.buf):
            f.buf.extend(b"\0" * (offset - len(f.buf)))
        f.buf[offset:offset + len(data)] = data
        f.dirty = True
        self.c.bytes_in += len(data)
        return struct.pack("<I", len(data)), Rwrite

    async def flush(self, f: Fid) -> None:
        if f.buf is None or not f.dirty:
            return
        body = bytes(f.buf)
        try:
            res = await self.verb("write", self.fs.write(path=f.path, content=body.decode("utf-8"), authority=self.authority))
        except UnicodeDecodeError:
            res = await self.verb("write", self.fs.write(path=f.path, data=body, authority=self.authority))
        f.dirty = False
        f.pending_create = False
        self.pending.pop(f.path, None)
        if res.errors:
            raise P9Error(self.err_of(res))
        o = res.observations[0]
        f.version = o.version or 0
        self.c.trace.append(f"clunk -> write {f.path} {len(body)}B version {o.version}")

    async def t_120(self, r: Reader):  # Tclunk
        fid = r.u32()
        f = self.fids.pop(fid, None)
        if f is None:
            raise P9Error("unknown fid")
        await self.flush(f)
        if f.open_mode is not None and f.open_mode & ORCLOSE:
            await self.verb("delete", self.fs.delete(path=f.path, cascade=False, authority=self.authority))
        return b"", Rclunk

    async def t_122(self, r: Reader):  # Tremove
        fid = r.u32()
        f = self.fids.pop(fid, None)
        if f is None:
            raise P9Error("unknown fid")
        if f.pending_create:
            self.pending.pop(f.path, None)
            return b"", Rremove
        res = await self.verb("delete", self.fs.delete(path=f.path, cascade=False, authority=self.authority))
        if res.errors:
            raise P9Error(self.err_of(res))
        return b"", Rremove

    async def t_124(self, r: Reader):  # Tstat
        fid = r.u32()
        f = self.fids.get(fid)
        if f is None:
            raise P9Error("unknown fid")
        if f.buf is None and not f.pending_create:
            st = await self.stat_row(f.path)
            f.is_dir, f.version, f.mtime = st["kind"] == "directory", st["version"], st["mtime"]
            f.size_hint = st["size"]
        st_bytes = self.stat_of_fid(f)
        return struct.pack("<H", len(st_bytes)) + st_bytes, Rstat

    async def t_126(self, r: Reader):  # Twstat
        fid = r.u32()
        r.u16()  # outer size
        s = Reader(r.d, r.p)
        s.u16(); s.u16(); s.u32(); s.bytes_(13)  # size, type, dev, qid
        mode, atime, mtime, length = s.u32(), s.u32(), s.u32(), s.u64()
        name = s.s()
        f = self.fids.get(fid)
        if f is None:
            raise P9Error("unknown fid")
        if name:
            dest = posixpath.join(posixpath.dirname(f.path), name)
            res = await self.verb("move", self.fs.move(src=f.path, dest=dest, authority=self.authority))
            if res.errors:
                raise P9Error(self.err_of(res))
            f.path = dest
        if length != 0xFFFFFFFFFFFFFFFF and not f.is_dir:
            if f.buf is None:
                res = await self.verb("read", self.fs.read(path=f.path, columns=READ_COLUMNS, authority=self.authority))
                if res.errors:
                    raise P9Error(self.err_of(res))
                o = res.observations[0]
                buf = bytearray(o.data if o.data is not None else (o.content or "").encode())
                del buf[length:]
                buf.extend(b"\0" * (length - len(buf)))
                tmp = Fid(f.path, False, buf=buf, dirty=True)
                await self.flush(tmp)
                f.version = tmp.version
            else:
                del f.buf[length:]
                f.buf.extend(b"\0" * (length - len(f.buf)))
                f.dirty = True
        # mode / atime / mtime: accepted and ignored; a null wstat (fsync) is a no-op.
        return b"", Rwstat


Fid.size_hint = 0  # type: ignore[attr-defined]


@dataclass
class Counters:
    msgs: Counter = field(default_factory=Counter)
    verbs: Counter = field(default_factory=Counter)
    sql_per_msg: Counter = field(default_factory=Counter)
    sql_total: int = 0
    bytes_in: int = 0
    bytes_out: int = 0
    in_flight: list = field(default_factory=list)
    msg_in_flight: list = field(default_factory=list)
    trace: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

async def serve_conn(fs: VirtualFileSystem, counters: Counters, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    session = Session(fs, counters)
    try:
        while True:
            head = await reader.readexactly(4)
            size = struct.unpack("<I", head)[0]
            rest = await reader.readexactly(size - 4)
            mtype, tag = struct.unpack_from("<BH", rest, 0)
            counters.msg_in_flight.append(NAMES.get(mtype, str(mtype)))
            try:
                reply = await session.handle(mtype, tag, Reader(rest, 3))
            finally:
                counters.msg_in_flight.pop()
            writer.write(reply)
            await writer.drain()
    except (asyncio.IncompleteReadError, ConnectionResetError, BrokenPipeError):
        pass
    finally:
        for f in list(session.fids.values()):
            try:
                await session.flush(f)
            except P9Error:
                pass
        writer.close()


CSV = "region,month,sales\n" + "\n".join(
    f"{r},{m},{(i * 37) % 100 + 10}"
    for i, (r, m) in enumerate((r, m) for r in ("north", "south", "east", "west") for m in range(1, 13))
) + "\n"


async def main() -> None:
    args = sys.argv[1:]
    port = int(args[args.index("--port") + 1]) if "--port" in args else 5640
    report = Path(args[args.index("--report") + 1]) if "--report" in args else None
    storage = InMemoryStorage()
    fs = VirtualFileSystem(storage=storage)
    seed = Authority.of(Principal("agent-7", kind="agent"))
    await fs.write(path="/data/sales.csv", content=CSV, parents=True, authority=seed)
    await fs.mkdir("/out", authority=seed)
    await fs.mkdir("/scripts", authority=seed)
    await fs.write(path="/scripts/job.py", content=(HERE / "guest_job.py").read_text(), authority=seed)

    counters = Counters()

    def count_sql(conn, cursor, statement, parameters, context, executemany):
        counters.sql_total += 1
        if counters.msg_in_flight:
            counters.sql_per_msg[counters.msg_in_flight[-1]] += 1

    event.listen(storage._host.engine.sync_engine, "before_cursor_execute", count_sql)
    server = await asyncio.start_server(lambda r, w: serve_conn(fs, counters, r, w), "0.0.0.0", port)
    print(f"9P2000 server on tcp port {port}", flush=True)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    async with server:
        await stop.wait()
    png = await fs.read(path="/out/plot.png", columns=READ_COLUMNS, authority=seed)
    png_row = None
    if not png.errors:
        o = png.observations[0]
        png_row = {"path": o.path, "mime_type": o.mime_type, "size_bytes": o.size_bytes, "version": o.version,
                   "data_is_png": bool(o.data and o.data[:8] == b"\x89PNG\r\n\x1a\n"), "content_is_none": o.content is None}
    out = {
        "messages": dict(counters.msgs), "verbs": dict(counters.verbs),
        "sql_total": counters.sql_total, "sql_per_message": dict(counters.sql_per_msg),
        "bytes_in": counters.bytes_in, "bytes_out": counters.bytes_out,
        "trace": counters.trace[-20:], "png_row": png_row,
        "out_listing": sorted(posixpath.basename(o.path) for o in (await fs.ls(path="/out", authority=seed)).observations),
        "trash": sorted(posixpath.basename(o.path) for o in (await fs.ls(path="/.vfs/trash", authority=seed)).observations),
    }
    text = json.dumps(out, indent=2)
    print(text, flush=True)
    if report:
        report.write_text(text)


if __name__ == "__main__":
    asyncio.run(main())
