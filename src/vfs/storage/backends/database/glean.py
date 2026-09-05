"""Ranked search over the lexical index — the BM25 leg of ``glean``.

The verb is grep's shape with a scorer where grep has a matcher: one
session, SELECTs only, the backend's redrive around it, scope crossing
the seam as pattern text on the ``globs`` channels with the ``ext``
channels beside them. A query's terms go through the index's tokenizer;
**round one** probes their summary rows (``lex_df`` with the epoch's
statistics) and fetches every term's head blocks (``block_no <
HEAD_BLOCKS``); the engine scores what it has at the fusion depth;
**round two** asks the engine which later blocks of the overflowing
terms can still change that top-k (:func:`~vfs.models.lexical.select_blocks`)
and fetches exactly those by key — the epoch equality inside every arm
so each is a full primary-key prefix — then scores again. No scoring
SQL runs on any dialect; every statement is a key fetch.

The ladder has two rungs. The channel's segment-posting allow-list
(grep's nomination pruning) prices the scope: when it resolves to at
most :data:`SCOPE_ID_BUDGET` entries their chunk ids become the
scorer's candidate set (**filter, then fetch** — exact); a wider or
unprunable scope scores first and gates the top chunks' entries as
their rows are fetched (**fetch, then filter**), one deeper probe when
the first runs short, then a loud record. Either way
:func:`~vfs.storage.backends.database.scope.passes_gates` is the
authority on every row that answers.

Freshness is grep's: ``encoded=True`` means the entry's terms are in
the current lexical epoch; the ``NOT encoded`` rows the gates admit are
the overlay — their live bodies tokenized and encoded as blocks at
query time and scored by the same engine with the epoch's statistics,
so the two sides share one formula, one accumulation order and one
scale. The pointer read is advisory and re-issued after the fetch (the
two-read protocol); a moved pointer raises :class:`StaleSnapshot` for
the backend to redrive.

The **vector leg** is one in-engine statement on every supported
dialect — ``ORDER BY <cosine distance> LIMIT k`` with the scope
predicate inside it, only the distance function's spelling varying
(:mod:`~vfs.storage.backends.database.distance`) — over the chunks of
live, chunked entries that carry a vector. The backend embeds the
query with the mount's own provider and hands the vector in; the leg
takes the same ladder as the lexical one (an allow-list narrows it to
per-chunk statements merged client-side; a wide scope fetches, gates,
and deepens once).

Entries out: each leg aggregates to entries by its best chunk (MaxP)
and is normalised to the unit interval by its own law — cosine by its
theoretical range, BM25 by min-max over the candidate union — then the
mount's :class:`~vfs.storage.ranking.Fusion` combines the legs; the
fused scores are min-max scaled, rounded, ordered ``score DESC, path
ASC``; each entry's top chunks from either leg ride as ``Match`` rows
with their line bounds and text.
"""

from __future__ import annotations

from collections import Counter
from functools import partial
from time import monotonic
from typing import TYPE_CHECKING, Any, Final, NamedTuple

from sqlalchemy import and_, or_, select, text

from vfs.models import Match, Observation
from vfs.models.lexical import (
    BLOCK_SIZE,
    ScoreBlock,
    decode_summary,
    encode_block,
    idf,
    score_blocks,
    select_blocks,
    term_weight,
    tokenize,
)
from vfs.paths import Path, normalize_ext_channel
from vfs.pattern_matching import PatternError, compile_filter, escape_glob, expand_channel
from vfs.pattern_matching.grep import split_lines
from vfs.results import Result, ResultError, Severity, VFSErrorKind
from vfs.results.preview import select_preview
from vfs.storage.backends.database.dialects import StaleSnapshot, arm_budget, chunked
from vfs.storage.backends.database.distance import cosine_distance
from vfs.storage.backends.database.indexing import current_epoch
from vfs.storage.backends.database.lexical import lexical_stats
from vfs.storage.backends.database.membership import membership
from vfs.storage.backends.database.offload import call_offloaded
from vfs.storage.backends.database.pathterms import allow_list_ids, compile_channel
from vfs.storage.backends.database.reads import (
    content_for_entries,
    effective_columns,
    kind_membership,
    pointer_with_overlay,
)
from vfs.storage.backends.database.scope import (
    CHANNEL_ARM_BINDS,
    FETCH_RIDE,
    entries_for_scan,
    passes_gates,
    pushdown_terms,
)
from vfs.storage.backends.database.seams import seam
from vfs.storage.backends.database.signals import signal_factors
from vfs.storage.ranking import REFINE_GUIDANCE, SCORE_DECIMALS, TOP_CHUNKS, Ranker, min_max, unit_cosine

