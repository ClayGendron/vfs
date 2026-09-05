"""The cross-mount merge: the corpus split into mounts, the router's merge
as a run, and the two floors it must beat.

The floors are the router's former behaviour — one sort over every
mount's native scores — and interleaving by rank; the real merge is the
verb through a :class:`VirtualFileSystem` holding one mount per half.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.ranking.corpora import Corpus

if TYPE_CHECKING:
    from collections.abc import Sequence

    from tests.ranking.driver import Run
    from vfs.base import VirtualFileSystem


def halves(corpus: Corpus) -> list[Corpus]:
    """The corpus split by top-level directory — one mount per half."""
    return [
        Corpus(f"{corpus.name}/{prefix}", docs, {d: corpus.paths[d] for d in docs}, corpus.queries, corpus.qrels)
        for prefix in ("docs", "context")
        if (docs := {d: t for d, t in corpus.docs.items() if d.startswith(prefix + "/")})
    ]


async def merged_glean_run(vfs: VirtualFileSystem, corpus: Corpus, mounts: Sequence[str], k: int = 50) -> Run:
    """Every query through the router over *mounts*, rows mapped back to doc ids."""
    doc_of = corpus.doc_of
    run: Run = {}
    for qid, query in corpus.queries.items():
        run[qid] = {doc_of[path]: score for path, score in await merged_ranking(vfs, query, mounts, k)}
    return run


async def merged_ranking(vfs: VirtualFileSystem, query: str, mounts: Sequence[str], k: int) -> list[tuple[str, float]]:
    """Top-``k`` entries as ``(mount-local path, score)`` through the router's merge."""
    result = await vfs.glean(query, limit=k)
    assert result.success is True, result.errors
    ranked: list[tuple[str, float]] = []
    for row in result.observations:
        assert row.score is not None
        ranked.append((_unmounted(str(row.path), mounts), row.score))
    return ranked


def _unmounted(path: str, mounts: Sequence[str]) -> str:
    owners = [m for m in mounts if path.startswith(m + "/")]
    assert len(owners) == 1, (path, mounts)
    return path[len(owners[0]) :]


def naive_score_sort(runs: Sequence[Run], k: int) -> Run:
    """One sort over the union of every mount's scored rows; a duplicate keeps its best."""
    merged: Run = {}
    for run in runs:
        for qid, scored in run.items():
            pool = merged.setdefault(qid, {})
            for doc, score in scored.items():
                pool[doc] = max(pool.get(doc, float("-inf")), score)
    return {qid: dict(sorted(pool.items(), key=lambda item: (-item[1], item[0]))[:k]) for qid, pool in merged.items()}


def round_robin(runs: Sequence[Run], k: int) -> Run:
    """Interleave the mounts' ranked lists; the merged score is the reciprocal position."""
    merged: Run = {}
    qids = {qid for run in runs for qid in run}
    for qid in qids:
        lists = [sorted(run.get(qid, {}).items(), key=lambda item: (-item[1], item[0])) for run in runs]
        ordered: list[str] = []
        for position in range(max((len(ranked) for ranked in lists), default=0)):
            for ranked in lists:
                if position < len(ranked) and ranked[position][0] not in ordered:
                    ordered.append(ranked[position][0])
        merged[qid] = {doc: 1.0 / (position + 1) for position, doc in enumerate(ordered[:k])}
    return merged
