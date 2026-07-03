"""Projection — which Observation fields an operation fetches and renders.

A projection is an ordered tuple of :class:`vfs.models2.Observation` field
names. It does double duty: the renderer uses it to pick the columns shown in
text output, and the backends use it to narrow the SQL SELECT to just the
columns the caller will see. Two sentinels expand at resolve time —
``default`` (the function's default projection) and ``all`` (every field
populated on at least one row):

    resolve_projection(("default", "score"), "grep", rows)
    # → ("path", "matches", "score")

The function vocabulary lives here too: ``KNOWN_FUNCTIONS`` is the registry
of every operation name the renderer and projection table understand. An
unknown function is not an error — it resolves to ``FALLBACK_PROJECTION`` so
a newer server's result still renders on an older client.
"""

from __future__ import annotations

from vfs.models2 import Observation
from vfs.ops import MUTATING_OPS

# ---------------------------------------------------------------------------
# Field and function vocabularies
# ---------------------------------------------------------------------------

OBSERVATION_FIELDS: frozenset[str] = frozenset(Observation.model_fields)
PROJECTION_SENTINELS: frozenset[str] = frozenset({"default", "all"})

# Arrangement groups. The envelope's ``function`` key picks an arrangement;
# multiple functions share one (e.g. all centrality methods).
RANKED_SEARCH_FUNCTIONS: frozenset[str] = frozenset(
    {"glean", "vector_search", "semantic_search", "lexical_search", "bm25"},
)
CENTRALITY_FUNCTIONS: frozenset[str] = frozenset(
    {
        "pagerank",
        "betweenness_centrality",
        "closeness_centrality",
        "degree_centrality",
        "in_degree_centrality",
        "out_degree_centrality",
        "hits",
    },
)
# The mutation verbs — shared with the dispatch gate so the rendering and
# permission vocabularies cannot drift apart.
ACTION_FUNCTIONS: frozenset[str] = MUTATING_OPS
TRAVERSAL_FUNCTIONS: frozenset[str] = frozenset(
    {"predecessors", "successors", "ancestors", "descendants", "neighborhood"}
    | {"meeting_subgraph", "min_meeting_subgraph"},
)

FALLBACK_PROJECTION: tuple[str, ...] = ("path",)
"""Default projection for a function this client does not recognize."""

# Per-function default projection. Users override with ``--output`` on the
# CLI or the ``projection=`` kwarg on ``to_str``. Grep's default is
# ``matches`` rather than ``content``: each Match carries its own region
# text, so the full file content never needs to be fetched for the render.
_DEFAULT_PROJECTION: dict[str, tuple[str, ...]] = {
    "grep": ("path", "matches"),
    "glob": ("path",),
    "ls": ("path",),
    "tree": ("path",),
    "read": ("content",),
    "stat": ("path", "kind", "size_bytes", "updated_at"),
    "run": ("path",),
    "hybrid": ("path",),
}
for _fn in RANKED_SEARCH_FUNCTIONS:
    _DEFAULT_PROJECTION[_fn] = ("path", "score")
for _fn in CENTRALITY_FUNCTIONS:
    _DEFAULT_PROJECTION[_fn] = ("path", "score", "in_degree", "out_degree")
for _fn in ACTION_FUNCTIONS:
    _DEFAULT_PROJECTION[_fn] = ("path",)
for _fn in TRAVERSAL_FUNCTIONS:
    _DEFAULT_PROJECTION[_fn] = ("path", "kind")

KNOWN_FUNCTIONS: frozenset[str] = frozenset(_DEFAULT_PROJECTION)
"""Every function name with a registered default projection."""


# ---------------------------------------------------------------------------
# Validation and resolution
# ---------------------------------------------------------------------------


def is_known_function(function: str) -> bool:
    """Return whether *function* is in the registered vocabulary."""
    return function in KNOWN_FUNCTIONS


def default_projection(function: str) -> tuple[str, ...]:
    """Return the default projection for *function*.

    Unknown functions fall back to :data:`FALLBACK_PROJECTION` — the wire is
    forward-compatible, so a function name this client does not know renders
    as a path list rather than failing.
    """
    return _DEFAULT_PROJECTION.get(function, FALLBACK_PROJECTION)


def validate_projection(projection: tuple[str, ...] | list[str] | None) -> tuple[str, ...] | None:
    """Return *projection* as a tuple after validating every name.

    ``None`` passes through. Only a tuple or list is accepted — a bare string
    (``projection=("path")`` is a tuple-literal typo needing a trailing comma)
    would otherwise iterate character-by-character into an ``unknown field
    'p'`` error, and dict/set/generator inputs hide caller bugs. An empty
    projection is rejected: pass ``None`` for the function default. Every
    name must be a known ``Observation`` field or a sentinel
    (``default`` / ``all``); unknowns raise ``ValueError``.
    """
    if projection is None:
        return None
    if isinstance(projection, str):
        msg = (
            f"projection must be a tuple or list of field names, not a bare string "
            f"{projection!r}. Did you mean ({projection!r},)?"
        )
        raise TypeError(msg)
    if not isinstance(projection, (tuple, list)):
        msg = f"projection must be a tuple or list of field names, got {type(projection).__name__}"
        raise TypeError(msg)
    if not projection:
        msg = "projection must not be empty; pass None for the function default"
        raise ValueError(msg)
    result: list[str] = []
    for name in projection:
        if not isinstance(name, str):
            msg = f"projection items must be field-name strings, got {name!r}"
            raise TypeError(msg)
        if name not in OBSERVATION_FIELDS and name not in PROJECTION_SENTINELS:
            msg = f"unknown field {name!r}"
            raise ValueError(msg)
        result.append(name)
    return tuple(result)


def resolve_projection(
    projection: tuple[str, ...] | None,
    function: str,
    observations: list[Observation],
) -> tuple[str, ...]:
    """Expand ``default`` / ``all`` sentinels into concrete Observation field names.

    - ``default`` → ``default_projection(function)``
    - ``all`` → every field that is non-null on at least one observation
    Order is preserved; duplicates are dropped (first-win).
    """
    if projection is None:
        return default_projection(function)
    seen: set[str] = set()
    out: list[str] = []

    def _add(name: str) -> None:
        if name not in seen:
            seen.add(name)
            out.append(name)

    for name in projection:
        if name == "default":
            for field in default_projection(function):
                _add(field)
        elif name == "all":
            populated = {f for o in observations for f in OBSERVATION_FIELDS if getattr(o, f) is not None}
            for field in Observation.model_fields:
                if field in populated:
                    _add(field)
        else:
            _add(name)
    return tuple(out)
