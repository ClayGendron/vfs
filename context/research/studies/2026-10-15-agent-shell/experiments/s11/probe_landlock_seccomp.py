"""S11 probe C1: can an unprivileged Linux process self-sandbox with Landlock + seccomp-bpf?

Runs as a non-root user with every capability dropped (docker --cap-drop=ALL
--security-opt=no-new-privileges) under Docker's default seccomp profile. Pure ctypes; no
package to install. Reports: Landlock ABI version, whether a ruleset restricts the process,
whether a C-level fopen() outside the allowed trees is refused, and whether a seccomp filter
denies socket/connect/execve/ptrace while numpy still imports.

usage: python -I probe_landlock_seccomp.py <allowed-ro-dir> [<allowed-rw-dir>]
"""

from __future__ import annotations

import ctypes
import ctypes.util
import errno
import json
import os
import platform
import socket
import subprocess
import sys
import time

libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
libc.syscall.restype = ctypes.c_long
MACHINE = platform.machine()
ARCH = {"aarch64": 0xC00000B7, "x86_64": 0xC000003E}[MACHINE]
NR = {
    "aarch64": {"landlock_create_ruleset": 444, "landlock_add_rule": 445, "landlock_restrict_self": 446,
                "seccomp": 277, "socket": 198, "connect": 203, "execve": 221, "execveat": 281, "ptrace": 117},
    "x86_64": {"landlock_create_ruleset": 444, "landlock_add_rule": 445, "landlock_restrict_self": 446,
               "seccomp": 317, "socket": 41, "connect": 42, "execve": 59, "execveat": 322, "ptrace": 101},
}[MACHINE]
PR_SET_NO_NEW_PRIVS = 38
LANDLOCK_CREATE_RULESET_VERSION = 1 << 0
LANDLOCK_RULE_PATH_BENEATH = 1
# Filesystem access rights, ABI 1..3 (ABI 4 adds net, 5 ioctl_dev, 6 scoping).
FS = {
    "EXECUTE": 1 << 0, "WRITE_FILE": 1 << 1, "READ_FILE": 1 << 2, "READ_DIR": 1 << 3, "REMOVE_DIR": 1 << 4,
    "REMOVE_FILE": 1 << 5, "MAKE_CHAR": 1 << 6, "MAKE_DIR": 1 << 7, "MAKE_REG": 1 << 8, "MAKE_SOCK": 1 << 9,
    "MAKE_FIFO": 1 << 10, "MAKE_BLOCK": 1 << 11, "MAKE_SYM": 1 << 12, "REFER": 1 << 13, "TRUNCATE": 1 << 14,
    "IOCTL_DEV": 1 << 15,
}
report: dict = {"machine": MACHINE, "kernel": platform.release(), "uid": os.getuid(), "python": sys.version.split()[0]}


class RulesetAttr(ctypes.Structure):
    _fields_ = [("handled_access_fs", ctypes.c_uint64), ("handled_access_net", ctypes.c_uint64), ("scoped", ctypes.c_uint64)]


class PathBeneath(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int32)]


def landlock_abi() -> int:
    r = libc.syscall(NR["landlock_create_ruleset"], None, 0, LANDLOCK_CREATE_RULESET_VERSION)
    return r if r >= 0 else -ctypes.get_errno()


