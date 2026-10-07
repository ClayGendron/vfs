"""The render stage of ``reindex`` — bytes entries to text renderings in short, resumable pages.

A bytes entry's text is a rendering made by a per-format renderer and
written to the content row under the same entry id, so chunking, the
gram index, grep, glean and permissions see it as they see any text.
The rendering is stamped on the entry row with the bytes hash and the
renderer's generation (``render_source_hash``, ``render_generation``),
and the fingerprint-skip law decides re-rendering exactly as it does
for chunks and links: same bytes under the same generation, nothing
to do; a generation bump (a renderer or library upgrade, an extra
installed) re-dirties every entry of that type on the next run.

The stage runs first in the reindex pass, under the lease, before the
chunk pass that will split the new text. It is a streaming loop like
the embed step: a short read selects one keyset page of dirty bytes
rows, the page is cut by bytes in flight, each cut's blobs are read,
rendered off the event loop with no transaction open, and landed in
one short write. **Dedup**: two entries with the same bytes under the
same generation render once — a settled twin already on a row lends
its rendering, and a twin inside the page is rendered once for both.
**The guarded landing**: the stamp is written
only where the row still holds the bytes it was rendered from and does
not already carry this exact stamp, so a bytes change in flight is a
miss (the write that changed them reset the row to pending) and a
rival's identical write is a no-op, each proven by the row's own
rowcount; the lease, checked before every landing, is what keeps a
straggler's generation from overwriting a rival's, since no stamp
guard can order two generation strings. A landing the engine refuses
is retried row by row, and a row still refused lands as ``failed``
with the engine's reason, so one bad row never stops the mount. The landing also resets the
chunk stamp of every row it writes: the chunk pass had stamped the
pending row as chunked-and-ineligible under its bytes hash, and the
new text must split in the same run.

Failure is a state, never a body: every status but ``ok``,
``truncated`` and ``partial`` lands with no content row, its reason in
``render_detail``, and the skip law keeps it from being retried until
the bytes or the generation change.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final, NamedTuple, cast

from sqlalchemy import bindparam, case, delete, func, or_, select, update

from vfs.models.media import RENDERED_STATUSES, SETTLED_STATUSES
from vfs.rendering.seam import UNSUPPORTED_GENERATION, Rendering, RenderSource, units_from_json, units_to_json
from vfs.results import Result
from vfs.storage.backends.database.dialects import BLOB_PAGE_BYTES, bulk_insert, byte_chunked, chunked
from vfs.storage.backends.database.membership import membership

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from sqlalchemy.engine import CursorResult
    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.models.rows import VFSTables
    from vfs.rendering.registry import RendererRegistry
    from vfs.rendering.seam import RenderLimits
    from vfs.storage.backends.database.dialects import DialectProfile

RENDER_PAGE_ROWS: Final = 256
"""Dirty bytes rows one short read selects — bounds the loop's residency, never the corpus."""


class RenderRow(NamedTuple):
    """One dirty bytes entry: its keyset id, identity, name, type, bytes hash and size."""

    id: int
    entry_id: str
    name: str
    mime: str
    content_hash: str
    size_bytes: int

    def key(self, registry: RendererRegistry) -> tuple[str, str]:
        """The twin key: the bytes hash and the generation this row's type stamps today."""
        return self.content_hash, registry.generation(self.mime)


class Rendered(NamedTuple):
    """One rendering ready to land: the row it is for, the stamp it carries, how it was made."""

    entry_id: str
    content_hash: str
    generation: str
    rendering: Rendering
    cached: bool


@dataclass
class RenderReport:
    """What the stage did — the ``rendering`` extra on the reindex result.

    Every row the stage landed is counted exactly once: ``rendered``
    (text served: ok, truncated or partial), ``empty`` (parsed, no
    text), ``unsupported`` (no renderer, or its extra absent),
    ``failed`` (encrypted, corrupt, or the renderer refused), or
    ``cached`` (any verdict borrowed from a twin, text or failure).
    ``unrendered`` is the live bytes rows still pending when the stage
    ended — nonzero only when a landing was skipped or refused.
    """

    rendered: int = 0
    empty: int = 0
    unsupported: int = 0
    failed: int = 0
    cached: int = 0
    unrendered: int = 0

    def record(self, item: Rendered) -> None:
        """Count one landed rendering under the one field it belongs to."""
        status = item.rendering.status
        if item.cached:
            self.cached += 1
        elif status in RENDERED_STATUSES:
            self.rendered += 1
        elif status == "empty":
            self.empty += 1
        elif status in ("unsupported", "unavailable"):
            self.unsupported += 1
        else:
            self.failed += 1

    @property
    def touched(self) -> bool:
        return any(self.as_extra().values())

    def as_extra(self) -> dict[str, Any]:
        return {
            "rendered": self.rendered,
            "empty": self.empty,
            "unsupported": self.unsupported,
            "failed": self.failed,
            "cached": self.cached,
            "unrendered": self.unrendered,
        }


