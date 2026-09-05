"""The markdown reference kernel's oracle.

A readable line-by-line reading of what the engine yields: the raw
destination of every inline link, image and reference definition, and
every path-shaped code span, each with its folded referring line, in
document order. Fenced code is skipped whole and a code span is cut
before the link scan, as the tree reads them. The oracle is a regex
reading of the CommonMark shapes the fixtures use, not a full parser —
the engine is the referee on nesting, indented code and HTML; the
parity fixtures stay inside what both agree on.
"""

from __future__ import annotations

import re
from functools import partial
from typing import NamedTuple

MAX_CONTEXT_CHARS = 256
MAX_EXTENSION_CHARS = 8

_INLINE = re.compile(r"!?\[[^\]\n]*\]\(\s*(<[^>\n]*>|(?:[^()\s]|\([^()\s]*\))+)(?:\s+(?:\"[^\"\n]*\"|'[^'\n]*'))?\s*\)")
_REFERENCE_DEFINITION = re.compile(r"^ {0,3}\[[^\]\n]+\]:[ \t]*(<[^>\n]*>|\S+)", re.MULTILINE)
_CODE_SPAN = re.compile(r"(`+)([^`\n]+?)\1")
_FENCE = re.compile(r"^ {0,3}(?:```|~~~)")
_PATH_CHARS = re.compile(r"^[\w.\-/@+~%]+$")
_FILE_NAME = re.compile(rf"^[^/]+\.[A-Za-z0-9]{{1,{MAX_EXTENSION_CHARS}}}$")
_WHITESPACE = re.compile(r"\s+")


class Ref(NamedTuple):
    dest: str
    context: str


def markdown_refs(content: str) -> list[Ref]:
    refs: list[Ref] = []
    fenced = False
    for line in content.splitlines():
        if _FENCE.match(line):
            fenced = not fenced
            continue
        if fenced:
            continue
        context = fold_line(line)
        found: list[tuple[int, Ref]] = []
        prose = _CODE_SPAN.sub(partial(_lift_span, context=context, found=found), line)
        for pattern in (_INLINE, _REFERENCE_DEFINITION):
            found.extend(
                (match.start(1), Ref(_strip_angles(match.group(1)), context)) for match in pattern.finditer(prose)
            )
        refs.extend(ref for _, ref in sorted(found, key=lambda item: item[0]))
    return refs


def fold_line(line: str) -> str:
    return _WHITESPACE.sub(" ", line).strip()[:MAX_CONTEXT_CHARS]


def _strip_angles(dest: str) -> str:
    return dest[1:-1] if dest.startswith("<") and dest.endswith(">") else dest


def _lift_span(match: re.Match[str], context: str, found: list[tuple[int, Ref]]) -> str:
    """Record a path-shaped span; the span leaves the prose as one space of the same width."""
    span = match.group(2)
    text = span[1:-1] if span.startswith(" ") and span.endswith(" ") and span.strip() else span
    text = text.strip()
    if _PATH_CHARS.match(text) and ("/" in text or _FILE_NAME.match(text)):
        found.append((match.start(), Ref(text, context)))
    return " " * len(match.group(0))
