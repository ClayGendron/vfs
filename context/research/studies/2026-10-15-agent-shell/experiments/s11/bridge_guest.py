"""S11 candidate C, guest side: native CPython that sandboxes ITSELF without privileges, and
reaches vfs only through a Python-level bridge over one inherited file descriptor.

Order of operations (the order is the security argument):
  1. connect the bridge (an inherited socket fd, or a TCP connect made BEFORE the sandbox);
  2. import the heavy packages the job will need, so their shared objects are mapped;
  3. apply the self-sandbox: Linux = Landlock (filesystem) + seccomp-bpf (socket, connect,
     execve, execveat, ptrace -> EPERM); macOS = Seatbelt `sandbox_init` with a deny-default
     SBPL profile; both need no root, no capabilities, no namespaces;
  4. install the bridge: `open`/`io.open`, `os.stat/listdir/mkdir/remove/rename/...` for any
     path under VFS_ROOT (/vfs) become bridge calls; everything else keeps its native meaning
     (and the sandbox decides what that is allowed to touch);
  5. read the script from vfs and run it.

usage: python -I bridge_guest.py (--fd N | --connect HOST:PORT) [--sandbox landlock|seatbelt|none]
                                 [--ro DIR]... [--rw DIR]... [--preimport mod,mod] SCRIPT_PATH_IN_VFS
"""

from __future__ import annotations

import builtins
import ctypes
import ctypes.util
import errno
import importlib
import io
import json
import os
import platform
import socket
import stat as statmod
import struct
import sys
import time

VFS_ROOT = "/vfs"

# ---------------------------------------------------------------------------
# The wire: 4-byte length + JSON header, then `body_len` raw bytes
# ---------------------------------------------------------------------------


class Bridge:
    def __init__(self, sock: socket.socket) -> None:
        self.sock = sock
        self.calls = 0
        self.wait_s = 0.0

    def _recv_exact(self, n: int) -> bytes:
        buf = bytearray()
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("bridge closed")
            buf += chunk
        return bytes(buf)

    def call(self, op: str, path: str, body: bytes = b"", **extra) -> tuple[dict, bytes]:
        self.calls += 1
        t = time.perf_counter()
        header = json.dumps({"op": op, "path": path, "body_len": len(body), **extra}).encode()
        self.sock.sendall(struct.pack(">I", len(header)) + header + body)
        n = struct.unpack(">I", self._recv_exact(4))[0]
        reply = json.loads(self._recv_exact(n))
        rbody = self._recv_exact(reply.get("body_len", 0)) if reply.get("body_len") else b""
        self.wait_s += time.perf_counter() - t
        if not reply.get("ok"):
            raise OSError(int(reply.get("errno", errno.EIO)), f"vfs: {reply.get('kind')}: {path}")
        return reply, rbody


BRIDGE: Bridge | None = None

# ---------------------------------------------------------------------------
# The Python-level filesystem bridge (the just-bash pattern): whole-file staging
# ---------------------------------------------------------------------------

_real = {
    "open": builtins.open, "io_open": io.open, "stat": os.stat, "lstat": os.lstat, "listdir": os.listdir,
    "mkdir": os.mkdir, "remove": os.remove, "unlink": os.unlink, "rmdir": os.rmdir, "rename": os.rename,
    "replace": os.replace, "scandir": os.scandir, "getcwd": os.getcwd,
}


def _vfs_path(p) -> str | None:
    """The vfs path for a guest path under the mount, else None (native path)."""
    s = os.fspath(p)
    if isinstance(s, bytes):
        s = s.decode()
    if not s.startswith("/"):
        s = os.path.join(_cwd, s)
    s = os.path.normpath(s)
    if s == VFS_ROOT:
        return "/"
    if s.startswith(VFS_ROOT + "/"):
        return s[len(VFS_ROOT):]
    return None


_cwd = VFS_ROOT


