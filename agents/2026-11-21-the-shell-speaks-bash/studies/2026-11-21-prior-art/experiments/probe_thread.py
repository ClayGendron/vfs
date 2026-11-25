"""Run one line through the vfs host on a thread whose stack is argv[2] KiB."""
import asyncio, sys, threading
from vfs import AsyncVirtualFileSystem
from vfs.authority import Authority, Principal

def work() -> None:
    r = asyncio.run(AsyncVirtualFileSystem().cli(sys.argv[1], authority=Authority.of(Principal("a"))))
    print(f"exit={r.exit_status} stdout={r.stdout[:40]!r} errors={[e.kind.value for e in r.errors]}", flush=True)

threading.stack_size(int(sys.argv[2]) * 1024)
t = threading.Thread(target=work)
t.start(); t.join()
