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

:func:`liveness_filters` is the one-scope namespace filter enumeration
verbs apply: the ``/.vfs`` meta subtree is excluded from default-scope
enumeration, and a directly-addressed target inside it bypasses the
exclusion. Trash is an ordinary subtree under that meta scope — a
deleted file's original path reads as missing because the reparent
rewrote its path cache (stable-node-identity), not because any filter
hides the trash side.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import or_, select

from vfs.paths import METADATA_ROOT, ROOT, Path
from vfs.results import ResultError, VFSErrorKind, classified
from vfs.storage.backends.database.dialects import chunked

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from sqlalchemy import ColumnElement, FromClause, Table
    from sqlalchemy.engine import RowMapping
    from sqlalchemy.ext.asyncio import AsyncSession

LIKE_ESCAPE: Final = "\\"


# ---------------------------------------------------------------------------
# Miss classification — the shared descent ladder
# ---------------------------------------------------------------------------


async def classify_misses(
    session: AsyncSession, entry: Table, targets: Sequence[Path], membership_budget: int
) -> list[ResultError]:
    """Classify every missed *target*; one chunked ancestor query serves the batch."""
    ancestors = {ancestor for target in targets for ancestor in ancestor_chain(target)}
    kinds: dict[str, str] = {}
    for chunk in chunked(sorted(ancestors), membership_budget):
        stmt = select(entry.c.path, entry.c.kind).where(entry.c.path.in_(chunk))
        kinds.update({row.path: row.kind for row in await session.execute(stmt)})
    return [classify_miss(target, kinds) for target in targets]


def classify_miss(target: Path, kinds: Mapping[str, str]) -> ResultError:
    """The descent ladder against an already-fetched ``path → kind`` map.

    The pure half of :func:`classify_misses`, for callers that classify
    against a pinned snapshot rather than live state — a first failing
    boundary in the ancestor chain wins, then the leaf's own miss.
    """
    for ancestor in ancestor_chain(target):
        kind = kinds.get(ancestor)
        if kind is None:
            return classified(VFSErrorKind.not_found, f"Not found: {ancestor}", ancestor, target=target)
        if kind != "directory":
            return classified(VFSErrorKind.wrong_kind, f"Not a directory: {ancestor}", ancestor, target=target)
    return classified(VFSErrorKind.not_found, f"Not found: {target}", target, target=target)


async def miss_errors(
    session: AsyncSession,
    entry: Table,
    targets: Sequence[Path],
    found: Mapping[str, object],
    membership_budget: int,
) -> dict[Path, ResultError]:
    """Descent-classified errors for each *target* absent from *found*, keyed by target."""
    misses = [target for target in dict.fromkeys(targets) if str(target) not in found]
    return dict(zip(misses, await classify_misses(session, entry, misses, membership_budget), strict=True))


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
        stmt = select(*columns).where(entry.c.path.in_(chunk))
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


def subtree_filter(entry: Table, root: str) -> ColumnElement[bool]:
    """*root* itself or any strict descendant, on the escaped path cache."""
    return or_(entry.c.path == root, descendant_filter(entry, root))


def descendant_filter(entry: Table, root: str) -> ColumnElement[bool]:
    """Strict descendants of *root*, on the escaped path cache.

    Owns the ROOT branch: naive prefix composition would produce
    ``//%``, which matches nothing — under the root, every row but the
    root itself is a descendant.
    """
    if root == ROOT:
        return entry.c.path != str(ROOT)
    return entry.c.path.like(escape_like(root) + "/%", escape=LIKE_ESCAPE)


def liveness_filters(entry: Table, *, include_meta: bool) -> list[ColumnElement[bool]]:
    """Enumeration-scope predicates: meta hidden unless anchored inside it."""
    if include_meta:
        return []
    return [
        entry.c.path != METADATA_ROOT,
        ~descendant_filter(entry, METADATA_ROOT),
    ]


def escape_like(text: str) -> str:
    """Escape LIKE metacharacters so *text* matches only itself as a prefix."""
    return (
        text.replace(LIKE_ESCAPE, LIKE_ESCAPE + LIKE_ESCAPE)
        .replace("%", LIKE_ESCAPE + "%")
        .replace("_", LIKE_ESCAPE + "_")
    )
