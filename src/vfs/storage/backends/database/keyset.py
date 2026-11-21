"""Keyset pages of the listing verbs: the fill rule, and the keys a page may resume from.

A listing page seeks strictly after a key, in path order, and never
counts an offset. The key it hands back is always the path of a row on
the page, so it names nothing the caller was not shown. Python drops
some fetched rows (a row the caller may not name, a candidate the
compiled pattern refuses), so the last row fetched cannot be the key.
:func:`filled` fetches until the page is known:

1. The first batch is ``limit + 1`` rows from each stream.
2. While fewer than ``limit + 1`` rows are shown at or before the
   frontier and a stream has more, each such stream fetches again from
   its own last row, the batch twice the last, up to
   :data:`LISTING_FILL_CEILING`.
3. It stops at ``limit + 1`` shown rows or when every stream ran out.

A stream is one statement in path order: the children of one directory,
one subtree, one chunk of a glob's arms, or one clause of a view's
pushdown. With nothing dropped, a page is one statement per stream.
The fill bounds one statement's working set, and it is not a cap: the
page keeps filling until it is whole.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, Literal, NamedTuple

from vfs.paths import TRASH_ROOT, Path, address_of
from vfs.results import ErrorKind, Result, classified
from vfs.results.paging import frontier_page

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterable, Sequence

    from sqlalchemy.engine import RowMapping

    from vfs.models import Observation

    # One stream: the rows strictly after a path, in path order, at most a batch of them (``None`` for all).
    Fetch = Callable[[str | None, int | None], Awaitable[Sequence[RowMapping]]]
    # The rows shown from one fetched batch, in path order.
    Emit = Callable[[Sequence[RowMapping]], Awaitable[list[Observation]]]

# The most rows one fill statement fetches after the first: grep's verify pass reads as many at once.
LISTING_FILL_CEILING: Final = 10_000

# ---------------------------------------------------------------------------
# The fill rule
# ---------------------------------------------------------------------------


class Filled(NamedTuple):
    """The rows a fill showed, in path order, and its frontier: ``None`` once every stream ran out."""

    rows: list[Observation]
    frontier: str | None


async def filled(
    streams: Sequence[Fetch],
    emit: Emit,
    *,
    after: str | None,
    limit: int | None,
) -> Filled:
    """Fetch from ``streams`` until ``limit + 1`` shown rows lie at or before the frontier, or none has more.

    ``emit`` turns one batch of fetched rows into the rows shown from it,
    in path order. A row two streams both return is shown once. With
    ``limit=None`` each stream is read whole in one statement. The
    frontier is the last path the slowest unfinished stream fetched;
    every row at or before it is in hand. A fill after the first batch
    asks only the streams at the frontier.
    """
    positions: list[str | None] = [after] * len(streams)
    unfinished = list(range(len(streams)))
    shown: dict[str, Observation] = {}
    wanted = None if limit is None else limit + 1
    batch = wanted
    frontier: str | None = None
    due = list(unfinished)
    while due:
        for index in due:
            rows = await streams[index](positions[index], batch)
            for row in await emit(rows):
                shown.setdefault(row.path, row)
            if batch is None or len(rows) < batch:
                unfinished.remove(index)
            else:
                positions[index] = rows[-1]["path"]
        frontier = min((position for index in unfinished if (position := positions[index]) is not None), default=None)
        if wanted is None or batch is None or frontier is None or sum(path <= frontier for path in shown) >= wanted:
            break
        batch = min(2 * batch, LISTING_FILL_CEILING)
        # Only the streams at the frontier hold it back; one further ahead has nothing to add yet.
        due = [index for index in unfinished if positions[index] == frontier]
    return Filled([shown[path] for path in sorted(shown)], frontier if unfinished else None)


def keyed(
    rows: Iterable[Observation], frontier: str | None, *, after: str | None, limit: int | None
) -> tuple[list[Observation], Path | None]:
    """Return the page of ``rows`` under ``frontier`` and its key, by the frontier rule of :mod:`vfs.results.paging`."""
    page, key = frontier_page(rows, [frontier], after=after, limit=limit, path_of=_path)
    return page, None if key is None else Path._brand(key)


# ---------------------------------------------------------------------------
# The pages a listing may serve
# ---------------------------------------------------------------------------


def page_refused(
    op: Literal["ls", "tree", "glob"],
    targets: Sequence[Path],
    *,
    after: Path | None,
    limit: int | None,
    max_depth: int | None = None,
    max_count: int | None = None,
) -> Result | None:
    """Return the ``invalid`` refusal of a listing call the storage cannot serve, before it reads a row, or ``None``.

    A page holds at least one row and lists one target, and a ``glob``
    page takes no ``max_count``. The key of ``ls`` names a child of the
    directory, and the key of ``tree`` a path strictly beneath its root,
    both at the stored address, so a target under the trash view's head
    is read as the row it names. The head itself lists rows at every
    depth and takes any key, and so does ``glob``, whose rows are in one
    global order. A ``tree`` reaches at least one level.
    """
    detail = None
    if max_depth is not None and max_depth < 1:
        detail = f"max_depth must be >= 1, got {max_depth}"
    elif after is None and limit is None:
        return None
    elif limit is not None and limit < 1:
        detail = f"limit must be >= 1, got {limit}"
    elif max_count is not None:
        detail = "glob takes a page (after and limit) or max_count, not both"
    elif op != "glob" and len(targets) != 1:
        detail = "a page lists one directory"
    elif after is not None and op != "glob" and not _resumes(op, str(targets[0]), after):
        detail = "the key is not in this listing"
    return None if detail is None else Result(ops=(op,), errors=[classified(ErrorKind.invalid, detail=detail)])


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resumes(op: Literal["ls", "tree"], target: str, after: Path) -> bool:
    """Whether ``after`` is a key of this listing of ``target``: a child for ``ls``, beneath it for ``tree``."""
    if op == "ls" and target == TRASH_ROOT:
        return True
    stored = address_of(target).stored
    inside = after.parent_dir == stored if op == "ls" else stored == "/" or after.startswith(stored + "/")
    return inside and after != stored


def _path(row: Observation) -> str:
    """Return the path of a shown row."""
    return row.path