class _StagedFile(io.BytesIO):
    """A whole row staged in memory; a dirty buffer is written back as one `write` on close."""

    def __init__(self, vpath: str, data: bytes, writable: bool, name: str) -> None:
        super().__init__(data)
        self._vpath, self._writable, self._dirty, self.name = vpath, writable, False, name

    def write(self, b):  # type: ignore[override]
        if not self._writable:
            raise io.UnsupportedOperation("not writable")
        self._dirty = True
        return super().write(b)

    def truncate(self, size=None):  # type: ignore[override]
        self._dirty = True
        return super().truncate(size)

    def writable(self) -> bool:
        return self._writable

    def close(self) -> None:
        if not self.closed and self._dirty:
            assert BRIDGE is not None
            BRIDGE.call("write", self._vpath, self.getvalue())
            self._dirty = False
        super().close()


def _open(file, mode="r", buffering=-1, encoding=None, errors=None, newline=None, closefd=True, opener=None):
    vpath = _vfs_path(file) if isinstance(file, (str, bytes, os.PathLike)) else None
    if vpath is None:
        return _real["open"](file, mode, buffering, encoding, errors, newline, closefd, opener)
    assert BRIDGE is not None
    m = mode.replace("b", "").replace("t", "")
    writable = any(c in m for c in "wa+x")
    if "w" in m:
        data = b""
    elif "x" in m:
        try:
            BRIDGE.call("stat", vpath)
        except OSError:
            data = b""
        else:
            raise FileExistsError(errno.EEXIST, "exists", vpath)
    else:
        _, data = BRIDGE.call("read", vpath)
    raw = _StagedFile(vpath, data, writable, os.fspath(file))
    if "a" in m:
        raw.seek(0, io.SEEK_END)
        raw._dirty = True  # a created-and-never-written append file still lands as a row
    if "w" in m:
        raw._dirty = True
    if "b" in mode:
        return raw
    return io.TextIOWrapper(raw, encoding=encoding or "utf-8", errors=errors, newline=newline)


def _stat_result(reply: dict) -> os.stat_result:
    is_dir = reply.get("kind") == "directory"
    mode = (statmod.S_IFDIR | 0o755) if is_dir else (statmod.S_IFREG | 0o644)
    mtime = float(reply.get("mtime") or 0)
    size = 4096 if is_dir else int(reply.get("size") or 0)
    return os.stat_result((mode, 0, 0, 1, 0, 0, size, mtime, mtime, mtime))


def _stat(path, *a, **k):
    vpath = _vfs_path(path) if isinstance(path, (str, bytes, os.PathLike)) else None
    if vpath is None:
        return _real["stat"](path, *a, **k)
    if vpath == "/":
        return os.stat_result((statmod.S_IFDIR | 0o755, 0, 0, 1, 0, 0, 4096, 0, 0, 0))
    assert BRIDGE is not None
    try:
        reply, _ = BRIDGE.call("stat", vpath)
    except OSError as e:
        raise FileNotFoundError(e.errno, "vfs", os.fspath(path)) if e.errno == errno.ENOENT else e
    return _stat_result(reply)


def _listdir(path="."):
    vpath = _vfs_path(path)
    if vpath is None:
        return _real["listdir"](path)
    assert BRIDGE is not None
    reply, _ = BRIDGE.call("readdir", vpath)
    return list(reply["entries"])


def _mkdir(path, mode=0o777, *, dir_fd=None):
    vpath = _vfs_path(path)
    if vpath is None:
        return _real["mkdir"](path, mode, dir_fd=dir_fd)
    assert BRIDGE is not None
    BRIDGE.call("mkdir", vpath)


def _remove(path, *, dir_fd=None):
    vpath = _vfs_path(path)
    if vpath is None:
        return _real["remove"](path, dir_fd=dir_fd)
    assert BRIDGE is not None
    BRIDGE.call("unlink", vpath)