if TYPE_CHECKING:
    from collections.abc import Sequence
    from concurrent.futures import Executor

    from sqlalchemy import ColumnElement
    from sqlalchemy.engine import RowMapping
    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.models.rows import EntryId, VFSTables
    from vfs.pattern_matching import Body, GlobFilter
    from vfs.storage.backends.database.dialects import DialectProfile
    from vfs.storage.backends.database.indexing import Epoch
    from vfs.storage.backends.database.lexical import TermStatistics
    from vfs.storage.backends.database.scope import Pushdown

HEAD_BLOCKS: Final = 8
"""Blocks per term fetched in round one — a term of ≤ 1,024 postings is complete there."""

FUSION_K: Final = 1000
"""Chunk depth scored per query, the fusion leg's K; entries come from these chunks."""

VECTOR_DEPTH_FACTOR: Final = 10
"""The vector leg fetches this many chunks per entry asked for …"""

VECTOR_DEPTH_FLOOR: Final = 100
"""… and never fewer than this: a short list starves fusion of candidates."""

SCOPE_ID_BUDGET: Final = 5_000
"""Entries an allow-list may nominate before the scope counts as wide."""

PROBE_DEEPEN: Final = 4
"""The wide rung's second probe scores this many times the fusion depth."""

OVERLAY_BUDGET: Final = 500
"""Unindexed entries the overlay scores per call, in path order."""

WALL_TIME_BUDGET: Final = 10.0

ChunkId = int
Ranking = list[tuple[ChunkId, float]]


class _Gates(NamedTuple):
    """The call's structural scope: compiled gates, ext sets, and the fetch pushdown."""

    gates: list[GlobFilter]
    not_gates: list[GlobFilter]
    wanted: frozenset[str]
    unwanted: frozenset[str]
    pushdown: Pushdown

    def admits(self, mapping: RowMapping) -> bool:
        return passes_gates(mapping, self.gates, self.not_gates, self.wanted, self.unwanted)


class VectorLeg(NamedTuple):
    """The vector leg's inputs, minted by the backend per call.

    ``query`` is the embedded query in the mount's space; ``tier`` names
    what will serve it (``native_exact`` or ``native_ann``); ``prelude``
    is a session-scoped statement to run first, or ``None`` (pgvector's
    iterative scan, where the version allows it).
    """

    query: list[float]
    model_id: str
    tier: str
    prelude: str | None


class _Hit(NamedTuple):
    """One entry's raw leg score and its best chunks ``(chunk_id, score)``, best first."""

    score: float
    chunks: list[tuple[ChunkId, float]]


class _Sources(NamedTuple):
    """The text a ``Match`` row is cut from: chunk rows by id, overlay bodies by entry, the query's terms."""

    chunks: dict[ChunkId, RowMapping]
    bodies: dict[EntryId, str]
    terms: Sequence[str]


# ---------------------------------------------------------------------------
# The verb
# ---------------------------------------------------------------------------