# ---------------------------------------------------------------------------
# Selection — the dirty page, its twins, its bytes
# ---------------------------------------------------------------------------


async def select_render_dirty(
    session: AsyncSession, tables: VFSTables, claims: Mapping[str, str], after: int, limit: int
) -> list[RenderRow]:
    """The next *limit* live bytes rows past *after* whose stamp pair misses, ascending id.

    A stamp misses when it is absent, differs from the generation the
    row's own media type resolves to today (*claims* is the registry's
    ``type → generation`` table; an unclaimed type expects the
    unsupported mark, so a type newly claimed re-dirties its rows), or
    was made from other bytes. The CASE is renderer-sized, never
    corpus-sized.
    """
    entry = tables.entry
    stale = or_(
        entry.c.render_generation.is_(None),
        entry.c.render_generation != expected_generation(entry, claims),
        entry.c.render_source_hash.is_(None),
        entry.c.render_source_hash != entry.c.content_hash,
    )
    stmt = (
        select(entry.c.id, entry.c.entry_id, entry.c.name, entry.c.mime_type, entry.c.content_hash, entry.c.size_bytes)
        .where(entry.c.source == "bytes", entry.c.deleted_at.is_(None), entry.c.id > after, stale)
        .order_by(entry.c.id)
        .limit(limit)
    )
    return [
        RenderRow(row.id, row.entry_id, row.name, row.mime_type, row.content_hash, row.size_bytes)
        for row in await session.execute(stmt)
    ]


async def cached_renderings(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    hashes: Sequence[str],
    claims: Mapping[str, str],
) -> dict[tuple[str, str], Rendering]:
    """One settled rendering per ``(bytes hash, generation)`` that some entry already carries.

    A rendered status lends its text from the content row; a failure
    state lends its verdict, so a corrupt file copied a thousand times
    is parsed once. Two chunked probes: the lowest donor id per key,
    then those rows alone — so a hash shared by a thousand copies costs
    one rendering's text, not a thousand. A donor is a row whose stamp
    is current and, for a rendered status, whose content row exists.
    """
    entry, content = tables.entry, tables.content
    generations = sorted({*claims.values(), UNSUPPORTED_GENERATION})
    joined = entry.outerjoin(content, content.c.entry_id == entry.c.entry_id)
    donors: list[int] = []
    for page in chunked(sorted(set(hashes)), membership_budget):
        lowest = (
            select(func.min(entry.c.id))
            .select_from(joined)
            .where(
                membership(entry.c.content_hash, page, profile),
                entry.c.source == "bytes",
                entry.c.render_source_hash == entry.c.content_hash,
                entry.c.render_generation.in_(generations),
                entry.c.render_status.in_(sorted(SETTLED_STATUSES)),
                or_(entry.c.render_status.not_in(sorted(RENDERED_STATUSES)), content.c.entry_id.isnot(None)),
            )
            .group_by(entry.c.content_hash, entry.c.render_generation)
        )
        donors.extend((await session.execute(lowest)).scalars())
    found: dict[tuple[str, str], Rendering] = {}
    for ids in chunked(sorted(donors), membership_budget):
        stmt = (
            select(
                entry.c.content_hash,
                entry.c.render_generation,
                entry.c.render_status,
                entry.c.render_detail,
                entry.c.render_units,
                entry.c.media_width,
                entry.c.media_height,
                content.c.content,
            )
            .select_from(joined)
            .where(membership(entry.c.id, ids, profile))
        )
        for row in await session.execute(stmt):
            found[row.content_hash, row.render_generation] = Rendering(
                row.render_status,
                row.content,
                units_from_json(row.render_units),
                row.render_detail,
                row.media_width,
                row.media_height,
            )
    return found


def expected_generation(entry: Any, claims: Mapping[str, str]) -> Any:
    """The generation a row's media type stamps today, as one renderer-sized CASE expression."""
    if not claims:
        return UNSUPPORTED_GENERATION
    return case(dict(claims), value=entry.c.mime_type, else_=UNSUPPORTED_GENERATION)


async def load_blobs(
    session: AsyncSession, tables: VFSTables, profile: DialectProfile, membership_budget: int, entry_ids: Sequence[str]
) -> dict[str, bytes]:
    """``entry_id → bytes`` for one cut of the page — the cut is already bytes-bounded."""
    blobs = tables.blobs
    out: dict[str, bytes] = {}
    for ids in chunked(sorted(set(entry_ids)), membership_budget):
        stmt = select(blobs.c.entry_id, blobs.c.data).where(membership(blobs.c.entry_id, ids, profile))
        out.update({row.entry_id: bytes(row.data) for row in await session.execute(stmt)})
    return out


# ---------------------------------------------------------------------------
# Rendering — the offload hop's share
# ---------------------------------------------------------------------------


