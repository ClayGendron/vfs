"""Run one line of bash through the vfs host and report what came back."""
import asyncio, resource, sys, time
from vfs import AsyncVirtualFileSystem
from vfs.authority import Authority, Principal

line = sys.argv[1]
if sys.argv[1] == "-f":
    line = open(sys.argv[2]).read()
fs = AsyncVirtualFileSystem()
t = time.monotonic()
r = asyncio.run(fs.cli(line, authority=Authority.of(Principal("a"))))
dt = time.monotonic() - t
rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024
print(f"exit={r.exit_status} stdout_len={len(r.stdout)} stderr_len={len(r.stderr)} secs={dt:.2f} maxrss_mb={rss}")
print("stdout_head=", repr(r.stdout[:120]))
print("stderr_head=", repr(r.stderr[:300]))
print("errors=", [(e.kind, str(e.model_dump())[:200]) for e in r.errors][:5], "n_errors=", len(r.errors))