def _rename(src, dst, *, src_dir_fd=None, dst_dir_fd=None):
    vs, vd = _vfs_path(src), _vfs_path(dst)
    if vs is None and vd is None:
        return _real["rename"](src, dst, src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd)
    if vs is None or vd is None:
        raise OSError(errno.EXDEV, "cross-device link")
    assert BRIDGE is not None
    BRIDGE.call("rename", vs, to=vd)


def install_bridge() -> None:
    builtins.open = _open  # type: ignore[assignment]
    io.open = _open  # type: ignore[assignment]
    os.stat = _stat  # type: ignore[assignment]
    os.lstat = _stat  # type: ignore[assignment]
    os.listdir = _listdir  # type: ignore[assignment]
    os.mkdir = _mkdir  # type: ignore[assignment]
    os.remove = _remove  # type: ignore[assignment]
    os.unlink = _remove  # type: ignore[assignment]
    os.rmdir = _remove  # type: ignore[assignment]
    os.rename = _rename  # type: ignore[assignment]
    os.replace = _rename  # type: ignore[assignment]
    os.getcwd = lambda: _cwd  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Self-sandbox: Linux Landlock + seccomp-bpf
# ---------------------------------------------------------------------------

PR_SET_NO_NEW_PRIVS = 38


def _libc():
    return ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)


def sandbox_linux(ro_dirs: list[str], rw_dirs: list[str]) -> dict:
    libc = _libc()
    libc.syscall.restype = ctypes.c_long
    machine = platform.machine()
    arch = {"aarch64": 0xC00000B7, "x86_64": 0xC000003E}[machine]
    nr = {
        "aarch64": {"create": 444, "add": 445, "restrict": 446, "seccomp": 277,
                    "deny": [198, 203, 221, 281, 117]},  # socket connect execve execveat ptrace
        "x86_64": {"create": 444, "add": 445, "restrict": 446, "seccomp": 317,
                   "deny": [41, 42, 59, 322, 101]},
    }[machine]
    out: dict = {}
    abi = libc.syscall(nr["create"], None, 0, 1)
    out["landlock_abi"] = abi if abi >= 0 else f"unavailable errno {ctypes.get_errno()}"
    if abi > 0:
        fs_all = (1 << 16) - 1
        if abi < 2:
            fs_all &= ~(1 << 13)
        if abi < 3:
            fs_all &= ~(1 << 14)
        if abi < 5:
            fs_all &= ~(1 << 15)

        class Attr(ctypes.Structure):
            _fields_ = [("fs", ctypes.c_uint64), ("net", ctypes.c_uint64), ("scoped", ctypes.c_uint64)]

        class Beneath(ctypes.Structure):
            _pack_ = 1
            _fields_ = [("allowed", ctypes.c_uint64), ("fd", ctypes.c_int32)]

        attr = Attr(fs_all, 0, 0)
        rfd = libc.syscall(nr["create"], ctypes.byref(attr), 8 if abi < 4 else (16 if abi < 6 else 24), 0)
        ro = (1 << 0) | (1 << 2) | (1 << 3)  # execute, read_file, read_dir
        for dirs, access in ((ro_dirs, ro), (rw_dirs, fs_all)):
            for d in dirs:
                if not os.path.isdir(d):
                    continue
                dfd = os.open(d, os.O_PATH | os.O_CLOEXEC)
                rule = Beneath(access, dfd)
                libc.syscall(nr["add"], rfd, 1, ctypes.byref(rule), 0)
                os.close(dfd)
        libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0)
        out["landlock"] = "ok" if libc.syscall(nr["restrict"], rfd, 0) == 0 else f"failed errno {ctypes.get_errno()}"
        os.close(rfd)

    class Filt(ctypes.Structure):
        _fields_ = [("code", ctypes.c_uint16), ("jt", ctypes.c_uint8), ("jf", ctypes.c_uint8), ("k", ctypes.c_uint32)]

    class Prog(ctypes.Structure):
        _fields_ = [("len", ctypes.c_uint16), ("filter", ctypes.POINTER(Filt))]

    LD_W_ABS, JEQ_K, RET_K = 0x20, 0x15, 0x06
    ALLOW, KILL, ERRNO = 0x7FFF0000, 0x00000000, 0x00050000
    prog = [Filt(LD_W_ABS, 0, 0, 4), Filt(JEQ_K, 1, 0, arch), Filt(RET_K, 0, 0, KILL), Filt(LD_W_ABS, 0, 0, 0)]
    denied = nr["deny"]
    for i, n in enumerate(denied):
        prog.append(Filt(JEQ_K, len(denied) - i, 0, n))
    prog.append(Filt(RET_K, 0, 0, ALLOW))
    prog.append(Filt(RET_K, 0, 0, ERRNO | errno.EPERM))
    arr = (Filt * len(prog))(*prog)
    fprog = Prog(len(prog), arr)
    libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0)
    r = libc.syscall(nr["seccomp"], 1, 0, ctypes.byref(fprog))
    out["seccomp"] = "ok" if r == 0 else f"failed errno {ctypes.get_errno()}"
    return out


