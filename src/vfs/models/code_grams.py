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
   Raw byte trigram extraction from newline-normalized UTF-8 content.

2. ``grams_for_fixed_string``
   Required byte trigrams for a fixed-string grep pattern.

3. ``GramQuery`` + ``build_code_gram_query``
   A small boolean algebra over required gram sets, derived from a traversal
   of Python's ``sre_parse`` regex AST.

The stored index is a **single folded stream**: index maintenance always
extracts with ``folded=True``, and case sensitivity is enforced by the final
regex verify, never by the index. **The query planner always plans folded** —
there is no raw query path, because raw-pattern grams do not exist in a
folded stream (a silent false negative); the tokenizer's ``folded`` parameter
exists for the content-indexing side.

The stream is **raw codepoints, folded** — newline-normalized,
Turkic-i-folded (U+0131 dotless i and U+0130 dotted I map to ASCII ``i``),
casefolded, UTF-8 encoded. There is deliberately **no Unicode
normalization** (NFC/NFD): the authoritative
matcher is Python ``re`` over raw content, which is codepoint-exact and
never unifies canonically-equivalent forms — while NFC is not
substring-stable, so a normalized index stream can lack the grams of a span
``re`` matches in raw content (a false negative). zoekt, codesearch, and
pg_trgm all index un-normalized streams for the same reason.

The fold exists to satisfy one invariant: **every codepoint pair that
``re.IGNORECASE`` treats as equal folds to identical text** — the candidate
fold is a superset of the verifier's case orbit, so case-insensitive matches
are never pruned before the verify. ``str.casefold`` covers every such pair
except the Turkic-i family: sre's simple-case orbit (plus its
``_EXTRA_CASES`` table) unifies U+0131 (dotless i) and U+0130 (dotted I)
with ASCII ``i``, and ``casefold`` does neither — hence the pre-fold. The
invariant is pinned by an exhaustive orbit-scan test.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterator

# The public sre_parse/sre_constants names are deprecated shims (3.11+); bind
# the real modules directly (typeshed has no stubs for them, hence the ignores).
from re import _constants as sre_constants  # ty: ignore[unresolved-import]
from re import _parser as sre_parse  # ty: ignore[unresolved-import]

GRAM_SIZE: Final = 3


def normalize_content(content: str) -> bytes:
    """Return UTF-8 bytes after newline normalization — nothing else.

    Deliberately no Unicode normalization: the index stream must contain
    the same codepoints the raw-content regex verify sees (module docstring).
    """
    if "\r" in content:
        content = content.replace("\r\n", "\n").replace("\r", "\n")
    return content.encode("utf-8")


def fold_content(content: str) -> str:
    """Return the folded form of *content* used for the folded gram stream.

    The one shared fold for indexer and planner: Turkic-i pre-fold, then
    ``casefold``. The pre-fold covers sre's simple-case orbit, which unifies
    U+0131 (dotless i) and U+0130 (dotted I) with ASCII ``i`` where
    ``casefold`` does not (U+0130 must map before casefold explodes it to
    ``i`` + U+0307).
    """
    if not content.isascii():
        content = content.replace("\u0131", "i").replace("\u0130", "i")
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


def grams_for_fixed_string(pattern: str) -> set[int]:
    """Return required byte trigrams for a fixed-string grep pattern, folded.

    Pattern-side extraction is always folded — the stored index is a single
    folded stream, and case sensitivity belongs to the final verify. Strings
    shorter than 3 bytes after normalization and folding have no required
    grams; the candidate query must fall back to ``ANY`` for those.
    """
    return unique_code_grams(pattern, folded=True)


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


def _emit_literal(codepoint: int) -> str | None:
    """Return the literal codepoint as run text, or ``None`` if unsafe.

    Case sensitivity never blocks a literal: planning is always folded, so
    the folded run covers every case the pattern could match. Folding
    happens at flush time over the whole run, through the same pipeline the
    indexer applies to content.
    """
    char = chr(codepoint)
    try:
        char.encode("utf-8")
    except UnicodeEncodeError:
        # Lone surrogates and other non-encodable code points cannot be
        # required as bytes in the index. Treat as opaque and flush the run.
        return None
    return char


def _encode_run(run: str) -> bytes:
    """Encode one literal run exactly as the folded index stream is encoded."""
    return normalize_content(fold_content(run))


def _pure_literal_text(ast: list) -> str | None:
    """Literal text of *ast* when every node is a guaranteed literal.

    Descends through nested groups whose bodies are themselves pure
    literal. Returns ``None`` as soon as any node could match bytes other
    than one fixed sequence — including a lone-surrogate literal that
    cannot be required as index bytes.
    """
    parts: list[str] = []
    for op, arg in ast:
        if op is sre_constants.LITERAL:
            char = _emit_literal(arg)
            if char is None:
                return None
            parts.append(char)
            continue
        if op is sre_constants.SUBPATTERN:
            inner = _pure_literal_text(list(arg[3]))
            if inner is None:
                return None
            parts.append(inner)
            continue
        return None
    return "".join(parts)