def landlock_restrict(ro_dirs: list[str], rw_dirs: list[str], abi: int) -> str:
    fs_mask = sum(v for v in FS.values())
    if abi < 2:
        fs_mask &= ~FS["REFER"]
    if abi < 3:
        fs_mask &= ~FS["TRUNCATE"]
    if abi < 5:
        fs_mask &= ~FS["IOCTL_DEV"]
    attr = RulesetAttr(fs_mask, 0, 0)
    size = 8 if abi < 4 else (16 if abi < 6 else 24)
    fd = libc.syscall(NR["landlock_create_ruleset"], ctypes.byref(attr), size, 0)
    if fd < 0:
        return f"create_ruleset failed errno {ctypes.get_errno()}"
    ro = FS["EXECUTE"] | FS["READ_FILE"] | FS["READ_DIR"]
    rw = fs_mask
    for dirs, access in ((ro_dirs, ro), (rw_dirs, rw)):
        for d in dirs:
            dfd = os.open(d, os.O_PATH | os.O_CLOEXEC)
            rule = PathBeneath(access, dfd)
            r = libc.syscall(NR["landlock_add_rule"], fd, LANDLOCK_RULE_PATH_BENEATH, ctypes.byref(rule), 0)
            os.close(dfd)
            if r < 0:
                return f"add_rule({d}) failed errno {ctypes.get_errno()}"
    if libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
        return f"prctl(NO_NEW_PRIVS) failed errno {ctypes.get_errno()}"
    if libc.syscall(NR["landlock_restrict_self"], fd, 0) != 0:
        return f"restrict_self failed errno {ctypes.get_errno()}"
    os.close(fd)
    return "ok"


# --- seccomp-bpf: deny a syscall set with EPERM, allow everything else ------------------
class SockFilter(ctypes.Structure):
    _fields_ = [("code", ctypes.c_uint16), ("jt", ctypes.c_uint8), ("jf", ctypes.c_uint8), ("k", ctypes.c_uint32)]


class SockFprog(ctypes.Structure):
    _fields_ = [("len", ctypes.c_uint16), ("filter", ctypes.POINTER(SockFilter))]


BPF_LD, BPF_W, BPF_ABS, BPF_JMP, BPF_JEQ, BPF_K, BPF_RET = 0x00, 0x00, 0x20, 0x05, 0x10, 0x00, 0x06
SECCOMP_RET_ALLOW, SECCOMP_RET_ERRNO, SECCOMP_RET_KILL = 0x7FFF0000, 0x00050000, 0x00000000
SECCOMP_SET_MODE_FILTER = 1


def seccomp_deny(names: list[str]) -> str:
    denied = [NR[n] for n in names]
    prog = []
    prog.append(SockFilter(BPF_LD | BPF_W | BPF_ABS, 0, 0, 4))                    # arch
    prog.append(SockFilter(BPF_JMP | BPF_JEQ | BPF_K, 1, 0, ARCH))                 # arch ok -> skip kill
    prog.append(SockFilter(BPF_RET | BPF_K, 0, 0, SECCOMP_RET_KILL))
    prog.append(SockFilter(BPF_LD | BPF_W | BPF_ABS, 0, 0, 0))                    # nr
    for i, nr in enumerate(denied):
        remaining = len(denied) - i - 1
        prog.append(SockFilter(BPF_JMP | BPF_JEQ | BPF_K, remaining + 1, 0, nr))  # match -> jump to deny
    prog.append(SockFilter(BPF_RET | BPF_K, 0, 0, SECCOMP_RET_ALLOW))
    prog.append(SockFilter(BPF_RET | BPF_K, 0, 0, SECCOMP_RET_ERRNO | errno.EPERM))
    arr = (SockFilter * len(prog))(*prog)
    fprog = SockFprog(len(prog), arr)
    if libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
        return f"prctl(NO_NEW_PRIVS) failed errno {ctypes.get_errno()}"
    r = libc.syscall(NR["seccomp"], SECCOMP_SET_MODE_FILTER, 0, ctypes.byref(fprog))
    if r != 0:
        return f"seccomp() failed errno {ctypes.get_errno()}"
    return "ok"


def try_open(path: str, mode: str = "r") -> str:
    try:
        with open(path, mode) as f:
            f.read(1) if "r" in mode else f.write("x")
        return "allowed"
    except OSError as e:
        return f"denied errno {e.errno} ({errno.errorcode.get(e.errno)})"