async def glean_rows(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    parameter_budget: int,
    membership_budget: int,
    executor: Executor,
    *,
    query: str,
    limit: int,
    ext: tuple[str, ...],
    ext_not: tuple[str, ...],
    globs: tuple[str, ...],
    globs_not: tuple[str, ...],
    observations: list[Observation] | None,
    columns: frozenset[str] | None,
    wall_seconds: float = WALL_TIME_BUDGET,
    dialect_name: str = "sqlite",
    vector: VectorLeg | None = None,
    ranker: Ranker | None = None,
    records: Sequence[ResultError] = (),
) -> Result:
    """One row per entry, best first: the legs fused, the index side unioned with the overlay.

    Scoping arrives as pattern text on the ``globs`` channels; piped
    *observations* are rows in entry coordinates and admit their own
    paths literally. *limit* counts entries. *wall_seconds* is the
    caller-configured wall-clock budget; the declared default keeps
    direct callers honest. *vector* is the embedded query and its tier,
    or ``None`` for a lexical-only answer; *ranker* names the fusion;
    *records* are the backend's per-call notes (an absent provider, a
    stale space) that ride the envelope.
    """
    ranker = ranker or Ranker()
    terms = list(dict.fromkeys(tokenize(query)))
    if not terms:
        message = f"glean query {query!r} has no searchable term after folding"
        return Result(ops=("glean",), errors=[ResultError(kind=VFSErrorKind.invalid, message=message)])
    if observations:
        globs = (*globs, *(escape_glob(str(row.path)) for row in observations))
    try:
        admissions = expand_channel("globs", globs)
        exclusions = expand_channel("globs_not", globs_not)
    except PatternError as exc:
        return Result(ops=("glean",), errors=[ResultError(kind=VFSErrorKind.invalid, message=str(exc))])
    entry = tables.entry
    channel = compile_channel(admissions)
    fan_arms = arm_budget(profile, parameter_budget, CHANNEL_ARM_BINDS)
    gates = [compile_filter(glob, ()) for glob in admissions]
    scope = _Gates(
        gates,
        [compile_filter(glob, ()) for glob in exclusions],
        normalize_ext_channel(ext),
        normalize_ext_channel(ext_not),
        pushdown_terms(
            entry, profile, fan_arms, membership_budget, channel, normalize_ext_channel(ext), hide_meta=not gates
        ),
    )
    fetched = effective_columns(columns, content=False)
    deadline = monotonic() + wall_seconds
    truncations: list[tuple[str, dict[str, Any] | None]] = []

    epoch, overlay_empty = await pointer_with_overlay(session, tables)
    await seam("glean:after-pointer-read")
    stats = await lexical_stats(session, tables, -1 if epoch is None else epoch, terms, membership_budget)
    present = [term for term in terms if term in stats.terms]

    hits: dict[EntryId, _Hit] = {}
    rows: dict[EntryId, RowMapping] = {}
    bodies: dict[EntryId, str] = {}
    allow: list[int] | None = None
    if (epoch is not None and present) or vector is not None:
        allow = await allow_list_ids(
            session, tables, profile, membership_budget, channel, fan_arms=fan_arms, deadline=deadline
        )
    if epoch is not None and present:
        candidates: list[ChunkId] | None = None
        if allow is not None and len(allow) <= SCOPE_ID_BUDGET:
            candidates = await _chunk_ids_for(session, tables, epoch, allow, profile, membership_budget)
        if candidates is None or candidates:
            depth, window_full = FUSION_K, False
            for _probe in range(2):
                ranking = await _chunk_ranking(
                    session, tables, epoch, stats, present, depth, candidates, parameter_budget, membership_budget
                )
                hits, rows = await _entries_for_chunks(
                    session, tables, epoch, ranking, fetched, scope, profile, membership_budget
                )
                window_full = len(ranking) >= depth
                short = window_full and len(hits) < limit
                if not short or candidates is not None or monotonic() > deadline:
                    break
                depth *= PROBE_DEEPEN
            if window_full and len(hits) < limit:
                reason = "candidate window" if candidates is not None else "scope probe budget"
                truncations.append((reason, {"window": depth, "found": len(hits)}))

    vector_hits: dict[EntryId, _Hit] = {}
    vector_depth = max(VECTOR_DEPTH_FACTOR * limit, VECTOR_DEPTH_FLOOR)
    if vector is not None and monotonic() <= deadline:
        vector_hits, vector_rows = await _vector_leg(
            session,
            tables,
            dialect_name,
            vector,
            vector_depth,
            allow,
            limit,
            fetched,
            scope,
            profile,
            membership_budget,
        )
        for entry_id, mapping in vector_rows.items():
            rows.setdefault(entry_id, mapping)

    if monotonic() > deadline:
        truncations.append(("wall-time budget", None))
    skip_verified = False
    if overlay_empty:
        current, still_empty = await pointer_with_overlay(session, tables)
        if current != epoch:
            raise StaleSnapshot("the gram-index epoch pointer moved mid-glean")
        skip_verified = still_empty
    if not skip_verified and monotonic() <= deadline:
        nominees = await entries_for_scan(
            session,
            tables,
            profile,
            parameter_budget,
            membership_budget,
            scope.gates,
            scope.wanted,
            everything=False,
            fetched=fetched,
            limit=OVERLAY_BUDGET,
            deadline=deadline,
        )
        admitted = [mapping for mapping in nominees.rows if scope.admits(mapping)]
        scored, bodies = await _overlay(session, tables, profile, membership_budget, executor, admitted, terms, stats)
        hits.update(scored)
        rows.update({mapping["entry_id"]: mapping for mapping in admitted if mapping["entry_id"] in scored})
        if nominees.overflow:
            truncations.append(("overlay budget", {"scanned": len(nominees.rows), "budget": OVERLAY_BUDGET}))
    if not skip_verified and epoch is not None and await current_epoch(session, tables) != epoch:
        raise StaleSnapshot("the gram-index epoch pointer moved mid-glean")

    fused = _fuse(ranker, hits, vector_hits)
    signals = await signal_factors(session, tables, profile, membership_budget, ranker, list(fused.entries))
    for entry_id, factor in signals.factors.items():
        fused.entries[entry_id] *= factor
    ordered = _order(fused.entries, rows)[:limit]
    wanted = [chunk_id for entry_id, _ in ordered for chunk_id, _ in fused.chunks[entry_id]]
    texts = await _chunk_texts(session, tables, wanted, profile, membership_budget)
    mask = frozenset(fetched | {"score", "matches"})
    projected = tuple(fetched - {"content"})
    sources = _Sources(texts, bodies, terms)
    carried = ranker.aggregate.chunks_per_entry
    observed = [
        _observe(rows[eid], _Hit(fused.entries[eid], fused.chunks[eid][:carried]), score, sources, projected, mask)
        for eid, score in ordered
    ]
    errors = [
        *records,
        *signals.records,
        *(
            ResultError(
                kind=VFSErrorKind.truncated,
                severity=Severity.warning,
                message=f"glean result truncated at the {reason}; {REFINE_GUIDANCE}",
                data=data,
            )
            for reason, data in truncations
        ),
    ]
    export = {
        "n_docs": stats.n_docs,
        "avg_dl": stats.avg_dl,
        "terms": {term: {"df": stats.terms[term].df, "idf": stats.terms[term].idf} for term in present},
    }
    legs: dict[str, Any] = {
        "lexical": {"hits": len(hits), "terms": present},
        "vector": None
        if vector is None
        else {"tier": vector.tier, "model": vector.model_id, "depth": vector_depth, "hits": len(vector_hits)},
        "fusion": repr(ranker.fusion),
        "fused": "client",
        "signals": signals.explain,
    }
    return Result(ops=("glean",), observations=observed, errors=errors, lexical_stats=export, legs=legs)


