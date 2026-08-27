"""ranx behind two functions: ``evaluate`` for the numbers, ``compare`` for significance.

ranx is a dev-only dependency; ``src/`` never imports it. Its first
``evaluate`` per process pays numba's JIT (a few seconds), once.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from ranx import Qrels, Run
from ranx import compare as ranx_compare
from ranx import evaluate as ranx_evaluate

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ranx.data_structures import Report

METRICS: Final = ("ndcg@10", "mrr@10", "recall@10", "recall@50")


def evaluate(
    qrels: dict[str, dict[str, int]], run: dict[str, dict[str, float]], metrics: Sequence[str] = METRICS
) -> dict[str, float]:
    """Mean metric values over the queries of *qrels* — zero-graded judgments dropped."""
    scores = ranx_evaluate(Qrels(relevant_only(qrels)), Run(run), list(metrics))
    assert isinstance(scores, dict)  # a list of metrics answers a dict; one metric alone a float
    return {metric: float(scores[metric]) for metric in metrics}


def compare(
    qrels: dict[str, dict[str, int]], runs: dict[str, dict[str, dict[str, float]]], metrics: Sequence[str] = METRICS
) -> Report:
    """Paired significance across named runs (Student's t, Bonferroni-corrected)."""
    named = [Run(run, name=name) for name, run in runs.items()]
    return ranx_compare(Qrels(relevant_only(qrels)), named, list(metrics), stat_test="student", max_p=0.05)


def relevant_only(qrels: dict[str, dict[str, int]]) -> dict[str, dict[str, int]]:
    """The positive judgments per query; a query with none is dropped."""
    kept = {qid: {doc: grade for doc, grade in graded.items() if grade > 0} for qid, graded in qrels.items()}
    return {qid: graded for qid, graded in kept.items() if graded}
