#!/usr/bin/env python3
"""Make every paragraph under ``context/`` one line.

A paragraph is one line of any length; a renderer joins wrapped lines anyway, and a
one-line paragraph keeps a heading, a label or a link whole and keeps a diff to the
sentence that changed. Prose lines are joined onto the line before them. Left alone:
fenced code (closed only by the marker that opened it), indented code (four spaces or
a tab after a blank line or after a prose line, under a list item or not), table rows
(with or without leading pipes), block quotes, HTML blocks, headings, horizontal rules,
link-reference and footnote definitions, and a line that ends in two spaces or a
backslash (a hard break, kept with its trailing spaces). A list item's indented
continuation lines, when no blank line separates them from the item, are joined onto
the item.

    scripts/unwrap_context.py --check   # print each wrapped file; exit 1 when any
    scripts/unwrap_context.py --fix     # rewrite every wrapped file in place
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CONTEXT = REPO / "context"
SKIPPED_DIRS = frozenset({"experiments", "__pycache__"})

FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
HEADING_RE = re.compile(r"^#{1,6}\s")
RULE_RE = re.compile(r"^\s*([-*_]\s*){3,}$|^\s*=+\s*$")
TABLE_RE = re.compile(r"^\s*\|")
DELIMITER_ROW_RE = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*$")
QUOTE_RE = re.compile(r"^\s*>")
HTML_RE = re.compile(r"^\s*<")
REFERENCE_RE = re.compile(r"^\s*\[[^\]]+\]: ")
LIST_RE = re.compile(r"^\s*([-*+]|\d+[.)])\s")
INDENTED_RE = re.compile(r"^( {4,}|\t)")


def markdown_files(root: Path = CONTEXT) -> list[Path]:
    """Every ``*.md`` under *root*; experiment folders and caches are pruned, not visited."""
    found: list[Path] = []
    for folder, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIPPED_DIRS]
        found += [Path(folder) / f for f in files if f.endswith(".md")]
    return sorted(found)


def closes(fence: str, line: str) -> bool:
    """A fence closes on the marker character that opened it, at least as long."""
    match = FENCE_RE.match(line)
    return bool(match) and match.group(1)[0] == fence[0] and len(match.group(1)) >= len(fence)


def kind_of(line: str, previous: str, after_blank: bool, following: str) -> str:
    """Classify one non-blank line given the kind of the line before it and the text after it."""
    if HEADING_RE.match(line):
        return "heading"
    if RULE_RE.match(line):
        return "rule"
    if TABLE_RE.match(line) or DELIMITER_ROW_RE.match(following) or (previous == "table" and "|" in line):
        return "table"
    if QUOTE_RE.match(line):
        return "quote"
    if previous == "html" or HTML_RE.match(line):
        return "html"
    if REFERENCE_RE.match(line):
        return "reference"
    if INDENTED_RE.match(line) and (previous in {"code", "prose"} or after_blank):
        return "code"
    if LIST_RE.match(line):
        return "list"
    return "prose"


def unwrap(lines: list[str]) -> list[str]:
    """The lines with every wrapped paragraph joined onto one line."""
    out: list[str] = []
    fence: str | None = None
    previous = "blank"
    after_blank = True
    for index, line in enumerate(lines):
        if fence is not None:
            out.append(line)
            if closes(fence, line):
                fence = None
                previous = "fence"
                after_blank = False
            continue
        opening = FENCE_RE.match(line)
        if opening:
            fence = opening.group(1)
            out.append(line)
            previous = "fence"
            after_blank = False
            continue
        if not line.strip():
            out.append(line)
            after_blank = True
            if previous != "code":
                previous = "blank"
            continue
        following = lines[index + 1] if index + 1 < len(lines) else ""
        kind = kind_of(line, previous, after_blank, following)
        joinable = previous in {"prose", "list"} and not out[-1].endswith(("  ", "\\"))
        if kind == "prose" and joinable:
            out[-1] = out[-1].rstrip() + " " + line.lstrip()
        else:
            out.append(line)
            previous = kind
        after_blank = False
    return out


def wrapped(path: Path) -> list[str] | None:
    """The unwrapped lines when the file changes, else None."""
    lines = path.read_text().split("\n")
    fixed = unwrap(lines)
    return fixed if fixed != lines else None


def main(argv: list[str]) -> int:
    fix = "--fix" in argv
    changed = 0
    for path in markdown_files():
        fixed = wrapped(path)
        if fixed is None:
            continue
        changed += 1
        if fix:
            path.write_text("\n".join(fixed))
        else:
            sys.stdout.write(f"{path.relative_to(REPO)}\n")
    if fix:
        sys.stderr.write(f"unwrapped {changed} file(s)\n")
        return 0
    return 1 if changed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
