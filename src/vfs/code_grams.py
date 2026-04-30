"""Code-oriented byte-trigram tokenizer and conservative regex-to-gram planner.

This module is the database-agnostic primitive behind Grover's portable code
search candidate index (story 013). It deliberately does NOT use ``pg_trgm``
semantics: punctuation, whitespace, operators, path separators, and bytes
inside non-ASCII UTF-8 code points all participate in candidate generation.

The output is a safe candidate generator. It may admit false positives but
must never introduce false negatives — the authoritative match is always run
in Python afterward by the caller.

Layers:

1. ``iter_code_grams`` / ``unique_code_grams``
   Raw byte trigram extraction from NFC-normalized UTF-8 content.

2. ``grams_for_fixed_string``
   Required byte trigrams for a fixed-string grep pattern.

3. ``GramQuery`` + ``build_code_gram_query``
   A small boolean algebra over required gram sets, derived from a traversal
   of Python's ``sre_parse`` regex AST.

Case folding is handled by emitting a separate folded byte stream from
``content.casefold()``. The caller decides whether to maintain folded grams
in addition to raw grams via ``gram_kind``.

Unicode normalization: both indexer and query planner apply NFC normalization
before encoding, so canonically-equivalent code points produce the same byte
stream. This avoids silent index/query divergence when a file is stored as
NFC and the user types NFD (or vice versa).
"""

from __future__ import annotations

import unicodedata
import warnings
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal

if TYPE_CHECKING:
    from collections.abc import Iterator

# ``sre_parse`` is the canonical way to inspect the regex AST. It was marked
# deprecated in Python 3.11 but is still the only supported access path; the
# replacement ``re._parser`` is private. We import sre_parse and silence the
# DeprecationWarning rather than reaching into private modules.
with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    import sre_constants
    import sre_parse

GRAM_SIZE: Final = 3

GramKind = Literal[0, 1]
GRAM_KIND_RAW: Final[GramKind] = 0
GRAM_KIND_FOLDED: Final[GramKind] = 1

_IGNORECASE: Final = sre_constants.SRE_FLAG_IGNORECASE


def normalize_content(content: str) -> bytes:
    """Return UTF-8 bytes after newline normalization and NFC normalization.

    Applied identically by indexers and query planners so canonically
    equivalent inputs produce the same byte stream.
    """
    if "\r" in content:
        content = content.replace("\r\n", "\n").replace("\r", "\n")
    if not content.isascii():
        content = unicodedata.normalize("NFC", content)
    return content.encode("utf-8")


def fold_content(content: str) -> str:
    """Return the case-folded form of *content* used for the folded gram stream.

    NFC normalization is applied first so casefold sees a stable form across
    NFC/NFD inputs.
    """
    if not content.isascii():
        content = unicodedata.normalize("NFC", content)
    return content.casefold()


def pack_gram(b0: int, b1: int, b2: int) -> int:
    """Pack three bytes into a 24-bit integer key."""
    return (b0 << 16) | (b1 << 8) | b2


def unpack_gram(gram: int) -> bytes:
    """Inverse of :func:`pack_gram`."""
    return bytes(((gram >> 16) & 0xFF, (gram >> 8) & 0xFF, gram & 0xFF))


def _iter_byte_trigrams(data: bytes) -> Iterator[int]:
    if len(data) < GRAM_SIZE:
        return
    for i in range(len(data) - GRAM_SIZE + 1):
        yield pack_gram(data[i], data[i + 1], data[i + 2])


def _grams_from_run(run: bytes) -> set[int]:
    return set(_iter_byte_trigrams(run))


def iter_code_grams(content: str, *, folded: bool = False) -> Iterator[int]:
    """Yield every sliding 3-byte UTF-8 trigram in *content*, in order.

    Duplicates are NOT collapsed; callers that want a set should use
    :func:`unique_code_grams`. Punctuation, whitespace, and operator bytes are
    intentionally preserved.
    """
    source = fold_content(content) if folded else content
    yield from _iter_byte_trigrams(normalize_content(source))


def unique_code_grams(content: str, *, folded: bool = False) -> set[int]:
    """Return the deduplicated set of byte trigrams in *content*."""
    return set(iter_code_grams(content, folded=folded))


def grams_for_fixed_string(pattern: str, *, folded: bool = False) -> set[int]:
    """Return required byte trigrams for a fixed-string grep pattern.

    Strings shorter than 3 bytes (after normalization and optional folding)
    have no required grams; the candidate query must fall back to ``ANY`` for
    those.
    """
    return unique_code_grams(pattern, folded=folded)


# ---------------------------------------------------------------------------
# GramQuery — boolean algebra over required gram sets
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GramAny:
    """Sentinel: no useful gram predicate. Caller must scan or use other filters."""

    def required_grams(self) -> set[int]:
        return set()

    def is_any(self) -> bool:
        return True


