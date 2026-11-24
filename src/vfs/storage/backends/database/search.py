"""Ranked search over the lexical index — the BM25 leg of ``search``.

The verb is grep's shape with a scorer where grep has a matcher: one
session, SELECTs only, the backend's redrive around it, scope crossing
the seam in one shape: the ``globs`` channels entry-wide, roots beside
the arms (``scope``), and the ``ext`` channels beside both. A query's
terms go through the index's tokenizer;
**round one** probes their summary rows (``lex_df`` with the epoch's
statistics) and fetches every term's head blocks (``block_no <
lexical.HEAD_BLOCKS``); the engine scores what it has at the fusion depth;
**round two** asks the engine which later blocks of the overflowing
terms can still change that top-k (:func:`~vfs.models.lexical.select_blocks`)
and fetches exactly those by key — as one ``(term, block_no)`` tuple
membership under the epoch equality where the engine accepts the form,
else as OR arms each a full primary-key prefix
(:func:`~vfs.storage.backends.database.lexical.tail_block_statements`) — then scores again. No scoring SQL
runs on any dialect; every statement is a key fetch.

The ladder has two rungs. The channel's segment-posting allow-list
(grep's nomination pruning) prices the scope: when it resolves to at
most :data:`SCOPE_ID_BUDGET` entries their chunk ids become the
scorer's candidate set (**filter, then fetch** — exact); a wider or
unprunable scope scores first and gates the top chunks' entries as
their rows are fetched (**fetch, then filter**), one deeper probe when
the first runs short, then a loud record. Either way
:func:`~vfs.storage.backends.database.scope.passes_gates` is the
authority on every row that answers, over verdicts judged in one hop
per fetched set on the offload pool, under the call's wall; a row the
engine did not judge in time is dropped, with one wall record.

Freshness is grep's: ``encoded=True`` on a content row means the
entry's terms are in the current lexical epoch (a directory, with
nothing to index, is always ``encoded``); the ``NOT encoded`` rows the
gates admit are the overlay — nominated in path order up to the scan
tier's shared count, their live bodies fetched in byte batches under
the call's wall and counted by the engine's overlay kernel (tokenized
with the index's own rules, the query terms counted in place, no body
kept past its batch), the postings encoded as blocks at query time and
scored by the same engine with the epoch's statistics, so the two
sides share one formula, one accumulation order and one scale. The
previews of the overlay entries that answer come from one bounded read
of those entries' live bodies after the order is settled. The generation
read is advisory and re-issued after the fetch (the two-read protocol);
a moved generation raises :class:`StaleSnapshot` for the backend to
redrive. A carried chunk the text read no longer finds answers from its
entry's live body in the overlay's whole-document shape; an entry whose
body is gone too raises :class:`StaleSnapshot`.

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

from functools import partial
from typing import TYPE_CHECKING, Any, Final, NamedTuple

from sqlalchemy import LargeBinary, cast, select, text

from vfs.batching import byte_chunked
from vfs.deadline import WALL_TIME_BUDGET, WALL_TIME_CAUSE, Deadline
from vfs.models import Match, Observation
from vfs.models.lexical import (
    BLOCK_SIZE,
    ScoreBlock,
    encode_block,
    idf,
    overlay_postings,
    score_blocks,
    term_weight,
    tokenize,
)
from vfs.offload import CONTENT_BYTE_BUDGET, call_offloaded, judge_rows, wall_truncation
from vfs.paths import ROOT, TRASH_ROOT, Path
from vfs.pattern_matching import PatternError, compile_gates, escape_glob
from vfs.pattern_matching.grep import split_lines
from vfs.results import ErrorKind, Result, ResultError, Severity, classified
from vfs.results.preview import select_preview
from vfs.storage.backends.database.dialects import StaleSnapshot, arm_budget, chunked
from vfs.storage.backends.database.distance import cosine_distance
from vfs.storage.backends.database.indexing import current_generation, live_set, pointer_with_overlay
from vfs.storage.backends.database.lexical import (
    ChunkId,
    Lexicon,
    Ranking,
    TermStatistics,
    chunk_ids_for,
    chunk_ranking,
    lexical_stats,
    visible_lexicon,
)
from vfs.storage.backends.database.membership import live_chunks, membership
from vfs.storage.backends.database.pathterms import allow_list_ids
from vfs.storage.backends.database.reads import (
    CHANNEL_ARM_BINDS,
    DERIVED_FIELDS,
    content_for_entries,
    effective_columns,
    kind_membership,
    meta_scoped,
    scope_facts,
    side_scope,
    vid_of,
)
from vfs.storage.backends.database.rights import RIGHTS_FIELDS
from vfs.storage.backends.database.scope import (
    FETCH_RIDE,
    SCAN_TIER_BUDGET,
    entries_for_scan,
    passes_gates,
    pushdown_terms,
    scope_channels,
    scope_exclusions,
    stored_size,
    trash_scope,
)
from vfs.storage.backends.database.seams import seam
from vfs.storage.backends.database.signals import signal_factors
from vfs.storage.ranking import REFINE_GUIDANCE, SCORE_DECIMALS, TOP_CHUNKS, Ranker, min_max, unit_cosine

if TYPE_CHECKING:
    from collections.abc import Sequence
    from concurrent.futures import Executor

    from sqlalchemy.engine import RowMapping
    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.models.lexical import OverlayPostings
    from vfs.models.rows import EntryId, VFSTables
    from vfs.pattern_matching import Body, GlobGates
    from vfs.storage.backends.database.dialects import DialectProfile
    from vfs.storage.backends.database.reads import AdmittedScope
    from vfs.storage.backends.database.rights import Clause, Visibility
    from vfs.storage.backends.database.scope import Pushdown
    from vfs.vid import VidMint

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

HEAD_ROWS: Final = frozenset({ROOT, TRASH_ROOT})
"""Rows in hand that name no file: the storage's root and the trash view's head, left out as directories are."""


class _Gates(NamedTuple):
    """The call's structural scope: its gates (glob and ext channels), the fetch pushdown, the tombstone side."""

    gates: GlobGates
    pushdown: Pushdown
    trashed: bool

    def admits(self, mapping: RowMapping, verdict: int | None) -> bool:
        return passes_gates(mapping, self.gates, verdict, trashed=self.trashed)

    async def judge(
        self, executor: Executor, rows: Sequence[RowMapping], deadline: Deadline
    ) -> tuple[dict[EntryId, int | None], bool]:
        """Each distinct entry's verdict among *rows*, judged in one hop, and whether all were judged.

        An entry's rows (one per chunk) share its path and name, so each entry is judged once.
        """
        subjects = {mapping["entry_id"]: (mapping["path"], mapping["name"]) for mapping in rows}
        verdicts, completed = await judge_rows(executor, self.gates, list(subjects.values()), deadline=deadline)
        return dict(zip(subjects, verdicts, strict=True)), completed


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


