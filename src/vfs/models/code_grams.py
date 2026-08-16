"""Code-oriented byte-trigram tokenizer and conservative regex-to-gram planner.

This module is the database-agnostic primitive behind the portable code
search candidate index. It deliberately does NOT use ``pg_trgm``
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
   A small boolean algebra over required gram sets, derived by compiling
   Python's ``sre_parse`` regex AST into a bounded set of guaranteed-literal
   *variants*: small character classes fork one variant per post-fold
   member, alternations at any depth fork one variant per arm composed
   with their surrounding context, groups and zero-width anchors are
   adjacency-transparent. Expansion is bounded by two declared caps
   (``MAX_CLASS_MEMBERS``, ``MAX_VARIANT_WIDTH``); an over-cap expansion
   degrades that node to a plain adjacency break — a weaker predicate,
   never a refusal.

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
from typing import TYPE_CHECKING, Annotated, Any, Final

if TYPE_CHECKING:
    from collections.abc import Iterator

# The public sre_parse/sre_constants names are deprecated shims (3.11+); bind
# the real modules directly (typeshed has no stubs for them, hence the ignores).
from re import _constants as sre_constants  # ty: ignore[unresolved-import]
from re import _parser as sre_parse  # ty: ignore[unresolved-import]

GRAM_SIZE: Final = 3

# A character class forks at most this many post-fold members; larger
# classes keep their adjacency break (degrade, never refuse).
MAX_CLASS_MEMBERS: Final = 8

# Ceiling on the variant product, enforced at every cross step; deliberately
# equal to the glob compiler's MAX_PATTERN_ARMS so both surfaces degrade alike.
MAX_VARIANT_WIDTH: Final = 64

GramKey = Annotated[int, "packed 24-bit byte trigram: (b0 << 16) | (b1 << 8) | b2"]


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


def pack_gram(b0: int, b1: int, b2: int) -> GramKey:
    """Pack three bytes into a 24-bit integer key."""
    return (b0 << 16) | (b1 << 8) | b2


def unpack_gram(gram: GramKey) -> bytes:
    """Inverse of :func:`pack_gram`."""
    return bytes(((gram >> 16) & 0xFF, (gram >> 8) & 0xFF, gram & 0xFF))


def iter_byte_trigrams(data: bytes) -> Iterator[GramKey]:
    """Yield every sliding 3-byte trigram of raw *data*, duplicates kept.

    The byte-level primitive under :func:`iter_code_grams`; callers that
    already hold the folded, normalized byte stream start here.
    """
    if len(data) < GRAM_SIZE:
        return
    for i in range(len(data) - GRAM_SIZE + 1):
        yield pack_gram(data[i], data[i + 1], data[i + 2])


def _grams_from_run(run: bytes) -> set[GramKey]:
    return set(iter_byte_trigrams(run))


def iter_code_grams(content: str, *, folded: bool = False) -> Iterator[GramKey]:
    """Yield every sliding 3-byte UTF-8 trigram in *content*, in order.

    Duplicates are NOT collapsed; callers that want a set should use
    :func:`unique_code_grams`. Punctuation, whitespace, and operator bytes are
    intentionally preserved.
    """
    source = fold_content(content) if folded else content
    yield from iter_byte_trigrams(normalize_content(source))


def unique_code_grams(content: str, *, folded: bool = False) -> set[GramKey]:
    """Return the deduplicated set of byte trigrams in *content*."""
    return set(iter_code_grams(content, folded=folded))


def grams_for_fixed_string(pattern: str) -> set[GramKey]:
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

    def required_grams(self) -> set[GramKey]:
        return set()

    def is_any(self) -> bool:
        return True


@dataclass(frozen=True)
class GramAnd:
    """Conjunction: candidate chunks must contain ALL of these grams."""

    grams: frozenset[GramKey]

    def required_grams(self) -> set[GramKey]:
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

    def required_grams(self) -> set[GramKey]:
        out: set[GramKey] = set()
        for branch in self.branches:
            out |= branch.required_grams()
        return out

    def is_any(self) -> bool:
        return False


GramQuery = GramAny | GramAnd | GramOr


# ---------------------------------------------------------------------------
# Pattern planning — compile a regex into a conservative GramQuery
# ---------------------------------------------------------------------------


def build_code_gram_query(
    pattern: str,
    *,
    fixed_strings: bool = False,
) -> GramQuery:
    r"""Compile *pattern* into a conservative :class:`GramQuery`, always folded.

    There is no raw planning mode: the stored index is a single folded
    stream, so raw-pattern grams would silently miss (a false negative);
    case sensitivity is enforced by the caller's final regex verify.

    Strategy:

    - ``fixed_strings=True`` → AND of every byte trigram in the literal
      pattern (the entire pattern is treated as a single literal run).
    - Otherwise, parse with :mod:`sre_parse` and compile the AST into a
      bounded set of guaranteed-literal variants — one ``GramAnd`` per
      variant, ``GramOr`` across variants:

      * A character class whose members enumerate to at most
        ``MAX_CLASS_MEMBERS`` after folding forks one variant per member;
        negated classes, category escapes (``\w``, ``\d``), and larger
        classes break the run instead.
      * An alternation at any depth forks one variant per arm, composed
        with the surrounding literal context; groups are adjacency-
        transparent regardless of body.
      * Zero-width anchors (``^``, ``$``, ``\b``, ...) contribute no bytes
        and sever no adjacency (soundness argument at
        :func:`_node_fragments`).
      * The variant product is capped at ``MAX_VARIANT_WIDTH`` at every
        cross step; an over-cap expansion degrades that node to a plain
        adjacency break — a weaker predicate, never a refusal.
      * Quantified bodies whose minimum repetition is zero are dropped;
        bodies that appear at least once contribute their variants with
        adjacency severed on both sides.
      * Case flags (``(?i)``, ``(?i:...)``) need no tracking — folding
        already covers every case a literal could match. Lookarounds,
        backreferences, negations, and unknown constructs break the run.
      * A variant with no required grams collapses the whole query to
        ``GramAny`` — an OR with an unconstrained branch is unconstrained.
      * Each guaranteed-literal segment is folded as a whole before
        encoding — newline-normalized, Turkic-i-folded, casefolded; the
        same pipeline the indexer applies to content, and deliberately no
        NFC (module docstring) — so planner and indexer agree on the byte
        stream.

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

    return _fragment_query(_compile_seq(list(parsed.data)))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# One variant's guaranteed-literal shape: text segments whose first/last