@dataclass(frozen=True)
class GramAnd:
    """Conjunction: candidate chunks must contain ALL of these grams."""

    grams: frozenset[int]

    def required_grams(self) -> set[int]:
        return set(self.grams)

    def is_any(self) -> bool:
        return False


@dataclass(frozen=True)
class GramOr:
    """Disjunction: candidate chunks must satisfy at least one branch.

    Each branch is itself a :class:`GramQuery`. ``GramOr`` is only sound when
    every branch is a real predicate (no ``GramAny`` branches) — the planner
    collapses to ``GramAny`` if any branch would otherwise be unconstrained.
    """

    branches: tuple[GramQuery, ...]

    def required_grams(self) -> set[int]:
        out: set[int] = set()
        for branch in self.branches:
            out |= branch.required_grams()
        return out

    def is_any(self) -> bool:
        return False


GramQuery = GramAny | GramAnd | GramOr


# ---------------------------------------------------------------------------
# AST walker — extract guaranteed literal byte runs from sre_parse output
# ---------------------------------------------------------------------------


def _emit_literal(codepoint: int, *, folded: bool, flags: int) -> bytes | None:
    """Return UTF-8 bytes for a literal codepoint, or ``None`` if unsafe.

    In folded mode every literal is casefolded before encoding — the index
    and the query planner agree on the lowercase byte stream regardless of
    surrounding flag toggles.

    In raw mode, a literal under an effective IGNORECASE flag could match
    either case in content, so we cannot assert any required byte. We return
    ``None`` and let the caller flush the run.
    """
    char = chr(codepoint)
    try:
        if folded:
            # NFC keeps casefold output stable for combining-mark-bearing inputs.
            return unicodedata.normalize("NFC", char.casefold()).encode("utf-8")
        if flags & _IGNORECASE:
            return None
        return unicodedata.normalize("NFC", char).encode("utf-8")
    except UnicodeEncodeError:
        # Lone surrogates and other non-encodable code points cannot be
        # required as bytes in the index. Treat as opaque and flush the run.
        return None


def _collect_runs(ast: list, *, folded: bool, flags: int) -> tuple[list[bytes], bool]:
    """Walk a flat AST sequence and return ``(runs, terminated)``.

    ``runs`` is the list of guaranteed-literal byte runs found in order. Each
    run is a maximal contiguous sequence of bytes every match must contain.

    ``terminated`` is ``True`` if every node in *ast* contributed soundly to
    the run stream (no opaque assertions encountered). The caller uses this
    to decide whether a *whole subtree* is a candidate for required-gram
    extraction — a non-top-level BRANCH whose every branch returns
    ``terminated=True`` AND yields at least one common gram could in principle
    be tightened, but our v1 keeps that conservative.
    """
    runs: list[bytes] = []
    buf: list[bytes] = []

    def flush() -> None:
        if buf:
            runs.append(b"".join(buf))
            buf.clear()

    for op, arg in ast:
        if op is sre_constants.LITERAL:
            byte = _emit_literal(arg, folded=folded, flags=flags)
            if byte is None:
                flush()
            else:
                buf.append(byte)
            continue

        if op is sre_constants.NOT_LITERAL:
            flush()
            continue

        if op is sre_constants.ANY:
            flush()
            continue

        if op is sre_constants.IN:
            # Character class — contributes exactly one byte position but we
            # don't know which byte, so it terminates the current run.
            flush()
            continue

        if op is sre_constants.AT:
            # Anchor (^, $, \A, \Z, \b, \B) — no byte contribution but it
            # also doesn't break the literal run. However grep applies
            # anchors line-by-line in Python, so we conservatively flush.
            flush()
            continue

        if op is sre_constants.MAX_REPEAT or op is sre_constants.MIN_REPEAT:
            min_repeat, _max_repeat, body = arg
            if min_repeat == 0:
                # Body may not appear at all — drop it.
                flush()
            else:
                # Body appears at least once. Descend, but flush on either
                # side so we don't claim adjacency that the repetition would
                # break.
                flush()
                inner_runs, _ = _collect_runs(list(body), folded=folded, flags=flags)
                runs.extend(inner_runs)
            continue

        if op is sre_constants.SUBPATTERN:
            # SUBPATTERN payload: (group_id, add_flags, del_flags, body).
            # Inline scoped flags like (?i:...) toggle our effective flags
            # for the body only.
            _group_id, add_flags, del_flags, body = arg
            new_flags = (flags | add_flags) & ~del_flags
            inner_runs, _ = _collect_runs(list(body), folded=folded, flags=new_flags)
            # Group boundaries don't break adjacency. Splice the inner runs
            # into our run stream, preserving any open buffer.
            for idx, inner in enumerate(inner_runs):
                if idx == 0 and buf:
                    buf.append(inner)
                else:
                    flush()
                    runs.append(inner)
            # If the inner produced no runs, our buf still continues; we
            # treat the empty group as transparent.
            continue

        if op is sre_constants.BRANCH:
            # Non-top-level BRANCH terminates the run conservatively.
            # (Top-level alternation is handled by the caller via
            # ``build_code_gram_query`` so each branch becomes its own
            # ``GramAnd`` inside an ``OR``.)
            flush()
            continue

        if op is sre_constants.GROUPREF:
            # Backreference — content is determined dynamically. Drop.
            flush()
            continue

        if op is sre_constants.ASSERT or op is sre_constants.ASSERT_NOT:
            # Lookarounds. The matched span doesn't include their content
            # so we cannot use their literals as required grams of the line.
            flush()
            continue

        # Unknown / not-yet-supported op (ATOMIC_GROUP, POSSESSIVE_REPEAT,
        # etc.). Conservative: terminate the run. We avoid descending into
        # unknown structures because we cannot guarantee soundness without
        # understanding their semantics.
        flush()

    flush()
    return runs, True


