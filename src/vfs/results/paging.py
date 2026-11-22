"""The one rule that turns several sorted streams of listing rows into one page.

A listing pages on a key: the path of the last row of a page. The next page
starts strictly after it. When one page is read from several streams at
once (several mounts, or several statements in one storage), each stream
returns its own rows in path order and its own key, or ``None`` when it
has nothing more. :func:`frontier_page` merges them:

    rows, key = frontier_page(rows, [stream_key, None], after=after, limit=1000, path_of=str)

The smallest key among the streams that are not finished is the
frontier. Every stream has handed over every row it holds up to its own
key, so every row at or before the frontier is in hand. The page keeps
those rows, in path order, and no row after the frontier. Nothing is
lost, because the next page starts after this page's key in every
stream. Nothing repeats, because every row on a page is at or before
its key. A row with no stream, such as a mount point the router adds,
obeys the same two bounds. With no stream at all the rule is the page
a storage derives from a whole listing: sort, cut after the key, keep
``limit``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, Literal, TypeVar

from vfs.paths import TRASH_ROOT, address_of

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from vfs.models import Observation
    from vfs.paths import Path
    from vfs.results.envelope import Result

T = TypeVar("T")

# The words of the refusal of a key that cannot resume the listing it was given to.
FOREIGN_KEY: Final = "the key is not in this listing"

# The words of the refusal of a glob that asks for a page and a max_count at once.
PAGE_BESIDE_MAX_COUNT: Final = "glob takes a page (after and limit) or max_count, not both"

# ---------------------------------------------------------------------------
# The frontier rule
# ---------------------------------------------------------------------------


def frontier_page(
    rows: Iterable[T],
    stream_keys: Iterable[str | None],
    *,
    after: str | None,
    limit: int | None,
    path_of: Callable[[T], str],
) -> tuple[list[T], str | None]:
    """Return one page of ``rows`` and its key, merged under the frontier of ``stream_keys``.

    ``rows`` holds what every stream returned for this page, in any
    order, and the rows that belong to no stream. A key of ``None`` is a
    finished stream. The page holds the rows strictly after ``after`` and
    at or before the frontier, in path order. When more than ``limit``
    remain, the page is the first ``limit`` and the key is the last of
    them. Otherwise the key is the frontier, which is ``None`` when every
    stream has finished. ``limit=None`` keeps every row in that range.
    """
    unfinished = [key for key in stream_keys if key is not None]
    frontier = min(unfinished) if unfinished else None
    kept = sorted(
        (
            row
            for row in rows
            if (after is None or path_of(row) > after) and (frontier is None or path_of(row) <= frontier)
        ),
        key=path_of,
    )
    if limit is not None and len(kept) > limit:
        kept = kept[:limit]
        return kept, path_of(kept[-1])
    return kept, frontier


def resumes(op: Literal["ls", "tree"], target: str, key: Path) -> bool:
    """Return whether ``key`` can resume this listing of ``target``, both in one storage's coordinates.

    The key of ``ls`` names a child of the directory, and the key of
    ``tree`` a path strictly beneath its root, both at the stored address,
    so a target under the trash view's head is read as the row it names.
    The head itself lists rows at every depth and takes any key. A
    ``glob`` takes any key, because its rows are in one global order, so
    it never asks.
    """
    if op == "ls" and target == TRASH_ROOT:
        return True
    stored = address_of(target).stored
    inside = key.parent_dir == stored if op == "ls" else stored == "/" or key.startswith(stored + "/")
    return inside and key != stored


def paged(result: Result, stream_keys: Iterable[Path | None], *, after: Path | None, limit: int | None) -> Result:
    """Return ``result`` cut to one page by :func:`frontier_page`, with the page's key as ``next_after``.

    A call that names neither ``after`` nor ``limit`` is no page, and
    ``result`` comes back as it is. The errors and the envelope are kept.
    """
    if after is None and limit is None:
        return result
    rows, key = frontier_page(result.observations, stream_keys, after=after, limit=limit, path_of=_path)
    return result.model_copy(update={"observations": rows, "next_after": key})


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _path(row: Observation) -> str:
    """Return the path of an observation row."""
    return row.path
