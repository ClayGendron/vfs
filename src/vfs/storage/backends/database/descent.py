"""Descent classification and namespace scoping for database reads.

Two jobs, one chokepoint. :func:`classify_misses` is the shared descent
ladder: a target that missed resolution is classified by walking its
ancestor chain leftmost-first — a missing ancestor is ``not_found`` at
that component, an ancestor stored as a non-directory is ``wrong_kind``
there, and only when the whole parent chain is sound is the miss the
leaf's own ``not_found``. The first failing boundary wins and the walk
never looks ahead, so ancestor errors dominate leaf errors structurally.
A trashed ancestor reads as missing on both of its paths: the old path
was rewritten away, and the trash-prefixed one is filtered out of the
ancestor query — the walk never surfaces a kind point reads would hide.

:func:`liveness_filters` is the two-scope namespace filter enumeration
verbs apply: the trash subtree is always invisible, and the ``/.vfs``
meta subtree is excluded from default-scope enumeration while a
directly-addressed anchor inside it bypasses the meta exclusion — never
the trash one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from sqlalchemy import select

from vfs.paths import METADATA_ROOT, Path
from vfs.results import ResultError, VFSErrorKind
from vfs.storage.backends.database.dialects import chunked

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy import ColumnElement, Table
    from sqlalchemy.ext.asyncio import AsyncSession

ROOT = Path("/")

# The reserved internal prefix trashed rows' path caches live under.
# Ingress never admits it, so no gated Path can ever equal one.
TRASH_ROOT: Final = f"{METADATA_ROOT}/trash"

LIKE_ESCAPE: Final = "\\"


# ---------------------------------------------------------------------------
# Miss classification — the shared descent ladder
# ---------------------------------------------------------------------------


async def classify_misses(
    session: AsyncSession, entry: Table, targets: Sequence[Path], membership: int
) -> list[ResultError]:
    """Classify every missed *target*; one chunked ancestor query serves the batch.

    The ancestor query carries the trash scope too: descent through a
    trashed row must read it as missing, never surface its kind — else
    the walk leaks what point reads hide.
    """
    ancestors = {ancestor for target in targets for ancestor in ancestor_chain(target)}
    kinds: dict[str, str] = {}
    for chunk in chunked(sorted(ancestors), membership):
        stmt = select(entry.c.path, entry.c.kind).where(entry.c.path.in_(chunk), *trash_filters(entry))
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


def classified(
    kind: VFSErrorKind,
    message: str,
    path: Path | None = None,
    *,
    target: Path | None = None,
) -> ResultError:
    """One classified error; *target* names the requested row for merge dedup."""
    data = {"target": str(target)} if target is not None else None
    return ResultError(kind=kind, message=message, path=path, data=data)


# ---------------------------------------------------------------------------
# Namespace scoping — the two-scope liveness prefix filter
# ---------------------------------------------------------------------------


def liveness_filters(entry: Table, *, include_meta: bool) -> list[ColumnElement[bool]]:
    """Enumeration-scope predicates: trash always hidden, meta unless anchored inside."""
    filters = trash_filters(entry)
    if not include_meta:
        filters.append(entry.c.path != METADATA_ROOT)
        filters.append(~entry.c.path.like(escape_like(METADATA_ROOT) + "/%", escape=LIKE_ESCAPE))
    return filters


def trash_filters(entry: Table) -> list[ColumnElement[bool]]:
    """The unconditional scope: no verb ever surfaces a trashed row.

    Applied to point reads as well as enumeration — a directly-addressed
    meta path bypasses the meta exclusion but never this one, so a
    trashed row's rewritten path cache classifies ``not_found``.
    """
    return [
        entry.c.path != TRASH_ROOT,
        ~entry.c.path.like(escape_like(TRASH_ROOT) + "/%", escape=LIKE_ESCAPE),
    ]


def in_meta(path: Path) -> bool:
    """Whether *path* addresses into the reserved ``/.vfs`` meta subtree."""
    return path == METADATA_ROOT or path.startswith(METADATA_ROOT + "/")


def in_trash(path: Path) -> bool:
    """Whether *path* addresses into the reserved internal trash subtree.

    Ingress never admits these paths, but backends take bare ``Path``
    objects — a write allowed here would mint rows no read verb can see.
    """
    return path == TRASH_ROOT or path.startswith(TRASH_ROOT + "/")


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
