"""At HEAD: does a forked child that builds its own storage answer a grep, after the parent ran one?

Usage: uv run python q3_fork_head.py [warm|cold] [kernel|storage]
The child arms SIGALRM so a hang is an exit code, never a wait.
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys

from vfs import InMemoryStorage
from vfs.pattern_matching import compile_verifier

WARM = (sys.argv[1] if len(sys.argv) > 1 else "warm") == "warm"
MODE = sys.argv[2] if len(sys.argv) > 2 else "storage"


async def grep_once() -> int:
    storage = InMemoryStorage()
    from_entry = __import__("vfs").Entry
    await storage.write(entries=[from_entry(path=f"/f{i}.txt", content=f"needle {i}\n") for i in range(50)])
    result = await storage.grep(pattern="needle")
    count = len(result.observations)
    await storage.close()
    return count


def kernel_once() -> int:
    verifier = compile_verifier("needle", fixed_strings=False, word_regexp=False, case_mode="sensitive")
    counts, completed = verifier.count_lines([f"needle {i}\n" * 50 for i in range(2000)], cap=None, invert=False, budget=None)
    return sum(counts) if completed else -1


def once() -> int:
    return kernel_once() if MODE == "kernel" else asyncio.run(grep_once())


def main() -> None:
    if WARM:
        print("parent:", once(), flush=True)
    pid = os.fork()
    if pid == 0:
        signal.alarm(8)
        try:
            got = once()
        except BaseException as exc:  # noqa: BLE001
            os.write(1, f"child raised {type(exc).__name__}: {exc}\n".encode())
            os._exit(3)
        os.write(1, f"child: {got}\n".encode())
        os._exit(0)
    _pid, status = os.waitpid(pid, 0)
    if os.WIFSIGNALED(status):
        print(f"child killed by signal {os.WTERMSIG(status)} (SIGALRM is {int(signal.SIGALRM)}): it hung")
    else:
        print("child exit code", os.WEXITSTATUS(status))


main()
