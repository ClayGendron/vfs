"""S7 experiment: a reference ShellSession over the live vfs tree.

A ShellSession holds the state a shell keeps between commands -- cwd,
env, last status, history, mount table view -- and dispatches a scripted
command list by hand (no parser) onto the EXISTING verbs of
``vfs.session.Session``. Two sessions with different authorities share
one tree; the script shows they see different things.

Run from the vfs repo root:
    uv run python context/research/studies/2026-10-15-agent-shell/experiments/s7/shell_session.py
"""

from __future__ import annotations

import asyncio
import posixpath
from dataclasses import dataclass, field

from vfs.authority import Authority, Principal
from vfs.base import VirtualFileSystem
from vfs.results import Result
from vfs.session import Session
from vfs.storage.backends.memory import InMemoryStorage

SYSTEM = Authority.system()
ALICE = Authority.of(Principal("alice"))
BOB = Authority.of(Principal("bob"))


@dataclass
class ShellSession:
    """What vfs's Session does NOT hold today, held here as plain fields."""

    session: Session
    cwd: str = "/"
    env: dict[str, str] = field(default_factory=dict)
    last_status: int = 0
    history: list[tuple[str, int]] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    def resolve(self, arg: str | None) -> str:
        if arg is None:
            return self.cwd
        if arg.startswith("/"):
            return posixpath.normpath(arg)
        return posixpath.normpath(posixpath.join(self.cwd, arg))

    async def run(self, line: str) -> str:
        """Hand-dispatch one command line; returns the text an agent would see."""
        argv = line.split()
        cmd, args = argv[0], argv[1:]
        out, status = await self._dispatch(cmd, args)
        self.last_status = status
        self.history.append((line, status))
        return out

    async def _dispatch(self, cmd: str, args: list[str]) -> tuple[str, int]:
        if cmd == "cd":
            target = self.resolve(args[0] if args else self.env.get("HOME", "/"))
            # cd needs an existence + kind check: stat is the verb.
            result = await self.session.stat(target)
            if not result.success:
                return self._refusal(result), 1
            first = result.first()
            if first is None or first.kind != "directory":
                return f"cd: not a directory: {target}", 1
            self.cwd = target
            return "", 0
        if cmd == "pwd":
            return self.cwd, 0
        if cmd == "export":
            name, _, value = args[0].partition("=")
            self.env[name] = value
            return "", 0
        if cmd == "echo":
            words = [self.env.get(w[1:], "") if w.startswith("$") else w for w in args]
            return " ".join(words), 0
        if cmd == "ls":
            result = await self.session.ls(self.resolve(args[0] if args else None))
            return self._render(result), (0 if result.success else 1)
        if cmd == "cat":
            result = await self.session.read(self.resolve(args[0]))
            return self._render(result), (0 if result.success else 1)
        if cmd == "stat":
            result = await self.session.stat(self.resolve(args[0]))
            return self._render(result), (0 if result.success else 1)
        if cmd == "write":  # write <path> <content...>
            result = await self.session.write(path=self.resolve(args[0]), content=" ".join(args[1:]), parents=True)
            return self._render(result), (0 if result.success else 1)
        if cmd == "mkdir":
            result = await self.session.mkdir(self.resolve(args[0]), parents=True, exist_ok=True)
            return self._render(result), (0 if result.success else 1)
        if cmd == "status":
            return str(self.last_status), 0
        if cmd == "history":
            return "\n".join(f"{i + 1}  [{s}] {line}" for i, (line, s) in enumerate(self.history)), 0
        if cmd == "env":
            return "\n".join(f"{k}={v}" for k, v in sorted(self.env.items())), 0
        self.missing.append(cmd)
        return f"{cmd}: no verb maps to this builtin", 127

    def _render(self, result: Result) -> str:
        if result.success:
            rows = result.observations
            return "\n".join(f"{o.kind:9s} {o.path}" + (f"  :: {o.content!r}" if o.content else "") for o in rows)
        return self._refusal(result)

    def _refusal(self, result: Result) -> str:
        return "; ".join(f"{e.kind}: {e.message}" for e in result.errors)


SCRIPT_A = [
    "cd /a",
    "ls",
    "export X=1",
    "echo $X",
    "write /a/secret.md alice wrote this",
    "ls",
    "cd ..",
    "pwd",
    "status",
    "cd /nowhere",
    "status",
    "history",
    "env",
    "grep foo",  # not mapped in this reference -> missing
]

SCRIPT_B = [
    "pwd",
    "echo $X",  # B's env is its own
    "ls /a",  # B holds `list` at /a: names and kinds only
    "cat /a/secret.md",  # read is refused, not hidden
    "cat /a/open.md",
    "write /a/mine.md bob tries",  # list rung: every mutation refused
    "status",
    "history",
]


async def main() -> None:
    storage = InMemoryStorage()
    fs = VirtualFileSystem(storage=storage)
    # The world: /a with one open file; everyone holds nothing; alice
    # holds read_write on /a; bob holds list on /a and read on /a/open.md.
    assert (await fs.mkdir("/a", authority=SYSTEM)).success
    assert (await fs.write(path="/a/open.md", content="public note", authority=SYSTEM)).success
    assert (await fs.posture("/", "none", authority=SYSTEM)).success
    assert (await fs.grant("/a", "alice", "read_write", authority=SYSTEM)).success
    assert (await fs.grant("/a", "bob", "list", authority=SYSTEM)).success
    assert (await fs.grant("/a/open.md", "bob", "read", authority=SYSTEM)).success

    a = ShellSession(fs.session(ALICE))
    b = ShellSession(fs.session(BOB))

    print("=== session A (alice, read_write on /a) ===")
    for line in SCRIPT_A:
        out = await a.run(line)
        print(f"A$ {line}")
        if out:
            print("   " + out.replace("\n", "\n   "))
    print()
    print("=== session B (bob, list on /a, read on /a/open.md), same tree ===")
    for line in SCRIPT_B:
        out = await b.run(line)
        print(f"B$ {line}")
        if out:
            print("   " + out.replace("\n", "\n   "))
    print()
    print("=== what the live Session holds vs what the ShellSession had to add ===")
    print("Session slots:", Session.__slots__)
    print("ShellSession fields:", [f for f in ShellSession.__dataclass_fields__ if f != "session"])
    print("A.cwd =", a.cwd, "| B.cwd =", b.cwd, "| A.env =", a.env, "| B.env =", b.env)
    print("builtins with no verb in this reference:", a.missing + b.missing)
    print("mount table rows:", [(m.path, m.storage_type, m.caps[:3]) for m in fs.mounts()])
    await fs.close()


if __name__ == "__main__":
    asyncio.run(main())
