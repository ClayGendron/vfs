"""Ranking seams — how a mount fuses its legs into one list, declared on the Storage.

A ``glean`` answer is one ranked list of entries. Inside a mount it is
built from *legs* — the vector leg's cosine-ranked entries, the lexical
leg's BM25-ranked entries — each already **aggregated to entries** (the
best chunk speaks for its entry) and **normalised to the unit interval**
by the law that fits the leg: cosine by its theoretical range
(:func:`unit_cosine`, ``(cos + 1) / 2``), BM25 by min-max over the leg's
candidate union (:func:`min_max`). A :class:`Fusion` combines those
normalised legs; the mount's :class:`Ranker` names which one, declared
at construction and never chosen per call.

    DatabaseStorage(url=..., embedder=..., ranker=Ranker(fusion=Convex({"vector": 0.4, "lexical": 0.6})))

:class:`Convex` is the reference — ``a * norm(vec) + (1 - a) * norm(lex)``,
the weights renormalised over the legs actually present so a one-leg
mount ranks exactly as that leg. :class:`RRF` is the rank-only floor for
a leg whose score is not comparable, with a small per-leg ``k``. Fusion
is arithmetic over two short lists and runs in Python inside the
backend; the same seam merges nothing across mounts — the router's
cross-mount merge is a different decision.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, Protocol, TypeVar, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Mapping

K = TypeVar("K")

LEG_NAMES: Final = ("vector", "lexical")
"""The legs a mount may run, in the order the fused score's terms are summed."""

DEFAULT_RRF_K: Final = 10
"""The rank-only floor's per-leg constant — small, for two shallow legs; 60 is the library cargo."""

TOP_CHUNKS: Final = 3
"""Chunk ``Match`` rows an entry carries by default, best first."""


# ---------------------------------------------------------------------------
# Per-leg normalisation — the one definition each leg's scores enter fusion under
# ---------------------------------------------------------------------------


def unit_cosine(similarity: float) -> float:
    """Cosine similarity on ``[-1, 1]`` mapped to ``[0, 1]`` by its theoretical range."""
    return (similarity + 1.0) / 2.0


def min_max(scores: Mapping[K, float]) -> dict[K, float]:
    """Every score scaled by the mapping's own range; one value alone, or a flat set, scales to 1."""
    if not scores:
        return {}
    low, high = min(scores.values()), max(scores.values())
    span = high - low
    if span == 0.0:
        return dict.fromkeys(scores, 1.0)
    return {key: (score - low) / span for key, score in scores.items()}


# ---------------------------------------------------------------------------
# The seam and its built-ins
# ---------------------------------------------------------------------------


@runtime_checkable
class Fusion(Protocol):
    """Combine normalised per-leg entry scores into one score per entry."""

    def fuse(self, legs: Mapping[str, Mapping[K, float]]) -> dict[K, float]:
        """Fuse *legs* — ``leg name → entry → score in [0, 1]`` — over the union of their entries.

        A leg absent from *legs* did not run; an entry absent from a
        present leg scored nothing there.
        """
        ...


class Convex:
    """The reference fusion: a weighted sum of the legs' normalised scores.

    The weights are renormalised over the legs present, so fusing one
    leg returns that leg unchanged. Every named leg needs a positive
    weight; the default is the even split the harness tunes from.
    """

    __slots__ = ("_weights",)

    def __init__(self, weights: Mapping[str, float] | None = None) -> None:
        given = dict(weights) if weights is not None else dict.fromkeys(LEG_NAMES, 0.5)
        unknown = set(given) - set(LEG_NAMES)
        if unknown:
            msg = f"Convex weights name unknown legs {sorted(unknown)}; the legs are {list(LEG_NAMES)}"
            raise ValueError(msg)
        if any(weight <= 0.0 for weight in given.values()) or not given:
            msg = f"Convex weights must be positive, got {given}"
            raise ValueError(msg)
        self._weights: tuple[tuple[str, float], ...] = tuple((leg, given[leg]) for leg in LEG_NAMES if leg in given)

    @property
    def weights(self) -> dict[str, float]:
        return dict(self._weights)

    def fuse(self, legs: Mapping[str, Mapping[K, float]]) -> dict[K, float]:
        present = [(leg, weight) for leg, weight in self._weights if leg in legs]
        total = sum(weight for _, weight in present)
        fused: dict[K, float] = {}
        for leg, weight in present:
            share = weight / total
            for key, score in legs[leg].items():
                fused[key] = fused.get(key, 0.0) + share * score
        return fused

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Convex) and other._weights == self._weights

    def __hash__(self) -> int:
        return hash(("Convex", self._weights))

    def __repr__(self) -> str:
        return f"Convex({self.weights!r})"


