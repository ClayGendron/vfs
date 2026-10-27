"""A WASI preview1 shim whose filesystem is a vfs VirtualFileSystem.

Research code (E1 spike). Every ``wasi_snapshot_preview1`` import a wasm32-wasip1
binary can name is registered on a wasmtime ``Linker`` with ``define_func``; the
file-shaped ones are served by vfs verbs with whole-file staging:

    path_open   -> one fs.read (or an empty buffer under O_CREAT)
    fd_read / fd_write / fd_seek / fd_tell / fd_pread / fd_pwrite -> the buffer
    fd_close    -> one fs.write if the buffer is dirty
    fd_readdir  -> fs.ls;  path_filestat_get -> fs.stat;  path_unlink_file -> fs.delete
    path_rename -> fs.move; path_create_directory -> fs.mkdir; path_remove_directory -> fs.delete

The guest runs on a worker thread (wasmtime callbacks are synchronous); each vfs
verb is awaited on the host's asyncio loop through ``run_coroutine_threadsafe``.
"""

from __future__ import annotations

import asyncio
import os
import struct
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from wasmtime import Caller, FuncType, Linker, ValType

# ---------------------------------------------------------------------------
# preview1 constants (WASI snapshot 1, witx)
# ---------------------------------------------------------------------------

SUCCESS, ACCES, BADF, EXIST, INVAL, IO, ISDIR, NOENT = 0, 2, 8, 20, 28, 29, 31, 44
NOSYS, NOTDIR, NOTEMPTY, NOTSUP, PERM, SPIPE, NOTCAPABLE, ROFS, FAULT = 52, 54, 55, 58, 63, 70, 76, 69, 21

FT_UNKNOWN, FT_CHARACTER_DEVICE, FT_DIRECTORY, FT_REGULAR_FILE = 0, 2, 3, 4
O_CREAT, O_DIRECTORY, O_EXCL, O_TRUNC = 1, 2, 4, 8
FDFLAG_APPEND = 1
WHENCE_SET, WHENCE_CUR, WHENCE_END = 0, 1, 2
RIGHTS_ALL = (1 << 30) - 1
RIGHT_FD_SEEK, RIGHT_FD_TELL = 1 << 2, 1 << 5
RIGHTS_STDIO = RIGHTS_ALL & ~(RIGHT_FD_SEEK | RIGHT_FD_TELL)
PREOPEN_FD = 3

# vfs error kind -> preview1 errno. The ErrorKind docstrings already name the errno.
KIND_ERRNO = {
    "vfs.not_found": NOENT,
    "vfs.exists": EXIST,
    "vfs.wrong_kind": NOTDIR,
    "vfs.not_empty": NOTEMPTY,
    "vfs.permission_denied": ACCES,
    "vfs.unauthenticated": ACCES,
    "vfs.read_only": ROFS,
    "vfs.unsupported": NOTSUP,
    "vfs.invalid": INVAL,
    "vfs.cross_mount": NOTCAPABLE,
}

I32, I64 = ValType.i32(), ValType.i64()

# Every preview1 function: name -> (params, results). 46 names.
SIGNATURES: dict[str, tuple[str, int]] = {
    "args_get": ("ii", 1), "args_sizes_get": ("ii", 1),
    "environ_get": ("ii", 1), "environ_sizes_get": ("ii", 1),
    "clock_res_get": ("ii", 1), "clock_time_get": ("iIi", 1),
    "fd_advise": ("iIIi", 1), "fd_allocate": ("iII", 1), "fd_close": ("i", 1), "fd_datasync": ("i", 1),
    "fd_fdstat_get": ("ii", 1), "fd_fdstat_set_flags": ("ii", 1), "fd_fdstat_set_rights": ("iII", 1),
    "fd_filestat_get": ("ii", 1), "fd_filestat_set_size": ("iI", 1), "fd_filestat_set_times": ("iIIi", 1),
    "fd_pread": ("iiiIi", 1), "fd_prestat_get": ("ii", 1), "fd_prestat_dir_name": ("iii", 1),
    "fd_pwrite": ("iiiIi", 1), "fd_read": ("iiii", 1), "fd_readdir": ("iiiIi", 1), "fd_renumber": ("ii", 1),
    "fd_seek": ("iIii", 1), "fd_sync": ("i", 1), "fd_tell": ("ii", 1), "fd_write": ("iiii", 1),
    "path_create_directory": ("iii", 1), "path_filestat_get": ("iiiii", 1),
    "path_filestat_set_times": ("iiiiIIi", 1), "path_link": ("iiiiiii", 1),
    "path_open": ("iiiiiIIii", 1), "path_readlink": ("iiiiii", 1), "path_remove_directory": ("iii", 1),
    "path_rename": ("iiiiii", 1), "path_symlink": ("iiiii", 1), "path_unlink_file": ("iii", 1),
    "poll_oneoff": ("iiii", 1), "proc_exit": ("i", 0), "proc_raise": ("i", 1), "sched_yield": ("", 1),
    "random_get": ("ii", 1), "sock_accept": ("iii", 1), "sock_recv": ("iiiiii", 1),
    "sock_send": ("iiiii", 1), "sock_shutdown": ("ii", 1),
}


