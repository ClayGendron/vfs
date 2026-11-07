"""The embed step of ``reindex`` — fill ``chunks.embedding`` in short, resumable batches.

Embedding is one of the indexes vfs builds, so it runs under the same
``reindex`` call as the chunks, grams and lexical postings — but not as
one of their phases. A 10,000-file store is ~10⁵ chunks and, against a
hosted provider at a low rate-limit tier, tens of minutes of network
wait: no writer transaction spans that, and the event loop is never
held. The step is a streaming loop instead: a short read selects one
page of ``embedding IS NULL`` rows past the last id seen (keyset, so
the loop always advances), the page is cut into token- and
input-bounded batches, the batches embed with **no transaction open**
under a small semaphore, and a short write lands each vector with
``UPDATE … WHERE id = :id AND embedding IS NULL`` — a rival's identical
write is a no-op. Between pages the lease's ``lost`` flag is checked; a
crash loses at most the batches in flight, and the next run resumes at
the first NULL row.

Two laws keep the provider bill honest. **The chunk row is the cache**:
before a batch is sent, any already-embedded row sharing a
``content_hash`` — a license header, a vendored copy — lends its vector
(:func:`cached_vectors`), and ``chunk_dirty`` carries vectors across a
re-split onto the fresh rows with the same hash. **Identity is
durable**: the meta row names the space the stored vectors live in;
when the configured provider differs, every embedding is cleared and
the pair re-stamped by the first batch written under the new identity
(:func:`clear_embeddings`) — model swap is a re-embed by the verb that
owns regeneration, never a read-time migration.

A batch the provider **refuses for its input** (HTTP 400, 413 or 422 with
no ``Retry-After``) is halved until its acceptable rows embed; a row still
refused alone is a candidate refusal. A page's candidates are recorded
only after one canary request, sent once the page's batches have all
answered, succeeds: a provider refusing a fixed short text is failing,
not refusing content, and the step ends as for any transient failure.
Recorded refusals live in ``vfs_embed_refusals``, keyed by the text's
hash with the model and its declared caps, so a refused text is never
sent again while those stand, across re-splits, twins and files; a
model change clears them, and a changed cap is a new key.
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, NamedTuple

from sqlalchemy import bindparam, delete, exists, func, insert, select, update

from vfs.results import Result
from vfs.storage.backends.database.dialects import chunked
from vfs.storage.backends.database.membership import membership

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.embedding import EmbeddingProvider
    from vfs.models.rows import VFSTables
    from vfs.storage.backends.database.dialects import DialectProfile

EMBED_CONCURRENCY: Final = 4
"""Provider requests in flight per reindex; TPM binds long before latency, so more buys only 429s."""

EMBED_PAGE_ROWS: Final = 4_096
"""Chunk rows one short read selects — bounds the loop's residency, never the corpus."""

EMBED_TIMEOUT_SECONDS: Final = 120.0
"""One provider request's wall budget; a hung socket ends the step classified, not stalled."""

EMBED_HEADROOM: Final = (5, 6)
"""The fraction of a token cap a batch plans to — provider counts drift past any estimate."""

RETRY_AFTER_CAP_SECONDS: Final = 60.0
"""The longest one ``Retry-After`` is honoured for before the step gives the rest to the next run."""

EMBED_CANARY: Final = "vfs embedding canary"
"""The fixed text sent once per page that would record a refusal: refused too, the provider is failing."""

_INPUT_REFUSAL_STATUSES: Final = frozenset({400, 413, 422})

_UNDECLARED_CAP: Final = -1

ChunkId = int
ContentHash = str

Identity = tuple[str, int]
"""``(model_id, dimension)`` — the pair the meta row stamps."""

RefusalKey = tuple[str, int, int]
"""``(model_id, max_input_tokens, max_batch_tokens)`` a refusal holds under, ``-1`` for an undeclared cap."""


class EmbedRow(NamedTuple):
    """One unembedded chunk: its id, its body hash, its text, its entry."""

    id: ChunkId
    content_hash: ContentHash | None
    content: str
    entry_id: str | None = None


