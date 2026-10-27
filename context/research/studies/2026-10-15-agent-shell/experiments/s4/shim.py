"""S4 experiment: a minimal WASI preview1 shim whose file calls resolve to vfs verbs.

Run from the vfs repo root:

    uv run --with wasmtime python context/research/studies/2026-10-15-agent-shell/experiments/s4/shim.py

The host is wasmtime-py. Every `wasi_snapshot_preview1` import the module
declares is bound to a Python function; the ones listed in IMPLEMENTED are
real, the rest answer ERRNO_NOSYS and are logged. The guest's filesystem is
a `VirtualFileSystem` over `InMemoryStorage`; one preopen named "/" is fd 3.

Staging rule under test: `path_open` stages the whole row with one `read`
(or none, for a create/truncate), reads and seeks run on the buffer, and
`fd_close` writes a dirty buffer back with one `write`.

The guest runs on a worker thread; every host call that needs a verb hops
back to the event loop with `run_coroutine_threadsafe`, because preview1
syscalls are synchronous and vfs verbs are coroutines.
"""

from __future__ import annotations

import asyncio
import json
import os
import posixpath
import struct
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import event
from wasmtime import Engine, Linker, Module, Store

from vfs import VirtualFileSystem
from vfs.storage.backends import InMemoryStorage

HERE = Path(__file__).resolve().parent
WASM = HERE / "catfile" / "target" / "wasm32-wasip1" / "release" / "catfile.wasm"

# errno (preview1 numbering)
SUCCESS, E2BIG, EACCES, EBADF, EEXIST, EFAULT, EINVAL, EIO, EISDIR = 0, 1, 2, 8, 20, 21, 28, 29, 31
ENOENT, ENOSYS, ENOTDIR, ENOTEMPTY, ENOTSUP, EPERM, EROFS, ESPIPE, EXDEV, ENOTCAPABLE = 44, 52, 54, 55, 58, 63, 69, 70, 75, 76
# filetype
FT_UNKNOWN, FT_CHAR, FT_DIR, FT_REG = 0, 2, 3, 4
# oflags / fdflags / rights / whence
O_CREAT, O_DIRECTORY, O_EXCL, O_TRUNC = 1, 2, 4, 8
FD_APPEND = 1
R_FD_READ, R_FD_SEEK, R_FD_TELL, R_FD_WRITE = 1 << 1, 1 << 2, 1 << 5, 1 << 6
ALL_RIGHTS = (1 << 30) - 1
SEEK_SET, SEEK_CUR, SEEK_END = 0, 1, 2
READ_COLUMNS = frozenset({"content", "data", "kind", "size_bytes", "mime_type", "version", "updated_at"})

VFS_KIND_TO_ERRNO = {
    "vfs.not_found": ENOENT,
    "vfs.exists": EEXIST,
    "vfs.wrong_kind": ENOTDIR,
    "vfs.not_empty": ENOTEMPTY,
    "vfs.permission_denied": EACCES,
    "vfs.unauthenticated": EACCES,
    "vfs.read_only": EROFS,
    "vfs.unsupported": ENOTSUP,
    "vfs.invalid": EINVAL,
    "vfs.cross_mount": EXDEV,
    "vfs.unavailable": EIO,
}


class GuestExit(Exception):
    def __init__(self, code: int) -> None:
        super().__init__(f"guest exit {code}")
        self.code = code


@dataclass
class Fd:
    kind: str  # "stdin" | "stdout" | "stderr" | "preopen" | "dir" | "file"
    path: str = "/"
    buf: bytearray = field(default_factory=bytearray)
    pos: int = 0
    dirty: bool = False
    append: bool = False
    entries: list[tuple[str, int]] | None = None  # (name, filetype) for dirs
    stat: dict | None = None  # cached observation fields at open


class Counters:
    def __init__(self) -> None:
        self.statements = 0
        self.verbs: Counter[str] = Counter()
        self.syscalls: Counter[str] = Counter()
        self.bytes_to_guest = 0
        self.bytes_from_guest = 0
        self.trace: list[str] = []
        self.unimplemented: Counter[str] = Counter()


