"""Experiment: wasi-python 0.1.0 over vfs through the public APIs only.

The guest sees vfs as its whole filesystem (a Mount at "/") and reaches the
verb table through the tool protocol (``from host import tools``). Both are
closed over one ``vfs.Session`` carrying Alice's ``Authority``. No wasi-python
``Grant`` (host folder) is used anywhere.
"""

from __future__ import annotations

import asyncio
import json
import sys

from wasi_python import Errno, Mount, Stat, run_async
from wasi_python.tools import tool

from vfs import Authority, Principal, VirtualFileSystem
from vfs.results import ErrorKind, Result
from vfs.storage.backends import InMemoryStorage

# Spec 169b §b7's table, in wasi-python's Errno names.
WASI_ERRNO: dict[ErrorKind, Errno] = {
    ErrorKind.not_found: Errno.ENOENT,
    ErrorKind.exists: Errno.EEXIST,
    ErrorKind.wrong_kind: Errno.ENOTDIR,
    ErrorKind.not_empty: Errno.ENOTEMPTY,
    ErrorKind.unauthenticated: Errno.EACCES,
    ErrorKind.permission_denied: Errno.EACCES,
    ErrorKind.read_only: Errno.EROFS,
    ErrorKind.unsupported: Errno.ENOTSUP,
    ErrorKind.unrecognized: Errno.ENOSYS,
    ErrorKind.invalid: Errno.EINVAL,
    ErrorKind.unindexable_pattern: Errno.EINVAL,
    ErrorKind.unaddressable: Errno.ENAMETOOLONG,
    ErrorKind.cross_mount: Errno.EXDEV,
    ErrorKind.busy: Errno.EBUSY,
    ErrorKind.conflict: Errno.ESTALE,
    ErrorKind.budget_exhausted: Errno.EIO,
    ErrorKind.truncated: Errno.EIO,
    ErrorKind.authority_budget: Errno.EIO,
    ErrorKind.unavailable: Errno.EIO,
    ErrorKind.backend_unavailable: Errno.EIO,
    ErrorKind.schema_mismatch: Errno.EIO,
    ErrorKind.timeout: Errno.ETIMEDOUT,
    ErrorKind.cancelled: Errno.ECANCELED,
    ErrorKind.internal: Errno.EIO,
}
assert set(WASI_ERRNO) == set(ErrorKind), set(ErrorKind) - set(WASI_ERRNO)

VERBS: list[str] = []  # every vfs verb the guest issued, in order


def _hidden(path: str) -> bool:
    return any(seg == ".vfs" for seg in path.split("/"))


def _errno(result: Result) -> Errno:
    for err in result.errors:
        if isinstance(err.kind, ErrorKind):
            return WASI_ERRNO[err.kind]
    return Errno.EIO


class VfsProvider:
    """A wasi-python WritableFileProvider over a vfs Session (sync, posts to the loop)."""

    def __init__(self, session, loop: asyncio.AbstractEventLoop) -> None:
        self.session = session
        self.loop = loop

    def _call(self, verb: str, coro) -> Result:
        VERBS.append(verb)
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result()

    # read half
    def stat(self, path: str):
        if _hidden(path):
            return Errno.ENOENT
        r = self._call("stat", self.session.stat(path))
        if not r.success:
            return _errno(r)
        obs = r.first()
        mtime = int(obs.updated_at.timestamp() * 1e9) if obs.updated_at else 0
        return Stat("dir" if obs.kind == "directory" else "file", obs.size_bytes or 0, mtime)

    def list(self, path: str):
        if _hidden(path):
            return Errno.ENOENT
        r = self._call("ls", self.session.ls(path))
        if not r.success:
            return _errno(r)
        return [
            (str(o.path).rsplit("/", 1)[-1], "dir" if o.kind == "directory" else "file")
            for o in r.observations
            if not _hidden(str(o.path))
        ]

    def read(self, path: str):
        if _hidden(path):
            return Errno.ENOENT
        r = self._call("read", self.session.read(path, columns=frozenset({"content", "data", "kind", "size_bytes"})))
        if not r.success:
            err = r.errors[0]
            if err.kind == ErrorKind.wrong_kind and str(err.path) == path and (err.data or {}).get("kind") == "directory":
                return Errno.EISDIR
            return _errno(r)
        obs = r.first()
        if obs.data is not None:
            return obs.data
        return (obs.content or "").encode()

    # write half
    def write(self, path: str, data: bytes):
        if _hidden(path):
            return Errno.ENOENT
        text = None
        if b"\0" not in data:
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                text = None
        coro = self.session.write(path=path, content=text) if text is not None else self.session.write(path=path, data=data)
        r = self._call("write", coro)
        return None if r.success else _errno(r)

    def mkdir(self, path: str):
        r = self._call("mkdir", self.session.mkdir(path))
        return None if r.success else _errno(r)

    def remove(self, path: str):
        s = self.stat(path)
        if isinstance(s, Errno):
            return s
        if s.kind == "dir":
            return Errno.EISDIR
        r = self._call("delete", self.session.delete(path, cascade=False))
        return None if r.success else _errno(r)

    def rmdir(self, path: str):
        s = self.stat(path)
        if isinstance(s, Errno):
            return s
        if s.kind != "dir":
            return Errno.ENOTDIR
        r = self._call("delete", self.session.delete(path, cascade=False))
        return None if r.success else _errno(r)

    def rename(self, src: str, dst: str):
        r = self._call("move", self.session.move(src, dst))
        return None if r.success else _errno(r)


