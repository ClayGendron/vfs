"""The listing cursor at the kernel: one page of ``ls``, ``tree`` or ``glob`` across every mount the listing reaches.

A caller pages a listing with ``after=`` and ``limit=``. The key is the
path of the last row of the page before, in the caller's namespace. One
listing can reach several mounts, so the kernel asks each of them for its
own page, from the key as that mount sees it, and merges the pages by the
frontier rule of :mod:`vfs.results.paging`:

    cursor = Cursor.opened("ls", after, limit)
    answer = await listing.listed(cursor.asking(ask), mount, "ls", path=rel)
    page = cursor.page(answer)

A storage that declares the ``listing_cursor`` trait receives ``after``
and ``limit`` and pages by itself. Any other storage is asked for its
whole listing, and the kernel cuts the page from it: a slower answer,
and the same rows. A mount that every row of the page lies before is not
asked at all. Rows the kernel adds itself, such as the row at a mount
point, obey the same key and the same frontier as the rows of a storage.

This module is not public. ``vfs.base`` opens a cursor for each paged call.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from vfs.paths import Path, local_after, rebase_overflows, resolve_path
from vfs.results import Result
from vfs.results.paging import FOREIGN_KEY, paged, resumes
from vfs.storage import SupportsTraits

if TYPE_CHECKING:
    from vfs.authority import Authority
    from vfs.mounts import AskStorage, Mount
    from vfs.ops import Op

ListingOp = Literal["ls", "tree", "glob"]

# ---------------------------------------------------------------------------
# The cursor of one call
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Cursor:
    """The page one call of ``ls``, ``tree`` or ``glob`` asks for, and the keys its storages gave back.

    ``after`` is the key, ``None`` at the first page, and ``limit`` the
    most rows the page holds, ``None`` for every row after the key.
    ``invalid`` says why the caller's key is no path, and is ``None``
    when it is one. ``keys`` gathers the key of each storage asked, in
    the kernel's coordinates, ``None`` for a storage that is finished.
    """

    op: ListingOp
    after: Path | None
    limit: int | None
    invalid: str | None = None
    keys: list[Path | None] = field(default_factory=list)

    @classmethod
    def opened(cls, op: ListingOp, after: str | None, limit: int | None) -> Cursor | None:
        """Return the cursor of a call that names ``after`` or ``limit``, and ``None`` for one that names neither."""
        if after is None:
            return None if limit is None else cls(op, None, limit)
        resolved = resolve_path(after)
        invalid = None if resolved.path is not None else f"after is no path: {resolved.error}"
        return cls(op, resolved.path, limit, invalid)

    def refusal(self, mount: Path | None = None, rel: Path | None = None) -> str | None:
        """Return why the key cannot resume this listing of ``rel`` in the mount at ``mount``, or ``None``.

        The key must be a path. For ``ls`` it must name a child of the
        directory, and for ``tree`` a path strictly beneath its root, both
        in that mount's coordinates and at the stored address, so a key
        under the trash view's head is read as the row it names. The head
        itself lists rows at every depth and takes any key in its mount.
        ``glob`` takes any key, because its rows are in one global order.
        The check is pure, so a foreign key costs no storage call.
        """
        if self.invalid is not None:
            return self.invalid
        if self.after is None or mount is None or rel is None:
            return None
        local = local_after(self.after, mount)
        if self.op == "glob" or (local.key is not None and resumes(self.op, str(rel), local.key)):
            return None
        return FOREIGN_KEY

    def asking(self, ask: AskStorage) -> AskStorage:
        """Return ``ask``, with each call of this cursor's verb turned into a call for that storage's page.

        Every other call passes through unchanged. A storage with no row
        after the key is not called, and counts as finished.
        """

        async def paged_ask(mount: Mount, op: Op, *, authority: Authority | None = None, **kwargs: Any) -> Result:
            if op != self.op:
                return await ask(mount, op, authority=authority, **kwargs)
            local = local_after(self.after, mount.path)
            if local.state == "past":
                self.keys.append(None)
                return Result(ops=(op,))
            if pages_itself(mount):
                answer = await ask(mount, op, authority=authority, after=local.key, limit=self.limit, **kwargs)
            else:
                whole = await ask(mount, op, authority=authority, **kwargs)
                answer = paged(whole, (), after=local.key, limit=self.limit)
            key = answer.next_after if answer.success else None
            # A key too long to rebase ends that mount's listing; the rebase of the answer records why.
            self.keys.append(None if key is None or rebase_overflows(mount.path, key) else key.with_mount(mount.path))
            return answer

        return paged_ask

    def page(self, result: Result) -> Result:
        """Return the merged ``result`` of this call cut to its page, with the page's key, by the frontier rule.

        A call that failed carries no key, so a caller never resumes
        a listing that did not answer.
        """
        if not result.success:
            return result.model_copy(update={"next_after": None})
        return paged(result, self.keys, after=self.after, limit=self.limit)


def pages_itself(mount: Mount) -> bool:
    """Return whether the storage of ``mount`` declares that it pages its own listings by key."""
    storage = mount.storage
    return isinstance(storage, SupportsTraits) and storage.traits().get("listing_cursor") == "keyset"
