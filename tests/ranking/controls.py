"""The standing control arm: an uninformative prior no real prior may do worse than.

A static prior enters the fused score as a bounded multiplicative factor
``score * (1 + beta * p)``; injecting a *random* ``p`` per document is the
control whose cost every real prior must beat. The factor is a hash of
``(qid, doc)`` so the arm is deterministic without random state.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from tests.ranking.driver import Run

BETA: Final = 0.5


def uninformative_prior(run: Run, beta: float = BETA) -> Run:
    """Every score scaled by ``1 + beta·u`` with ``u`` a per-document hash in ``[0, 1)``."""
    return {
        qid: {doc: score * (1.0 + beta * _unit(qid, doc)) for doc, score in scored.items()}
        for qid, scored in run.items()
    }


def _unit(qid: str, doc: str) -> float:
    digest = hashlib.blake2b(f"{qid}\0{doc}".encode(), digest_size=8).digest()
    return int.from_bytes(digest, "little") / 2**64