def vfs_tools(session):
    """The verb table as tools, each closed over the caller's session (ADR 082 pin 2's shape)."""

    @tool(read_only=True)
    async def ls(path: str = "/") -> dict:
        """List a directory in vfs.

        Args:
            path: The directory to list.
        """
        VERBS.append("tool:ls")
        return (await session.ls(path)).to_payload()

    @tool(read_only=True)
    async def grep(pattern: str, path: str = "/") -> dict:
        """Search file contents in vfs.

        Args:
            pattern: The regular expression to search for.
            path: The directory to search under.
        """
        VERBS.append("tool:grep")
        return (await session.grep(pattern, paths=(path,))).to_payload()

    @tool()
    async def write(path: str, content: str) -> dict:
        """Write a text file in vfs.

        Args:
            path: Where to write.
            content: The text body.
        """
        VERBS.append("tool:write")
        return (await session.write(path=path, content=content)).to_payload()

    return [ls, grep, write]


GUEST = r"""
import os, sys, json
from host import tools

print("listdir /:", sorted(os.listdir("/")))
print("read:", open("/docs/hello.md").read().strip())
print("stat size:", os.stat("/docs/hello.md").st_size)

import pandas as pd
df = pd.read_csv("/data/in.csv")
df["z"] = df.x * df.y
df.to_csv("/out/result.csv", index=False)
print("csv back:", pd.read_csv("/out/result.csv").z.tolist())

os.mkdir("/out/sub")
open("/out/sub/a.txt", "w").write("a")
os.rename("/out/sub/a.txt", "/out/sub/b.txt")
print("after rename:", os.listdir("/out/sub"))
os.remove("/out/sub/b.txt")
os.rmdir("/out/sub")
print("sub gone:", "sub" in os.listdir("/out"))

for path in ("/ro/locked.md", "/.vfs/trash", "/docs"):
    try:
        f = open(path, "w") if path.startswith("/ro") else open(path)
        print(path, "-> opened?!")
    except OSError as e:
        print(path, "->", type(e).__name__, e.errno)

r = tools.ls("/docs")
print("tool ls:", r["success"], [o["path"] for o in r["observations"]])
r = tools.grep("MFA", "/docs")
print("tool grep:", r["success"], len(r["observations"]))
r = tools.write("/ro/nope.md", "x")
print("tool write to read-only mount:", r["success"], [e["kind"] for e in r["errors"]])
r = tools.write("/out/from_tool.md", "written through the tool door")
print("tool write ok:", r["success"])
"""


async def main() -> None:
    fs = VirtualFileSystem(storage=InMemoryStorage())
    await fs.add_mount(InMemoryStorage(), "/ro", permissions="read")
    admin = Authority.system()
    await fs.write(path="/docs/hello.md", content="hello from a vfs row\n", parents=True, authority=admin)
    await fs.write(path="/docs/policy.md", content="All logins require MFA.\n", parents=True, authority=admin)
    await fs.write(path="/data/in.csv", content="x,y\n1,2\n3,4\n", parents=True, authority=admin)
    await fs.mkdir("/out", authority=admin)

    alice = Authority.of(Principal("alice"))
    loop = asyncio.get_running_loop()
    async with fs.session(alice) as session:
        done = await run_async(
            ["-c", GUEST],
            mounts=[Mount(VfsProvider(session, loop), "/", writable=True)],
            tools=vfs_tools(session),
            deadline_s=120,
            max_file_calls=10_000,
        )
    print("--- guest stdout ---")
    print(done.stdout.decode())
    print("--- guest stderr ---")
    print(done.stderr.decode()[-2000:])
    print("exit:", done.exit_code, "trapped:", done.trapped)
    print("provider calls:", dict(done.files.calls))
    print("faults:", done.files.faults)
    print("refused:", [(w.method, w.paths, w.errno.name, w.at, w.cause) for w in done.files.refused])
    print("tool outcomes:", [(o.tool, o.outcome) for o in done.tools.outcomes])
    print("vfs verbs issued:", len(VERBS))
    from collections import Counter

    print("by verb:", dict(Counter(VERBS)))
    after = await fs.read("/out/result.csv", authority=admin)
    print("row written as text?", after.first().content is not None, repr(after.first().content[:30]))
    await fs.close()


if __name__ == "__main__":
    asyncio.run(main())