# ---------------------------------------------------------------------------
# Self-sandbox: macOS Seatbelt (sandbox_init), deny by default
# ---------------------------------------------------------------------------


def sandbox_macos(ro_dirs: list[str], rw_dirs: list[str]) -> dict:
    def sub(ds):
        return " ".join(f'(subpath "{os.path.realpath(d)}")' for d in ds if os.path.isdir(d))

    profile = f"""(version 1)
(deny default)
(allow process-exec (literal "{os.path.realpath(sys.executable)}"))
(allow file-read-metadata)
(allow file-read* (subpath "/usr/lib") (subpath "/usr/share") (subpath "/System/Library") (subpath "/Library/Preferences")
                  (subpath "/private/var/db/timezone") (subpath "/dev/urandom") (literal "/dev/null") (literal "/dev/random")
                  {sub(ro_dirs)})
(allow file-write* (literal "/dev/null") {sub(rw_dirs)})
(allow file-ioctl (literal "/dev/null") (literal "/dev/tty"))
(allow sysctl-read)
(allow mach-lookup (global-name "com.apple.system.logger") (global-name "com.apple.system.notification_center"))
(allow ipc-posix-shm-read-data)
(allow signal (target self))
(deny network*)
(deny process-fork)
"""
    lib = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
    lib.sandbox_init.argtypes = [ctypes.c_char_p, ctypes.c_uint64, ctypes.POINTER(ctypes.c_char_p)]
    lib.sandbox_init.restype = ctypes.c_int
    err = ctypes.c_char_p()
    r = lib.sandbox_init(profile.encode(), 0, ctypes.byref(err))
    out = {"seatbelt": "ok" if r == 0 else f"failed: {err.value.decode() if err.value else r}", "profile_lines": profile.count("\n")}
    return out


# ---------------------------------------------------------------------------
# Probes the host asks for after the sandbox is up
# ---------------------------------------------------------------------------