def _grams_from_runs(runs: list[bytes]) -> set[int]:
    out: set[int] = set()
    for run in runs:
        out |= _grams_from_run(run)
    return out


def _query_from_ast(
    ast: list,
    *,
    folded: bool,
    flags: int,
) -> GramQuery:
    """Compile a flat AST sequence into a :class:`GramQuery`.

    Top-level alternation is split here. Otherwise, required grams are
    collected from guaranteed literal runs.
    """
    # Detect top-level alternation: the AST is exactly ``[(BRANCH, (None, [
    # branch1, branch2, ... ]))]``.
    if len(ast) == 1 and ast[0][0] is sre_constants.BRANCH:
        _none, branches = ast[0][1]
        compiled: list[GramQuery] = []
        for branch in branches:
            sub = _query_from_ast(list(branch), folded=folded, flags=flags)
            if isinstance(sub, GramAny):
                # An OR with an unconstrained branch is unconstrained.
                return GramAny()
            compiled.append(sub)
        if not compiled:
            return GramAny()
        if len(compiled) == 1:
            return compiled[0]
        return GramOr(tuple(compiled))

    runs, _ = _collect_runs(ast, folded=folded, flags=flags)
    grams = _grams_from_runs(runs)
    if not grams:
        return GramAny()
    return GramAnd(frozenset(grams))


def build_code_gram_query(
    pattern: str,
    *,
    fixed_strings: bool = False,
    folded: bool = False,
) -> GramQuery:
    """Compile *pattern* into a conservative :class:`GramQuery`.

    Strategy:

    - ``fixed_strings=True`` → AND of every byte trigram in the literal
      pattern (the entire pattern is treated as a single literal run).
    - Otherwise, parse with :mod:`sre_parse` and traverse the AST:

      * Top-level alternation becomes an OR of per-branch queries; if any
        branch is unconstrained the whole OR collapses to ANY.
      * Quantified bodies whose minimum repetition is zero are dropped.
      * Inline scoped flags (``(?i:...)``, ``(?-i:...)``) are tracked through
        ``SUBPATTERN`` arguments so case-insensitive subtrees do not leak
        case-sensitive grams.
      * Lookarounds, anchors, character classes, backrefs, and unknown
        constructs flush the current literal run.
      * Unicode literals are NFC-normalized (and casefolded in folded mode)
        before encoding so the planner and indexer agree on the byte stream.

    No false negatives. Weaker predicates are always acceptable; unsoundness
    is not.
    """
    if not pattern:
        return GramAny()

    if fixed_strings:
        grams = grams_for_fixed_string(pattern, folded=folded)
        if not grams:
            return GramAny()
        return GramAnd(frozenset(grams))

    try:
        parsed = sre_parse.parse(pattern)
    except sre_constants.error:
        # Pattern doesn't compile — degrade to ANY rather than raise. The
        # authoritative Python regex compile will report the error to the
        # caller.
        return GramAny()
    except UnicodeEncodeError:
        # Lone surrogates or other non-encodable code points inside the
        # pattern. Degrade to ANY rather than raise.
        return GramAny()

    initial_flags = parsed.state.flags
    return _query_from_ast(list(parsed.data), folded=folded, flags=initial_flags)


__all__ = [
    "GRAM_KIND_FOLDED",
    "GRAM_KIND_RAW",
    "GRAM_SIZE",
    "GramAnd",
    "GramAny",
    "GramKind",
    "GramOr",
    "GramQuery",
    "build_code_gram_query",
    "fold_content",
    "grams_for_fixed_string",
    "iter_code_grams",
    "normalize_content",
    "pack_gram",
    "unique_code_grams",
    "unpack_gram",
]
