"""The cross-mount merge: one BM25 over the union, under each mount's own order.

One mount's ``glean`` answer is ranked on one scale. Two mounts' answers
are not: each scored against its own corpus with its own legs, so their
``score`` columns cannot be sorted together. When more than one mount
answers, the router fetches deeper than the caller's limit from each,
unions the rows, re-scores every chunk with one BM25 built on the
corpus-wide statistics the mounts export, and orders the union by that
score — under one law: **a mount's own order is never changed.** The
rerank decides how many rows each mount contributes and how the mounts
interleave; within a mount the rows keep the order the mount gave them.
Isotonic repair along each mount's list makes that well defined, and it
follows that every mount contributes a prefix of its own answer.

    merged = merge_ranked("lease heartbeat", answers, limit=10, rerankers=(BM25Rerank(),))
    merged.observations  # the union's top ten, one scale, each mount's order intact
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final, NamedTuple, Protocol, runtime_checkable

from vfs.models.lexical import idf, term_weight, tokenize
from vfs.results import ResultError, Severity, VFSErrorKind
from vfs.storage.ranking import REFINE_GUIDANCE, SCORE_DECIMALS, min_max

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from vfs.models import Match, Observation
    from vfs.paths import Path
    from vfs.results import Result

# ---------------------------------------------------------------------------
# Module constants and shared types
# ---------------------------------------------------------------------------

FANOUT_DEPTH: Final = 3
"""Each answering mount is asked for this many times the caller's limit."""

FANOUT_CAP: Final = 256
"""The most rows one mount is ever asked for in a fan-out; past it the union may lose recall."""


def fanout_depth(limit: int) -> int:
    """How many rows each mount is asked for when more than one may answer."""
    return min(limit * FANOUT_DEPTH, FANOUT_CAP)


class Statistics(NamedTuple):
    """BM25 statistics summed over the answering mounts' exports.

    ``exported`` counts the mounts that supplied statistics; when none
    did, the union's own chunk texts stand in (``n_docs`` chunks,
    ``avg_dl`` their mean length, ``df`` counted over them).
    """

    n_docs: int
    avg_dl: float
    df: dict[str, int]
    exported: int

    def idf(self, term: str) -> float:
        return idf(self.df.get(term, 0), self.n_docs)


class Candidate(NamedTuple):
    """One entry row of the union with its provenance and rerank scores.

    ``source`` is the answering mount's position in dispatch order and
    ``rank`` the row's position in that mount's own answer; together they
    are the row's identity through the stages and the order law's key.
    ``score`` and ``chunk_scores`` (one per ``Match`` row) start as the
    mount's own values and are rewritten by each stage; ``stats`` is the
    union's shared :class:`Statistics`.
    """

    source: int
    mount: Path
    rank: int
    row: Observation
    score: float
    chunk_scores: tuple[float, ...]
    stats: Statistics


@runtime_checkable
class Reranker(Protocol):
    """One stage over the union: rescore and reorder, never retrieve.

    A stage returns exactly the candidates it received — every row, no
    additions — with ``score`` and ``chunk_scores`` rewritten on one
    scale of its choosing. ``limit`` is the caller's bound, advice for a
    stage that scores expensively; the router trims after the order law.
    """

    async def rerank(self, query: str, candidates: Sequence[Candidate], *, limit: int) -> Sequence[Candidate]: ...


class RankedMerge(NamedTuple):
    """The merge's answer: ordered rows, the records it minted, and its explanation."""

    observations: list[Observation]
    records: list[ResultError]
    legs: dict[str, Any]


# ---------------------------------------------------------------------------
# The built-in stage
# ---------------------------------------------------------------------------


class BM25Rerank:
    """The union rerank: the lexical index's BM25 over each row's chunk texts.

    Every ``Match`` region is tokenized with the index's own tokenizer and
    scored with the index's formula against the union's corpus-wide
    statistics; the entry takes its best chunk. A region without text
    (an overlay row answers with its preview alone) is scored on the
    preview; a row with no regions scores zero.
    """

    async def rerank(self, query: str, candidates: Sequence[Candidate], *, limit: int) -> Sequence[Candidate]:
        terms = list(dict.fromkeys(tokenize(query)))
        rescored: list[Candidate] = []
        for candidate in candidates:
            stats = candidate.stats
            weights = {term: stats.idf(term) for term in terms}
            chunk_scores = tuple(_bm25(text, weights, stats.avg_dl) for text in region_texts(candidate.row))
            rescored.append(candidate._replace(score=max(chunk_scores, default=0.0), chunk_scores=chunk_scores))
        return rescored

    def __eq__(self, other: object) -> bool:
        return isinstance(other, BM25Rerank)

    def __hash__(self) -> int:
        return hash("BM25Rerank")

    def __repr__(self) -> str:
        return "BM25Rerank()"


