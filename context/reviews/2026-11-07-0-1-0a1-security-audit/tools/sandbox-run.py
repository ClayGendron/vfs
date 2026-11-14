#!/usr/bin/python3 -I
"""Trusted parent-side launcher: sandbox-run.py <scratch-dir> <cmd...>

Enforces: no external network, writes only under <scratch-dir> (sandbox-exec profile);
an empty allowlisted environment; RLIMIT_CPU 60 s, RLIMIT_FSIZE 64 MiB, RLIMIT_NPROC 256;
a 2 GiB resident-memory cap on the whole process group (50 ms RSS watchdog, SIGKILL);
a 120 s wall-clock cap (SIGKILL). The target and toolchain are read-only to the child.
"""
import os, resource, signal, subprocess, sys, time
MEM_KIB, WALL_S, CPU_S, FSIZE, NPROC = 2 * 1024 * 1024, 120, 60, 64 * 1024 * 1024, 256
scratch = os.path.realpath(sys.argv[1]); cmd = sys.argv[2:]
for d in ("home", "tmp", "pycache"):
    os.makedirs(os.path.join(scratch, d), exist_ok=True)
env = {"HOME": f"{scratch}/home", "TMPDIR": f"{scratch}/tmp", "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8",
       "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPYCACHEPREFIX": f"{scratch}/pycache"}
def limits():
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_S, CPU_S))
    resource.setrlimit(resource.RLIMIT_FSIZE, (FSIZE, FSIZE))
    resource.setrlimit(resource.RLIMIT_NPROC, (NPROC, NPROC))
sb = os.path.join(os.path.dirname(os.path.realpath(__file__)), "sandbox.sb")
p = subprocess.Popen(["/usr/bin/sandbox-exec", "-D", f"SCRATCH={scratch}", "-f", sb, *cmd],
                     env=env, cwd=scratch, start_new_session=True, preexec_fn=limits)
start, reason = time.monotonic(), None
while p.poll() is None:
    if time.monotonic() - start > WALL_S:
        reason = f"wall-clock {WALL_S}s"
    else:
        out = subprocess.run(["/bin/ps", "-A", "-o", "pgid=,rss="], capture_output=True, text=True).stdout
        rss = sum(int(r) for g, r in (l.split() for l in out.splitlines() if l.strip()) if int(g) == p.pid)
        if rss > MEM_KIB:
            reason = f"memory {rss} KiB > {MEM_KIB} KiB"
    if reason:
        os.killpg(p.pid, signal.SIGKILL); p.wait()
        print(f"[sandbox-run] killed: {reason}", file=sys.stderr); sys.exit(137)
    time.sleep(0.05)
sys.exit(p.returncode)