class Shim:
    def __init__(self, fs: VirtualFileSystem, loop: asyncio.AbstractEventLoop, argv: list[str], stdin: bytes, counters: Counters) -> None:
        self.fs, self.loop, self.argv, self.c = fs, loop, argv, counters
        self.stdin = bytearray(stdin)
        self.stdout = bytearray()
        self.stderr = bytearray()
        self.fds: dict[int, Fd] = {
            0: Fd("stdin"), 1: Fd("stdout"), 2: Fd("stderr"), 3: Fd("preopen", "/"),
        }
        self.next_fd = 4
        self.inos: dict[str, int] = {}
        self.env: list[str] = []

    # -- bridges ---------------------------------------------------------
    def verb(self, name: str, coro):
        self.c.verbs[name] += 1
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result()

    def ino(self, path: str) -> int:
        return self.inos.setdefault(path, len(self.inos) + 1)

    @staticmethod
    def errno_of(result) -> int:
        for err in result.errors:
            return VFS_KIND_TO_ERRNO.get(str(getattr(err.kind, "value", err.kind)), EIO)
        return SUCCESS

    def resolve(self, dirfd: int, rel: str) -> tuple[int, str]:
        d = self.fds.get(dirfd)
        if d is None:
            return EBADF, ""
        if d.kind not in ("preopen", "dir"):
            return ENOTDIR, ""
        if rel.startswith("/"):
            return ENOTCAPABLE, ""
        parts: list[str] = []
        for seg in rel.split("/"):
            if seg in ("", "."):
                continue
            if seg == "..":
                if not parts:
                    return ENOTCAPABLE, ""
                parts.pop()
                continue
            parts.append(seg)
        return SUCCESS, posixpath.join(d.path, *parts) if parts else d.path

    # -- memory helpers --------------------------------------------------
    @staticmethod
    def mem(caller):
        return caller.get("memory")

    def rd(self, caller, ptr: int, n: int) -> bytes:
        m = self.mem(caller)
        if ptr + n > m.data_len(caller):
            raise MemoryError("guest pointer out of bounds")
        return bytes(m.read(caller, ptr, ptr + n))

    def wr(self, caller, ptr: int, data: bytes) -> None:
        if data:
            self.mem(caller).write(caller, bytearray(data), ptr)

    def u32(self, caller, ptr: int, v: int) -> None:
        self.wr(caller, ptr, struct.pack("<I", v))

    def u64(self, caller, ptr: int, v: int) -> None:
        self.wr(caller, ptr, struct.pack("<Q", v & (2**64 - 1)))

    def iovs(self, caller, ptr: int, n: int) -> list[tuple[int, int]]:
        raw = self.rd(caller, ptr, 8 * n)
        return [struct.unpack_from("<II", raw, 8 * i) for i in range(n)]

    def filestat(self, caller, ptr: int, path: str, filetype: int, size: int, st: dict | None) -> None:
        ns = int((st or {}).get("updated_at", time.time()) * 1e9) if st else 0
        self.wr(caller, ptr, struct.pack("<QQBxxxxxxxQQQQQ", 0, self.ino(path), filetype, 1, size, ns, ns, ns))

    # -- the preview1 surface ---------------------------------------------
    def args_sizes_get(self, caller, argc_ptr, buf_size_ptr):
        self.u32(caller, argc_ptr, len(self.argv))
        self.u32(caller, buf_size_ptr, sum(len(a.encode()) + 1 for a in self.argv))
        return SUCCESS

    def args_get(self, caller, argv_ptr, buf_ptr):
        off = buf_ptr
        for i, a in enumerate(self.argv):
            self.u32(caller, argv_ptr + 4 * i, off)
            b = a.encode() + b"\0"
            self.wr(caller, off, b)
            off += len(b)
        return SUCCESS

    def environ_sizes_get(self, caller, count_ptr, size_ptr):
        self.u32(caller, count_ptr, len(self.env))
        self.u32(caller, size_ptr, sum(len(e) + 1 for e in self.env))
        return SUCCESS

    def environ_get(self, caller, env_ptr, buf_ptr):
        off = buf_ptr
        for i, e in enumerate(self.env):
            self.u32(caller, env_ptr + 4 * i, off)
            b = e.encode() + b"\0"
            self.wr(caller, off, b)
            off += len(b)
        return SUCCESS

    def clock_time_get(self, caller, clock_id, precision, out_ptr):
        self.u64(caller, out_ptr, time.time_ns() if clock_id == 0 else time.monotonic_ns())
        return SUCCESS

    def random_get(self, caller, ptr, n):
        self.wr(caller, ptr, os.urandom(n))
        return SUCCESS

    def proc_exit(self, caller, code):
        raise GuestExit(code)

    def fd_prestat_get(self, caller, fd, ptr):
        f = self.fds.get(fd)
        if f is None or f.kind != "preopen":
            self.c.trace.append(f"fd_prestat_get({fd}) -> EBADF (end of preopen scan)")
            return EBADF
        self.wr(caller, ptr, struct.pack("<II", 0, len(f.path.encode())))
        return SUCCESS

    def fd_prestat_dir_name(self, caller, fd, ptr, n):
        f = self.fds.get(fd)
        if f is None or f.kind != "preopen":
            return EBADF
        name = f.path.encode()
        self.wr(caller, ptr, name[:n])
        return SUCCESS

    def fd_fdstat_get(self, caller, fd, ptr):
        f = self.fds.get(fd)
        if f is None:
            return EBADF
        if f.kind in ("stdin", "stdout", "stderr"):
            ft, rights = FT_CHAR, (R_FD_READ if f.kind == "stdin" else R_FD_WRITE)
        elif f.kind == "file":
            ft, rights = FT_REG, ALL_RIGHTS
        else:
            ft, rights = FT_DIR, ALL_RIGHTS
        flags = FD_APPEND if f.append else 0
        self.wr(caller, ptr, struct.pack("<BxHxxxxQQ", ft, flags, rights, rights))
        return SUCCESS

    def fd_fdstat_set_flags(self, caller, fd, flags):
        f = self.fds.get(fd)
        if f is None:
            return EBADF
        f.append = bool(flags & FD_APPEND)
        return SUCCESS

    def fd_filestat_get(self, caller, fd, ptr):
        f = self.fds.get(fd)
        if f is None:
            return EBADF
        if f.kind == "file":
            self.filestat(caller, ptr, f.path, FT_REG, len(f.buf), f.stat)
        elif f.kind in ("dir", "preopen"):
            self.filestat(caller, ptr, f.path, FT_DIR, 0, f.stat)
        else:
            self.filestat(caller, ptr, f.kind, FT_CHAR, 0, None)
        return SUCCESS

    def fd_filestat_set_size(self, caller, fd, size):
        f = self.fds.get(fd)
        if f is None or f.kind != "file":
            return EBADF
        del f.buf[size:]
        f.buf.extend(b"\0" * (size - len(f.buf)))
        f.dirty = True
        return SUCCESS

    def _stat_obs(self, path: str):
        r = self.verb("stat", self.fs.stat(path=path))
        if r.errors:
            return self.errno_of(r), None
        o = r.observations[0]
        return SUCCESS, {
            "kind": o.kind,
            "size": o.size_bytes or 0,
            "updated_at": o.updated_at.timestamp() if o.updated_at else 0,
            "version": o.version,
        }

    def path_filestat_get(self, caller, fd, flags, path_ptr, path_len, out_ptr):
        rel = self.rd(caller, path_ptr, path_len).decode()
        err, path = self.resolve(fd, rel)
        self.c.trace.append(f"path_filestat_get(fd={fd}, {rel!r}) -> {path!r}")
        if err:
            return err
        err, st = self._stat_obs(path)
        if err:
            return err
        self.filestat(caller, out_ptr, path, FT_DIR if st["kind"] == "directory" else FT_REG, st["size"], st)
        return SUCCESS

    def path_open(self, caller, dirfd, dirflags, path_ptr, path_len, oflags, rights_base, rights_inh, fdflags, out_ptr):
        """One verb per open: a plain open is one `read`; a directory open is one `ls`;
        a create/truncate open is zero verbs now and one `write` at close. Only
        O_EXCL needs an existence probe (`stat`) first."""
        rel = self.rd(caller, path_ptr, path_len).decode()
        err, path = self.resolve(dirfd, rel)
        self.c.trace.append(
            f"path_open(dirfd={dirfd}, {rel!r}, oflags={oflags:#x}, rights={rights_base:#x}, fdflags={fdflags:#x}) -> {path!r}"
        )
        if err:
            return err
        append = bool(fdflags & FD_APPEND)
        f: Fd | None = None
        if oflags & O_DIRECTORY:
            r = self.verb("ls", self.fs.ls(path=path))
            if r.errors:
                return self.errno_of(r)
            f = Fd("dir", path, entries=self._entries(r), stat=None)
        elif oflags & O_EXCL:
            err, st = self._stat_obs(path)
            if err == SUCCESS:
                return EEXIST
            if err != ENOENT:
                return err
            f = Fd("file", path, bytearray(), 0, dirty=True, append=append)
        elif (oflags & O_TRUNC) and (oflags & O_CREAT):
            f = Fd("file", path, bytearray(), 0, dirty=True, append=append)
        else:
            r = self.verb("read", self.fs.read(path=path, columns=READ_COLUMNS))
            kind = str(getattr(r.errors[0].kind, "value", r.errors[0].kind)) if r.errors else None
            if kind == "vfs.not_found":
                if not (oflags & O_CREAT):
                    return ENOENT
                f = Fd("file", path, bytearray(), 0, dirty=True, append=append)
            elif kind == "vfs.wrong_kind":
                if rights_base & R_FD_WRITE:
                    return EISDIR
                r = self.verb("ls", self.fs.ls(path=path))
                if r.errors:
                    return self.errno_of(r)
                f = Fd("dir", path, entries=self._entries(r), stat=None)
            elif kind is not None:
                return self.errno_of(r)
            else:
                o = r.observations[0]
                body = bytearray() if oflags & O_TRUNC else bytearray(o.data if o.data is not None else (o.content or "").encode())
                st = {"kind": o.kind, "size": o.size_bytes or 0, "updated_at": o.updated_at.timestamp() if o.updated_at else 0, "version": o.version}
                f = Fd("file", path, body, 0, dirty=bool(oflags & O_TRUNC), append=append, stat=st)
        fd = self.next_fd
        self.next_fd += 1
        self.fds[fd] = f
        self.u32(caller, out_ptr, fd)
        return SUCCESS

    @staticmethod
    def _entries(r) -> list[tuple[str, int]]:
        return sorted((posixpath.basename(o.path), FT_DIR if o.kind == "directory" else FT_REG) for o in r.observations)

    def fd_read(self, caller, fd, iovs_ptr, iovs_len, nread_ptr):
        f = self.fds.get(fd)
        if f is None:
            return EBADF
        if f.kind == "stdin":
            src, pos = self.stdin, 0
        elif f.kind == "file":
            src, pos = f.buf, f.pos
        elif f.kind in ("dir", "preopen"):
            return EISDIR
        else:
            return EBADF
        total = 0
        for ptr, n in self.iovs(caller, iovs_ptr, iovs_len):
            chunk = bytes(src[pos : pos + n])
            if not chunk:
                break
            self.wr(caller, ptr, chunk)
            pos += len(chunk)
            total += len(chunk)
            if len(chunk) < n:
                break
        if f.kind == "stdin":
            del self.stdin[:total]
        else:
            f.pos = pos
        self.c.bytes_to_guest += total
        self.u32(caller, nread_ptr, total)
        return SUCCESS

    def fd_write(self, caller, fd, iovs_ptr, iovs_len, nwritten_ptr):
        f = self.fds.get(fd)
        if f is None:
            return EBADF
        data = b"".join(self.rd(caller, ptr, n) for ptr, n in self.iovs(caller, iovs_ptr, iovs_len))
        self.c.bytes_from_guest += len(data)
        if f.kind == "stdout":
            self.stdout += data
        elif f.kind == "stderr":
            self.stderr += data
        elif f.kind == "file":
            if f.append:
                f.pos = len(f.buf)
            if f.pos > len(f.buf):
                f.buf.extend(b"\0" * (f.pos - len(f.buf)))
            f.buf[f.pos : f.pos + len(data)] = data
            f.pos += len(data)
            f.dirty = True
        else:
            return EBADF
        self.u32(caller, nwritten_ptr, len(data))
        return SUCCESS

    def fd_seek(self, caller, fd, offset, whence, out_ptr):
        f = self.fds.get(fd)
        if f is None:
            return EBADF
        if f.kind != "file":
            return ESPIPE if f.kind in ("stdin", "stdout", "stderr") else EBADF
        base = {SEEK_SET: 0, SEEK_CUR: f.pos, SEEK_END: len(f.buf)}.get(whence)
        if base is None or base + offset < 0:
            return EINVAL
        f.pos = base + offset
        self.u64(caller, out_ptr, f.pos)
        return SUCCESS

    def fd_tell(self, caller, fd, out_ptr):
        f = self.fds.get(fd)
        if f is None or f.kind != "file":
            return EBADF
        self.u64(caller, out_ptr, f.pos)
        return SUCCESS

    def fd_readdir(self, caller, fd, buf, buf_len, cookie, bufused_ptr):
        f = self.fds.get(fd)
        if f is None:
            return EBADF
        if f.kind not in ("dir", "preopen"):
            return ENOTDIR
        if f.entries is None:
            r = self.verb("ls", self.fs.ls(path=f.path))
            if r.errors:
                return self.errno_of(r)
            f.entries = sorted((posixpath.basename(o.path), FT_DIR if o.kind == "directory" else FT_REG) for o in r.observations)
        listing = [(".", FT_DIR, f.path), ("..", FT_DIR, posixpath.dirname(f.path))] + [(n, t, posixpath.join(f.path, n)) for n, t in f.entries]
        used = 0
        i = cookie
        self.c.trace.append(f"fd_readdir(fd={fd}, cookie={cookie}, buf_len={buf_len})")
        while i < len(listing):
            name, ft, full = listing[i]
            nb = name.encode()
            head = struct.pack("<QQIBxxx", i + 1, self.ino(full), len(nb), ft)
            rec = head + nb
            room = buf_len - used
            if room <= 0:
                break
            self.wr(caller, buf + used, rec[:room])
            used += min(len(rec), room)
            if len(rec) > room:
                break  # truncated entry: the guest sees bufused == buf_len and re-asks
            i += 1
        self.u32(caller, bufused_ptr, used)
        return SUCCESS

    def path_create_directory(self, caller, fd, path_ptr, path_len):
        err, path = self.resolve(fd, self.rd(caller, path_ptr, path_len).decode())
        if err:
            return err
        r = self.verb("mkdir", self.fs.mkdir(path))
        return self.errno_of(r)

    def path_remove_directory(self, caller, fd, path_ptr, path_len):
        err, path = self.resolve(fd, self.rd(caller, path_ptr, path_len).decode())
        if err:
            return err
        err, st = self._stat_obs(path)
        if err:
            return err
        if st["kind"] != "directory":
            return ENOTDIR
        r = self.verb("delete", self.fs.delete(path=path, cascade=False))
        return self.errno_of(r)

    def path_unlink_file(self, caller, fd, path_ptr, path_len):
        err, path = self.resolve(fd, self.rd(caller, path_ptr, path_len).decode())
        if err:
            return err
        err, st = self._stat_obs(path)
        if err:
            return err
        if st["kind"] == "directory":
            return EISDIR
        r = self.verb("delete", self.fs.delete(path=path))
        return self.errno_of(r)

    def path_rename(self, caller, fd, old_ptr, old_len, new_fd, new_ptr, new_len):
        err, src = self.resolve(fd, self.rd(caller, old_ptr, old_len).decode())
        if err:
            return err
        err, dest = self.resolve(new_fd, self.rd(caller, new_ptr, new_len).decode())
        if err:
            return err
        r = self.verb("move", self.fs.move(src=src, dest=dest))
        return self.errno_of(r)

    def fd_close(self, caller, fd):
        f = self.fds.pop(fd, None)
        if f is None:
            return EBADF
        return self.flush(f)

    def flush(self, f: Fd) -> int:
        if f.kind == "file" and f.dirty:
            body = bytes(f.buf)
            try:
                text = body.decode("utf-8")
                r = self.verb("write", self.fs.write(path=f.path, content=text))
            except UnicodeDecodeError:
                r = self.verb("write", self.fs.write(path=f.path, data=body))
            self.c.trace.append(f"fd_close -> write({f.path!r}, {len(body)} bytes) errors={[str(e.kind) for e in r.errors]}")
            f.dirty = False
            return self.errno_of(r)
        return SUCCESS

    def fd_renumber(self, caller, fd, to):
        if fd not in self.fds or to not in self.fds:
            return EBADF
        self.flush(self.fds.pop(to))
        self.fds[to] = self.fds.pop(fd)
        return SUCCESS

    def fd_sync(self, caller, fd):
        return SUCCESS if fd in self.fds else EBADF

    fd_datasync = fd_sync

    def sched_yield(self, caller):
        return SUCCESS

    def fd_advise(self, caller, fd, offset, length, advice):
        return SUCCESS if fd in self.fds else EBADF