def region_texts(row: Observation) -> list[str]:
    """The text each ``Match`` region is scored on: its content, else its preview."""
    return [match.content if match.content is not None else (match.preview or "") for match in row.matches or ()]


# ---------------------------------------------------------------------------
# The order law
# ---------------------------------------------------------------------------


def isotonic_nonincreasing(values: Sequence[float]) -> list[float]:
    """The closest non-increasing sequence to *values* (least squares): pool adjacent violators.

    Where a later value exceeds the one before it, the run pools to its
    mean, so a strong row lifts the rows above it in its own list and a
    weak row is carried by them — never reordered.
    """
    pools: list[list[float]] = []
    for value in values:
        pools.append([value, 1.0])
        while len(pools) > 1 and pools[-2][0] / pools[-2][1] < pools[-1][0] / pools[-1][1]:
            total, count = pools.pop()
            pools[-1][0] += total
            pools[-1][1] += count
    return [total / count for total, count in pools for _ in range(int(count))]


def order_law(candidates: Iterable[Candidate]) -> list[Candidate]:
    """Order the union by rerank score without changing any mount's own order.

    Each mount's scores are repaired to be non-increasing along the
    mount's list, then the union sorts by repaired score with ties to
    dispatch order and then mount rank. Every mount's surviving rows are
    therefore a prefix of its answer: a row never outranks one its own
    mount placed above it.
    """
    by_source: dict[int, list[Candidate]] = {}
    for candidate in candidates:
        by_source.setdefault(candidate.source, []).append(candidate)
    repaired: list[Candidate] = []
    for rows in by_source.values():
        rows.sort(key=lambda candidate: candidate.rank)
        for candidate, score in zip(rows, isotonic_nonincreasing([c.score for c in rows]), strict=True):
            repaired.append(candidate._replace(score=score))
    return sorted(repaired, key=lambda candidate: (-candidate.score, candidate.source, candidate.rank))


# ---------------------------------------------------------------------------
# The merge
# ---------------------------------------------------------------------------


async def merge_ranked(
    query: str,
    answers: Sequence[tuple[Path, Result]],
    *,
    limit: int,
    depth: int,
    rerankers: Sequence[Reranker],
) -> RankedMerge:
    """Merge the mounts' ``glean`` answers into one ranked list of at most *limit* rows.

    *answers* pairs each answering mount's path with its rebased result,
    in dispatch order. One answering mount is returned as it stands,
    trimmed — its order and scores are already one scale, and its
    explanation rides through. More than one: the union is deduplicated
    on ``content_hash`` (the first mount keeps the row), every stage runs
    in order, the order law applies, and the scores are min-max scaled
    to the unit interval with each entry's best chunk carrying its
    score. A mount that filled its *depth* at the fan-out cap earns a
    warning: the union may have lost recall.
    """
    answering = [(mount, result) for mount, result in answers if result.observations]
    if len(answering) <= 1:
        return _sole_answer(answering, limit)
    candidates, duplicates, stats = _union(answering)
    for stage in rerankers:
        candidates = _checked(stage, candidates, await stage.rerank(query, candidates, limit=limit))
    ordered = order_law(candidates)
    rows = _scaled_rows(ordered)[:limit]
    records = [
        ResultError(
            kind=VFSErrorKind.truncated,
            severity=Severity.warning,
            message=f"glean fan-out reached the {FANOUT_CAP}-row cap on {mount}; the merge may have lost recall; "
            f"{REFINE_GUIDANCE}",
            data={"mount": str(mount), "cap": FANOUT_CAP},
        )
        for mount, result in answering
        if depth >= FANOUT_CAP and len(result.observations) >= FANOUT_CAP
    ]
    legs = {
        "merge": {
            "mounts": [str(mount) for mount, _ in answering],
            "depth": depth,
            "rerankers": [repr(stage) for stage in rerankers],
            "statistics": "corpus-wide" if stats.exported else "union",
            "candidates": len(candidates),
            "duplicates": duplicates,
        },
        "mounts": {str(mount): _extra(result, "legs") for mount, result in answering},
    }
    return RankedMerge(rows, records, legs)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _sole_answer(answering: Sequence[tuple[Path, Result]], limit: int) -> RankedMerge:
    """Zero or one answering mount: its rows and explanation stand, trimmed to *limit*."""
    if not answering:
        return RankedMerge([], [], {})
    _mount, result = answering[0]
    legs = _extra(result, "legs")
    return RankedMerge(list(result.observations[:limit]), [], legs if isinstance(legs, dict) else {})


