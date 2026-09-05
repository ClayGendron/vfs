"""The centrality prior — the ranking-signal kernel behind ``reindex``, from the engine.

The owner of one seam: a reference graph over dense node indices, the
containing tree, and a link measure go in; one prior per node in
``[0, 1]`` comes back, files only. The engine counts (or power-iterates)
the measure, ``log1p``-transforms it, smooths it through the tree —
directory means bottom-up, then ``p = (1 - gamma) * own + gamma * p(parent)``
top-down — and min-max scales the files. Directories read ``0.0`` and
are never candidates. The readable reference lives in
``tests/support/oracles/signals.py``.
"""

from __future__ import annotations

from array import array
from typing import TYPE_CHECKING, Final

from vfs.native import extension

if TYPE_CHECKING:
    from collections.abc import Sequence

    from vfs.storage.ranking import InDegree, Katz, PageRank

NO_PARENT: Final = -1
"""The parent slot of a node with no containing directory."""


def centrality_prior(
    node_count: int,
    sources: Sequence[int],
    targets: Sequence[int],
    parents: Sequence[int],
    files: Sequence[bool],
    measure: InDegree | PageRank | Katz,
    gamma: float,
) -> list[float]:
    """One prior per node: ``[0, 1]`` for files, ``0.0`` for directories.

    *sources* and *targets* are the reference edges as node indices
    (never the hierarchy); *parents* holds each node's directory index or
    :data:`NO_PARENT`; *files* marks the retrievable nodes; *gamma* is
    the hierarchy share. A malformed graph, a looping parent chain, or a
    parameter out of range is refused with ``ValueError``.
    """
    name, damping, alpha, iterations = measure.kernel_args()
    packed = extension().centrality_prior(
        node_count,
        array("q", sources).tobytes(),
        array("q", targets).tobytes(),
        array("q", parents).tobytes(),
        bytes(files),
        name,
        damping,
        alpha,
        iterations,
        gamma,
    )
    values = array("d")
    values.frombytes(packed)
    return values.tolist()
