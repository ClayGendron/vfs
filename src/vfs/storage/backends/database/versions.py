"""The version mint — the write path's one history writer.

A write that replaces a body keeps the body it replaced: an overwrite
of a live file, a revive of a tombstoned one, and an arbitration
clobber of a rival's row all land one ``vfs_versions`` row in the same
transaction, carrying the replaced body whole (text in ``content``,
bytes in ``data``; ``is_snapshot`` true, no diff form), the replaced
version as its number, the body's own hash, size and line count, and
the attribution of the authority that replaced it — actor, provenance,
source identity, the grant revision in force — with one
``vfs_version_subjects`` row per subject. Creates mint nothing; a row
with no body (a directory, a bytes row never rendered and never stored)
mints nothing; and a body replaced by an identical one mints nothing,
because nothing was lost — an agent rewriting an unchanged file leaves
no history behind.

The mint runs after the entry rows are updated — their locks held —
and before the bodies are replaced, so it reads the pre-image under the
same lock that guards the write. The pre-image's metrics are measured
from the body itself, never copied from the entry row: an arbitration
clobber has already overwritten that row's columns by the time the mint
runs. A row whose snapshot already joined its text body (an edit's)
mints from that copy: the guarded update proved the row unchanged since
the snapshot, so the copy is the pre-image and a second read would
fetch the same bytes. The rest are read one page at a time — a page is
bounded by the blob page's bytes, metered by each replaced body's size
at snapshot, and by the membership budget — and inserted in bulk, text
rows paged by the dialect's parameter budget and bytes rows by the blob
page, so a 10,000-file overwrite issues a bounded number of statements
and never holds more than one page of bodies in flight. A clobbered
rival's body has no size at snapshot and is metered at the whole page,
so it is read alone.

    minted = await mint_versions(session, tables, profile, budget, membership, replaced, authority=who, now=now)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from vfs.models.version import measure_bytes, measure_text
from vfs.storage.backends.database.dialects import BLOB_PAGE_BYTES, bulk_insert, byte_chunked, chunked
from vfs.storage.backends.database.membership import membership
from vfs.storage.backends.database.revision import read_revision

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.authority import Authority
    from vfs.models.rows import VFSTables
    from vfs.storage.backends.database.dialects import DialectProfile
    from vfs.storage.backends.database.staging import StagedEntry


# ---------------------------------------------------------------------------
# The mint
# ---------------------------------------------------------------------------


async def mint_versions(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    replaced: Sequence[StagedEntry],
    *,
    authority: Authority | None,
    now: datetime,
) -> int:
    """Keep the body each of *replaced* is about to lose as a version row; the count minted.

    Every staged row here has already taken its new version on the entry
    row, so the version it replaced is one below — the number the row
    records. A row whose body tables hold nothing mints nothing, and a
    body whose hash equals the one replacing it mints nothing.
    """
    if not replaced:
        return 0
    by_id = {staged.entry_id: staged for staged in replaced}
    revision = await read_revision(session, tables)
    ordered = [by_id[entry_id] for entry_id in sorted(by_id)]
    held = [(s.entry_id, s.base_content, None) for s in ordered if s.base_content is not None]
    minted = await _mint_rows(session, tables, held, by_id, authority=authority, revision=revision, now=now)
    unread = [s for s in ordered if s.base_content is None]
    for page in byte_chunked(unread, _pre_image_size, BLOB_PAGE_BYTES):
        for ids in chunked([staged.entry_id for staged in page], membership_budget):
            minted += await _mint_page(
                session, tables, profile, ids, by_id, authority=authority, revision=revision, now=now
            )
    return minted


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _mint_page(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    ids: Sequence[str],
    by_id: Mapping[str, StagedEntry],
    *,
    authority: Authority | None,
    revision: int,
    now: datetime,
) -> int:
    """Read one page of pre-image bodies and insert the version rows they earn; the count minted."""
    entry, content, blobs = tables.entry, tables.content, tables.blobs
    stmt = (
        select(entry.c.entry_id, content.c.content, blobs.c.data)
        .select_from(tables.bodies_joined(content=True, data=True))
        .where(membership(entry.c.entry_id, ids, profile))
    )
    bodies = [(row.entry_id, row.content, row.data) for row in await session.execute(stmt)]
    return await _mint_rows(session, tables, bodies, by_id, authority=authority, revision=revision, now=now)


async def _mint_rows(
    session: AsyncSession,
    tables: VFSTables,
    bodies: Sequence[tuple[str, str | None, bytes | None]],
    by_id: Mapping[str, StagedEntry],
    *,
    authority: Authority | None,
    revision: int,
    now: datetime,
) -> int:
    """Insert the version rows the pre-image *bodies* (entry_id, text, data) earn; the count minted."""
    texts: list[dict[str, object]] = []
    binaries: list[dict[str, object]] = []
    subjects: list[dict[str, object]] = []
    for entry_id, text, data in bodies:
        if text is None and data is None:
            continue
        staged = by_id[entry_id]
        number = staged.version - 1
        version = _version_row(entry_id, number, text, data, authority, revision, now)
        if version["content_hash"] == staged.content_hash:
            continue
        (binaries if data is not None else texts).append(version)
        subjects.extend(_subject_rows(entry_id, number, authority))
    if not texts and not binaries:
        return 0
    await bulk_insert(session, tables.versions, texts)
    for page in byte_chunked(binaries, _blob_size, BLOB_PAGE_BYTES):
        await bulk_insert(session, tables.versions, page)
    await bulk_insert(session, tables.version_subjects, subjects)
    return len(texts) + len(binaries)


def _version_row(
    entry_id: str,
    number: int,
    text: str | None,
    data: bytes | None,
    authority: Authority | None,
    revision: int,
    now: datetime,
) -> dict[str, object]:
    """One snapshot row: the body as stored, measured by the models' one law, attributed from *authority*."""
    if data is not None:
        # A bytes body's line count is its rendering's, the text beside it.
        metrics = measure_bytes(data, text)
    else:
        assert text is not None
        metrics = measure_text(text)
    return {
        "entry_id": entry_id,
        "version_number": number,
        "is_snapshot": True,
        "content_hash": metrics.content_hash,
        "lines": metrics.lines,
        "size_bytes": metrics.size_bytes,
        "actor": None if authority is None else authority.actor.sub,
        "provenance": None if authority is None else authority.provenance,
        "source_identity": None if authority is None else authority.source_identity,
        "grant_revision": revision,
        "created_at": now,
        "content": None if data is not None else text,
        "version_diff": None,
        "data": data,
    }


def _subject_rows(entry_id: str, number: int, authority: Authority | None) -> list[dict[str, object]]:
    """One side-table row per subject the write was done for; none under the system actor."""
    if authority is None:
        return []
    return [
        {"entry_id": entry_id, "version_number": number, "principal_id": principal}
        for principal in authority.subject_names
    ]


def _pre_image_size(staged: StagedEntry) -> int:
    """What a replaced body costs a read page: its size at snapshot, or a whole page when the snapshot never saw it."""
    return BLOB_PAGE_BYTES if staged.base_size_bytes is None else staged.base_size_bytes


def _blob_size(row: Mapping[str, object]) -> int:
    data = row["data"]
    assert isinstance(data, bytes)
    return len(data)
