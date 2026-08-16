"""Prototype of the three planner upgrades, caps tunable — research only.

Run via measure.py in this directory. Never imported by live code; the live
planner is ``vfs.models.code_grams`` and this file deliberately reuses its
fold/encode/gram helpers so prototype and live agree on the byte stream.

Compiles a pattern to a set of *fragments*. A fragment is one alternative's
guaranteed-literal shape: a tuple of text segments where the first/last
segment can still join adjacent literal text (open ends), and interior
boundaries are severed adjacency (today's "flush"). The BREAK fragment
("", "") requires nothing and severs both sides — every conservative
give-up compiles to it, which is exactly today's flush.

Upgrades, each behind a toggle so rescue attribution is per-upgrade:

- classes:  IN nodes with enumerable members (literals + small ranges, no
  negation/categories) fork one fragment per member, deduped after folding.
- branches: BRANCH at any depth forks per-branch fragments that join the
  surrounding context; SUBPATTERN becomes adjacency-transparent (required
  for ``foo_(bar|baz)`` to compose — the group must pass adjacency through).
- anchors:  AT nodes are identity (zero-width, adjacency-transparent).

Caps: ``member_cap`` bounds post-fold class members; ``width_cap`` bounds the
fragment-set width at every step (the shared final-width ceiling). An
over-cap expansion degrades that node to BREAK — degrade, never refuse.

With all toggles off this reproduces the live planner exactly (validated in
measure.py against ``build_code_gram_query`` over the whole corpus).
"""

from __future__ import annotations

from dataclasses import dataclass

from re import _constants as sre_constants
from re import _parser as sre_parse

from vfs.models.code_grams import (
    GramAnd,
    GramAny,
    GramOr,
    GramQuery,
    _encode_run,
    _grams_from_run,
    fold_content,
)

Fragment = tuple[str, ...]  # segments; first/last are open ends
BREAK: Fragment = ("", "")
IDENTITY: Fragment = ("",)


@dataclass(frozen=True)
class Caps:
    classes: bool = False
    branches: bool = False
    anchors: bool = False
    member_cap: int = 16
    width_cap: int = 64


def _concat(f1: Fragment, f2: Fragment) -> Fragment:
    return f1[:-1] + (f1[-1] + f2[0],) + f2[1:]


def _close(f: Fragment) -> Fragment:
    """Sever both open ends: the fragment's runs stand alone."""
    return ("", *f, "")


def _emit(codepoint: int) -> str | None:
    char = chr(codepoint)
    try:
        char.encode("utf-8")
    except UnicodeEncodeError:
        return None
    return char


def _class_members(items: list, cap: int) -> list[str] | None:
    """Enumerate a class's members, deduped after folding; None = give up."""
    raw: list[str] = []
    for op, arg in items:
        if op is sre_constants.LITERAL:
            char = _emit(arg)
            if char is None:
                return None
            raw.append(char)
        elif op is sre_constants.RANGE:
            lo, hi = arg
            if hi - lo + 1 > cap:
                return None
            for cp in range(lo, hi + 1):
                char = _emit(cp)
                if char is None:
                    return None
                raw.append(char)
        else:
            # NEGATE, CATEGORY (\w, \d), nested IN: keep today's flush.
            return None
    folded: list[str] = []
    seen: set[str] = set()
    for char in raw:
        key = fold_content(char)
        if key not in seen:
            seen.add(key)
            folded.append(char)
    if len(folded) > cap:
        return None
    return folded


def _cross(frags: list[Fragment], node: list[Fragment], cap: int) -> list[Fragment]:
    if len(frags) * len(node) > cap:
        node = [BREAK]
    out: list[Fragment] = []
    seen: set[Fragment] = set()
    for f in frags:
        for g in node:
            fg = _concat(f, g)
            if fg not in seen:
                seen.add(fg)
                out.append(fg)
    return out


def _node_fragments(op, arg, caps: Caps) -> list[Fragment]:
    """Fragment set of one AST node. BREAK is every conservative give-up."""
    if op is sre_constants.LITERAL:
        char = _emit(arg)
        return [BREAK] if char is None else [(char,)]

    if op is sre_constants.IN:
        if caps.classes:
            members = _class_members(arg, caps.member_cap)
            if members is not None:
                return [(m,) for m in members]
        return [BREAK]

    if op is sre_constants.AT:
        return [IDENTITY] if caps.anchors else [BREAK]

    if op is sre_constants.BRANCH:
        if caps.branches:
            _none, branches = arg
            out: list[Fragment] = []
            for branch in branches:
                out.extend(_compile_seq(list(branch), caps))
                if len(out) > caps.width_cap:
                    return [BREAK]
            return out
        return [BREAK]

    if op is sre_constants.SUBPATTERN:
        _group, _add, _del, body = arg
        inner = _compile_seq(list(body), caps)
        if caps.branches:
            return inner  # adjacency-transparent group
        # Today's shape: pure-literal bodies splice, everything else is
        # flushed standalone runs.
        if len(inner) == 1 and len(inner[0]) == 1:
            return inner
        return [_close(f) for f in inner]

    if op is sre_constants.MAX_REPEAT or op is sre_constants.MIN_REPEAT:
        min_repeat, _max, body = arg
        if min_repeat == 0:
            return [BREAK]
        # Body appears >= 1 times; adjacency severed on both sides.
        return [_close(f) for f in _compile_seq(list(body), caps)]

    # ANY, NOT_LITERAL, GROUPREF, ASSERT, ASSERT_NOT, unknown ops.
    return [BREAK]


def _compile_seq(ast: list, caps: Caps) -> list[Fragment]:
    frags: list[Fragment] = [IDENTITY]
    for op, arg in ast:
        frags = _cross(frags, _node_fragments(op, arg, caps), caps.width_cap)
    return frags


def _fragment_query(frags: list[Fragment]) -> GramQuery:
    branches: list[GramQuery] = []
    seen: set[frozenset] = set()
    for f in frags:
        grams: set[int] = set()
        for seg in f:
            if seg:
                grams |= _grams_from_run(_encode_run(seg))
        if not grams:
            return GramAny()
        key = frozenset(grams)
        if key not in seen:
            seen.add(key)
            branches.append(GramAnd(key))
    if len(branches) == 1:
        return branches[0]
    return GramOr(tuple(branches))


def plan(pattern: str, caps: Caps) -> tuple[GramQuery, int]:
    """Compile *pattern*; returns (query, final fragment width)."""
    try:
        parsed = sre_parse.parse(pattern)
    except (sre_constants.error, UnicodeEncodeError):
        return GramAny(), 0

    ast = list(parsed.data)
    # Today's top-level alternation split, kept when branches are off so the
    # off-configuration reproduces the live planner exactly.
    match ast:
        case [(sre_constants.BRANCH, (None, branches))] if not caps.branches:
            compiled: list[GramQuery] = []
            for branch in branches:
                sub, _w = plan_seq(list(branch), caps)
                if isinstance(sub, GramAny):
                    return GramAny(), 0
                compiled.append(sub)
            return GramOr(tuple(compiled)), len(compiled)

    return plan_seq(ast, caps)


def plan_seq(ast: list, caps: Caps) -> tuple[GramQuery, int]:
    frags = _compile_seq(ast, caps)
    return _fragment_query(frags), len(frags)
