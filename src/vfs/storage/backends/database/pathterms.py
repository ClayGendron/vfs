"""Glob text to nomination terms — the term compiler and the allow-list seam.

The compiler turns each admission glob's canonical anchored form, per
brace expansion arm, into the facts nomination can use: literal path
components in directory position each contribute one **segment term**
(a lookup key into the segment posting table), and the arm's tail
contributes **column predicates** — the derived-extension fact and a
basename literal or stem-prefix name fact — for SQL pushdown into the
candidate fetch. Wildcard and class components contribute nothing.

Soundness is the one law every product obeys: a path matched by the
glob necessarily has every literal directory component among its
ancestor segments, its derived extension (or dot-suffix name) where
the tail pins one, and its leaf name equal to or prefixed by the
tail's literal — so the term conjunction **over-approximates** the
glob, position and order staying the compiled authority's job.
Nomination built on these terms may over-nominate and never
under-nominates; every survivor is re-checked by the compiled
``GlobFilter``. Exclusion channels never enter this module — pruning
by a superset of an exclusion would under-nominate — so the seam has
no exclusion input at all.

The allow-list: the admissions channel is an OR, so the entry-id set
is the union of per-arm sets, and it exists only while *every* arm
carries at least one segment term — the only term shape the posting
table can bound. One arm without segment terms voids pruning for the
whole call (its ``ext``/``name`` facts remain compiled here for the
fetch pushdown); a term that posts nothing yields an honestly empty
arm. Ids are the entries-table surrogate ids — the doc-id space the
gram postings already speak — via one indexed join per term.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Final, NamedTuple

from sqlalchemy import select

from vfs.pattern_matching import canonical_pattern, derive_ext, expand_pattern

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.models.rows import VFSTables
    from vfs.pattern_matching import DerivedExt

# Characters that make a pattern component non-literal: wildcards and
# the class opener (an unclosed "[" reads literally, but conservatively
# dropping the term only widens the superset).
_PATTERN_CHARS: Final = frozenset("*?[")

DocIds = Annotated[list[int], "sorted entries-table surrogate ids - the posting doc-id space"]


class NameFact(NamedTuple):
    """The leaf-name fact an arm's tail pins.

    ``prefix=False`` pins the whole name (``name = text``);
    ``prefix=True`` pins a literal head (``name LIKE text%``, sargable
    on the bytewise column).
    """

    text: str
    prefix: bool


@dataclass(frozen=True)
class ArmTerms:
    """One brace-free arm's nomination terms — always an over-approximation.

    ``segments`` are the literal directory-position components — every
    match carries each of them among its ancestor segments.  ``ext``
    and ``name`` are the tail's column facts for SQL pushdown.  An arm
    with no segment terms cannot be bounded by the posting table
    (``segment_bounded`` false) and voids the channel's allow-list.
    """

    pattern: str
    segments: frozenset[str]
    ext: DerivedExt | None
    name: NameFact | None

    @property
    def segment_bounded(self) -> bool:
        return bool(self.segments)


@dataclass(frozen=True)
class ChannelTerms:
    """The admissions channel compiled: an OR of arms, deduped in order.

    ``prunable`` is the allow-list's existence condition: at least one
    arm, and every arm segment-bounded — one unbounded arm voids
    pruning for the call, because the union would be unbounded.
    """

    arms: tuple[ArmTerms, ...]

    @property
    def prunable(self) -> bool:
        return bool(self.arms) and all(arm.segment_bounded for arm in self.arms)


# ---------------------------------------------------------------------------
# Term compilation — glob text to (segments, predicates)
# ---------------------------------------------------------------------------


def compile_terms(pattern: str) -> tuple[ArmTerms, ...]:
    """Compile one defect-free admission glob, one ``ArmTerms`` per brace arm.

    Input contract matches :func:`~vfs.pattern_matching.compile_glob`:
    the pattern is defect-gated upstream. Callers that pre-expand
    braces lose nothing — a brace-free pattern is its own single arm.
    """
    return tuple(_arm_terms(arm) for arm in expand_pattern(pattern))


def compile_channel(patterns: Sequence[str]) -> ChannelTerms:
    """Compile the whole admissions channel, patterns and arms deduped in order."""
    arms: dict[ArmTerms, None] = {}
    for pattern in dict.fromkeys(patterns):
        for arm in compile_terms(pattern):
            arms.setdefault(arm)
    return ChannelTerms(arms=tuple(arms))


# ---------------------------------------------------------------------------
# The allow-list seam — entry-id sets from the compiled channel
# ---------------------------------------------------------------------------


async def allow_list_ids(session: AsyncSession, tables: VFSTables, channel: ChannelTerms) -> DocIds | None:
    """The channel's nomination allow-list, or ``None`` when pruning is void.

    ``None`` — never an empty list — means the channel cannot bound
    nomination: no admission glob at all, or some arm without a segment
    term. Otherwise the union over arms of each arm's segment-posting
    intersection, resolved smallest-first so a dead term short-circuits
    its arm. Ids arrive per term through one indexed join
    (``segments → entries``) into the surrogate doc-id space and are
    returned sorted and deduped. The set is a superset by law —
    ``ext``/``name`` facts and the compiled authority narrow later.
    """
    if not channel.prunable:
        return None
    admitted: set[int] = set()
    for arm in channel.arms:
        admitted |= await _arm_ids(session, tables, arm)
    return sorted(admitted)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _arm_terms(arm: str) -> ArmTerms:
    """One brace-free arm's terms off its canonical anchored form."""
    canonical = canonical_pattern(arm)
    if "/" in canonical:
        components = canonical.split("/")
        directories = components[1:-1]
        leaf = components[-1]
    else:
        # A floating name-arm pattern matches leaf names at any depth.
        directories = []
        leaf = canonical
    segments = frozenset(component for component in directories if _is_literal(component))
    return ArmTerms(pattern=canonical, segments=segments, ext=derive_ext(canonical), name=_name_fact(leaf))


def _is_literal(component: str) -> bool:
    return bool(component) and not (_PATTERN_CHARS & set(component))


def _name_fact(leaf: str) -> NameFact | None:
    """The leaf's name fact: a whole literal, a literal head, or nothing.

    ``**`` spans whole segments and pins no name; a leaf with no
    literal head pins nothing. The head stops at the first wildcard or
    class opener — a class matching one literal character is treated
    as a wildcard, which only widens the superset.
    """
    if leaf == "**":
        return None
    if _is_literal(leaf):
        return NameFact(text=leaf, prefix=False)
    head = leaf[: min(index for index, char in enumerate(leaf) if char in _PATTERN_CHARS)]
    if not head:
        return None
    return NameFact(text=head, prefix=True)


async def _arm_ids(session: AsyncSession, tables: VFSTables, arm: ArmTerms) -> set[int]:
    """One arm's doc ids: per-term indexed joins, intersected smallest-first."""
    postings = [await _term_ids(session, tables, term) for term in sorted(arm.segments)]
    postings.sort(key=len)
    ids = postings[0]
    for other in postings[1:]:
        if not ids:
            break
        ids &= other
    return ids


async def _term_ids(session: AsyncSession, tables: VFSTables, term: str) -> set[int]:
    """One segment term's posting, joined into the surrogate doc-id space."""
    segments, entry = tables.segments, tables.entry
    joined = segments.join(entry, segments.c.entry_id == entry.c.entry_id)
    stmt = select(entry.c.id).select_from(joined).where(segments.c.segment == term)
    return {row.id for row in await session.execute(stmt)}