def probes() -> dict:
    out: dict = {}
    libc = _libc()
    libc.fopen.restype = ctypes.c_void_p
    for p in ("/etc/hosts", os.path.expanduser("~/.ssh/config"), os.path.expanduser("~/.zshrc")):
        ptr = libc.fopen(p.encode(), b"r")
        if ptr:
            libc.fclose(ctypes.c_void_p(ptr))
            out[f"c_fopen {p}"] = "ALLOWED"
        else:
            out[f"c_fopen {p}"] = f"denied errno {ctypes.get_errno()}"
    try:
        _real["open"]("/etc/passwd").read(1)
        out["py_open /etc/passwd"] = "ALLOWED"
    except OSError as e:
        out["py_open /etc/passwd"] = f"denied errno {e.errno}"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.settimeout(1)
            s.connect(("127.0.0.1", 9))
            out["socket+connect"] = "ALLOWED (connect returned)"
        except OSError as e:
            out["socket+connect"] = f"socket ok, connect errno {e.errno} ({errno.errorcode.get(e.errno, '?')})"
        finally:
            s.close()
    except OSError as e:
        out["socket+connect"] = f"socket denied errno {e.errno} ({errno.errorcode.get(e.errno, '?')})"
    try:
        import subprocess
        subprocess.run(["/bin/echo", "x"], check=False, capture_output=True)
        out["execve"] = "ALLOWED"
    except OSError as e:
        out["execve"] = f"denied errno {e.errno} ({errno.errorcode.get(e.errno, '?')})"
    try:
        _real["open"]("/tmp/s11_probe_escape.txt", "w").write("x")
        out["write /tmp"] = "ALLOWED"
    except OSError as e:
        out["write /tmp"] = f"denied errno {e.errno}"
    try:
        import threading
        th = threading.Thread(target=lambda: None); th.start(); th.join()
        out["thread"] = "ok"
    except Exception as e:  # noqa: BLE001
        out["thread"] = f"failed {type(e).__name__}"
    return out


def main() -> None:
    args = sys.argv[1:]
    fd = None
    connect = None
    sandbox = "none"
    ro, rw, pre = [], [], []
    rest = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--fd":
            fd = int(args[i + 1]); i += 2
        elif a == "--connect":
            connect = args[i + 1]; i += 2
        elif a == "--sandbox":
            sandbox = args[i + 1]; i += 2
        elif a == "--ro":
            ro.append(args[i + 1]); i += 2
        elif a == "--rw":
            rw.append(args[i + 1]); i += 2
        elif a == "--preimport":
            pre = args[i + 1].split(","); i += 2
        else:
            rest.append(a); i += 1
    script = rest[0]
    t0 = time.perf_counter()
    if fd is not None:
        sock = socket.socket(fileno=fd)
    else:
        host, port = connect.rsplit(":", 1)
        sock = socket.create_connection((host, int(port)))
    global BRIDGE
    BRIDGE = Bridge(sock)
    timing = {"connect_ms": round((time.perf_counter() - t0) * 1000)}
    t = time.perf_counter()
    for m in pre:
        importlib.import_module(m)
    timing["preimport_ms"] = round((time.perf_counter() - t) * 1000)
    t = time.perf_counter()
    sb = {}
    if sandbox == "landlock":
        sb = sandbox_linux(ro or [sys.prefix, "/usr", "/lib"], rw)
    elif sandbox == "seatbelt":
        sb = sandbox_macos(ro or [sys.prefix], rw)
    timing["sandbox_ms"] = round((time.perf_counter() - t) * 1000, 2)
    sb["probes"] = probes()
    install_bridge()
    os.environ["VFS_ROOT"] = VFS_ROOT
    os.environ.setdefault("MPLCONFIGDIR", rw[0] if rw else "/tmp")
    t = time.perf_counter()
    exit_code, error = 0, None
    try:
        with open(script) as f:
            src = f.read()
        g = {"__name__": "__main__", "__file__": script}
        exec(compile(src, script, "exec"), g)
    except SystemExit as e:
        exit_code = int(e.code or 0)
    except BaseException as e:  # noqa: BLE001
        exit_code, error = 1, f"{type(e).__name__}: {e}"
    timing["run_ms"] = round((time.perf_counter() - t) * 1000)
    sys.stdout.flush()
    try:
        import resource
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        rss_mb = rss / 1024 / (1024 if sys.platform == "darwin" else 1)
    except Exception:  # noqa: BLE001
        rss_mb = None
    BRIDGE.call("done", "/", json.dumps({"exit": exit_code, "error": error, "timing": timing, "sandbox": sb,
                                           "bridge_calls": BRIDGE.calls, "bridge_wait_ms": round(BRIDGE.wait_s * 1000),
                                           "rss_mb": rss_mb, "platform": sys.platform, "python": sys.version.split()[0]}).encode())
    os._exit(exit_code)


if __name__ == "__main__":
    main()