IMPLEMENTED = {
    name for name in dir(Shim) if not name.startswith("_") and name not in {"verb", "ino", "errno_of", "resolve", "mem", "rd", "wr", "u32", "u64", "iovs", "filestat", "flush"}
}


def bind(linker: Linker, module: Module, shim: Shim) -> list[str]:
    stubbed: list[str] = []
    for imp in module.imports:
        if imp.module != "wasi_snapshot_preview1":
            continue
        name = imp.name
        assert name is not None
        ty = imp.type
        if name in IMPLEMENTED:
            impl = getattr(shim, name)

            def real(caller, *args, _impl=impl, _name=name):
                shim.c.syscalls[_name] += 1
                return _impl(caller, *args)

            linker.define_func("wasi_snapshot_preview1", name, ty, real, access_caller=True)
        else:
            stubbed.append(name)
            has_result = len(ty.results) == 1

            def stub(caller, *args, _name=name, _has_result=has_result):
                shim.c.unimplemented[_name] += 1
                return ENOSYS if _has_result else None

            linker.define_func("wasi_snapshot_preview1", name, ty, stub, access_caller=True)
    return stubbed


def run_guest(engine: Engine, module: Module, shim: Shim) -> tuple[int, list[str]]:
    linker = Linker(engine)
    stubbed = bind(linker, module, shim)
    store = Store(engine)
    instance = linker.instantiate(store, module)
    start = instance.exports(store)["_start"]
    code = 0
    try:
        start(store)
    except GuestExit as exit_:
        code = exit_.code
    for fd in list(shim.fds):
        if fd > 3:
            shim.flush(shim.fds.pop(fd))
    return code, stubbed