class GuestExit(Exception):
    """Raised by proc_exit; carries the guest's exit code."""

    def __init__(self, code: int) -> None:
        super().__init__(f"guest exit {code}")
        self.code = code


# ---------------------------------------------------------------------------
# Fd table entries: the entry row is the inode; the open handle is a buffer + cursor
# ---------------------------------------------------------------------------


@dataclass
class FileFd:
    path: str
    buf: bytearray
    pos: int = 0
    dirty: bool = False
    append: bool = False
    was_text: bool = False  # the vfs row had a text body (content) rather than bytes


@dataclass
class DirFd:
    path: str


@dataclass
class StreamFd:
    buf: bytearray
    readable: bool
    pos: int = 0


AnyFd = FileFd | DirFd | StreamFd


@dataclass
class Counts:
    verbs: dict[str, int] = field(default_factory=dict)
    per_path: dict[str, list[str]] = field(default_factory=dict)
    calls: dict[str, int] = field(default_factory=dict)  # preview1 function -> call count

    def verb(self, name: str, path: str) -> None:
        self.verbs[name] = self.verbs.get(name, 0) + 1
        self.per_path.setdefault(path, []).append(name)


# ---------------------------------------------------------------------------
# The shim
# ---------------------------------------------------------------------------


class VfsWasi:
    """One instance per guest run: argv, env, stdio buffers, an fd table, a vfs."""

    def __init__(
        self,
        fs: Any,
        loop: asyncio.AbstractEventLoop,
        *,
        argv: list[str],
        env: dict[str, str] | None = None,
        stdin: bytes = b"",
        authority: Any = None,
        stdout_is_tty: bool = False,
        text_writeback: bool = True,
    ) -> None:
        self.fs, self.loop, self.authority = fs, loop, authority
        self.argv = [a.encode() + b"\0" for a in argv]
        self.env = [f"{k}={v}".encode() + b"\0" for k, v in (env or {}).items()]
        self.stdout_is_tty = stdout_is_tty
        self.text_writeback = text_writeback
        self.counts = Counts()
        self.fds: dict[int, AnyFd] = {
            0: StreamFd(bytearray(stdin), readable=True),
            1: StreamFd(bytearray(), readable=False),
            2: StreamFd(bytearray(), readable=False),
            PREOPEN_FD: DirFd("/"),
        }
        self.next_fd = PREOPEN_FD + 1
        self.stubbed: dict[str, int] = {}

    @property
    def stdout(self) -> bytes:
        return bytes(self.fds[1].buf)  # type: ignore[union-attr]

    @property
    def stderr(self) -> bytes:
        return bytes(self.fds[2].buf)  # type: ignore[union-attr]

    # ---- registration -----------------------------------------------------

    def define(self, linker: Linker) -> None:
        for name, (params, nres) in SIGNATURES.items():
            impl = getattr(self, name, None)
            ty = FuncType([I64 if c == "I" else I32 for c in params], [I32] * nres)
            if impl is None:
                impl = self._stub(name, len(params))
            linker.define_func("wasi_snapshot_preview1", name, ty, self._counted(name, impl), access_caller=True)

    def _counted(self, name: str, impl: Callable[..., Any]) -> Callable[..., Any]:
        def wrapped(caller: Caller, *args: Any) -> Any:
            self.counts.calls[name] = self.counts.calls.get(name, 0) + 1
            return impl(caller, *args)

        return wrapped

    def _stub(self, name: str, nparams: int) -> Callable[..., int]:
        def stub(caller: Caller, *args: Any) -> int:
            self.stubbed[name] = self.stubbed.get(name, 0) + 1
            return NOTSUP

        return stub

    # ---- async bridge and vfs helpers --------------------------------------

    def _await(self, coro: Any) -> Any:
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result()

    def _errno(self, result: Any) -> int:
        failures = result.failures
        if not failures:
            return SUCCESS
        return KIND_ERRNO.get(str(failures[0].kind), IO)

    def _resolve(self, dirfd: int, rel: str) -> tuple[int, str]:
        base = self.fds.get(dirfd)
        if not isinstance(base, DirFd):
            return (NOTDIR if base is not None else BADF), ""
        if rel.startswith("/"):
            return NOTCAPABLE, ""  # libc never sends absolute paths; a guest bypassing libc might
        parts: list[str] = [p for p in base.path.split("/") if p]
        for seg in rel.split("/"):
            if seg in ("", "."):
                continue
            if seg == "..":
                if not parts:
                    return NOTCAPABLE, ""
                parts.pop()
            else:
                parts.append(seg)
        return SUCCESS, "/" + "/".join(parts)

    def _stat(self, path: str) -> tuple[int, Any]:
        self.counts.verb("stat", path)
        res = self._await(self.fs.stat(path, authority=self.authority))
        return self._errno(res), res.first()

    # ---- memory helpers ----------------------------------------------------

    @staticmethod
    def _mem(caller: Caller) -> Any:
        return caller.get("memory")

    def _read(self, caller: Caller, ptr: int, n: int) -> bytes:
        return bytes(self._mem(caller).read(caller, ptr, ptr + n))

    def _write(self, caller: Caller, ptr: int, data: bytes) -> None:
        self._mem(caller).write(caller, data, ptr)

    def _u32(self, caller: Caller, ptr: int, value: int) -> None:
        self._write(caller, ptr, struct.pack("<I", value))

    def _u64(self, caller: Caller, ptr: int, value: int) -> None:
        self._write(caller, ptr, struct.pack("<Q", value))

    def _path(self, caller: Caller, ptr: int, n: int) -> str:
        return self._read(caller, ptr, n).decode("utf-8", "surrogateescape")

    def _iovs(self, caller: Caller, ptr: int, n: int) -> list[tuple[int, int]]:
        raw = self._read(caller, ptr, 8 * n)
        return [struct.unpack_from("<II", raw, 8 * i) for i in range(n)]

    def _alloc_fd(self, entry: AnyFd) -> int:
        fd = self.next_fd
        self.next_fd += 1
        self.fds[fd] = entry
        return fd

    # ---- args / env / clock / random ----------------------------------------

    def _sizes(self, caller: Caller, items: list[bytes], count_ptr: int, size_ptr: int) -> int:
        self._u32(caller, count_ptr, len(items))
        self._u32(caller, size_ptr, sum(len(i) for i in items))
        return SUCCESS

    def _fill(self, caller: Caller, items: list[bytes], ptrs: int, buf: int) -> int:
        off = buf
        for i, item in enumerate(items):
            self._u32(caller, ptrs + 4 * i, off)
            self._write(caller, off, item)
            off += len(item)
        return SUCCESS

    def args_sizes_get(self, caller: Caller, count_ptr: int, size_ptr: int) -> int:
        return self._sizes(caller, self.argv, count_ptr, size_ptr)

    def args_get(self, caller: Caller, argv_ptr: int, buf_ptr: int) -> int:
        return self._fill(caller, self.argv, argv_ptr, buf_ptr)

    def environ_sizes_get(self, caller: Caller, count_ptr: int, size_ptr: int) -> int:
        return self._sizes(caller, self.env, count_ptr, size_ptr)

    def environ_get(self, caller: Caller, env_ptr: int, buf_ptr: int) -> int:
        return self._fill(caller, self.env, env_ptr, buf_ptr)

    def clock_res_get(self, caller: Caller, clock_id: int, out: int) -> int:
        self._u64(caller, out, 1_000)
        return SUCCESS

    def clock_time_get(self, caller: Caller, clock_id: int, precision: int, out: int) -> int:
        self._u64(caller, out, time.time_ns() if clock_id == 0 else time.monotonic_ns())
        return SUCCESS

    def random_get(self, caller: Caller, buf: int, n: int) -> int:
        self._write(caller, buf, os.urandom(n))
        return SUCCESS

    def sched_yield(self, caller: Caller) -> int:
        return SUCCESS

    def proc_exit(self, caller: Caller, code: int) -> None:
        raise GuestExit(code)

    # ---- the preopen handshake --------------------------------------------

    def fd_prestat_get(self, caller: Caller, fd: int, out: int) -> int:
        if fd != PREOPEN_FD:
            return BADF  # the only errno that ends libc's scan cleanly
        self._write(caller, out, struct.pack("<BxxxI", 0, len(b"/")))
        return SUCCESS

    def fd_prestat_dir_name(self, caller: Caller, fd: int, path_ptr: int, path_len: int) -> int:
        if fd != PREOPEN_FD:
            return BADF
        self._write(caller, path_ptr, b"/"[:path_len])
        return SUCCESS

    # ---- fd-level calls ---------------------------------------------------

    def fd_fdstat_get(self, caller: Caller, fd: int, out: int) -> int:
        entry = self.fds.get(fd)
        if entry is None:
            return BADF
        if isinstance(entry, StreamFd):
            ft = FT_CHARACTER_DEVICE if (fd != 0 and self.stdout_is_tty) else FT_UNKNOWN
            flags, rights = 0, RIGHTS_STDIO
        elif isinstance(entry, DirFd):
            ft, flags, rights = FT_DIRECTORY, 0, RIGHTS_ALL
        else:
            ft, flags, rights = FT_REGULAR_FILE, (FDFLAG_APPEND if entry.append else 0), RIGHTS_ALL
        self._write(caller, out, struct.pack("<BxHxxxxQQ", ft, flags, rights, rights))
        return SUCCESS

    def fd_fdstat_set_flags(self, caller: Caller, fd: int, flags: int) -> int:
        entry = self.fds.get(fd)
        if entry is None:
            return BADF
        if isinstance(entry, FileFd):
            entry.append = bool(flags & FDFLAG_APPEND)
        return SUCCESS

    def fd_fdstat_set_rights(self, caller: Caller, fd: int, base: int, inheriting: int) -> int:
        return SUCCESS if fd in self.fds else BADF

    def _filestat(self, caller: Caller, out: int, ft: int, size: int, mtime_ns: int = 0) -> None:
        self._write(caller, out, struct.pack("<QQBxxxxxxxQQQQQ", 0, 0, ft, 1, size, mtime_ns, mtime_ns, mtime_ns))

    def fd_filestat_get(self, caller: Caller, fd: int, out: int) -> int:
        entry = self.fds.get(fd)
        if entry is None:
            return BADF
        if isinstance(entry, FileFd):
            self._filestat(caller, out, FT_REGULAR_FILE, len(entry.buf))
        elif isinstance(entry, DirFd):
            self._filestat(caller, out, FT_DIRECTORY, 0)
        else:
            self._filestat(caller, out, FT_CHARACTER_DEVICE if self.stdout_is_tty else FT_UNKNOWN, 0)
        return SUCCESS

    def fd_filestat_set_size(self, caller: Caller, fd: int, size: int) -> int:
        entry = self.fds.get(fd)
        if not isinstance(entry, FileFd):
            return BADF
        del entry.buf[size:]
        entry.buf.extend(b"\0" * (size - len(entry.buf)))
        entry.dirty = True
        return SUCCESS

    def fd_filestat_set_times(self, caller: Caller, fd: int, atim: int, mtim: int, flags: int) -> int:
        return SUCCESS if fd in self.fds else BADF

    def fd_advise(self, caller: Caller, fd: int, offset: int, length: int, advice: int) -> int:
        return SUCCESS if fd in self.fds else BADF

    def fd_sync(self, caller: Caller, fd: int) -> int:
        return self._flush(fd)

    def fd_datasync(self, caller: Caller, fd: int) -> int:
        return self._flush(fd)

    def _read_into(self, caller: Caller, src: bytes | bytearray, pos: int, iovs: list[tuple[int, int]]) -> int:
        total = 0
        for base, length in iovs:
            chunk = bytes(src[pos + total : pos + total + length])
            if not chunk:
                break
            self._write(caller, base, chunk)
            total += len(chunk)
        return total

    def fd_read(self, caller: Caller, fd: int, iovs_ptr: int, iovs_len: int, nread_ptr: int) -> int:
        entry = self.fds.get(fd)
        if entry is None:
            return BADF
        if isinstance(entry, DirFd):
            return ISDIR
        if isinstance(entry, StreamFd) and not entry.readable:
            return BADF
        n = self._read_into(caller, entry.buf, entry.pos, self._iovs(caller, iovs_ptr, iovs_len))
        entry.pos += n
        self._u32(caller, nread_ptr, n)  # EOF is n == 0 and SUCCESS
        return SUCCESS

    def fd_pread(self, caller: Caller, fd: int, iovs_ptr: int, iovs_len: int, offset: int, nread_ptr: int) -> int:
        entry = self.fds.get(fd)
        if not isinstance(entry, FileFd):
            return BADF if entry is None else SPIPE
        n = self._read_into(caller, entry.buf, offset, self._iovs(caller, iovs_ptr, iovs_len))
        self._u32(caller, nread_ptr, n)
        return SUCCESS

    def _gather(self, caller: Caller, iovs: list[tuple[int, int]]) -> bytes:
        return b"".join(self._read(caller, base, length) for base, length in iovs)

    def fd_write(self, caller: Caller, fd: int, iovs_ptr: int, iovs_len: int, nwritten_ptr: int) -> int:
        entry = self.fds.get(fd)
        if entry is None:
            return BADF
        data = self._gather(caller, self._iovs(caller, iovs_ptr, iovs_len))
        if isinstance(entry, StreamFd):
            if entry.readable:
                return BADF
            entry.buf += data
        elif isinstance(entry, DirFd):
            return ISDIR
        else:
            if entry.append:
                entry.pos = len(entry.buf)
            end = entry.pos + len(data)
            if end > len(entry.buf):
                entry.buf.extend(b"\0" * (end - len(entry.buf)))
            entry.buf[entry.pos : end] = data
            entry.pos = end
            entry.dirty = True
        self._u32(caller, nwritten_ptr, len(data))
        return SUCCESS

    def fd_pwrite(self, caller: Caller, fd: int, iovs_ptr: int, iovs_len: int, offset: int, nwritten_ptr: int) -> int:
        entry = self.fds.get(fd)
        if not isinstance(entry, FileFd):
            return BADF if entry is None else SPIPE
        data = self._gather(caller, self._iovs(caller, iovs_ptr, iovs_len))
        end = offset + len(data)
        if end > len(entry.buf):
            entry.buf.extend(b"\0" * (end - len(entry.buf)))
        entry.buf[offset:end] = data
        entry.dirty = True
        self._u32(caller, nwritten_ptr, len(data))
        return SUCCESS

    def fd_seek(self, caller: Caller, fd: int, offset: int, whence: int, out: int) -> int:
        entry = self.fds.get(fd)
        if entry is None:
            return BADF
        if not isinstance(entry, FileFd):
            return SPIPE
        base = {WHENCE_SET: 0, WHENCE_CUR: entry.pos, WHENCE_END: len(entry.buf)}.get(whence)
        if base is None:
            return INVAL
        new = base + offset  # offset is signed i64
        if new < 0:
            return INVAL
        entry.pos = new
        self._write(caller, out, struct.pack("<q", new))
        return SUCCESS

    def fd_tell(self, caller: Caller, fd: int, out: int) -> int:
        entry = self.fds.get(fd)
        if entry is None:
            return BADF
        if not isinstance(entry, FileFd):
            return SPIPE
        self._u64(caller, out, entry.pos)
        return SUCCESS

    def fd_renumber(self, caller: Caller, fd: int, to: int) -> int:
        if fd not in self.fds:
            return BADF
        self._flush(to)
        self.fds[to] = self.fds.pop(fd)
        return SUCCESS

    def _flush(self, fd: int) -> int:
        entry = self.fds.get(fd)
        if entry is None:
            return BADF
        if isinstance(entry, FileFd) and entry.dirty:
            self.counts.verb("write", entry.path)
            body = bytes(entry.buf)
            kwargs: dict[str, Any] = {"path": entry.path, "parents": False, "authority": self.authority}
            if self.text_writeback:
                try:
                    kwargs["content"] = body.decode("utf-8")
                except UnicodeDecodeError:
                    kwargs["data"] = body
            else:
                kwargs["data"] = body
            res = self._await(self.fs.write(**kwargs))
            entry.dirty = False
            return self._errno(res)
        return SUCCESS

    def fd_close(self, caller: Caller, fd: int) -> int:
        if fd not in self.fds:
            return BADF
        errno = self._flush(fd)
        if fd > 2:
            del self.fds[fd]
        return errno

    def fd_readdir(self, caller: Caller, fd: int, buf: int, buf_len: int, cookie: int, bufused_ptr: int) -> int:
        entry = self.fds.get(fd)
        if entry is None:
            return BADF
        if not isinstance(entry, DirFd):
            return NOTDIR
        self.counts.verb("ls", entry.path)
        res = self._await(self.fs.ls(entry.path, authority=self.authority))
        errno = self._errno(res)
        if errno:
            return errno
        rows = sorted(res, key=lambda r: str(r.path))
        out = bytearray()
        for i in range(cookie, len(rows)):
            row = rows[i]
            name = str(row.path).rsplit("/", 1)[-1].encode()
            ft = FT_DIRECTORY if row.kind == "directory" else FT_REGULAR_FILE
            dirent = struct.pack("<QQIBxxx", i + 1, i + 1, len(name), ft) + name
            room = buf_len - len(out)
            out += dirent[:room]
            if len(dirent) > room:
                break  # truncated last entry: bufused == buf_len tells libc to grow and retry
        self._write(caller, buf, bytes(out))
        self._u32(caller, bufused_ptr, len(out))
        return SUCCESS

    # ---- path-level calls -------------------------------------------------

    def path_open(
        self, caller: Caller, dirfd: int, dirflags: int, path_ptr: int, path_len: int,
        oflags: int, rights_base: int, rights_inheriting: int, fdflags: int, out: int,
    ) -> int:
        errno, full = self._resolve(dirfd, self._path(caller, path_ptr, path_len))
        if errno:
            return errno
        errno, row = self._stat(full)
        if errno not in (SUCCESS, NOENT):
            return errno
        if row is not None and row.kind == "directory":
            self._u32(caller, out, self._alloc_fd(DirFd(full)))
            return SUCCESS
        if oflags & O_DIRECTORY:
            return NOTDIR if row is not None else NOENT
        if row is None:
            if not (oflags & O_CREAT):
                return NOENT
            handle = FileFd(full, bytearray(), dirty=True)
        else:
            if (oflags & O_CREAT) and (oflags & O_EXCL):
                return EXIST
            if oflags & O_TRUNC:
                handle = FileFd(full, bytearray(), dirty=True)
            else:
                self.counts.verb("read", full)
                res = self._await(self.fs.read(full, columns=frozenset({"data", "content"}), authority=self.authority))
                errno = self._errno(res)
                if errno:
                    return errno
                body = res.first()
                raw = body.data if body.data is not None else (body.content or "").encode("utf-8")
                handle = FileFd(full, bytearray(raw), was_text=body.data is None)
        handle.append = bool(fdflags & FDFLAG_APPEND)
        self._u32(caller, out, self._alloc_fd(handle))
        return SUCCESS

    def path_filestat_get(self, caller: Caller, dirfd: int, flags: int, path_ptr: int, path_len: int, out: int) -> int:
        errno, full = self._resolve(dirfd, self._path(caller, path_ptr, path_len))
        if errno:
            return errno
        errno, row = self._stat(full)
        if errno:
            return errno
        ft = FT_DIRECTORY if row.kind == "directory" else FT_REGULAR_FILE
        mtime = int(row.updated_at.timestamp() * 1e9) if row.updated_at else 0
        self._filestat(caller, out, ft, row.size_bytes or 0, mtime)
        return SUCCESS

    def path_create_directory(self, caller: Caller, dirfd: int, path_ptr: int, path_len: int) -> int:
        errno, full = self._resolve(dirfd, self._path(caller, path_ptr, path_len))
        if errno:
            return errno
        self.counts.verb("mkdir", full)
        return self._errno(self._await(self.fs.mkdir(full, authority=self.authority)))

    def path_remove_directory(self, caller: Caller, dirfd: int, path_ptr: int, path_len: int) -> int:
        errno, full = self._resolve(dirfd, self._path(caller, path_ptr, path_len))
        if errno:
            return errno
        self.counts.verb("delete", full)
        return self._errno(self._await(self.fs.delete(full, cascade=False, authority=self.authority)))

    def path_unlink_file(self, caller: Caller, dirfd: int, path_ptr: int, path_len: int) -> int:
        errno, full = self._resolve(dirfd, self._path(caller, path_ptr, path_len))
        if errno:
            return errno
        errno, row = self._stat(full)
        if errno:
            return errno
        if row.kind == "directory":
            return ISDIR
        self.counts.verb("delete", full)
        return self._errno(self._await(self.fs.delete(full, authority=self.authority)))

    def path_rename(
        self, caller: Caller, dirfd: int, path_ptr: int, path_len: int, new_dirfd: int, new_ptr: int, new_len: int,
    ) -> int:
        errno, src = self._resolve(dirfd, self._path(caller, path_ptr, path_len))
        if errno:
            return errno
        errno, dest = self._resolve(new_dirfd, self._path(caller, new_ptr, new_len))
        if errno:
            return errno
        self.counts.verb("move", src)
        return self._errno(self._await(self.fs.move(src, dest, authority=self.authority)))