class _OverlayCount(NamedTuple):
    """What the overlay's kernel batches counted: per query term, the ``(doc_id, tf, dl)`` postings
    in arrival order; the bodies reached; their summed token count."""

    postings: list[list[tuple[int, int, int]]]
    reached: int
    total_dl: int


# ---------------------------------------------------------------------------
# The verb
# ---------------------------------------------------------------------------


async def search_rows(
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
    view: Visibility | None = None,
    scope: AdmittedScope | None = None,
    mint: VidMint,
) -> Result:
    """One row per entry, best first: the legs fused, the index side unioned with the overlay.

    Scoping arrives in grep's one shape: the ``globs`` channels
    entry-wide and the roots beside the arms as *scope*, in the same one
    call and snapshot, read by the allow-list, the pushdown, the
    overlay's fan and the gates exactly as grep reads them, under the
    prefilter the scope's side chose; piped
    *observations* are rows in entry coordinates and admit their own
    paths literally. *limit* counts entries. *wall_seconds* is the
    caller-configured wall-clock budget; the declared default keeps
    direct callers honest. *vector* is the embedded query and its tier,
    or ``None`` for a lexical-only answer; *ranker* names the fusion;
    *records* are the backend's per-call notes (an absent provider, a
    stale space) that ride the envelope.

    Under a partial *view* the statistics are the visible set's — ``N``,
    mean length and every term's ``df`` counted over the rows the caller
    can see, so a hidden row never moves a visible score — and the
    lexical leg scores only visible chunks; see :func:`~vfs.storage.backends.database.lexical.visible_lexicon`
    for what that costs. Both legs and the overlay pass every row
    through the view.
    """
    ranker = ranker or Ranker()
    terms = list(dict.fromkeys(tokenize(query)))
    if not terms:
        detail = f"search query {query!r} has no searchable term after folding"
        return Result(ops=("search",), errors=[classified(ErrorKind.invalid, detail=detail)])
    if observations:
        held = tuple(escape_glob(str(row.path)) for row in observations if str(row.path) not in HEAD_ROWS)
        if not held and not globs:
            return Result(ops=("search",))
        globs = (*globs, *held)
    try:
        admissions, trashed = trash_scope(globs, scope)
        exclusions = scope_exclusions(globs_not, trashed=trashed)
    except PatternError as exc:
        return Result(ops=("search",), errors=[classified(ErrorKind.invalid, detail=str(exc))])
    side = side_scope(scope, trashed=trashed)
    entry = tables.entry
    channels = scope_channels(admissions, side, None if scope is None else scope.composed(trashed=trashed))
    channel = channels.allowed
    fan_arms = arm_budget(profile, parameter_budget, CHANNEL_ARM_BINDS)
    gates = compile_gates(admissions, exclusions, ext=ext, ext_not=ext_not, marked=meta_scoped, scope=side)
    pushdown = pushdown_terms(
        entry,
        profile,
        fan_arms,
        membership_budget,
        channels.facts,
        gates.wanted,
        hide_meta=not (gates.admissions or gates.scoped),
        trashed=trashed,
    )
    gated = _Gates(gates, pushdown, trashed)
    fetched = effective_columns(columns, content=False)
    deadline = Deadline.after(wall_seconds)
    truncations: list[tuple[str, dict[str, Any] | None]] = []

    snapshot = await pointer_with_overlay(session, tables)
    epoch, overlay_empty = snapshot.pointer, snapshot.overlay_empty
    live = await live_set(session, tables, epoch)
    await seam("search:after-pointer-read")
    stats = await lexical_stats(session, tables, profile, live, terms, membership_budget)
    lexicon: Lexicon | None = None
    if view is not None and epoch is not None:
        lexicon = await visible_lexicon(session, tables, profile, membership_budget, live, stats, terms, view)
        stats = lexicon.stats
    present = [term for term in terms if term in stats.terms]

    hits: dict[EntryId, _Hit] = {}
    rows: dict[EntryId, RowMapping] = {}
    overlay: dict[EntryId, _Hit] = {}
    allow: list[int] | None = None
    if (epoch is not None and present) or vector is not None:
        allow = await allow_list_ids(
            session, tables, profile, membership_budget, channel, fan_arms=fan_arms, deadline=deadline
        )
    if epoch is not None and present:
        candidates: list[ChunkId] | None = None
        if allow is not None and len(allow) <= SCOPE_ID_BUDGET:
            candidates = await chunk_ids_for(session, tables, live, allow, profile, membership_budget)
        if lexicon is not None:
            candidates = lexicon.visible if candidates is None else sorted(set(candidates) & set(lexicon.visible))
        if candidates is None or candidates:
            depth, window_full = FUSION_K, False
            for _probe in range(2):
                if lexicon is not None:
                    ranking = score_blocks(lexicon.blocks, lexicon.idfs, stats.avg_dl, depth, candidates=candidates)
                else:
                    ranking = await chunk_ranking(
                        session,
                        tables,
                        live,
                        stats,
                        present,
                        depth,
                        candidates,
                        profile,
                        membership_budget,
                    )
                hits, rows, completed = await _entries_for_chunks(
                    session,
                    tables,
                    live,
                    ranking,
                    fetched,
                    gated,
                    profile,
                    membership_budget,
                    executor,
                    deadline,
                    view,
                )
                if not completed:
                    _record_wall(truncations)
                window_full = len(ranking) >= depth
                short = window_full and len(hits) < limit
                if not short or candidates is not None or deadline.expired():
                    break
                depth *= PROBE_DEEPEN
            if window_full and len(hits) < limit:
                reason = "candidate window" if candidates is not None else "scope probe budget"
                truncations.append((reason, {"window": depth, "found": len(hits)}))

    vector_hits: dict[EntryId, _Hit] = {}
    vector_depth = max(VECTOR_DEPTH_FACTOR * limit, VECTOR_DEPTH_FLOOR)
    if vector is not None and not deadline.expired():
        vector_hits, vector_rows, completed = await _vector_leg(
            session,
            tables,
            dialect_name,
            vector,
            vector_depth,
            allow,
            limit,
            fetched,
            gated,
            profile,
            membership_budget,
            executor,
            deadline,
            view,
        )
        if not completed:
            _record_wall(truncations)
        for entry_id, mapping in vector_rows.items():
            rows.setdefault(entry_id, mapping)

    if deadline.expired():
        _record_wall(truncations)
    skip_verified = False
    if overlay_empty:
        again = await pointer_with_overlay(session, tables)
        if again.generation != snapshot.generation:
            raise StaleSnapshot("the index generation moved mid-search")
        skip_verified = again.overlay_empty
    if not skip_verified and not deadline.expired():
        nominees = await entries_for_scan(
            session,
            tables,
            profile,
            parameter_budget,
            membership_budget,
            (*gated.gates.admissions, *channels.prefilter),
            gated.gates.wanted,
            everything=False,
            fetched=fetched,
            limit=SCAN_TIER_BUDGET,
            deadline=deadline,
            trashed=gated.trashed,
            scope_roots=channels.roots,
            scope_facts=scope_facts(entry, profile, parameter_budget, membership_budget, channels.arms),
            view=view,
        )
        verdicts, completed = await gated.judge(executor, nominees.rows, deadline)
        if not completed:
            _record_wall(truncations)
        admitted = [m for m in nominees.rows if gated.admits(m, verdicts[m["entry_id"]])]
        overlay, completed = await _overlay(
            session, tables, profile, membership_budget, executor, admitted, terms, stats, deadline
        )
        if not completed:
            _record_wall(truncations)
        hits.update(overlay)
        rows.update({mapping["entry_id"]: mapping for mapping in admitted if mapping["entry_id"] in overlay})
        if nominees.overflow:
            truncations.append(("overlay budget", {"scanned": len(nominees.rows), "budget": SCAN_TIER_BUDGET}))
    if not skip_verified and epoch is not None and await current_generation(session, tables) != snapshot.generation:
        raise StaleSnapshot("the index generation moved mid-search")

    fused = _fuse(ranker, hits, vector_hits)
    signals = await signal_factors(session, tables, profile, membership_budget, ranker, list(fused.entries))
    for entry_id, factor in signals.factors.items():
        fused.entries[entry_id] *= factor
    ordered = _order(fused.entries, rows)[:limit]
    wanted = [chunk_id for entry_id, _ in ordered for chunk_id, _ in fused.chunks[entry_id]]
    await seam("search:before-chunk-texts")
    texts = await _chunk_texts(session, tables, wanted, profile, membership_budget)
    # An entry whose ranked chunk is gone was re-split or purged: its live body answers it whole, or it redrives.
    gone = [eid for eid, _ in ordered if any(cid >= 0 and cid not in texts for cid, _ in fused.chunks[eid])]
    resplit = await _resplit_bodies(session, tables, profile, membership_budget, gone, view)
    if len(resplit) < len(gone):
        raise StaleSnapshot("an entry the answer carries is gone since it was ranked")
    fused.chunks.update({entry_id: [(-1, fused.chunks[entry_id][0][1])] for entry_id in resplit})
    answering = [entry_id for entry_id, _ in ordered if entry_id in overlay]
    bodies = {**await _overlay_bodies(session, tables, profile, membership_budget, answering), **resplit}
    # An overlay body that did not come back was purged between the count and
    # the preview read: absent, as grep leaves a body that did not come back.
    ordered = [(entry_id, score) for entry_id, score in ordered if entry_id not in overlay or entry_id in bodies]
    mask = frozenset(fetched | {"score", "matches"})
    projected = tuple(fetched - {"content"} - DERIVED_FIELDS)
    sources = _Sources(texts, bodies, terms)
    carried = ranker.aggregate.chunks_per_entry
    observed = [
        _observe(
            rows[eid], _Hit(fused.entries[eid], fused.chunks[eid][:carried]), score, sources, projected, mask, mint
        )
        for eid, score in ordered
    ]
    errors = [
        *records,
        *signals.records,
        *(_truncation_record(reason, data) for reason, data in truncations),
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
    return Result(ops=("search",), observations=observed, errors=errors, lexical_stats=export, legs=legs)


async def _entries_for_chunks(
    session: AsyncSession,
    tables: VFSTables,
    live: Sequence[int],
    ranking: Ranking,
    fetched: frozenset[str],
    scope: _Gates,
    profile: DialectProfile,
    membership_budget: int,
    executor: Executor,
    deadline: Deadline,
    view: Visibility | None = None,
) -> tuple[dict[EntryId, _Hit], dict[EntryId, RowMapping], bool]:
    """MaxP: the ranked chunks resolved to their live, encoded, admitted entries' rows.

    One join per id chunk — ``lex_docs`` names the chunk's entry and the
    entry row supplies the facts — carrying the content-kind gate,
    ``encoded`` and the scope's pushdown; the authoritative gate then
    runs on every fetched entry, judged in one hop. Each entry keeps its
    best :data:`TOP_CHUNKS` chunks; its score is the best one's. The
    flag says whether every entry was judged before the wall.
    """
    entry, docs = tables.entry, tables.lex_docs
    columns = [
        docs.c.chunk_id,
        *(entry.c[field] for field in sorted((fetched | FETCH_RIDE | {"entry_id"}) - {"content", "vid"})),
    ]
    kinds = kind_membership(entry)
    per_chunk = max(1, membership_budget - scope.pushdown.binds - kinds.binds)
    score_of = dict(ranking)
    owner: dict[ChunkId, EntryId] = {}
    rows: dict[EntryId, RowMapping] = {}
    found: list[RowMapping] = []
    for epochs, chunk in live_chunks(live, [chunk_id for chunk_id, _ in ranking], per_chunk):
        stmt = (
            select(*columns)
            .select_from(docs.join(entry, entry.c.entry_id == docs.c.entry_id))
            .where(
                membership(docs.c.epoch, epochs, profile),
                membership(docs.c.chunk_id, chunk, profile),
                entry.c.encoded,
                kinds.predicate,
                *scope.pushdown.terms,
            )
        )
        found.extend((await session.execute(stmt)).mappings())
    verdicts, completed = await scope.judge(executor, found, deadline)
    for mapping in found:
        entry_id = mapping["entry_id"]
        if entry_id not in rows and not (
            scope.admits(mapping, verdicts[entry_id]) and (view is None or view.holds(mapping, view.need))
        ):
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
    return hits, {entry_id: rows[entry_id] for entry_id in hits}, completed


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
    executor: Executor,
    deadline: Deadline,
    view: Visibility | None = None,
) -> tuple[dict[EntryId, _Hit], dict[EntryId, RowMapping], bool]:
    """The *depth* nearest chunks by cosine, resolved to admitted entries and MaxP'd.

    One statement shape on every dialect: the chunk table joined to its
    entry, ``embedding IS NOT NULL`` and the kind and pushdown predicates
    (the liveness term rides in the pushdown) inside, ordered by the
    engine's cosine distance then
    chunk id, limited. A narrow allow-list runs it once per id chunk
    and merges the lists client-side (a per-chunk top-k is not the
    union's, so every chunk's list is kept whole); a wide scope runs
    it once, gates the rows it fetched, and deepens once when the
    gate leaves fewer entries than asked. Scores are similarities
    (``1 - distance``), best first. Under a partial *view* each
    statement runs once per visibility clause — the distance is computed
    only on rows a clause admits — and the lists merge by distance.
    Each ranked set is judged against the gates in one hop, and the
    flag says whether every hop judged all its entries before the wall.
    """
    chunks, entry = tables.chunks, tables.entry
    if vector.prelude is not None:
        await session.execute(text(vector.prelude))
    distance = cosine_distance(dialect_name, chunks.c.embedding, vector.query).label("distance")
    columns = [
        chunks.c.id.label("chunk_id"),
        distance,
        *(entry.c[field] for field in sorted((fetched | FETCH_RIDE | {"entry_id"}) - {"content", "vid"})),
    ]
    kinds = kind_membership(entry)
    base = (
        select(*columns)
        .select_from(chunks.join(entry, entry.c.entry_id == chunks.c.entry_id))
        .where(
            chunks.c.embedding.isnot(None),
            entry.c.chunked,
            kinds.predicate,
            *scope.pushdown.terms,
        )
        .order_by(distance, chunks.c.id)
    )
    clauses: list[Clause] | None = None if view is None else view.clauses()
    statements = [base] if clauses is None else [base.where(clause.predicate) for clause in clauses]
    spend = max((clause.binds for clause in clauses or ()), default=0)

    verdicts: dict[EntryId, int | None] = {}

    def passes(mapping: RowMapping) -> bool:
        return scope.admits(mapping, verdicts[mapping["entry_id"]]) and (view is None or view.holds(mapping, view.need))

    ranked: list[RowMapping] = []
    finished = True
    if allow is not None and len(allow) <= SCOPE_ID_BUDGET:
        per_chunk = max(1, membership_budget - scope.pushdown.binds - kinds.binds - spend)
        for ids in chunked(list(allow), per_chunk):
            for statement in statements:
                stmt = statement.where(membership(entry.c.id, ids, profile)).limit(depth)
                ranked.extend((await session.execute(stmt)).mappings().all())
        ranked = _nearest(ranked, depth)
        verdicts, finished = await scope.judge(executor, ranked, deadline)
    else:
        window = depth
        for _probe in range(2):
            lists = [
                list((await session.execute(statement.limit(window))).mappings().all()) for statement in statements
            ]
            ranked = _nearest([mapping for found in lists for mapping in found], window)
            verdicts, completed = await scope.judge(executor, ranked, deadline)
            finished = finished and completed
            admitted = {mapping["entry_id"] for mapping in ranked if passes(mapping)}
            if len(admitted) >= limit or all(len(found) < window for found in lists):
                break
            window *= PROBE_DEEPEN
    hits: dict[EntryId, _Hit] = {}
    rows: dict[EntryId, RowMapping] = {}
    for mapping in ranked:
        entry_id = mapping["entry_id"]
        if entry_id not in rows and not passes(mapping):
            continue
        similarity = 1.0 - float(mapping["distance"])
        hit = hits.get(entry_id)
        if hit is None:
            hits[entry_id] = _Hit(similarity, [(mapping["chunk_id"], similarity)])
            rows[entry_id] = mapping
        else:
            hit.chunks.append((mapping["chunk_id"], similarity))
    return hits, rows, finished


