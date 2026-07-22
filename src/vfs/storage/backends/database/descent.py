"""Descent classification and namespace scoping for database reads.

Two jobs, one chokepoint. :func:`classify_misses` is the shared descent
ladder: a target that missed resolution is classified by walking its
ancestor chain leftmost-first — a missing ancestor is ``not_found`` at
that component, an ancestor stored as a non-directory is ``wrong_kind``
there, and only when the whole parent chain is sound is the miss the
leaf's own ``not_found``. The first failing boundary wins and the walk
never looks ahead, so ancestor errors dominate leaf errors structurally.

:func:`liveness_filters` is the one-scope namespace filter enumeration
verbs apply: the ``/.vfs`` meta subtree is excluded from default-scope
enumeration, and a directly-addressed anchor inside it bypasses the
exclusion. Trash is an ordinary subtree under that meta scope — a
deleted file's original path reads as missing because the reparent
rewrote its path cache (stable-node-identity), not because any filter
hides the trash side.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from sqlalchemy import select

from vfs.paths import METADATA_ROOT, ROOT, Path
from vfs.results import ResultError, VFSErrorKind, classified
from vfs.storage.backends.database.dialects import chunked

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy import ColumnElement, Table
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
    return [_classify_miss(target, kinds) for target in targets]


def ancestor_chain(path: Path) -> list[Path]:
    """Proper ancestors of *path*, shallowest first, root excluded."""
    chain: list[Path] = []
    node = path.parent_dir
    while node != ROOT:
        chain.append(node)
        node = node.parent_dir
    return list(reversed(chain))


# ---------------------------------------------------------------------------
# Namespace scoping — the meta-scope liveness prefix filter
# ---------------------------------------------------------------------------


def liveness_filters(entry: Table, *, include_meta: bool) -> list[ColumnElement[bool]]:
    """Enumeration-scope predicates: meta hidden unless anchored inside it."""
    if include_meta:
        return []
    return [
        entry.c.path != METADATA_ROOT,
        ~entry.c.path.like(escape_like(METADATA_ROOT) + "/%", escape=LIKE_ESCAPE),
    ]


def escape_like(text: str) -> str:
    """Escape LIKE metacharacters so *text* matches only itself as a prefix."""
    return (
        text.replace(LIKE_ESCAPE, LIKE_ESCAPE + LIKE_ESCAPE)
        .replace("%", LIKE_ESCAPE + "%")
        .replace("_", LIKE_ESCAPE + "_")
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _classify_miss(target: Path, kinds: dict[str, str]) -> ResultError:
    for ancestor in ancestor_chain(target):
        kind = kinds.get(ancestor)
        if kind is None:
            return classified(VFSErrorKind.not_found, f"Not found: {ancestor}", ancestor, target=target)
        if kind != "directory":
            return classified(VFSErrorKind.wrong_kind, f"Not a directory: {ancestor}", ancestor, target=target)
    return classified(VFSErrorKind.not_found, f"Not found: {target}", target, target=target)