# ---------------------------------------------------------------------------
# The narrow rung — allow-list entries to chunk ids
# ---------------------------------------------------------------------------


async def _chunk_ids_for(
    session: AsyncSession,
    tables: VFSTables,
    epoch: Epoch,
    doc_ids: Sequence[int],
    profile: DialectProfile,
    membership_budget: int,
) -> list[ChunkId]:
    """The epoch's chunk ids of the entries with surrogate ids *doc_ids*, sorted."""
    entry, docs = tables.entry, tables.lex_docs
    found: list[ChunkId] = []
    for chunk in chunked(list(doc_ids), membership_budget):
        stmt = (
            select(docs.c.chunk_id)
            .select_from(docs.join(entry, entry.c.entry_id == docs.c.entry_id))
            .where(docs.c.epoch == epoch, membership(entry.c.id, chunk, profile))
        )
        found.extend((await session.execute(stmt)).scalars())
    found.sort()
    return found


# ---------------------------------------------------------------------------
# The two rounds
# ---------------------------------------------------------------------------


async def _chunk_ranking(
    session: AsyncSession,
    tables: VFSTables,
    epoch: Epoch,
    stats: TermStatistics,
    present: Sequence[str],
    k: int,
    candidates: Sequence[ChunkId] | None,
    parameter_budget: int,
    membership_budget: int,
) -> Ranking:
    """Top-``k`` ``(chunk_id, score)`` from the head fetch plus the selected blocks."""
    postings = tables.lex_postings
    columns = (postings.c.term, postings.c.block_no, postings.c.doc_ids, postings.c.tfs, postings.c.dls)
    summaries = {term: decode_summary(stats.terms[term].blocks) for term in present}
    idfs = [stats.terms[term].idf for term in present]
    index = {term: position for position, term in enumerate(present)}

    def as_blocks(fetched: Sequence[Any]) -> list[ScoreBlock]:
        return [
            ScoreBlock(
                index[r.term], summaries[r.term].max_weights[r.block_no], bytes(r.doc_ids), bytes(r.tfs), bytes(r.dls)
            )
            for r in fetched
        ]

    blocks: list[ScoreBlock] = []
    for probe in chunked(list(present), membership_budget):
        head = select(*columns).where(
            postings.c.epoch == epoch, postings.c.term.in_(probe), postings.c.block_no < HEAD_BLOCKS
        )
        blocks += as_blocks((await session.execute(head)).all())
    scored = score_blocks(blocks, idfs, stats.avg_dl, 10**9, candidates=candidates)
    theta = scored[k - 1][1] if len(scored) >= k else 0.0
    score_of = dict(scored)
    sorted_candidates = sorted(score_of)
    tail = [score_of[chunk] for chunk in sorted_candidates]
    overflowing = [term for term in present if len(summaries[term].first_ids) > HEAD_BLOCKS]
    selected = select_blocks([summaries[term] for term in overflowing], sorted_candidates, tail, theta)
    arms: list[tuple[int, ColumnElement[bool]]] = []
    for term, competing in zip(overflowing, selected, strict=True):
        wanted = [no for no in competing if no >= HEAD_BLOCKS]
        for nos in chunked(wanted, membership_budget):
            arm = and_(postings.c.epoch == epoch, postings.c.term == term, postings.c.block_no.in_(list(nos)))
            arms.append((len(nos) + 2, arm))
    for statement in _packed_arms(arms, parameter_budget):
        blocks += as_blocks((await session.execute(select(*columns).where(or_(*statement)))).all())
    return score_blocks(blocks, idfs, stats.avg_dl, k, candidates=candidates)