def render_rows(
    rows: Sequence[RenderRow],
    blobs: Mapping[str, bytes],
    registry: RendererRegistry,
    limits: RenderLimits,
    cached: Mapping[tuple[str, str], Rendering],
) -> list[Rendered]:
    """Render each row once per ``(bytes hash, generation)``; twins reuse the first result.

    Pure over its inputs — no session, no shared state — so it runs
    whole on the offload pool. A row whose blob is missing (a write
    replaced it between the select and the read) is skipped; the write
    reset its stamp, and the next run renders the fresh bytes.
    """
    seen: dict[tuple[str, str], Rendering] = dict(cached)
    out: list[Rendered] = []
    for row in rows:
        key = row.key(registry)
        generation = key[1]
        rendering = seen.get(key)
        if rendering is not None:
            out.append(Rendered(row.entry_id, row.content_hash, generation, rendering, cached=True))
            continue
        data = blobs.get(row.entry_id)
        if data is None:
            continue
        rendering = registry.render(RenderSource(data, row.mime, row.name), limits)
        seen[key] = rendering
        out.append(Rendered(row.entry_id, row.content_hash, generation, rendering, cached=False))
    return out


def row_size(row: RenderRow) -> int:
    """The page cutter's metering: the bytes a row's render will hold in flight."""
    return row.size_bytes


# ---------------------------------------------------------------------------
# Landing — the guarded stamp, then the text for the rows stamped
# ---------------------------------------------------------------------------


async def land_renderings(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    rendered: Sequence[Rendered],
    report: RenderReport,
) -> Result:
    """Stamp each rendering where its bytes still stand, then write the text for the rows stamped.

    One guarded UPDATE per row, its rowcount the proof of what this
    landing reached: a row whose bytes changed under the render misses
    (the write reset it to pending), and a row already carrying this
    exact stamp — a rival's identical landing — misses too and is left
    whole, text included. The rows reached have their old content rows
    dropped and their renderings inserted in bytes-bounded pages; their
    chunk stamp is reset so the chunk pass splits the new text.

    Cost profile, honestly: a round trip per row, the shape the vector
    landing uses too; at 256 rows a page it is milliseconds beside the
    renders that produced them. A VALUES-join UPDATE carrying per-row
    values, with a RETURNING of the rows reached, is the direction.
    """
    if not rendered:
        return Result(ops=("reindex",))
    entry, content = tables.entry, tables.content
    b_id, b_hash, b_gen = bindparam("b_id"), bindparam("b_hash"), bindparam("b_gen")
    stamp = (
        update(entry)
        .where(
            entry.c.entry_id == b_id,
            entry.c.source == "bytes",
            entry.c.content_hash == b_hash,
            or_(
                entry.c.render_generation.is_(None),
                entry.c.render_generation != b_gen,
                entry.c.render_source_hash.is_(None),
                entry.c.render_source_hash != b_hash,
            ),
        )
        .values(
            render_source_hash=b_hash,
            render_generation=b_gen,
            render_status=bindparam("b_status"),
            render_detail=bindparam("b_detail"),
            render_units=bindparam("b_units"),
            media_width=bindparam("b_width"),
            media_height=bindparam("b_height"),
            lines=bindparam("b_lines"),
            chunked=False,
            encoded=False,
            chunk_source_hash=None,
        )
    )
    landed: list[Rendered] = []
    for item in rendered:
        outcome = cast("CursorResult[Any]", await session.execute(stamp, _stamp_params(item)))
        if outcome.rowcount == 1:
            landed.append(item)
    for ids in chunked(sorted(item.entry_id for item in landed), membership_budget):
        await session.execute(delete(content).where(membership(content.c.entry_id, ids, profile)))
    now = datetime.now(UTC)
    texts = [
        {"entry_id": item.entry_id, "created_at": now, "content": item.rendering.text}
        for item in landed
        if item.rendering.text is not None
    ]
    for page in byte_chunked(texts, _text_row_size, BLOB_PAGE_BYTES):
        await bulk_insert(session, content, page)
    for item in landed:
        report.record(item)
    return Result(ops=("reindex",))


async def count_unrendered(session: AsyncSession, tables: VFSTables) -> int:
    """Live bytes rows still pending — the ``unrendered`` count."""
    entry = tables.entry
    stmt = (
        select(func.count())
        .select_from(entry)
        .where(entry.c.source == "bytes", entry.c.deleted_at.is_(None), entry.c.render_status == "pending")
    )
    return (await session.execute(stmt)).scalar_one()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _stamp_params(item: Rendered) -> dict[str, object]:
    rendering = item.rendering
    return {
        "b_id": item.entry_id,
        "b_hash": item.content_hash,
        "b_gen": item.generation,
        "b_status": rendering.status,
        "b_detail": rendering.detail,
        "b_units": units_to_json(rendering.units),
        "b_width": rendering.width,
        "b_height": rendering.height,
        "b_lines": rendering.lines,
    }


def _text_row_size(row: Mapping[str, object]) -> int:
    """The insert page's metering: characters as the byte proxy, exact in the ASCII-dominant regime."""
    text = row["content"]
    assert isinstance(text, str)
    return len(text)