@dataclass
class EmbedReport:
    """What the step did — the ``embedding`` extra on the reindex result."""

    embedded: int = 0
    cached: int = 0
    tokens: int = 0
    requests: int = 0
    truncated: int = 0
    unembedded: int = 0
    refused: int = 0
    stopped_by: str | None = None
    """The provider failure that ended the step early, if one did."""
    refusal: str | None = None
    """The first input refusal the step recorded, for the warning."""

    def as_extra(self, model_id: str) -> dict[str, Any]:
        return {
            "model": model_id,
            "embedded": self.embedded,
            "cached": self.cached,
            "tokens": self.tokens,
            "requests": self.requests,
            "truncated": self.truncated,
            "unembedded": self.unembedded,
            "refused": self.refused,
        }


# ---------------------------------------------------------------------------
# Batching — the token-bounded sibling of ``byte_chunked``
# ---------------------------------------------------------------------------


def token_batched(rows: Sequence[EmbedRow], provider: EmbeddingProvider) -> Iterator[list[EmbedRow]]:
    """*rows* cut into batches within the provider's input and token caps, in order.

    Tokens are the provider's own estimate metered against
    ``max_batch_tokens`` with :data:`EMBED_HEADROOM` (~5/6 of the cap);
    inputs against ``max_batch_inputs`` exactly. A row over the token
    budget on its own rides alone — the budget shapes batches, never
    eligibility — and the provider's per-input cap decides its fate.
    """
    budget = None if provider.max_batch_tokens is None else _with_headroom(provider.max_batch_tokens)
    batch: list[EmbedRow] = []
    spent = 0
    for row in rows:
        cost = provider.estimate_tokens(row.content)
        full = len(batch) >= provider.max_batch_inputs or (budget is not None and batch and spent + cost > budget)
        if full:
            yield batch
            batch, spent = [], 0
        batch.append(row)
        spent += cost
    if batch:
        yield batch


def refusal_key(provider: EmbeddingProvider) -> RefusalKey:
    """The provider facts a refusal depends on: its model and its declared caps."""

    def declared(cap: int | None) -> int:
        return _UNDECLARED_CAP if cap is None else cap

    return (provider.model_id, declared(provider.max_input_tokens), declared(provider.max_batch_tokens))


def truncated_for(text: str, provider: EmbeddingProvider) -> str:
    """*text* cut to the provider's per-input cap by its own estimator; unchanged when it fits."""
    cap = provider.max_input_tokens
    if cap is None or provider.estimate_tokens(text) <= cap:
        return text
    keep = len(text)
    while keep > 0 and provider.estimate_tokens(text[:keep]) > cap:
        keep = int(keep * cap / provider.estimate_tokens(text[:keep]))
    return text[:keep]


# ---------------------------------------------------------------------------
# The statements — every one short, none growing with the corpus
# ---------------------------------------------------------------------------


async def read_identity(session: AsyncSession, tables: VFSTables) -> Identity | None:
    """The stamped ``(model_id, dimension)``, or ``None`` before the first embed."""
    meta = tables.meta
    row = (
        await session.execute(select(meta.c.embedding_model, meta.c.embedding_dimension).where(meta.c.id == 1))
    ).one_or_none()
    if row is None or row.embedding_model is None or row.embedding_dimension is None:
        return None
    return (row.embedding_model, row.embedding_dimension)


async def clear_embeddings(session: AsyncSession, tables: VFSTables) -> Result:
    """The migration: every vector NULL and the identity unstamped, in one writer transaction."""
    await session.execute(update(tables.chunks).values(embedding=None))
    await session.execute(delete(tables.embed_refusals))
    await session.execute(
        update(tables.meta).where(tables.meta.c.id == 1).values(embedding_model=None, embedding_dimension=None)
    )
    return Result(ops=("reindex",))