def _packed_arms(
    arms: Sequence[tuple[int, ColumnElement[bool]]], parameter_budget: int
) -> list[list[ColumnElement[bool]]]:
    """Round-two arms grouped into statements whose bind spend stays inside the budget."""
    statements: list[list[ColumnElement[bool]]] = []
    spend = 0
    for binds, arm in arms:
        if not statements or spend + binds > parameter_budget:
            statements.append([])
            spend = 0
        statements[-1].append(arm)
        spend += binds
    return statements


async def _entries_for_chunks(
    session: AsyncSession,
    tables: VFSTables,
    epoch: Epoch,
    ranking: Ranking,
    fetched: frozenset[str],
    scope: _Gates,
    profile: DialectProfile,
    membership_budget: int,
) -> tuple[dict[EntryId, _Hit], dict[EntryId, RowMapping]]:
    """MaxP: the ranked chunks resolved to their live, encoded, admitted entries' rows.

    One join per id chunk — ``lex_docs`` names the chunk's entry and the
    entry row supplies the facts — carrying the content-kind gate,
    ``encoded`` and the scope's pushdown; the authoritative gate then
    runs on every row. Each entry keeps its best :data:`TOP_CHUNKS`
    chunks; its score is the best one's.
    """
    entry, docs = tables.entry, tables.lex_docs
    columns = [
        docs.c.chunk_id,
        *(entry.c[field] for field in sorted((fetched | FETCH_RIDE | {"entry_id"}) - {"content"})),
    ]
    kinds = kind_membership(entry)
    per_chunk = max(1, membership_budget - scope.pushdown.binds - kinds.binds)
    score_of = dict(ranking)
    owner: dict[ChunkId, EntryId] = {}
    rows: dict[EntryId, RowMapping] = {}
    for chunk in chunked([chunk_id for chunk_id, _ in ranking], per_chunk):
        stmt = (
            select(*columns)
            .select_from(docs.join(entry, entry.c.entry_id == docs.c.entry_id))
            .where(
                docs.c.epoch == epoch,
                membership(docs.c.chunk_id, chunk, profile),
                entry.c.encoded,
                kinds.predicate,
                *scope.pushdown.terms,
            )
        )
        for mapping in (await session.execute(stmt)).mappings():
            entry_id = mapping["entry_id"]
            if entry_id not in rows and not scope.admits(mapping):
                continue
            owner[mapping["chunk_id"]] = entry_id
            rows.setdefault(entry_id, mapping)
    hits: dict[EntryId, _Hit] = {}
    for chunk_id, score in ranking:  # already best first
        entry_id = owner.get(chunk_id)
        if entry_id is None:
            continue
        hit = hits.get(entry_id)
        if hit is None:
            hits[entry_id] = _Hit(score_of[chunk_id], [(chunk_id, score)])
        elif len(hit.chunks) < TOP_CHUNKS:
            hit.chunks.append((chunk_id, score))
    return hits, {entry_id: rows[entry_id] for entry_id in hits}