def _extra(result: Result, name: str) -> Any:
    return (result.model_extra or {}).get(name)


def _union(answering: Sequence[tuple[Path, Result]]) -> tuple[list[Candidate], int, Statistics]:
    """The deduplicated union as candidates carrying the mounts' scores, plus the summed statistics."""
    stats = _statistics(answering)
    seen_hashes: set[str] = set()
    candidates: list[Candidate] = []
    duplicates = 0
    for source, (mount, result) in enumerate(answering):
        for rank, row in enumerate(result.observations):
            if row.content_hash is not None:
                if row.content_hash in seen_hashes:
                    duplicates += 1
                    continue
                seen_hashes.add(row.content_hash)
            chunk_scores = tuple(match.score or 0.0 for match in row.matches or ())
            candidates.append(Candidate(source, mount, rank, row, row.score or 0.0, chunk_scores, stats))
    if not stats.exported:
        stats = _union_statistics(candidates)
        candidates = [candidate._replace(stats=stats) for candidate in candidates]
    return candidates, duplicates, stats


def _statistics(answering: Sequence[tuple[Path, Result]]) -> Statistics:
    """Sum the mounts' exported statistics: document counts, length-weighted ``avg_dl``, per-term ``df``."""
    n_docs = 0
    total_length = 0.0
    df: dict[str, int] = {}
    exported = 0
    for _mount, result in answering:
        export = _extra(result, "lexical_stats")
        if not isinstance(export, dict) or not export.get("n_docs"):
            continue
        exported += 1
        n_docs += export["n_docs"]
        total_length += export["n_docs"] * export["avg_dl"]
        for term, counts in export.get("terms", {}).items():
            df[term] = df.get(term, 0) + counts["df"]
    return Statistics(n_docs, total_length / n_docs if n_docs else 0.0, df, exported)


def _union_statistics(candidates: Sequence[Candidate]) -> Statistics:
    """Statistics over the union's own chunk texts, for mounts that exported none."""
    lengths: list[int] = []
    df: dict[str, int] = {}
    for candidate in candidates:
        for text in region_texts(candidate.row):
            tokens = tokenize(text)
            lengths.append(len(tokens))
            for term in set(tokens):
                df[term] = df.get(term, 0) + 1
    n_docs = len(lengths)
    return Statistics(n_docs, sum(lengths) / n_docs if n_docs else 0.0, df, 0)


def _bm25(text: str, weights: dict[str, float], avg_dl: float) -> float:
    """The index's BM25 over one region: query-term frequencies against the corpus-wide idf."""
    tokens = tokenize(text)
    if not tokens or not avg_dl:
        return 0.0
    counts: dict[str, int] = {}
    for token in tokens:
        if token in weights:
            counts[token] = counts.get(token, 0) + 1
    return sum(term_weight(tf, len(tokens), avg_dl, weights[term]) for term, tf in counts.items())


def _checked(stage: Reranker, given: Sequence[Candidate], returned: Sequence[Candidate]) -> list[Candidate]:
    """Refuse a stage that returned a different row set than it received."""
    identity = [(candidate.source, candidate.rank) for candidate in returned]
    if sorted(identity) != sorted((candidate.source, candidate.rank) for candidate in given):
        msg = f"{stage!r} returned {len(returned)} candidates for {len(given)} given; a stage reorders, never retrieves"
        raise ValueError(msg)
    return list(returned)


def _scaled_rows(ordered: Sequence[Candidate]) -> list[Observation]:
    """Rows in merge order on the unit scale, each entry's best chunk carrying its score."""
    scaled = min_max({index: candidate.score for index, candidate in enumerate(ordered)})
    rows: list[Observation] = []
    for index, candidate in enumerate(ordered):
        score = round(scaled[index], SCORE_DECIMALS)
        best = max(candidate.chunk_scores, default=0.0)
        ratio = score / best if best else 0.0
        matches: list[Match] = [
            match.model_copy(update={"score": round(chunk * ratio, SCORE_DECIMALS)})
            for match, chunk in zip(candidate.row.matches or (), candidate.chunk_scores, strict=True)
        ]
        rows.append(candidate.row.model_copy(update={"score": score, "matches": matches or None}))
    return rows
