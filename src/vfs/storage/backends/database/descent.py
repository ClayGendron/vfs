"""Descent classification, bounded path fetches, and namespace scoping.

The shared idioms every database verb family leans on, named once.
:func:`classify_misses` is the shared descent ladder: a target that
missed resolution is classified by walking its ancestor chain
leftmost-first — a missing ancestor is ``not_found`` at that component,
an ancestor stored as a non-directory is ``wrong_kind`` there, and only
when the whole parent chain is sound is the miss the leaf's own
``not_found``. The first failing boundary wins and the walk never looks
ahead, so ancestor errors dominate leaf errors structurally.

:func:`rows_by_path` is the one bounded membership fetch — chunked
``path IN`` selects merged into a ``path → row`` map, so no statement
grows with batch size on any engine. :func:`subtree_filter` and
:func:`descendant_filter` are the one composition of the escaped
subtree ``LIKE`` — ``escape=`` is always explicit, and the helper owns
the ROOT branch, where naive prefix composition would produce ``//%``.
:func:`tombstone_side` is the one spelling of the tombstone term every
predicate carries, and :func:`tombstoned_roots` names the rows a delete
named.

:func:`liveness_filters` is the one-scope namespace filter enumeration
verbs apply: the tombstone term first — a deleted row stays at its own
path with ``deleted_at`` set, and every live enumeration carries
``deleted_at IS NULL``, every trash-view enumeration its negation —
then the ``/.vfs`` meta subtree, excluded from default-scope
enumeration unless the target is anchored inside it. A point verb
fetches without the term and classifies a tombstoned row as absent
through :func:`classify_miss`: ``not_found`` carrying the trashed hint
(:func:`trashed_hint`), so an agent knows ``restore`` applies, and a
tombstoned ancestor is ``not_found`` at that component for every
parent gate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import or_, select

from vfs.paths import METADATA_ROOT, ROOT, Path
from vfs.results import ErrorKind, ResultError, classified, wrong_kind
from vfs.storage.backends.database.dialects import chunked
from vfs.storage.backends.database.membership import membership

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence
    from datetime import datetime

    from sqlalchemy import ColumnElement, FromClause, Table
    from sqlalchemy.engine import RowMapping
    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.storage.backends.database.dialects import DialectProfile

LIKE_ESCAPE: Final = "\\"

# A tombstoned row's refusal carries these so an agent knows ``restore`` applies.
TRASHED_KEY: Final = "vfs.trashed"
DELETED_AT_KEY: Final = "vfs.deleted_at"
# A restore aimed inside a tombstoned tree names the root that restores it.
TRASH_ROOT_KEY: Final = "vfs.trash_root"


# ---------------------------------------------------------------------------
# Miss classification — the shared descent ladder
# ---------------------------------------------------------------------------


async def classify_misses(
    session: AsyncSession, entry: Table, targets: Sequence[Path], profile: DialectProfile, membership_budget: int
) -> list[ResultError]:
    """Classify every missed *target*; one chunked query of the targets and their ancestors serves the batch.

    A tombstoned row reads as absent: at the leaf the miss is
    ``not_found`` with the trashed hint, and a tombstoned ancestor is
    ``not_found`` at that component with the hint — no verb reaches a
    tombstoned row through its path, and ``restore`` is the answer.
    """
    kinds: dict[str, str] = {}
    tombstones: dict[str, datetime] = {}
    for chunk in chunked(sorted(targets_with_ancestors(targets)), membership_budget):
        stmt = select(entry.c.path, entry.c.kind, entry.c.deleted_at).where(membership(entry.c.path, chunk, profile))
        for row in await session.execute(stmt):
            if row.deleted_at is None:
                kinds[row.path] = row.kind
            else:
                tombstones[row.path] = row.deleted_at
    return [classify_miss(target, kinds, tombstones) for target in targets]


def classify_miss(
    target: Path, kinds: Mapping[str, str], tombstones: Mapping[str, datetime] | None = None
) -> ResultError:
    """The descent ladder against an already-fetched ``path → kind`` map of live rows.

    The pure half of :func:`classify_misses`, for callers that classify
    against a pinned snapshot rather than live state — a first failing
    boundary in the ancestor chain wins, then the leaf's own miss.
    *tombstones* names the tombstoned rows the caller may learn about,
    ``path → deleted_at``; a miss at one of them carries the hint.
    """
    found = tombstones or {}
    for ancestor in ancestor_chain(target):
        kind = kinds.get(ancestor)
        if kind is None:
            return tombstone_miss(ancestor, found.get(ancestor), target=target)
        if kind != "directory":
            return wrong_kind(kind, ancestor, target=target)
    return tombstone_miss(target, found.get(target))


def tombstone_miss(path: Path, deleted_at: datetime | None, *, target: Path | None = None) -> ResultError:
    """``not_found`` at *path* — with the trashed hint when a tombstoned row sits there."""
    if deleted_at is None:
        return classified(ErrorKind.not_found, path, target=target)
    return classified(ErrorKind.not_found, path, target=target, data=trashed_hint(deleted_at))


def trashed_hint(deleted_at: datetime) -> dict[str, object]:
    """The fields a refusal at a tombstoned row carries: the flag and the time of the delete."""
    return {TRASHED_KEY: True, DELETED_AT_KEY: deleted_at.isoformat()}


async def miss_errors(
    session: AsyncSession,
    entry: Table,
    targets: Sequence[Path],
    found: Mapping[str, object],
    profile: DialectProfile,
    membership_budget: int,
) -> dict[Path, ResultError]:
    """Descent-classified errors for each *target* absent from *found* — the live rows — keyed by target."""
    misses = [target for target in dict.fromkeys(targets) if str(target) not in found]
    return dict(zip(misses, await classify_misses(session, entry, misses, profile, membership_budget), strict=True))


def ancestor_chain(path: Path) -> list[Path]:
    """Proper ancestors of *path*, shallowest first, root excluded."""
    chain: list[Path] = []
    node = path.parent_dir
    while node != ROOT:
        chain.append(node)
        node = node.parent_dir
    return list(reversed(chain))


# ---------------------------------------------------------------------------
# Bounded fetch — the path-membership kernel
# ---------------------------------------------------------------------------


async def rows_by_path(
    session: AsyncSession,
    entry: Table,
    paths: Iterable[str],
    columns: Sequence[ColumnElement[Any]],
    profile: DialectProfile,
    membership_budget: int,
    *,
    source: FromClause | None = None,
) -> dict[str, RowMapping]:
    """Chunked ``path IN`` selects merged into a ``path → row`` map.

    *columns* must include ``entry.c.path`` — it keys the map. *source*
    replaces the implicit FROM when the projection joins another table
    (the content join). Deduplicated and sorted, so no statement grows
    with batch size and chunk boundaries are deterministic.
    """
    found: dict[str, RowMapping] = {}
    for chunk in chunked(sorted(set(paths)), membership_budget):
        stmt = select(*columns).where(membership(entry.c.path, chunk, profile))
        if source is not None:
            stmt = stmt.select_from(source)
        found.update({mapping["path"]: mapping for mapping in (await session.execute(stmt)).mappings()})
    return found


def targets_with_ancestors(targets: Iterable[Path]) -> set[str]:
    """Every target plus its proper ancestors and the root, as stored path strings."""
    batch = list(targets)
    ancestors = {str(ancestor) for target in batch for ancestor in ancestor_chain(target)}
    return {str(target) for target in batch} | ancestors | {"/"}


# ---------------------------------------------------------------------------
# Namespace scoping — subtree predicates and the meta liveness filter
# ---------------------------------------------------------------------------


def subtree_filter(entry: Table, root: str, profile: DialectProfile) -> ColumnElement[bool]:
    """*root* itself or any strict descendant, on the escaped path cache."""
    return or_(entry.c.path == root, descendant_filter(entry, root, profile))


def descendant_filter(entry: Table, root: str, profile: DialectProfile) -> ColumnElement[bool]:
    """Strict descendants of *root*, on the escaped path cache.

    Owns the ROOT branch: naive prefix composition would produce
    ``//%``, which matches nothing — under the root, every row but the
    root itself is a descendant.
    """
    if root == ROOT:
        return entry.c.path != str(ROOT)
    return entry.c.path.like(descendant_pattern(root, profile), escape=LIKE_ESCAPE)


def descendant_pattern(root: str, profile: DialectProfile) -> str:
    """The escaped ``LIKE`` pattern of *root*'s strict descendants — the one composition, for a bound pattern too."""
    return escape_like(root, profile) + "/%"