# ---------------------------------------------------------------------------
# The vector leg — one in-engine statement, the scope inside it
# ---------------------------------------------------------------------------


async def _vector_leg(
    session: AsyncSession,
    tables: VFSTables,
    dialect_name: str,
    vector: VectorLeg,
    depth: int,
    allow: Sequence[int] | None,
    limit: int,
    fetched: frozenset[str],
    scope: _Gates,
    profile: DialectProfile,
    membership_budget: int,
) -> tuple[dict[EntryId, _Hit], dict[EntryId, RowMapping]]:
    """The *depth* nearest chunks by cosine, resolved to admitted entries and MaxP'd.

    One statement shape on every dialect: the chunk table joined to its
    entry, ``embedding IS NOT NULL`` and the liveness, kind and pushdown
    predicates inside, ordered by the engine's cosine distance then
    chunk id, limited. A narrow allow-list runs it once per id chunk
    and merges the lists client-side (a per-chunk top-k is not the
    union's, so every chunk's list is kept whole); a wide scope runs
    it once, gates the rows it fetched, and deepens once when the
    gate leaves fewer entries than asked. Scores are similarities
    (``1 - distance``), best first.
    """
    chunks, entry = tables.chunks, tables.entry
    if vector.prelude is not None:
        await session.execute(text(vector.prelude))
    distance = cosine_distance(dialect_name, chunks.c.embedding, vector.query).label("distance")
    columns = [
        chunks.c.id.label("chunk_id"),
        distance,
        *(entry.c[field] for field in sorted((fetched | FETCH_RIDE | {"entry_id"}) - {"content"})),
    ]
    kinds = kind_membership(entry)
    base = (
        select(*columns)
        .select_from(chunks.join(entry, entry.c.entry_id == chunks.c.entry_id))
        .where(
            chunks.c.embedding.isnot(None),
            entry.c.chunked,
            entry.c.deleted_at.is_(None),
            kinds.predicate,
            *scope.pushdown.terms,
        )
        .order_by(distance, chunks.c.id)
    )
    ranked: list[RowMapping] = []
    if allow is not None and len(allow) <= SCOPE_ID_BUDGET:
        per_chunk = max(1, membership_budget - scope.pushdown.binds - kinds.binds)
        for ids in chunked(list(allow), per_chunk):
            stmt = base.where(membership(entry.c.id, ids, profile)).limit(depth)
            ranked.extend((await session.execute(stmt)).mappings().all())
        ranked.sort(key=lambda mapping: (mapping["distance"], mapping["chunk_id"]))
        ranked = ranked[:depth]
    else:
        window = depth
        for _probe in range(2):
            ranked = list((await session.execute(base.limit(window))).mappings().all())
            admitted = {mapping["entry_id"] for mapping in ranked if scope.admits(mapping)}
            if len(admitted) >= limit or len(ranked) < window:
                break
            window *= PROBE_DEEPEN
    hits: dict[EntryId, _Hit] = {}
    rows: dict[EntryId, RowMapping] = {}
    for mapping in ranked:
        entry_id = mapping["entry_id"]
        if entry_id not in rows and not scope.admits(mapping):
            continue
        similarity = 1.0 - float(mapping["distance"])
        hit = hits.get(entry_id)
        if hit is None:
            hits[entry_id] = _Hit(similarity, [(mapping["chunk_id"], similarity)])
            rows[entry_id] = mapping
        else:
            hit.chunks.append((mapping["chunk_id"], similarity))
    return hits, rows


# ---------------------------------------------------------------------------
# The overlay — live bodies as query-time blocks
# ---------------------------------------------------------------------------