async def run_scenario(fs: VirtualFileSystem, storage: InMemoryStorage, wasm: Path, argv: list[str], stdin: bytes = b"", env: list[str] | None = None) -> dict:
    """Run one guest invocation and return the counters. Statements are attributed to the verb in flight."""
    counters = Counters()
    per_verb_statements: Counter[str] = Counter()
    in_flight: list[str] = []

    def _count(conn, cursor, statement, parameters, context, executemany):
        counters.statements += 1
        if in_flight:
            per_verb_statements[in_flight[-1]] += 1

    sync_engine = storage._host.engine.sync_engine
    event.listen(sync_engine, "before_cursor_execute", _count)
    engine = Engine()
    t0 = time.perf_counter()
    module = Module.from_file(engine, str(wasm))
    compile_s = time.perf_counter() - t0
    loop = asyncio.get_running_loop()
    shim = Shim(fs, loop, argv, stdin, counters)
    shim.env = env or []

    original_verb = shim.verb

    def attributed_verb(name, coro):
        async def wrapped():
            in_flight.append(name)
            try:
                return await coro
            finally:
                in_flight.pop()
        return original_verb(name, wrapped())

    shim.verb = attributed_verb  # type: ignore[method-assign]
    t1 = time.perf_counter()
    try:
        code, stubbed = await loop.run_in_executor(None, run_guest, engine, module, shim)
        trapped = None
    except Exception as exc:  # a wasm trap or a host bug surfaces here
        code, stubbed, trapped = -1, [], f"{type(exc).__name__}: {exc}"
    run_s = time.perf_counter() - t1
    event.remove(sync_engine, "before_cursor_execute", _count)
    return {
        "argv": argv,
        "exit_code": code,
        "trapped": trapped,
        "stdout": shim.stdout.decode(errors="replace")[:400],
        "stderr": shim.stderr.decode(errors="replace")[:400],
        "syscalls": dict(sorted(counters.syscalls.items())),
        "unimplemented_called": dict(counters.unimplemented),
        "imports_stubbed": stubbed,
        "verbs": dict(counters.verbs),
        "sql_statements": counters.statements,
        "sql_statements_per_verb": dict(per_verb_statements),
        "bytes_to_guest": counters.bytes_to_guest,
        "bytes_from_guest": counters.bytes_from_guest,
        "compile_seconds": round(compile_s, 4),
        "run_seconds": round(run_s, 4),
        "trace": counters.trace[:80],
    }


async def main() -> None:
    storage = InMemoryStorage()
    fs = VirtualFileSystem(storage=storage)
    await fs.write(path="/data/hello.txt", content="hello from vfs\nsecond line\n", parents=True)
    await fs.write(path="/data/other.md", content="# other\n")
    report = await run_scenario(fs, storage, WASM, ["catfile", "/data/hello.txt"])
    after = await fs.read(path="/data/hello.txt.out")
    report["written_back"] = {o.path: (o.content, o.version) for o in after.observations}
    report["wasm_bytes"] = WASM.stat().st_size
    (HERE / "run1.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    await fs.close()


if __name__ == "__main__":
    asyncio.run(main())
