"""Differential battery: vfs glob against find and ripgrep over one real tree.

Unix semantics stop being cited and start being executed. One scratch
tree is built on the real filesystem and mirrored into two vfs worlds
(plain directories, and the /data subtree as a mount with /data/api
nested inside it). Then:

- the **find leg** runs ``find <roots> -name <pattern>`` for name-arm
  cases — find's ``-name`` fnmatch over entry names is exactly vfs's
  name arm, and find's operand rule (roots are tested, missing roots
  are loud beside served results, exit 1) is exactly ADR 023's law;
- the **rg leg** runs ``rg --files -uu -g <glob>`` for path-arm and
  name-arm cases — ripgrep's glob language (``*`` within a segment,
  ``**`` across, ``/`` anchors) is vfs's, and ``-uu`` disables the
  hidden-file and ignore-file filtering vfs deliberately lacks.

Deliberate divergences (the allowlist, asserted where demonstrable):

- rg lists files only → the rg leg compares file-kind rows only;
- rg exempts an explicitly named file operand from ``-g`` entirely;
  vfs follows find and tests the operand (pinned as a divergence case);
- defective patterns refuse loudly in vfs (never silent-empty);
- vfs never consults ignore files and matches dotfiles (rg -uu parity).

Run:  uv run python context/specs/active/092-pattern-only-glob-seam/spike/differential_battery.py
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import tempfile
from pathlib import Path as OsPath

from vfs.base import VirtualFileSystem
from vfs.results import VFSErrorKind
from vfs.storage.backends.memory import InMemoryStorage

FIND = "/usr/bin/find"
RG = "rg"

# The scratch tree: dotfiles, metachar names, nesting, multiple roots.
FILES = (
    "notes.txt",
    ".hidden.txt",
    "data/a.txt",
    "data/b.md",
    "data/x.py",
    "data/.dot.txt",
    "data/deep/b.txt",
    "data/deep/nested/c.txt",
    "data/api/y.txt",
    "code/x.py",
    "code/sub/x.py",
    "m/100%.txt",
    "m/x_y.txt",
)

# find leg: name-arm patterns; roots () means unscoped (the tree root).
FIND_CASES = (
    ("*.txt", ()),
    ("*.txt", ("/data",)),
    ("*.txt", ("/data", "/code")),
    ("b.txt", ()),
    ("?.py", ()),
    ("[ab]*.txt", ()),
    ("*", ("/data/deep",)),
    ("**", ("/data",)),  # composed adjacent ** canonicalizes; behaves as *
    ("*.txt", ("/notes.txt",)),  # a file operand is matched itself
    ("100%*", ()),
    ("x_y*", ()),
)

# rg leg: the segment-aware pattern language over files.
RG_CASES = (
    ("*.txt", ()),
    ("/data/*.txt", ()),  # direct children only: * stops at /
    ("/data/**/*.txt", ()),  # ** spans, including zero segments
    ("**/*.txt", ()),
    ("*/x.py", ()),  # depth pin
    ("/m/*", ()),
    ("/x/*.py", ("/code",)),  # no /code/x dir: clean empty on both legs
    ("/sub/*.py", ("/code",)),  # a leading slash anchors at the scope root
    ("*.txt", ("/data",)),
)

# Refusable defects: loud invalid in vfs, never silent-empty.
DEFECTIVE = ("a**b", "/data//x", "***")

failures: list[str] = []


def check(label: str, expected: object, got: object) -> None:
    if expected != got:
        failures.append(f"{label}\n  expected: {expected}\n  got:      {got}")


def run_find(scratch: OsPath, pattern: str, roots: tuple[str, ...]) -> tuple[set[str], bool]:
    args = [str(scratch) + root for root in roots] if roots else [str(scratch)]
    proc = subprocess.run([FIND, *args, "-name", pattern], capture_output=True, text=True, check=False)
    hits = {line.removeprefix(str(scratch)) for line in proc.stdout.splitlines() if line.removeprefix(str(scratch))}
    return hits, proc.returncode == 0


def run_rg(scratch: OsPath, pattern: str, roots: tuple[str, ...]) -> set[str]:
    """One rg run per scope root, anchored there — vfs's root-relative rule.

    rg anchors a leading-slash glob at its working directory, so running
    from each root reproduces vfs's anchoring exactly; results union.
    """
    hits: set[str] = set()
    for root in roots or ("",):
        proc = subprocess.run(
            [RG, "--files", "-uu", "-g", pattern], capture_output=True, text=True, check=False, cwd=str(scratch) + root
        )
        hits.update(f"{root}/{line}" for line in proc.stdout.splitlines())
    return hits


async def build_worlds() -> tuple[VirtualFileSystem, VirtualFileSystem]:
    plain = VirtualFileSystem()
    mounted = VirtualFileSystem()
    await mounted.add_mount(InMemoryStorage(), "/data")
    await mounted.add_mount(InMemoryStorage(), "/data/api")
    for world in (plain, mounted):
        for rel in FILES:
            await world.write(path=f"/{rel}", content=rel, parents=True)
    return plain, mounted


async def main() -> int:
    scratch = OsPath(tempfile.mkdtemp(prefix="vfs-differential-"))
    for rel in FILES:
        target = scratch / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rel)
    plain, mounted = await build_worlds()

    for pattern, roots in FIND_CASES:
        expected, clean = run_find(scratch, pattern, roots)
        for name, world in (("plain", plain), ("mounted", mounted)):
            result = await world.glob(pattern, paths=roots)
            check(f"find[{name}] {pattern!r} roots={roots}", sorted(expected), sorted(result.paths))
            check(f"find[{name}] {pattern!r} roots={roots} (envelope)", clean, result.success)

    for pattern, roots in RG_CASES:
        expected = run_rg(scratch, pattern, roots)
        for name, world in (("plain", plain), ("mounted", mounted)):
            result = await world.glob(pattern, paths=roots)
            files = sorted(str(o.path) for o in result.observations if o.kind == "file")
            check(f"rg[{name}] {pattern!r} roots={roots}", sorted(expected), files)

    # Missing roots: find exits 1 and serves the healthy operands; vfs
    # fails the envelope and serves the healthy roots' rows beside it.
    expected, clean = run_find(scratch, "*.txt", ("/data", "/nope"))
    assert clean is False
    for name, world in (("plain", plain), ("mounted", mounted)):
        result = await world.glob("*.txt", paths=("/data", "/nope"))
        check(f"missing-root[{name}] rows", sorted(expected), sorted(result.paths))
        check(f"missing-root[{name}] envelope", False, result.success)

    # Allowlisted divergence: rg exempts a named file operand from -g;
    # vfs follows find and tests the operand against the pattern.
    proc = subprocess.run(
        [RG, "--files", "-uu", "-g", "*.py", "notes.txt"], capture_output=True, text=True, check=False, cwd=str(scratch)
    )
    check("rg operand exemption (rg side)", ["notes.txt"], proc.stdout.splitlines())
    for name, world in (("plain", plain), ("mounted", mounted)):
        result = await world.glob("*.py", paths=("/notes.txt",))
        check(f"operand-tested[{name}]", (True, ()), (result.success, result.paths))

    # Refusal, never silent-empty: a defective pattern is loud in vfs.
    for pattern in DEFECTIVE:
        for name, world in (("plain", plain), ("mounted", mounted)):
            result = await world.glob(pattern)
            check(f"defect[{name}] {pattern!r}", (False, VFSErrorKind.invalid), (result.success, result.errors[0].kind))

    total = (len(FIND_CASES) + len(RG_CASES)) * 2 + 6 + len(DEFECTIVE) * 2
    if failures:
        print(f"FAILURES ({len(failures)} of ~{total} checks):\n")
        print("\n\n".join(failures))
        return 1
    print(f"differential battery: {total} case-checks green (find leg, rg leg, operand law, refusals)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
