"""Experiment 2: the permission ladder reaches the guest as errno; rename-replace; the
verb count of the bare pandas CSV job (spec 172's criterion 3 says at most 15 verbs)."""

from __future__ import annotations

import asyncio
from collections import Counter

from exp_vfs_mount import VERBS, VfsProvider, vfs_tools
from wasi_python import Mount, run_async

from vfs import Authority, Principal, VirtualFileSystem
from vfs.storage.backends import InMemoryStorage

LADDER_GUEST = r"""
import os
for path in ("/secret/x.md", "/secret"):
    try:
        if path == "/secret":
            print(path, "-> listdir", os.listdir(path))
        else:
            print(path, "->", open(path).read().strip())
    except OSError as e:
        print(path, "->", type(e).__name__, e.errno)
"""

RENAME_GUEST = r"""
import os
open("/out/a.txt", "w").write("a")
open("/out/b.txt", "w").write("b")
try:
    os.replace("/out/a.txt", "/out/b.txt")
    print("replace ok; b now:", open("/out/b.txt").read())
except OSError as e:
    print("replace ->", type(e).__name__, e.errno)
"""

PANDAS_GUEST = r"""
import pandas as pd
df = pd.read_csv("/data/in.csv")
df.groupby("x").y.sum().to_csv("/out/agg.csv")
print(pd.read_csv("/out/agg.csv").y.tolist())
"""


async def run_as(fs, authority, guest, loop):
    VERBS.clear()
    async with fs.session(authority) as session:
        done = await run_async(
            ["-c", guest],
            mounts=[Mount(VfsProvider(session, loop), "/", writable=True)],
            tools=vfs_tools(session),
            deadline_s=120,
        )
    return done, list(VERBS)


async def main() -> None:
    fs = VirtualFileSystem(storage=InMemoryStorage())
    admin = Authority.system()
    await fs.write(path="/secret/x.md", content="top secret\n", parents=True, authority=admin)
    await fs.write(path="/data/in.csv", content="x,y\n1,2\n1,3\n2,4\n", parents=True, authority=admin)
    await fs.mkdir("/out", authority=admin)
    r = await fs.posture("/secret", "none", authority=admin)
    assert r.success, r.errors
    r = await fs.grant("/secret", "bob", "read", authority=admin)
    assert r.success, r.errors
    loop = asyncio.get_running_loop()

    for who in ("alice", "bob"):
        done, verbs = await run_as(fs, Authority.of(Principal(who)), LADDER_GUEST, loop)
        print(f"--- ladder as {who} ---")
        print(done.stdout.decode().rstrip())
        print("exit:", done.exit_code, "faults:", done.files.faults)

    done, verbs = await run_as(fs, Authority.of(Principal("alice")), RENAME_GUEST, loop)
    print("--- rename-replace as alice ---")
    print(done.stdout.decode().rstrip())
    print("refused:", [(w.method, w.paths, w.errno.name, w.at) for w in done.files.refused])

    done, verbs = await run_as(fs, Authority.of(Principal("alice")), PANDAS_GUEST, loop)
    print("--- bare pandas csv job as alice ---")
    print(done.stdout.decode().rstrip(), "exit:", done.exit_code)
    print("provider calls:", dict(done.files.calls))
    print("vfs verbs:", len(verbs), dict(Counter(verbs)))
    print("verb sequence:", verbs)
    await fs.close()


if __name__ == "__main__":
    asyncio.run(main())