# ends may still join adjacent literals; interior boundaries are severed.
_Fragment = tuple[str, ...]

# The give-up fragment: requires nothing, severs adjacency on both sides.
_BREAK: Final[_Fragment] = ("", "")

# The zero-width fragment: requires nothing, preserves adjacency.
_IDENTITY: Final[_Fragment] = ("",)


def _compile_seq(ast: list) -> list[_Fragment]:
    """Compile a flat AST sequence into its guaranteed-literal variants."""
    fragments: list[_Fragment] = [_IDENTITY]
    for op, arg in ast:
        fragments = _cross(fragments, _node_fragments(op, arg))
    return fragments


def _cross(fragments: list[_Fragment], node: list[_Fragment]) -> list[_Fragment]:
    """Concatenate every variant with every node fragment, deduped.

    The product is bounded at every step: if it would exceed
    ``MAX_VARIANT_WIDTH``, the node degrades to ``_BREAK`` — the
    accumulated variants survive, only the over-cap expansion is lost.
    """
    if len(fragments) * len(node) > MAX_VARIANT_WIDTH:
        node = [_BREAK]
    out: list[_Fragment] = []
    seen: set[_Fragment] = set()
    for fragment in fragments:
        for tail in node:
            joined = _concat(fragment, tail)
            if joined not in seen:
                seen.add(joined)
                out.append(joined)
    return out


def _node_fragments(op: Any, arg: Any) -> list[_Fragment]:
    """Variant fragments of one AST node; ``_BREAK`` is every conservative give-up.

    Zero-width assertions (``AT``) are identity fragments: they contribute
    no bytes and sever no adjacency. If a match exists, the literals
    flanking the assertion are byte-adjacent in it; a pattern the assertion
    makes unsatisfiable has no matches to lose, so requiring the joined
    grams is vacuously sound.
    """
    if op is sre_constants.LITERAL:
        char = _emit_literal(arg)
        return [_BREAK] if char is None else [(char,)]

    if op is sre_constants.IN:
        members = _class_members(arg)
        if members:
            return [(member,) for member in members]
        return [_BREAK]

    if op is sre_constants.AT:
        return [_IDENTITY]

    if op is sre_constants.BRANCH:
        _none, branches = arg
        arms: list[_Fragment] = []
        for branch in branches:
            arms.extend(_compile_seq(list(branch)))
            if len(arms) > MAX_VARIANT_WIDTH:
                return [_BREAK]
        return arms

    if op is sre_constants.SUBPATTERN:
        # SUBPATTERN payload: (group_id, add_flags, del_flags, body).
        # Scoped case flags are irrelevant to a folded-only planner.
        _group_id, _add_flags, _del_flags, body = arg
        return _compile_seq(list(body))

    if op is sre_constants.MAX_REPEAT or op is sre_constants.MIN_REPEAT:
        min_repeat, _max_repeat, body = arg
        if min_repeat == 0:
            # Body may not appear at all — drop it.
            return [_BREAK]
        # Body appears at least once; adjacency severed on both sides so we
        # never claim adjacency the repetition would break.
        return [_close(fragment) for fragment in _compile_seq(list(body))]

    # Everything else gives up conservatively: ANY and NOT_LITERAL match
    # unknown bytes; lookarounds and backrefs contribute no matched bytes;
    # unknown ops (ATOMIC_GROUP, POSSESSIVE_REPEAT, ...) are not descended
    # into because soundness cannot be guaranteed without their semantics.
    return [_BREAK]