async def select_unembedded(
    session: AsyncSession, tables: VFSTables, after: ChunkId, limit: int, key: RefusalKey
) -> list[EmbedRow]:
    """The next *limit* live, chunked entries' rows past *after* with no vector and no refusal, ascending id."""
    chunks, entry = tables.chunks, tables.entry
    stmt = (
        select(chunks.c.id, chunks.c.content_hash, chunks.c.content, chunks.c.entry_id)
        .select_from(chunks.join(entry, entry.c.entry_id == chunks.c.entry_id))
        .where(
            chunks.c.id > after,
            chunks.c.embedding.is_(None),
            entry.c.chunked,
            entry.c.deleted_at.is_(None),
            ~_refused(tables, key),
        )
        .order_by(chunks.c.id)
        .limit(limit)
    )
    return [EmbedRow(row.id, row.content_hash, row.content, row.entry_id) for row in await session.execute(stmt)]


async def cached_vectors(
    session: AsyncSession,
    tables: VFSTables,
    hashes: Sequence[ContentHash],
    profile: DialectProfile,
    membership_budget: int,
) -> dict[ContentHash, list[float]]:
    """One stored vector per hash in *hashes* that some embedded row already carries.

    Two chunked probes: the lowest embedded id per hash, then those
    rows' vectors — so a hash shared by a thousand copies costs one
    vector, not a thousand.
    """
    chunks = tables.chunks
    lowest: dict[ContentHash, ChunkId] = {}
    for page in chunked(list(dict.fromkeys(hashes)), membership_budget):
        stmt = (
            select(chunks.c.content_hash, func.min(chunks.c.id))
            .where(membership(chunks.c.content_hash, page, profile), chunks.c.embedding.isnot(None))
            .group_by(chunks.c.content_hash)
        )
        lowest.update({row[0]: row[1] for row in await session.execute(stmt)})
    found: dict[ContentHash, list[float]] = {}
    for page in chunked(sorted(lowest.values()), membership_budget):
        stmt = select(chunks.c.content_hash, chunks.c.embedding).where(membership(chunks.c.id, page, profile))
        found.update({row.content_hash: list(row.embedding) for row in await session.execute(stmt)})
    return found


async def write_vectors(
    session: AsyncSession,
    tables: VFSTables,
    pairs: Sequence[tuple[ChunkId, list[float]]],
    stamp: Identity | None,
    *,
    refused: Sequence[ContentHash],
    key: RefusalKey,
    profile: DialectProfile,
    membership_budget: int,
) -> Result:
    """Land *pairs* on rows still NULL, stamping *stamp* on the meta row when it is unclaimed.

    *refused* hashes are recorded under *key* in the same transaction:
    deleted first in chunks of *membership_budget*, then inserted once
    each, so a text refused again under a new key takes the new key and
    the insert never meets the primary key.

    One executemany: the driver sends a row at a time on the engines
    without a multi-row UPDATE (the MySQL family), which at 10⁵ chunks
    is seconds against the minutes the provider took — a recorded
    suboptimality, never a cap.
    """
    chunks = tables.chunks
    if pairs:
        stmt = (
            update(chunks)
            .where(chunks.c.id == bindparam("b_id"), chunks.c.embedding.is_(None))
            .values(embedding=bindparam("b_vec"))
        )
        await session.execute(stmt, [{"b_id": chunk_id, "b_vec": vector} for chunk_id, vector in pairs])
    if stamp is not None:
        meta = tables.meta
        model_id, dimension = stamp
        await session.execute(
            update(meta)
            .where(meta.c.id == 1, meta.c.embedding_model.is_(None))
            .values(embedding_model=model_id, embedding_dimension=dimension)
        )
    hashes = list(dict.fromkeys(refused))
    if hashes:
        table = tables.embed_refusals
        for page in chunked(hashes, membership_budget):
            await session.execute(delete(table).where(membership(table.c.content_hash, page, profile)))
        model_id, input_cap, batch_cap = key
        rows = [
            {"content_hash": h, "model_id": model_id, "max_input_tokens": input_cap, "max_batch_tokens": batch_cap}
            for h in hashes
        ]
        await session.execute(insert(table), rows)
    return Result(ops=("reindex",))


