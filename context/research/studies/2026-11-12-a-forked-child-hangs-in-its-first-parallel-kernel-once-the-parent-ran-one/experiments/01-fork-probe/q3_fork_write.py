"""At HEAD: a parent writes one large body (a measure hop), forks, and the child writes one too, then greps.

Usage: uv run python q3_fork_write.py
The child arms SIGALRM before each step so a hang is an exit code, never a wait.
"""

from __future__ import annotations

import asyncio
import os
import signal
import threading

from vfs import Entry, InMemoryStorage
from vfs.storage.backends.database import writes

BODY = "needle line\n" * (writes.MEASURE_OFFLOAD_BYTES // 12 + 10)


async def write_once(grep: bool) -> str:
    storage = InMemoryStorage()
    result = await storage.write(entries=[Entry(path="/big.txt", content=BODY)])
    out = f"write ok={result.success}"
    if grep:
        found = await storage.grep(pattern="needle", output_mode="files")
        out += f" grep rows={len(found.observations)}"
    await storage.close()
    return out


def main() -> None:
    print("parent:", asyncio.run(write_once(False)), "| threads:", sorted(t.name for t in threading.enumerate()), flush=True)
    for label, grep in (("child write only", False), ("child write then grep", True)):
        pid = os.fork()
        if pid == 0:
            signal.alarm(8)
            os.write(1, f"{label}: {asyncio.run(write_once(grep))}\n".encode())
            os._exit(0)
        _pid, status = os.waitpid(pid, 0)
        if os.WIFSIGNALED(status):
            print(f"{label}: killed by signal {os.WTERMSIG(status)}: it hung", flush=True)
        else:
            print(f"{label}: exit code {os.WEXITSTATUS(status)}", flush=True)


main()
