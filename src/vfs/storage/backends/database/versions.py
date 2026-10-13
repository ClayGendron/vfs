"""The version mint — the write path's one history writer.

A write that replaces a body keeps the body it replaced: an overwrite
of a live file, a revive of a tombstoned one, and an arbitration
clobber of a rival's row all land one ``vfs_versions`` row in the same
transaction, carrying the replaced body whole (text in ``content``,
bytes in ``data``; ``is_snapshot`` true, no diff form), the replaced
version as its number, the body's own hash, size and line count, and
the attribution of the authority that replaced it — actor, provenance,
source identity, the grant revision in force — with one
``vfs_version_subjects`` row per subject. Creates mint nothing, and a
row with no body (a directory, a bytes row never rendered and never
stored) mints nothing.

The mint runs after the entry rows are updated — their locks held —
and before the bodies are replaced, so it reads the pre-image under the
same lock that guards the write. The pre-image's metrics are measured
from the body it reads, never copied from the entry row: an
arbitration clobber has already overwritten that row's columns by the
time the mint runs. Bodies are read one membership chunk at a time and
inserted in bulk, text rows paged by the dialect's parameter budget
and bytes rows by the blob page, so a 10,000-file overwrite issues a
bounded number of statements and holds one chunk of bodies in flight.

    minted = await mint_versions(session, tables, profile, budget, membership, replaced, authority=who, now=now)
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from sqlalchemy import select

from vfs.models.version import line_count
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
    records. A row whose body tables hold nothing mints nothing.
    """
    if not replaced:
        return 0
    entry, content, blobs = tables.entry, tables.content, tables.blobs
    by_id = {staged.entry_id: staged for staged in replaced}
    revision = await read_revision(session, tables)
    joined = tables.bodies_joined(content=True, data=True)
    minted = 0
    for ids in chunked(sorted(by_id), membership_budget):
        stmt = (
            select(entry.c.entry_id, content.c.content, blobs.c.data)
            .select_from(joined)
            .where(membership(entry.c.entry_id, ids, profile))
        )
        texts: list[dict[str, object]] = []
        binaries: list[dict[str, object]] = []
        subjects: list[dict[str, object]] = []
        for row in await session.execute(stmt):
            if row.content is None and row.data is None:
                continue
            number = by_id[row.entry_id].version - 1
            version = _version_row(row.entry_id, number, row.content, row.data, authority, revision, now)
            (binaries if row.data is not None else texts).append(version)
            subjects.extend(_subject_rows(row.entry_id, number, authority))
        await bulk_insert(session, tables.versions, texts)
        for page in byte_chunked(binaries, _blob_size, BLOB_PAGE_BYTES):
            await bulk_insert(session, tables.versions, page)
        await bulk_insert(session, tables.version_subjects, subjects)
        minted += len(texts) + len(binaries)
    return minted


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _version_row(
    entry_id: str,
    number: int,
    text: str | None,
    data: bytes | None,
    authority: Authority | None,
    revision: int,
    now: datetime,
) -> dict[str, object]:
    """One snapshot row: the body as stored, measured from itself, attributed from *authority*."""
    if data is not None:
        # A bytes body's line count is its rendering's, the text beside it.
        digest, size, lines = hashlib.sha256(data).hexdigest(), len(data), line_count(text or "")
    else:
        assert text is not None
        encoded = text.encode()
        digest, size, lines = hashlib.sha256(encoded).hexdigest(), len(encoded), line_count(text)
    return {
        "entry_id": entry_id,
        "version_number": number,
        "is_snapshot": True,
        "content_hash": digest,
        "lines": lines,
        "size_bytes": size,
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


def _blob_size(row: Mapping[str, object]) -> int:
    data = row["data"]
    assert isinstance(data, bytes)
    return len(data)