async def count_unembedded(session: AsyncSession, tables: VFSTables, key: RefusalKey) -> int:
    """Live, chunked entries' rows still without a vector and not refused — the ``unembedded`` count."""
    return await _count_null(session, tables, ~_refused(tables, key))


async def count_refused(session: AsyncSession, tables: VFSTables, key: RefusalKey) -> int:
    """Live, chunked entries' rows without a vector whose text is refused under *key* — the ``refused`` count."""
    return await _count_null(session, tables, _refused(tables, key))


async def refused_paths(
    session: AsyncSession, tables: VFSTables, entry_ids: Sequence[str], profile: DialectProfile, membership_budget: int
) -> list[str]:
    """The paths of *entry_ids*, in their order, read in chunks of *membership_budget*."""
    entry = tables.entry
    paths: dict[str, str] = {}
    for page in chunked(list(dict.fromkeys(entry_ids)), membership_budget):
        stmt = select(entry.c.entry_id, entry.c.path).where(membership(entry.c.entry_id, page, profile))
        paths.update({row.entry_id: row.path for row in await session.execute(stmt)})
    return [paths[entry_id] for entry_id in dict.fromkeys(entry_ids) if entry_id in paths]


# ---------------------------------------------------------------------------
# One page's worth of provider calls
# ---------------------------------------------------------------------------


class Embedding(NamedTuple):
    """A page's outcome: vectors landed per chunk id, the failure that cut it short, the rows refused."""

    vectors: list[tuple[ChunkId, list[float]]]
    failure: BaseException | None
    refused: tuple[EmbedRow, ...] = ()


