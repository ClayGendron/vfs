"""The corpus's files check out the same on every file system: no two paths differ only by letter case."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

CASES = Path(__file__).parent / "cases"


def test_no_two_case_files_differ_only_by_letter_case() -> None:
    by_folded: defaultdict[str, list[str]] = defaultdict(list)
    for path in CASES.rglob("*"):
        relative = path.relative_to(CASES).as_posix()
        by_folded[relative.casefold()].append(relative)
    clashes = sorted(paths for paths in by_folded.values() if len(paths) > 1)
    assert clashes == [], "macOS and Windows keep only one of each pair"