def _class_members(items: list) -> list[str] | None:
    """Enumerate a class's members, deduped after folding; ``None`` = give up.

    Negated classes, category escapes, and classes whose raw or post-fold
    member count exceeds ``MAX_CLASS_MEMBERS`` all return ``None`` — the
    caller keeps the adjacency break.
    """
    raw: list[str] = []
    for op, arg in items:
        if op is sre_constants.LITERAL:
            char = _emit_literal(arg)
            if char is None:
                return None
            raw.append(char)
        elif op is sre_constants.RANGE:
            low, high = arg
            if high - low + 1 > MAX_CLASS_MEMBERS:
                return None
            for codepoint in range(low, high + 1):
                char = _emit_literal(codepoint)
                if char is None:
                    return None
                raw.append(char)
        else:
            # NEGATE, CATEGORY (\w, \d), nested set operations: give up.
            return None
    members: list[str] = []
    seen: set[str] = set()
    for char in raw:
        key = fold_content(char)
        if key not in seen:
            seen.add(key)
            members.append(char)
    if len(members) > MAX_CLASS_MEMBERS:
        return None
    return members


def _concat(head: _Fragment, tail: _Fragment) -> _Fragment:
    return (*head[:-1], head[-1] + tail[0], *tail[1:])


def _close(fragment: _Fragment) -> _Fragment:
    """Sever both open ends: the fragment's segments stand alone."""
    return ("", *fragment, "")


def _emit_literal(codepoint: int) -> str | None:
    """Return the literal codepoint as segment text, or ``None`` if unsafe.

    Case sensitivity never blocks a literal: planning is always folded, so
    the folded segment covers every case the pattern could match. Folding
    happens at gram extraction over each whole segment, through the same
    pipeline the indexer applies to content.
    """
    char = chr(codepoint)
    try:
        char.encode("utf-8")
    except UnicodeEncodeError:
        # Lone surrogates and other non-encodable code points cannot be
        # required as bytes in the index. Treat as opaque and give up.
        return None
    return char


def _encode_run(run: str) -> bytes:
    """Encode one literal segment exactly as the folded index stream is."""
    return normalize_content(fold_content(run))


def _fragment_query(fragments: list[_Fragment]) -> GramQuery:
    """Compile variants into the algebra: AND per variant, OR across variants.

    A variant with no grams collapses the whole query to ``GramAny`` — the
    collapse law: an OR with an unconstrained branch is unconstrained.
    Variants with identical gram sets dedupe to one branch.
    """
    branches: list[GramQuery] = []
    seen: set[frozenset[GramKey]] = set()
    for fragment in fragments:
        grams: set[GramKey] = set()
        for segment in fragment:
            if segment:
                grams |= _grams_from_run(_encode_run(segment))
        if not grams:
            return GramAny()
        key = frozenset(grams)
        if key not in seen:
            seen.add(key)
            branches.append(GramAnd(key))
    if len(branches) == 1:
        return branches[0]
    return GramOr(tuple(branches))


__all__ = [
    "GRAM_SIZE",
    "MAX_CLASS_MEMBERS",
    "MAX_VARIANT_WIDTH",
    "GramAnd",
    "GramAny",
    "GramKey",
    "GramOr",
    "GramQuery",
    "build_code_gram_query",
    "fold_content",
    "grams_for_fixed_string",
    "iter_byte_trigrams",
    "iter_code_grams",
    "normalize_content",
    "pack_gram",
    "unique_code_grams",
    "unpack_gram",
]
