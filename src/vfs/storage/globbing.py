"""Shared glob selection semantics — one home, so backends cannot drift.

The rules every backend applies identically, whatever its candidate
discovery looks like: a slash in the pattern matches whole paths while a
bare pattern matches names; ``fnmatch`` is the one match authority; the
ext filter reads the **path-derived** extension — deliberately not any
stored column, so explicit-ext rows and extension-carrying directory
names match the same way everywhere; and ``max_count`` takes the first N
in path order. Backends own candidate discovery, scoping, and liveness.

    glob = compile_glob("*.py", ext=())
    kept = [p for p in candidates if glob.matches(p)]
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass

from vfs.paths import Path, extract_extension


@dataclass(frozen=True)
class GlobFilter:
    """The compiled per-candidate predicate; build via :func:`compile_glob`."""

    pattern: str
    by_path: bool
    wanted_ext: frozenset[str]

    def matches(self, path: Path) -> bool:
        """fnmatch authority over the subject, then the path-derived ext gate."""
        subject = str(path) if self.by_path else path.name
        if not fnmatch.fnmatchcase(subject, self.pattern):
            return False
        return not self.wanted_ext or (extract_extension(path) or "") in self.wanted_ext


def compile_glob(pattern: str, ext: tuple[str, ...]) -> GlobFilter:
    """Compile the shared filter: the subject rule plus the normalized ext set."""
    return GlobFilter(
        pattern=pattern,
        by_path="/" in pattern,
        wanted_ext=frozenset(e.lstrip(".").lower() for e in ext),
    )