def tombstone_side(entry: FromClause, *, trashed: bool) -> ColumnElement[bool]:
    """The side of the tombstone a predicate wants its rows on: live, or tombstoned under the trash view. No bind."""
    return entry.c.deleted_at.is_not(None) if trashed else entry.c.deleted_at.is_(None)


def tombstoned_roots(entry: FromClause) -> ColumnElement[bool]:
    """The rows a delete named: a tombstoned root is its own ``trash_root_id``."""
    return entry.c.trash_root_id == entry.c.entry_id


def liveness_filters(
    entry: Table, profile: DialectProfile, *, include_meta: bool, trashed: bool = False
) -> list[ColumnElement[bool]]:
    """Enumeration-scope predicates: the tombstone term, then meta hidden unless anchored inside it.

    *trashed* flips the term for the trash view, which enumerates the
    tombstoned rows alone; the meta exclusion keeps its meaning either way.
    """
    terms: list[ColumnElement[bool]] = [tombstone_side(entry, trashed=trashed)]
    if not include_meta:
        terms += [entry.c.path != METADATA_ROOT, ~descendant_filter(entry, METADATA_ROOT, profile)]
    return terms


def escape_like(text: str, profile: DialectProfile) -> str:
    """Escape LIKE metacharacters so *text* matches only itself as a prefix.

    The metachar set is the dialect's: ``[`` opens a class only where
    the profile declares it (T-SQL), and escaping it elsewhere is
    itself an error (ORA-01424) — so the bracket escape is conditional.
    """
    escaped = (
        text.replace(LIKE_ESCAPE, LIKE_ESCAPE + LIKE_ESCAPE)
        .replace("%", LIKE_ESCAPE + "%")
        .replace("_", LIKE_ESCAPE + "_")
    )
    if profile.like_bracket_class:
        escaped = escaped.replace("[", LIKE_ESCAPE + "[")
    return escaped