async def _overlay(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    executor: Executor,
    admitted: Sequence[RowMapping],
    terms: Sequence[str],
    stats: TermStatistics,
) -> tuple[dict[EntryId, _Hit], dict[EntryId, str]]:
    """The admitted ``NOT encoded`` rows scored from their live text on the epoch's scale.

    A term the epoch never saw — a word first written since the last
    reindex, or every term of a never-indexed store — takes its idf
    from the overlay itself (its document frequency there, over the
    epoch's corpus size plus the overlay's); with no epoch at all the
    overlay is the corpus, mean length included. The scored entries'
    bodies ride back beside the hits: their previews are cut from the
    text already fetched here, never from a second read.
    """
    if not admitted:
        return {}, {}
    surrogate = await _surrogate_ids(
        session, tables, [mapping["entry_id"] for mapping in admitted], profile, membership_budget
    )
    bodies = await content_for_entries(session, tables, profile, membership_budget, list(surrogate))
    docs = sorted((surrogate[entry_id], _text(body)) for entry_id, body in bodies.items())
    blocks, idfs, avg_dl = await call_offloaded(executor, partial(_overlay_blocks, docs, terms, stats))
    by_surrogate = {doc_id: entry_id for entry_id, doc_id in surrogate.items()}
    ranked = score_blocks(blocks, idfs, avg_dl, OVERLAY_BUDGET)
    hits = {by_surrogate[doc_id]: _Hit(score, [(-1, score)]) for doc_id, score in ranked}
    texts = dict(docs)
    return hits, {entry_id: texts[surrogate[entry_id]] for entry_id in hits}


def _text(body: Body) -> str:
    return body if isinstance(body, str) else body.decode("utf-8", "surrogatepass")


async def _surrogate_ids(
    session: AsyncSession,
    tables: VFSTables,
    entry_ids: Sequence[EntryId],
    profile: DialectProfile,
    membership_budget: int,
) -> dict[EntryId, int]:
    """``entry_id → surrogate id``: the overlay's doc ids, strictly ordered as the codec requires."""
    entry = tables.entry
    out: dict[EntryId, int] = {}
    for chunk in chunked(list(entry_ids), membership_budget):
        stmt = select(entry.c.entry_id, entry.c.id).where(membership(entry.c.entry_id, chunk, profile))
        out.update({row.entry_id: row.id for row in await session.execute(stmt)})
    return out


def _overlay_blocks(
    docs: Sequence[tuple[int, str]], terms: Sequence[str], stats: TermStatistics
) -> tuple[list[ScoreBlock], list[float], float]:
    """Every query term's postings over the overlay documents as blocks, with
    the idfs and mean length they score under — the offloaded CPU."""
    per_term: list[list[tuple[int, int, int]]] = [[] for _ in terms]
    positions = {term: position for position, term in enumerate(terms)}
    total_dl = 0
    for doc_id, content in docs:
        tokens = tokenize(content)
        total_dl += len(tokens)
        counts = Counter(tokens)
        for term, position in positions.items():
            tf = counts.get(term, 0)
            if tf:
                per_term[position].append((doc_id, tf, len(tokens)))
    n_docs = stats.n_docs + len(docs)
    avg_dl = stats.avg_dl if stats.n_docs else (total_dl / len(docs) if docs else 0.0)
    idfs = [
        stats.terms[term].idf if term in stats.terms else idf(len(per_term[position]), n_docs)
        for position, term in enumerate(terms)
    ]
    blocks: list[ScoreBlock] = []
    for position, postings in enumerate(per_term):
        for page in chunked(postings, BLOCK_SIZE):
            ids, tfs, dls = zip(*page, strict=True)
            bound = max(term_weight(tf, dl, avg_dl, idfs[position]) for tf, dl in zip(tfs, dls, strict=True))
            blocks.append(ScoreBlock(position, bound, *encode_block(ids, tfs, dls)))
    return blocks, idfs, avg_dl


# ---------------------------------------------------------------------------
# Assembly — normalise, order, observe
# ---------------------------------------------------------------------------


class _Fused(NamedTuple):
    """The fused entry scores and, per entry, its chunks ``(chunk_id, fused score)`` best first."""

    entries: dict[EntryId, float]
    chunks: dict[EntryId, list[tuple[ChunkId, float]]]


