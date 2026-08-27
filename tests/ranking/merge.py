"""The cross-mount merge floors: naive score sort and round-robin.

Two named baselines the regression gate keeps under the real merge
(download-and-rerank, a later spec): the router's present behaviour —
one sort over every mount's native scores — and interleaving by rank.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from tests.ranking.driver import Run


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