async def embed_page(
    page: Sequence[EmbedRow],
    provider: EmbeddingProvider,
    known: dict[ContentHash, list[float]],
    report: EmbedReport,
    semaphore: asyncio.Semaphore,
    *,
    timeout: float = EMBED_TIMEOUT_SECONDS,
) -> Embedding:
    """Vectors for every row of *page*: lent from *known* by hash, else embedded in batches.

    Rows sharing a hash embed once; each request runs under *semaphore*
    with its own *timeout*, one ``Retry-After`` honoured by sleeping. A
    batch refused for its input is halved outside the semaphore until
    its rows embed or stand refused alone; those candidates, with their
    in-page twins, come back as ``refused`` only when the page met no
    transient failure and the canary answered. A transient failure ends
    the page — the batches and halves already answered still land.
    """
    vectors: list[tuple[ChunkId, list[float]]] = []
    pending: list[EmbedRow] = []
    seen: set[ContentHash] = set()
    for row in page:
        if row.content_hash is not None and row.content_hash in known:
            vectors.append((row.id, known[row.content_hash]))
            report.cached += 1
        elif row.content_hash is None or row.content_hash not in seen:
            pending.append(row)
            if row.content_hash is not None:
                seen.add(row.content_hash)
    by_hash: dict[ContentHash, list[ChunkId]] = {}
    for row in page:
        if row.content_hash is not None and row.content_hash not in known:
            by_hash.setdefault(row.content_hash, []).append(row.id)
    texts = {row.id: truncated_for(row.content, provider) for row in pending}
    report.truncated += sum(1 for row in pending if len(texts[row.id]) != len(row.content))
    refusals: list[BaseException] = []

    async def one(batch: list[EmbedRow]) -> Embedding:
        try:
            async with semaphore:
                answer = await _embed_with_retry(provider, [texts[row.id] for row in batch], timeout)
        except Exception as exc:
            # Halved outside the semaphore, so refused batches never hold slots while they wait.
            if not _input_refusal(exc):
                return Embedding([], exc)
            refusals.append(exc)
            if len(batch) == 1:
                return Embedding([], None, tuple(batch))
            middle = len(batch) // 2
            left = await one(batch[:middle])
            if left.failure is not None:
                return left
            right = await one(batch[middle:])
            # A half that answered lands beside its sibling's failure.
            return Embedding(left.vectors + right.vectors, right.failure, left.refused + right.refused)
        report.requests += 1
        report.tokens += answer.tokens
        landed: list[tuple[ChunkId, list[float]]] = []
        for row, vector in zip(batch, answer.vectors, strict=True):
            unit = unit_vector(vector)
            targets = by_hash.get(row.content_hash, [row.id]) if row.content_hash is not None else [row.id]
            for target in targets:
                landed.append((target, unit))
                if row.content_hash is not None:
                    known[row.content_hash] = unit
            report.embedded += 1
            report.cached += len(targets) - 1
        return Embedding(landed, None)

    failure: BaseException | None = None
    candidates: list[EmbedRow] = []
    # A provider's malformed answer raises past `one`; it fails the page classified, never raw.
    batches = token_batched(pending, provider)
    for outcome in await asyncio.gather(*(one(batch) for batch in batches), return_exceptions=True):
        if isinstance(outcome, BaseException):
            failure = failure or outcome
            continue
        failure = failure or outcome.failure
        vectors.extend(outcome.vectors)
        candidates.extend(outcome.refused)
    if failure is not None or not candidates:
        return Embedding(vectors, failure)
    try:
        async with semaphore:
            await asyncio.wait_for(provider.embed_documents([EMBED_CANARY]), timeout)
    except Exception:
        return Embedding(vectors, refusals[0])
    report.refusal = report.refusal or f"{type(refusals[0]).__name__}: {refusals[0]}"
    refused_hashes = {row.content_hash for row in candidates if row.content_hash is not None}
    return Embedding(vectors, None, tuple(row for row in page if row.content_hash in refused_hashes))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _with_headroom(cap: int) -> int:
    numerator, denominator = EMBED_HEADROOM
    return max(1, cap * numerator // denominator)


def unit_vector(vector: Sequence[float]) -> list[float]:
    """The vector scaled to unit length — cosine becomes a dot product; a zero vector stays zero."""
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        return list(vector)
    return [value / norm for value in vector]


async def _embed_with_retry(provider: EmbeddingProvider, texts: list[str], timeout: float) -> Any:
    """One request under *timeout*; a refusal naming ``Retry-After`` is slept once and retried."""
    try:
        return await asyncio.wait_for(provider.embed_documents(texts), timeout)
    except Exception as exc:
        delay = _retry_after_seconds(exc)
        if delay is None:
            raise
        await asyncio.sleep(min(delay, RETRY_AFTER_CAP_SECONDS))
        return await asyncio.wait_for(provider.embed_documents(texts), timeout)


def _refused(tables: VFSTables, key: RefusalKey) -> Any:
    """Whether a chunk's text has a refusal under *key*, as a correlated ``EXISTS``."""
    chunks, table = tables.chunks, tables.embed_refusals
    model_id, input_cap, batch_cap = key
    return exists().where(
        table.c.content_hash == chunks.c.content_hash,
        table.c.model_id == model_id,
        table.c.max_input_tokens == input_cap,
        table.c.max_batch_tokens == batch_cap,
    )


async def _count_null(session: AsyncSession, tables: VFSTables, refusal: Any) -> int:
    """Live, chunked entries' rows without a vector that meet *refusal*."""
    chunks, entry = tables.chunks, tables.entry
    stmt = (
        select(func.count())
        .select_from(chunks.join(entry, entry.c.entry_id == chunks.c.entry_id))
        .where(chunks.c.embedding.is_(None), entry.c.chunked, entry.c.deleted_at.is_(None), refusal)
    )
    return (await session.execute(stmt)).scalar_one()


def _input_refusal(exc: BaseException) -> bool:
    """An HTTP 400, 413 or 422 with no ``Retry-After``: the provider refused the batch's input."""
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    return status in _INPUT_REFUSAL_STATUSES and _retry_after_seconds(exc) is None


def _retry_after_seconds(exc: BaseException) -> float | None:
    """The ``Retry-After`` seconds an HTTP-shaped exception carries, if any."""
    headers = getattr(getattr(exc, "response", None), "headers", None)
    if headers is None:
        return None
    raw = headers.get("retry-after-ms") or headers.get("retry-after")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value / 1000.0 if headers.get("retry-after-ms") else value