def _fuse(ranker: Ranker, lexical: dict[EntryId, _Hit], vector: dict[EntryId, _Hit]) -> _Fused:
    """Normalise each leg by its own law, fuse entries, then fuse each entry's chunks the same way.

    BM25 is min-max scaled over the lexical candidate union — chunks by
    the entries' range, so no chunk outranks its own entry — and cosine
    by its theoretical range. A leg with no hits is absent, and the
    fusion's weights renormalise over the legs present; an entry the
    fusion did not score (its only leg carries no weight) is dropped
    with its chunks. Chunk keys are ``(entry, chunk)``: the overlay's
    whole-document chunk shares one id across entries.
    """
    legs: dict[str, dict[EntryId, float]] = {}
    chunk_legs: dict[str, dict[tuple[EntryId, ChunkId], float]] = {}
    if lexical:
        raw = {entry_id: hit.score for entry_id, hit in lexical.items()}
        low, high = min(raw.values()), max(raw.values())
        span = high - low
        legs["lexical"] = min_max(raw)
        chunk_legs["lexical"] = {
            (entry_id, chunk_id): (1.0 if span == 0.0 else max(0.0, (score - low) / span))
            for entry_id, hit in lexical.items()
            for chunk_id, score in hit.chunks
        }
    if vector:
        legs["vector"] = {entry_id: unit_cosine(hit.score) for entry_id, hit in vector.items()}
        chunk_legs["vector"] = {
            (entry_id, chunk_id): unit_cosine(score)
            for entry_id, hit in vector.items()
            for chunk_id, score in hit.chunks
        }
    entries = ranker.fusion.fuse(legs)
    fused_chunks = ranker.fusion.fuse(chunk_legs)
    chunks: dict[EntryId, list[tuple[ChunkId, float]]] = {entry_id: [] for entry_id in entries}
    for (entry_id, chunk_id), score in fused_chunks.items():
        if entry_id in chunks:
            chunks[entry_id].append((chunk_id, score))
    for scored in chunks.values():
        scored.sort(key=lambda item: (-item[1], item[0]))
    return _Fused(entries, chunks)


def _order(scores: dict[EntryId, float], rows: dict[EntryId, RowMapping]) -> list[tuple[EntryId, float]]:
    """Entries by fused score, then path: min-max over the union, rounded — the unit scale every answer keeps."""
    scaled = {entry_id: round(score, SCORE_DECIMALS) for entry_id, score in min_max(scores).items()}
    return sorted(scaled.items(), key=lambda item: (-item[1], rows[item[0]]["path"]))


async def _chunk_texts(
    session: AsyncSession,
    tables: VFSTables,
    chunk_ids: Sequence[ChunkId],
    profile: DialectProfile,
    membership_budget: int,
) -> dict[ChunkId, RowMapping]:
    """The winning chunks' line bounds and text — only what the answer carries."""
    chunks = tables.chunks
    wanted = sorted({chunk_id for chunk_id in chunk_ids if chunk_id >= 0})
    out: dict[ChunkId, RowMapping] = {}
    for page in chunked(wanted, membership_budget):
        stmt = select(chunks.c.id, chunks.c.line_start, chunks.c.line_end, chunks.c.content).where(
            membership(chunks.c.id, page, profile)
        )
        out.update({mapping["id"]: mapping for mapping in (await session.execute(stmt)).mappings()})
    return out


def _observe(
    mapping: RowMapping,
    hit: _Hit,
    score: float,
    sources: _Sources,
    projected: tuple[str, ...],
    mask: frozenset[str],
) -> Observation:
    """One entry row with its best chunks as ``Match`` rows, chunk scores on the entry's scale.

    Every region carries its preview, cut from text already in hand: a
    chunk's own row, or the live body the overlay scored. An overlay
    entry answers as one whole document — bounds over the whole body,
    no ``content`` (a file is not a chunk), the preview alone.
    """
    values: dict[str, object] = {field: mapping[field] for field in projected}
    values["path"] = Path._brand(mapping["path"])
    # Chunks ride on the entry's scale: the best chunk carries the entry's score.
    ratio = score / hit.score if hit.score else 0.0
    matches: list[Match] = []
    for chunk_id, chunk_score in hit.chunks:
        chunk_scaled = round(chunk_score * ratio, SCORE_DECIMALS)
        if chunk_id < 0:
            body = sources.bodies[mapping["entry_id"]]
            start, end, content = 1, max(1, len(split_lines(body))), None
            excerpt = select_preview(body, 1, sources.terms)
        else:
            chunk = sources.chunks[chunk_id]
            start, end, content = chunk["line_start"], chunk["line_end"], chunk["content"]
            excerpt = select_preview(content, start, sources.terms)
        matches.append(
            Match(
                start=start,
                end=end,
                match=None,
                content=content,
                score=chunk_scaled,
                preview=excerpt.text,
                preview_start=excerpt.start,
                preview_end=excerpt.end,
            )
        )
    values["score"] = score
    values["matches"] = matches
    values["populated"] = mask
    return Observation.model_validate(values)