def _nearest(rows: Sequence[RowMapping], depth: int) -> list[RowMapping]:
    """The *depth* nearest rows, each chunk once, by distance then chunk id."""
    unique = {mapping["chunk_id"]: mapping for mapping in rows}
    return sorted(unique.values(), key=lambda mapping: (mapping["distance"], mapping["chunk_id"]))[:depth]


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
    deadline: Deadline,
) -> tuple[dict[EntryId, _Hit], bool]:
    """The admitted ``NOT encoded`` rows scored from their live text on the epoch's scale, and whether all were counted.

    The bodies are fetched and counted in ``CONTENT_BYTE_BUDGET`` batches
    metered by stored size, sequentially, the deadline consulted before
    each batch and cut again at worker start inside the kernel hop, so a
    batch's bodies are the only ones resident and none outlives its
    batch. A term the epoch never saw — a word first written since the
    last rebuild, or every term of a never-indexed store — takes its idf
    from the overlay itself (its document frequency there, over the
    epoch's corpus size plus the bodies counted); with no epoch at all
    the overlay is the corpus, mean length included. A wall reached
    before or inside a batch stops there: the bodies counted so far are
    scored, the rest are absent, and the flag says so. Hits only come
    back; the preview of an overlay entry that answers is a second read
    of its live body (:func:`_overlay_bodies`), so a write landing
    between the count and that read yields a preview from the newer body.
    """
    if not admitted:
        return {}, True
    counted = _OverlayCount([[] for _ in terms], 0, 0)
    by_surrogate: dict[int, EntryId] = {}
    completed = True
    for batch in byte_chunked(admitted, stored_size, CONTENT_BYTE_BUDGET):
        if deadline.expired():
            completed = False
            break
        entry_ids = [mapping["entry_id"] for mapping in batch]
        surrogate = await _surrogate_ids(session, tables, entry_ids, profile, membership_budget)
        bodies = await content_for_entries(session, tables, profile, membership_budget, entry_ids)
        present = [entry_id for entry_id in entry_ids if entry_id in bodies and entry_id in surrogate]
        docs = [(surrogate[entry_id], _text(bodies[entry_id])) for entry_id in present]
        by_surrogate.update((surrogate[entry_id], entry_id) for entry_id in present)
        outcome = await call_offloaded(executor, partial(_count_overlay, docs, terms, deadline))
        for postings, found in zip(counted.postings, outcome.postings, strict=True):
            postings.extend(found)
        counted = _OverlayCount(
            counted.postings, counted.reached + outcome.reached, counted.total_dl + outcome.total_dl
        )
        if not outcome.completed:
            completed = False
            break
    blocks, idfs, avg_dl = await call_offloaded(executor, partial(_overlay_blocks, counted, terms, stats))
    ranked = score_blocks(blocks, idfs, avg_dl, SCAN_TIER_BUDGET)
    return {by_surrogate[doc_id]: _Hit(score, [(-1, score)]) for doc_id, score in ranked}, completed