def c_fopen(path: str) -> str:
    libc.fopen.restype = ctypes.c_void_p
    p = libc.fopen(path.encode(), b"r")
    if p:
        libc.fclose(ctypes.c_void_p(p))
        return "allowed"
    return f"denied errno {ctypes.get_errno()} ({errno.errorcode.get(ctypes.get_errno())})"


def main() -> None:
    ro_dirs = [sys.argv[1]] if len(sys.argv) > 1 else ["/usr"]
    rw_dirs = [sys.argv[2]] if len(sys.argv) > 2 else []
    report["before"] = {"open_etc_passwd": try_open("/etc/passwd"), "c_fopen_etc_hosts": c_fopen("/etc/hosts")}
    abi = landlock_abi()
    report["landlock_abi"] = abi
    if abi > 0:
        t = time.perf_counter()
        report["landlock_restrict"] = landlock_restrict(ro_dirs, rw_dirs, abi)
        report["landlock_restrict_ms"] = round((time.perf_counter() - t) * 1000, 2)
    else:
        report["landlock_restrict"] = f"unavailable ({errno.errorcode.get(-abi, -abi)})"
    t = time.perf_counter()
    report["seccomp"] = seccomp_deny(["socket", "connect", "execve", "execveat", "ptrace"])
    report["seccomp_ms"] = round((time.perf_counter() - t) * 1000, 2)
    after: dict = {
        "open_etc_passwd": try_open("/etc/passwd"),
        "c_fopen_etc_hosts": c_fopen("/etc/hosts"),
        "open_allowed_ro": try_open(os.path.join(ro_dirs[0], os.listdir(ro_dirs[0])[0])) if os.path.isdir(ro_dirs[0]) else "n/a",
    }
    try:
        os.listdir("/")
        after["listdir_root"] = "allowed"
    except OSError as e:
        after["listdir_root"] = f"denied errno {e.errno}"
    try:
        os.listdir("/etc")
        after["listdir_etc"] = "allowed"
    except OSError as e:
        after["listdir_etc"] = f"denied errno {e.errno}"
    if rw_dirs:
        after["write_rw_dir"] = try_open(os.path.join(rw_dirs[0], "probe.txt"), "w")
    after["write_tmp"] = try_open("/tmp/probe_s11.txt", "w")
    try:
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).close()
        after["socket"] = "allowed"
    except OSError as e:
        after["socket"] = f"denied errno {e.errno} ({errno.errorcode.get(e.errno)})"
    try:
        subprocess.run(["/bin/true"], check=False)
        after["execve"] = "allowed"
    except OSError as e:
        after["execve"] = f"denied errno {e.errno} ({errno.errorcode.get(e.errno)})"
    try:
        import threading
        th = threading.Thread(target=lambda: None); th.start(); th.join()
        after["thread"] = "allowed"
    except Exception as e:  # noqa: BLE001
        after["thread"] = f"failed {type(e).__name__}"
    t = time.perf_counter()
    try:
        import numpy, pandas  # noqa: F401
        after["import_numpy_pandas"] = f"ok numpy {numpy.__version__} pandas {pandas.__version__} in {round((time.perf_counter()-t)*1000)} ms"
    except Exception as e:  # noqa: BLE001
        after["import_numpy_pandas"] = f"FAIL {type(e).__name__}: {str(e)[:200]}"
    t = time.perf_counter()
    try:
        import matplotlib
        matplotlib.use("agg")
        import matplotlib.pyplot as plt
        import io
        fig, ax = plt.subplots(); ax.plot([1, 2, 3]); b = io.BytesIO(); fig.savefig(b, format="png")
        after["matplotlib_png"] = f"ok {len(b.getvalue())} bytes in {round((time.perf_counter()-t)*1000)} ms"
    except Exception as e:  # noqa: BLE001
        after["matplotlib_png"] = f"FAIL {type(e).__name__}: {str(e)[:300]}"
    report["after"] = after
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
