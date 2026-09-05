"""The extracted ``links`` edges — minted inside the chunk pass from markdown bodies.

The chunk pass materialises every dirty body once for its offload hop;
:func:`extract_link_work` runs in that hop and turns the markdown rows
that are not link-skipped into per-document reference lists, and
:func:`publish_links` then resolves those references against the live
tree and rewrites each source's extracted out-edges. Resolution is an
exact-path probe under the membership budget — the candidate paths come
from the link text, never from a corpus-wide path map — so the pass
holds only the dirty documents' references. Only a *source's* own
extracted out-edges are ever rewritten; a row a verb authored on the
same triple wins the unique key and is left alone, as is every row
where the changed entry is the target.
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, NamedTuple

from sqlalchemy import delete, select

from vfs.models.edge import EXTRACTED_PROVENANCE
from vfs.models.links import LINK_EDGE_TYPE, MARKDOWN_EXTENSIONS, extract_links, link_candidates
from vfs.paths import Path
from vfs.storage.backends.database.dialects import chunked
from vfs.storage.backends.database.edges import insert_arbitrated
from vfs.storage.backends.database.membership import membership

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Any

    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.models.links import LinkRef
    from vfs.models.rows import VFSTables
    from vfs.storage.backends.database.dialects import DialectProfile


class LinkWork(NamedTuple):
    """One re-extracted document: its id, its path, and the references it holds."""

    entry_id: str
    document: Path
    refs: list[LinkRef]


class LinkOutcome(NamedTuple):
    """What one publish did: documents rewritten, edges minted, references left unresolved."""

    sources: int
    edges: int
    unresolved: int


# ---------------------------------------------------------------------------
# Extraction — the offload hop's share
# ---------------------------------------------------------------------------


def extract_link_work(rows: Sequence[Any], generation: str) -> list[LinkWork]:
    """The dirty markdown rows' references, skipping bodies the stamp pair already covers.

    Every row not skipped becomes a work item, references or none — a
    document whose links were all removed must still have its old
    out-edges deleted. The batch parses in parallel inside the engine.
    """
    targets = [
        row
        for row in rows
        if row.ext in MARKDOWN_EXTENSIONS
        and row.content is not None
        and not (row.content_hash == row.link_source_hash and row.link_generation == generation)
    ]
    parsed = extract_links([row.content for row in targets])
    return [LinkWork(row.entry_id, Path(row.path), refs) for row, refs in zip(targets, parsed, strict=True)]


# ---------------------------------------------------------------------------
# Publish — resolve, replace each source's extracted out-edges
# ---------------------------------------------------------------------------


async def publish_links(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    work: Sequence[LinkWork],
) -> LinkOutcome:
    """Rewrite the extracted ``links`` out-edges of every document in *work*.

    Candidates are probed by exact path in chunks; each reference takes
    its first live candidate and a document's references to one target
    fold into one row whose weight is their count and whose context is
    the first referring line. The old extracted rows are deleted by
    source before the fresh set inserts; a fresh row that collides with
    an authored row on the same triple is dropped — the authored row is
    the caller's, not ours.
    """
    if not work:
        return LinkOutcome(0, 0, 0)
    resolved = await _resolve_candidates(session, tables, profile, membership_budget, work)
    rows: list[dict[str, object]] = []
    unresolved = 0
    for item in work:
        weights: Counter[str] = Counter()
        contexts: dict[str, str] = {}
        for ref in item.refs:
            target_id = next((resolved[c] for c in link_candidates(item.document, ref.dest) if c in resolved), None)
            if target_id is None:
                unresolved += 1
                continue
            if target_id == item.entry_id:
                continue
            weights[target_id] += 1
            contexts.setdefault(target_id, ref.context)
        rows.extend(
            {
                "source_id": item.entry_id,
                "target_id": target_id,
                "edge_type": LINK_EDGE_TYPE,
                "weight": float(count),
                "distance": None,
                "provenance": EXTRACTED_PROVENANCE,
                "context": contexts[target_id],
            }
            for target_id, count in sorted(weights.items())
        )
    edges = tables.edges
    for ids in chunked(sorted(item.entry_id for item in work), membership_budget):
        await session.execute(
            delete(edges).where(
                membership(edges.c.source_id, ids, profile),
                edges.c.edge_type == LINK_EDGE_TYPE,
                edges.c.provenance == EXTRACTED_PROVENANCE,
            )
        )
    conflicted = await insert_arbitrated(session, edges, rows)
    return LinkOutcome(len(work), len(rows) - len(conflicted), unresolved)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _resolve_candidates(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    work: Sequence[LinkWork],
) -> dict[str, str]:
    """``path → entry_id`` for every candidate path that names a live entry."""
    wanted = {candidate for item in work for ref in item.refs for candidate in link_candidates(item.document, ref.dest)}
    entry = tables.entry
    found: dict[str, str] = {}
    for paths in chunked(sorted(wanted), membership_budget):
        stmt = select(entry.c.path, entry.c.entry_id).where(
            membership(entry.c.path, paths, profile), entry.c.deleted_at.is_(None)
        )
        found.update({row.path: row.entry_id for row in await session.execute(stmt)})
    return found