def _count_overlay(docs: Sequence[tuple[int, str]], terms: Sequence[str], deadline: Deadline) -> OverlayPostings:
    """One batch through the engine's kernel, the budget cut at worker start so queue time shortens it."""
    return overlay_postings(docs, terms, budget=deadline.remaining())


async def _overlay_bodies(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    entry_ids: Sequence[EntryId],
) -> dict[EntryId, str]:
    """The live bodies of the overlay entries in the ordered answer, for their previews.

    The caller passes at most its ``limit`` of them; no statement runs
    when no overlay entry answers.
    """
    if not entry_ids:
        return {}
    bodies = await content_for_entries(session, tables, profile, membership_budget, entry_ids)
    return {entry_id: _text(body) for entry_id, body in bodies.items()}


async def _resplit_bodies(
    session: AsyncSession,
    tables: VFSTables,
    profile: DialectProfile,
    membership_budget: int,
    entry_ids: Sequence[EntryId],
    view: Visibility | None,
) -> dict[EntryId, str]:
    """The live bodies of the answer's entries whose ranked chunks are gone, each a row *view* admits where it sits.

    At most the answer's entries, one read per membership chunk, none when no chunk is gone. An entry
    purged, holding no text, or moved out of the view is absent, and the caller redrives.
    """
    entry, content = tables.entry, tables.content
    body = cast(content.c.content, LargeBinary).label("content") if profile.content_bytes else content.c.content
    columns = [entry.c.entry_id, body, entry.c.path, *(entry.c[name] for name in sorted(RIGHTS_FIELDS))]
    out: dict[EntryId, str] = {}
    for chunk in chunked(list(entry_ids), membership_budget):
        stmt = select(*columns).select_from(tables.content_joined()).where(membership(entry.c.entry_id, chunk, profile))
        found = (await session.execute(stmt)).mappings()
        # A body that is missing or empty holds no text: absent, as a purged entry is.
        kept = [m for m in found if m["content"] and (view is None or view.holds(m, view.need))]
        out.update({m["entry_id"]: _text(m["content"]) for m in kept})
    return out


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
    counted: _OverlayCount, terms: Sequence[str], stats: TermStatistics
) -> tuple[list[ScoreBlock], list[float], float]:
    """Every query term's counted postings as blocks, with the idfs and mean
    length they score under — the offloaded CPU.

    The postings arrive in path order across batches and the codec needs
    increasing ids within a block, so each term's are sorted by doc id
    once before paging. The statistics count the bodies the kernel
    reached: a body a wall left uncounted is in neither ``n_docs`` nor
    the mean length.
    """
    n_docs = stats.n_docs + counted.reached
    avg_dl = stats.avg_dl if stats.n_docs else (counted.total_dl / counted.reached if counted.reached else 0.0)
    idfs = [
        stats.terms[term].idf if term in stats.terms else idf(len(counted.postings[position]), n_docs)
        for position, term in enumerate(terms)
    ]
    blocks: list[ScoreBlock] = []
    for position, postings in enumerate(counted.postings):
        for page in chunked(sorted(postings), BLOCK_SIZE):
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
    mint: VidMint,
) -> Observation:
    """One entry row with its best chunks as ``Match`` rows, chunk scores on the entry's scale.

    Every region carries its preview, cut from text already in hand: a
    chunk's own row, or a live body as a bounded read returned it. An
    overlay entry, or one whose chunks are gone, answers as one whole
    document — bounds over the whole body, no ``content`` (a file is
    not a chunk), the preview alone.
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
    if "vid" in mask:
        values["vid"] = vid_of(mint, mapping)
    values["populated"] = mask
    return Observation.model_validate(values)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _record_wall(truncations: list[tuple[str, dict[str, Any] | None]]) -> None:
    """Note the wall once: every site that reaches it writes the same record, and the first one stands."""
    if all(reason != WALL_TIME_CAUSE for reason, _data in truncations):
        truncations.append((WALL_TIME_CAUSE, None))


def _truncation_record(reason: str, data: dict[str, Any] | None) -> ResultError:
    """One truncation cause as its record: the wall's from its one mint, any other with its data."""
    if reason == WALL_TIME_CAUSE:
        return wall_truncation(REFINE_GUIDANCE)
    detail = f"at the {reason}; {REFINE_GUIDANCE}"
    return classified(ErrorKind.truncated, severity=Severity.warning, detail=detail, data=data)
