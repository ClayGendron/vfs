"""Differential battery: vfs grep against grep -E and ripgrep over one tree.

The glob battery's discipline applied to content search. One scratch
tree is built on the real filesystem and mirrored into vfs worlds; each
case runs in **four** vfs worlds — plain directories and a mounted
split (/data a mount, /data/api nested inside it), each before any
reindex (scan side) and after every backend reindexed (index side) —
because tier and placement must both be invisible to the answer. Then:

- the **grep leg** runs ``/usr/bin/grep -E`` for the flag surface —
  ``-i``/``-w``/``-F``/``-v``/``-c``/``-l``/``-m``, scope roots, the
  file-operand rule, and the missing-root exit beside served rows;
- the **rg leg** runs ``rg -uu --line-number`` for the glob channels
  and case modes — rg's glob language is vfs's, ``-S`` is smart case,
  and ``-uu`` disables the hidden-file and ignore-file filtering vfs
  deliberately lacks.

Deliberate divergences (the allowlist, asserted where demonstrable):

- **refusal-not-silent**: a gramless pattern (``ab``) serves on both
  external legs but refuses classified in vfs under the default gate;
  under ``allow_scan=True`` the vfs answer equals the rg answer;
- rg exempts an explicitly named file operand from ``-g`` entirely;
  vfs tests the operand against the glob (clean success when it fails);
- vfs never consults ignore files and matches dotfiles (rg -uu parity).

One portability find carried over from the glob battery: rg anchors
leading-slash globs at its *cwd*, so the rg leg runs once per scope
root with cwd set there — vfs's root-relative anchoring rule exactly.

Landed-run record (2026-08-05): 109 case-checks green — grep -E leg
(output modes, operands, missing-root exit beside served rows), rg -uu
leg (15 line-parity cases: flags, case modes, glob channels, scoping),
the refusal and operand-exemption divergences — identical across all
four worlds. (One harness find: rg's implicit current-directory search
can silently return nothing under a sandboxed subprocess — the leg
passes ``.`` explicitly and was verified non-vacuous against per-case
hit counts.)

Brace-alternation run (2026-08-07, with the 094 landing): three rg
cases added — admission braces by name and by anchored path, exclusion
braces — because rg's ``-g`` brace language is now vfs's brace
language. 121 case-checks green across the same four worlds.

Run:  uv run python context/research/studies/2026-08-05-grep-differential-battery/grep_differential_battery.py
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

GREP = "/usr/bin/grep"
RG = "rg"

# The scratch tree: needles at every level, dotfiles, case and word
# targets, regex targets, a metachar filename.
FILES = {
    "notes.txt": "needle at root\nplain line\ncat scratched\n",
    ".hidden.txt": "needle hidden\n",
    "data/a.txt": "needle a\nNeedle capital\n",
    "data/b.md": "alpha line\nbeta line\nalpha bridge omega\n",
    "data/x.py": "needle in py\na.b literal\naxb decoy\n",
    "data/.dot.txt": "needle dot\n",
    "data/deep/b.txt": "needle deep\nconcatenate\n",
    "data/deep/nested/c.txt": "needle nested\nneedle nested twice\n",
    "data/api/y.txt": "needle api\n",
    "code/x.py": "needle code\ncat alone\n",
    "m/100%.txt": "needle percent\n",
}

# rg leg: (pattern, roots, vfs kwargs, rg flags) — line-level parity.
RG_CASES = (
    ("needle", (), {}, ()),
    ("needle", ("/data",), {}, ()),
    ("needle", ("/data", "/code"), {}, ()),
    ("NEEDLE", (), {"case_mode": "insensitive"}, ("-i",)),
    ("needle", (), {"case_mode": "smart"}, ("-S",)),
    ("Needle", (), {"case_mode": "smart"}, ("-S",)),
    ("a.b", (), {"fixed_strings": True}, ("-F",)),
    ("cat", (), {"word_regexp": True}, ("-w",)),
    ("alpha|beta", (), {}, ()),
    ("alpha.*omega", (), {}, ()),
    ("needle", (), {"globs": ("*.py",)}, ("-g", "*.py")),
    ("needle", (), {"globs": ("/data/**",)}, ("-g", "/data/**")),
    ("needle", (), {"globs_not": ("*.py",)}, ("-g", "!*.py")),
    ("needle", (), {"max_count": 1}, ("-m", "1")),
    ("needle", (), {"invert_match": True}, ("-v",)),
    # Brace alternation (2026-08-07): rg's -g braces are vfs's braces.
    ("needle", (), {"globs": ("*.{py,md}",)}, ("-g", "*.{py,md}")),
    ("needle", (), {"globs": ("/data/{deep,api}/**",)}, ("-g", "/data/{deep,api}/**")),
    ("needle", (), {"globs_not": ("*.{md,py}",)}, ("-g", "!*.{md,py}")),
)

failures: list[str] = []


def check(label: str, expected: object, got: object) -> None:
    if expected != got:
        failures.append(f"{label}\n  expected: {expected}\n  got:      {got}")


def parse_hits(stdout: str, prefix: str) -> set[tuple[str, int]]:
    hits = set()
    for line in stdout.splitlines():
        path, num, _body = line.split(":", 2)
        hits.add((f"{prefix}/{path.removeprefix('./')}", int(num)))
    return hits


def run_rg(scratch: OsPath, pattern: str, roots: tuple[str, ...], flags: tuple[str, ...]) -> set[tuple[str, int]]:
    """One rg run per scope root, anchored there — the root-relative rule."""
    hits: set[tuple[str, int]] = set()
    for root in roots or ("",):
        proc = subprocess.run(
            [RG, "-uu", "--line-number", "--no-heading", *flags, "-e", pattern, "."],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(scratch) + root,
        )
        hits.update(parse_hits(proc.stdout, root))
    return hits


def run_grep(scratch: OsPath, args: list[str]) -> tuple[str, int]:
    proc = subprocess.run([GREP, *args], capture_output=True, text=True, check=False)
    return proc.stdout.replace(str(scratch), ""), proc.returncode


def vfs_hits(result) -> set[tuple[str, int]]:
    return {(str(o.path), m.match) for o in result.observations for m in o.matches or ()}


async def build_worlds(indexed: bool) -> tuple[VirtualFileSystem, VirtualFileSystem]:
    plain_backend = InMemoryStorage()
    plain = VirtualFileSystem(storage=plain_backend)
    backends = (InMemoryStorage(), InMemoryStorage(), InMemoryStorage())
    mounted = VirtualFileSystem(storage=backends[0])
    await mounted.add_mount(backends[1], "/data")
    await mounted.add_mount(backends[2], "/data/api")
    for world in (plain, mounted):
        for rel, content in FILES.items():
            await world.write(path=f"/{rel}", content=content, parents=True)
    if indexed:
        for backend in (plain_backend, *backends):
            assert (await backend.reindex()).success is True
    return plain, mounted


async def main() -> int:
    scratch = OsPath(tempfile.mkdtemp(prefix="vfs-grep-differential-"))
    for rel, content in FILES.items():
        target = scratch / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    worlds = []
    for indexed in (False, True):
        plain, mounted = await build_worlds(indexed)
        tier = "indexed" if indexed else "scan"
        worlds.extend(((f"plain-{tier}", plain), (f"mounted-{tier}", mounted)))

    for pattern, roots, kwargs, flags in RG_CASES:
        expected = run_rg(scratch, pattern, roots, flags)
        for name, world in worlds:
            result = await world.grep(pattern, paths=roots, **kwargs)
            check(f"rg[{name}] {pattern!r} roots={roots} {kwargs}", sorted(expected), sorted(vfs_hits(result)))

    # grep -E leg: output modes and the operand rules.
    files_out, _ = run_grep(scratch, ["-rlE", "needle", str(scratch)])
    counts_out, _ = run_grep(scratch, ["-rcE", "needle", f"{scratch}/data"])
    operand_out, _ = run_grep(scratch, ["-hnE", "needle", f"{scratch}/notes.txt"])
    _, missing_code = run_grep(scratch, ["-rlE", "needle", f"{scratch}/data", f"{scratch}/nope"])
    assert missing_code == 2
    grep_files = set(files_out.splitlines())
    grep_counts = {
        line.rsplit(":", 1)[0]: int(line.rsplit(":", 1)[1])
        for line in counts_out.splitlines()
        if line.rsplit(":", 1)[1] != "0"
    }
    grep_operand_lines = {int(line.split(":", 1)[0]) for line in operand_out.splitlines()}
    for name, world in worlds:
        listed = await world.grep("needle", output_mode="files")
        check(f"grep-files[{name}]", sorted(grep_files), sorted(listed.paths))
        check(f"grep-files[{name}] rows carry no lines", set(), vfs_hits(listed))
        counted = await world.grep("needle", paths=("/data",), output_mode="count")
        check(f"grep-count[{name}]", grep_counts, {str(o.path): int(o.score or 0) for o in counted.observations})
        operand = await world.grep("needle", paths=("/notes.txt",))
        check(f"grep-operand[{name}] rows", ("/notes.txt",), operand.paths)
        check(f"grep-operand[{name}] lines", grep_operand_lines, {m.match for m in operand.observations[0].matches})
        missing = await world.grep("needle", paths=("/data", "/nope"))
        check(f"missing-root[{name}] envelope", False, missing.success)
        check(f"missing-root[{name}] kind", VFSErrorKind.not_found, missing.errors[0].kind)
        check(f"missing-root[{name}] served beside", True, len(missing.observations) > 0)

    # Allowlisted divergence: a gramless pattern serves on the external
    # legs but refuses classified under vfs's default gate; the opt-out
    # then matches rg exactly.
    expected = run_rg(scratch, "ab", (), ())
    for name, world in worlds:
        refused = await world.grep("ab")
        check(f"refusal[{name}] envelope", False, refused.success)
        check(f"refusal[{name}] kind", VFSErrorKind.unindexable_pattern, refused.errors[0].kind)
        opted = await world.grep("ab", allow_scan=True)
        check(f"refusal[{name}] allow_scan parity", sorted(expected), sorted(vfs_hits(opted)))

    # Allowlisted divergence: rg exempts a named file operand from -g;
    # vfs tests the operand and drops it as clean success.
    proc = subprocess.run(
        [RG, "-uu", "-l", "-g", "*.py", "-e", "needle", "notes.txt"],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(scratch),
    )
    check("rg operand exemption (rg side)", ["notes.txt"], proc.stdout.splitlines())
    for name, world in worlds:
        result = await world.grep("needle", paths=("/notes.txt",), globs=("*.py",))
        check(f"operand-tested[{name}]", (True, ()), (result.success, result.paths))

    total = len(RG_CASES) * len(worlds) + 8 * len(worlds) + 3 * len(worlds) + 1 + len(worlds)
    if failures:
        print(f"FAILURES ({len(failures)} of ~{total} checks):\n")
        print("\n\n".join(failures))
        return 1
    print(
        f"grep differential battery: {total} case-checks green (grep -E leg, rg -uu leg, refusal and operand divergences, 4 worlds)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
