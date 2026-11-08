"""The glob matcher's oracle: the stdlib-text translator.

Glob patterns once compiled to these regex sources and matched under
Python's ``re``; the runtime now matches on the native glob program,
and this module keeps the text as the reference it is pinned to. The
text itself is pinned to the stdlib's ``glob.translate`` byte for byte
wherever that function exists (3.13 and later); the engine is pinned to
``re.match`` over this text by verdict, on every interpreter.
"""

from __future__ import annotations

import re
import sys
from typing import Final

# The stdlib translators switched their end-of-string anchor to \z in 3.14;
# mirror them exactly (\z is a re.error before 3.14).
_END_OF_STRING: Final = r"\z" if sys.version_info >= (3, 14) else r"\Z"


def _translate(pattern: str, *, recursive: bool) -> str:
    """Regex source for *pattern* — segment-aware, dotfiles ordinary, ``/`` seps.

    An original implementation of the ``glob.translate`` contract (stdlib
    3.13+, newer than the project floor), fixed to the one call shape every
    consumer uses: hidden files included, ``/`` the only separator. Input
    is defect-gated and canonical — no ``**`` inside a component, no
    adjacent ``**`` — so the stdlib's collapses for both are omitted here.
    Parity with the stdlib is pinned textually by the differential test
    wherever the stdlib function exists. ``**`` as a whole component spans
    zero or more segments only under *recursive*; a bare ``*`` component
    requires a non-empty segment.
    """
    parts = pattern.split("/")
    last = len(parts) - 1
    pieces: list[str] = []
    for index, part in enumerate(parts):
        if recursive and part == "**":
            pieces.append(".*" if index == last else "(?:.+/)?")
            continue
        if part == "*":
            pieces.append("[^/]+")
        elif part:
            pieces.append(_translate_component(part))
        if index < last:
            pieces.append("/")
    return "(?s:" + "".join(pieces) + ")" + _END_OF_STRING


def _translate_component(component: str) -> str:
    """One component's regex source: wildcards, classes, escaped literals."""
    pieces: list[str] = []
    index = 0
    while index < len(component):
        char = component[index]
        index += 1
        if char == "*":
            pieces.append("[^/]*")
        elif char == "?":
            pieces.append("[^/]")
        elif char == "[" and (end := _component_class_end(component, index)) is not None:
            pieces.append(_translate_class(component[index:end]))
            index = end + 1
        else:
            pieces.append(re.escape(char))
    return "".join(pieces)


def _component_class_end(component: str, start: int) -> int | None:
    """Index of the ``]`` closing the class opened at *start*, or ``None`` when literal.

    The fnmatch scan: only ``!`` negates (a leading ``^`` is an ordinary
    member), unlike :func:`_class_end`, whose ``!^`` opacity serves the
    brace parser.
    """
    index = start
    if index < len(component) and component[index] == "!":
        index += 1
    if index < len(component) and component[index] == "]":
        index += 1
    end = component.find("]", index)
    return end if end != -1 else None


def _translate_class(stuff: str) -> str:
    """One class interior's regex source, empty ranges pruned fnmatch-style."""
    if "-" not in stuff:
        body = stuff.replace("\\", r"\\")
    else:
        chunks: list[str] = []
        start = 0
        probe = 2 if stuff[0] == "!" else 1
        while (hit := stuff.find("-", probe)) >= 0:
            chunks.append(stuff[start:hit])
            # A range consumes the dash and its bounds; probe past them.
            start, probe = hit + 1, hit + 3
        if rest := stuff[start:]:
            chunks.append(rest)
        else:
            chunks[-1] += "-"
        for k in range(len(chunks) - 1, 0, -1):
            # An inverted range ([z-a]) is invalid regex; merge it away.
            if chunks[k - 1][-1] > chunks[k][0]:
                chunks[k - 1] = chunks[k - 1][:-1] + chunks[k][1:]
                del chunks[k]
        body = "-".join(s.replace("\\", r"\\").replace("-", r"\-") for s in chunks)
    body = re.sub(r"([&~|])", r"\\\1", body)
    if not body:
        return "(?!)"
    if body == "!":
        # A negated empty range matches any character (fnmatch's rule);
        # falling through would emit the invalid class [^].
        return "."
    if body[0] == "!":
        body = "^" + body[1:]
    elif body[0] in "^[":
        body = "\\" + body
    return "[" + body + "]"