def _collect_runs(ast: list) -> list[str]:
    """Walk a flat AST sequence and return its guaranteed-literal text runs.

    Runs are kept as text so the shared fold applies to each whole run at
    gram extraction. Each run is a maximal contiguous sequence every match
    must contain.
    """
    runs: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        if buf:
            runs.append("".join(buf))
            buf.clear()

    for op, arg in ast:
        if op is sre_constants.LITERAL:
            char = _emit_literal(arg)
            if char is None:
                flush()
            else:
                buf.append(char)
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
                runs.extend(_collect_runs(list(body)))
            continue

        if op is sre_constants.SUBPATTERN:
            # SUBPATTERN payload: (group_id, add_flags, del_flags, body).
            # Scoped case flags are irrelevant to a folded-only planner.
            _group_id, _add_flags, _del_flags, body = arg
            literal = _pure_literal_text(list(body))
            if literal is not None:
                # Only a pure-literal (or empty) body is adjacency-
                # transparent: the group matches exactly these bytes.
                buf.append(literal)
                continue
            # Any other body may match bytes its inner runs don't cover, so
            # adjacency breaks on both sides; the runs stand alone.
            flush()
            runs.extend(_collect_runs(list(body)))
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
    return runs


def _grams_from_runs(runs: list[str]) -> set[int]:
    out: set[int] = set()
    for run in runs:
        out |= _grams_from_run(_encode_run(run))
    return out


def _query_from_ast(ast: list) -> GramQuery:
    """Compile a flat AST sequence into a :class:`GramQuery`.

    Top-level alternation is split here. Otherwise, required grams are
    collected from guaranteed literal runs.
    """
    # Detect top-level alternation: the AST is exactly ``[(BRANCH, (None, [
    # branch1, branch2, ... ]))]``.
    if len(ast) == 1 and ast[0][0] is sre_constants.BRANCH:
        # A parsed BRANCH always holds two or more alternatives.
        _none, branches = ast[0][1]
        compiled: list[GramQuery] = []
        for branch in branches:
            sub = _query_from_ast(list(branch))
            if isinstance(sub, GramAny):
                # An OR with an unconstrained branch is unconstrained.
                return GramAny()
            compiled.append(sub)
        return GramOr(tuple(compiled))

    grams = _grams_from_runs(_collect_runs(ast))
    if not grams:
        return GramAny()
    return GramAnd(frozenset(grams))


def build_code_gram_query(
    pattern: str,
    *,
    fixed_strings: bool = False,
) -> GramQuery:
    """Compile *pattern* into a conservative :class:`GramQuery`, always folded.

    There is no raw planning mode: the stored index is a single folded
    stream, so raw-pattern grams would silently miss (a false negative);
    case sensitivity is enforced by the caller's final regex verify.

    Strategy:

    - ``fixed_strings=True`` → AND of every byte trigram in the literal
      pattern (the entire pattern is treated as a single literal run).
    - Otherwise, parse with :mod:`sre_parse` and traverse the AST:

      * Top-level alternation becomes an OR of per-branch queries; if any
        branch is unconstrained the whole OR collapses to ANY.
      * A group splices into the surrounding literal run only when its
        body is pure literal (nested literal groups included); any other
        body breaks adjacency on both sides and contributes its inner
        runs standalone.
      * Quantified bodies whose minimum repetition is zero are dropped.
      * Case flags (``(?i)``, ``(?i:...)``) need no tracking — folding
        already covers every case a literal could match.
      * Lookarounds, anchors, character classes, backrefs, and unknown
        constructs flush the current literal run.
      * Each guaranteed-literal run is folded as a whole before encoding —
        newline-normalized, Turkic-i-folded, casefolded; the same pipeline
        the indexer applies to content, and deliberately no NFC (module
        docstring) — so planner and indexer agree on the byte stream.

    No false negatives. Weaker predicates are always acceptable; unsoundness
    is not.
    """
    if not pattern:
        return GramAny()

    if fixed_strings:
        grams = grams_for_fixed_string(pattern)
        if not grams:
            return GramAny()
        return GramAnd(frozenset(grams))

    try:
        parsed = sre_parse.parse(pattern)
    except (sre_constants.error, UnicodeEncodeError):
        # A pattern that doesn't parse degrades to ANY rather than raising —
        # the authoritative Python regex compile reports the error to the
        # caller (compile-first discipline).
        return GramAny()

    return _query_from_ast(list(parsed.data))


__all__ = [
    "GRAM_SIZE",
    "GramAnd",
    "GramAny",
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