class RRF:
    """Reciprocal rank fusion — the rank-only floor: ``Σ_leg w_leg / (k + rank)``.

    Ranks are 1-based within each leg, ties broken by key so the answer
    is deterministic. *k* is per leg and small by default; weights
    default to one per leg.
    """

    __slots__ = ("_weights", "k")

    def __init__(self, k: int = DEFAULT_RRF_K, weights: Mapping[str, float] | None = None) -> None:
        if k < 1:
            msg = f"RRF k must be at least 1, got {k}"
            raise ValueError(msg)
        given = dict(weights) if weights is not None else dict.fromkeys(LEG_NAMES, 1.0)
        unknown = set(given) - set(LEG_NAMES)
        if unknown:
            msg = f"RRF weights name unknown legs {sorted(unknown)}; the legs are {list(LEG_NAMES)}"
            raise ValueError(msg)
        if any(weight <= 0.0 for weight in given.values()) or not given:
            msg = f"RRF weights must be positive, got {given}"
            raise ValueError(msg)
        self.k = k
        self._weights: tuple[tuple[str, float], ...] = tuple((leg, given[leg]) for leg in LEG_NAMES if leg in given)

    @property
    def weights(self) -> dict[str, float]:
        return dict(self._weights)

    def fuse(self, legs: Mapping[str, Mapping[K, float]]) -> dict[K, float]:
        fused: dict[K, float] = {}
        for leg, weight in self._weights:
            if leg not in legs:
                continue
            ranked = sorted(legs[leg].items(), key=lambda item: (-item[1], _key_order(item[0])))
            for rank, (key, _score) in enumerate(ranked, start=1):
                fused[key] = fused.get(key, 0.0) + weight / (self.k + rank)
        return fused

    def __eq__(self, other: object) -> bool:
        return isinstance(other, RRF) and (other.k, other._weights) == (self.k, self._weights)

    def __hash__(self) -> int:
        return hash(("RRF", self.k, self._weights))

    def __repr__(self) -> str:
        return f"RRF(k={self.k}, weights={self.weights!r})"


class MaxP:
    """Aggregate chunks to entries by the best chunk, carrying *chunks_per_entry* ``Match`` rows."""

    __slots__ = ("chunks_per_entry",)

    def __init__(self, chunks_per_entry: int = TOP_CHUNKS) -> None:
        if chunks_per_entry < 1:
            msg = f"chunks_per_entry must be at least 1, got {chunks_per_entry}"
            raise ValueError(msg)
        self.chunks_per_entry = chunks_per_entry

    def __eq__(self, other: object) -> bool:
        return isinstance(other, MaxP) and other.chunks_per_entry == self.chunks_per_entry

    def __hash__(self) -> int:
        return hash(("MaxP", self.chunks_per_entry))

    def __repr__(self) -> str:
        return f"MaxP(chunks_per_entry={self.chunks_per_entry})"


class Ranker:
    """A mount's ranking declaration: its fusion and its chunk-to-entry aggregate."""

    __slots__ = ("aggregate", "fusion")

    def __init__(self, *, fusion: Fusion | None = None, aggregate: MaxP | None = None) -> None:
        self.fusion: Fusion = Convex() if fusion is None else fusion
        self.aggregate: MaxP = MaxP() if aggregate is None else aggregate

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Ranker) and (other.fusion, other.aggregate) == (self.fusion, self.aggregate)

    def __hash__(self) -> int:
        return hash(("Ranker", self.fusion, self.aggregate))

    def __repr__(self) -> str:
        return f"Ranker(fusion={self.fusion!r}, aggregate={self.aggregate!r})"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _key_order(key: object) -> tuple[str, str]:
    """A total order over any key type for tie-breaks: by type name, then by its text."""
    return (type(key).__name__, str(key))
