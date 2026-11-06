"""Move the project version along the release lane.

``pyproject.toml`` is the only file that states the version; this script
rewrites that one line and runs ``uv lock`` so the lock file follows. The lane
is alpha, beta, release candidate, final, in that order and never backwards::

    uv run python scripts/bump_version.py --patch            # 0.0.22  -> 0.0.23
    uv run python scripts/bump_version.py --minor --pre a    # 0.0.22  -> 0.1.0a1
    uv run python scripts/bump_version.py --pre a            # 0.1.0a1 -> 0.1.0a2
    uv run python scripts/bump_version.py --pre b            # 0.1.0a4 -> 0.1.0b1
    uv run python scripts/bump_version.py --final            # 0.1.0b3 -> 0.1.0
    uv run python scripts/bump_version.py --set 0.2.0.dev1   # anything the rules do not cover

A move the lane does not allow is refused on stderr with exit status 2 and
nothing is written.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

from packaging.version import InvalidVersion, Version

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"

# The stages of the lane, in the only order they may be entered.
STAGES = ("a", "b", "rc")

# The subprocess runner; a test replaces it to see the lock call without a network.
run = subprocess.run


class BumpRefused(ValueError):
    """The requested move is not one the lane allows."""


class VersionLine(NamedTuple):
    """Where the ``[project]`` table's version string sits in the file text."""

    start: int
    end: int


# ---------------------------------------------------------------------------
# Reading and writing the one version line
# ---------------------------------------------------------------------------


def read_version(text: str) -> Version:
    """The ``[project]`` table's version, parsed."""
    span = _version_line(text)
    found = text[span.start : span.end]
    try:
        return Version(found)
    except InvalidVersion as error:
        raise BumpRefused(f"{found!r} under [project] is not a PEP 440 version") from error


def write_version(path: Path, new: Version) -> None:
    """Rewrite the ``[project]`` version string in *path* and nothing else."""
    text = path.read_text()
    span = _version_line(text)
    path.write_text(f"{text[: span.start]}{new}{text[span.end :]}")


# ---------------------------------------------------------------------------
# The transitions
# ---------------------------------------------------------------------------


def next_version(
    current: Version,
    *,
    part: str | None = None,
    pre: str | None = None,
    final: bool = False,
    explicit: str | None = None,
) -> Version:
    """The version after one move along the lane, or ``BumpRefused``.

    Versions outside the lane (dev, post, local, epoch, more than three release
    components) are treated as finals by ``part`` and ``final``; ``--set`` is the
    only tool that writes them, and the command, not this function, refuses
    ``--pre`` beside ``--final`` or ``--set``.
    """
    if explicit is not None:
        try:
            return Version(explicit)
        except InvalidVersion as error:
            raise BumpRefused(f"{explicit!r} is not a PEP 440 version") from error
    if final:
        if current.pre is None:
            raise BumpRefused(f"{current} is already a final version; nothing to strip")
        return Version(current.base_version)
    if part is not None:
        if current.pre is not None:
            raise BumpRefused(
                f"{current} is a pre-release: continue it with --pre or close it with --final; "
                f"--{part} would abandon the lane, and --set is the way to do that on purpose"
            )
        base = _bump_release(current, part)
        return Version(base if pre is None else f"{base}{pre}1")
    if pre is not None:
        if current.pre is None:
            raise BumpRefused(
                f"{current} is a final version: a part flag with --pre says which number the lane opens, "
                f"e.g. --minor --pre {pre}"
            )
        letter, number = current.pre
        if STAGES.index(pre) < STAGES.index(letter):
            raise BumpRefused(f"the lane never moves backwards: {current} is past stage {pre!r}")
        if pre == letter:
            return Version(f"{current.base_version}{pre}{number + 1}")
        return Version(f"{current.base_version}{pre}1")
    raise BumpRefused("nothing to do: give a part flag, --pre, --final or --set")


# ---------------------------------------------------------------------------
# The command
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Apply one move to the project's ``pyproject.toml`` and lock; 0 on success, 2 on a refusal."""
    args = _parser().parse_args(argv)
    if args.pre is not None and (args.final or args.explicit is not None):
        print(
            "error: --pre stands alone or combines with --major, --minor or --patch; not with --final or --set",
            file=sys.stderr,
        )
        return 2
    pyproject: Path = args.pyproject
    text = pyproject.read_text()
    try:
        old = read_version(text)
        new = next_version(old, part=args.part, pre=args.pre, final=args.final, explicit=args.explicit)
    except BumpRefused as refusal:
        print(f"error: {refusal}", file=sys.stderr)
        return 2
    write_version(pyproject, new)
    try:
        run(["uv", "lock"], cwd=pyproject.parent, check=True)
    except subprocess.CalledProcessError as failure:
        print(
            f"error: uv lock failed (exit {failure.returncode}) after {pyproject} was rewritten to {new}; run uv lock by hand",
            file=sys.stderr,
        )
        return 1
    print(f"{old} → {new}")
    return 0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Move the project version along the release lane")
    move = parser.add_mutually_exclusive_group()
    move.add_argument("--major", action="store_const", const="major", dest="part")
    move.add_argument("--minor", action="store_const", const="minor", dest="part")
    move.add_argument("--patch", action="store_const", const="patch", dest="part")
    move.add_argument("--final", action="store_true", help="strip the pre-release suffix")
    move.add_argument("--set", dest="explicit", metavar="VERSION", help="write this PEP 440 version")
    parser.add_argument("--pre", choices=STAGES, help="open, continue or advance a pre-release stage")
    parser.add_argument("--pyproject", type=Path, default=PYPROJECT, help=argparse.SUPPRESS)
    return parser


def _bump_release(current: Version, part: str) -> str:
    major, minor, micro = (*current.release, 0, 0)[:3]
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{micro + 1}"


def _version_line(text: str) -> VersionLine:
    """The span of the first ``version = "…"`` string inside the ``[project]`` table."""
    offset = 0
    in_project = False
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("["):
            in_project = stripped == "[project]"
        elif in_project and re.match(r'version\s*=\s*"', stripped):
            opening = line.index('"') + 1
            return VersionLine(offset + opening, offset + line.index('"', opening))
        offset += len(line)
    raise BumpRefused(f"no version line under [project] in {text[:40]!r}…")


if __name__ == "__main__":
    sys.exit(main())
