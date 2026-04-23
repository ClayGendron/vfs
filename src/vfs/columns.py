"""Per-function default column map for narrowed backend reads.

Two vocabularies are at play:

- **Candidate fields** — what :class:`vfs.results.Candidate` carries. Users
  express projection in this vocabulary (``--output path,score,updated_at``).
- **Model columns** — actual ``VFSEntry`` column names that end up in
  the ``SELECT``. Backends use this vocabulary to narrow queries.
"""

from __future__ import annotations

# Model columns that back each Candidate field. Empty frozenset = computed,
# not read off the row (``score``, ``lines``).
CANDIDATE_FIELD_TO_MODEL_COLUMNS: dict[str, frozenset[str]] = {
    "path": frozenset({"path"}),
    "kind": frozenset({"kind"}),
    "content": frozenset({"content"}),
    "size_bytes": frozenset({"size_bytes"}),
    "updated_at": frozenset({"updated_at"}),
    "in_degree": frozenset(),
    "out_degree": frozenset(),
    "score": frozenset(),
    "lines": frozenset(),
}

# Valid public ``columns=`` input — union of every Candidate-backed model column.
CANDIDATE_BACKED_MODEL_COLUMNS: frozenset[str] = frozenset().union(*CANDIDATE_FIELD_TO_MODEL_COLUMNS.values())

_METADATA_COLUMNS: frozenset[str] = frozenset(
    {"path", "kind", "size_bytes", "updated_at"},
)
_PATH_KIND_ONLY: frozenset[str] = frozenset({"path", "kind"})

# Minimum model columns each function reads from the row by default.
# Unknown functions fall back to ``{"path"}`` in required_model_columns.
DEFAULT_COLUMNS: dict[str, frozenset[str]] = {
    # Reads
    "read": _METADATA_COLUMNS | frozenset({"content"}),
    "stat": _METADATA_COLUMNS,
    "ls": _PATH_KIND_ONLY,
    "tree": _PATH_KIND_ONLY,
    # Pattern + text search
    "glob": _METADATA_COLUMNS,
    "grep": _PATH_KIND_ONLY | frozenset({"content"}),  # content sliced at render time
    # Ranked search
    "vector_search": _METADATA_COLUMNS,
    "semantic_search": _METADATA_COLUMNS,
    "lexical_search": _METADATA_COLUMNS,
    "bm25": _METADATA_COLUMNS,
    # Centrality / rank
    "pagerank": _METADATA_COLUMNS,
    "betweenness_centrality": _METADATA_COLUMNS,
    "closeness_centrality": _METADATA_COLUMNS,
    "degree_centrality": _METADATA_COLUMNS,
    "in_degree_centrality": _METADATA_COLUMNS,
    "out_degree_centrality": _METADATA_COLUMNS,
    "hits": _METADATA_COLUMNS,
    # Writes and mutations
    "write": _PATH_KIND_ONLY,
    "delete": _PATH_KIND_ONLY,
    "edit": _PATH_KIND_ONLY,
    "move": _PATH_KIND_ONLY,
    "copy": _PATH_KIND_ONLY,
    "mkdir": _PATH_KIND_ONLY,
    "mkedge": _PATH_KIND_ONLY,
    # Graph traversals
    "predecessors": _PATH_KIND_ONLY,
    "successors": _PATH_KIND_ONLY,
    "ancestors": _PATH_KIND_ONLY,
    "descendants": _PATH_KIND_ONLY,
    "neighborhood": _PATH_KIND_ONLY,
    "meeting_subgraph": _PATH_KIND_ONLY,
    "min_meeting_subgraph": _PATH_KIND_ONLY,
    # Merged
    "hybrid": _PATH_KIND_ONLY,
}


def default_columns(function: str) -> frozenset[str]:
    """Return the default model-column set for *function*.

    Unknown functions return ``{"path"}`` — path is the only column every
    Candidate must carry.
    """
    return DEFAULT_COLUMNS.get(function, frozenset({"path"}))


def candidate_field_columns(name: str) -> frozenset[str]:
    """Return the model columns that back Candidate field *name*.

    Raises ``KeyError`` on unknown names; callers should validate against
    :data:`vfs.results.CANDIDATE_FIELDS` first.
    """
    return CANDIDATE_FIELD_TO_MODEL_COLUMNS[name]


def required_model_columns(
    function: str,
    projection: tuple[str, ...] | list[str] | None = None,
) -> frozenset[str]:
    """Model columns a backend impl must SELECT for *function* + *projection*.

    ``projection=None`` returns just the function's default columns.
    ``default`` in projection is a no-op; ``all`` widens to every
    model-backed Candidate field; any other Candidate field name adds its
    backing model columns.  Unknown names raise ``ValueError``.
    """
    cols: set[str] = set(default_columns(function))
    if projection is None:
        return frozenset(cols)
    for name in projection:
        if name == "default":
            continue
        if name == "all":
            cols |= CANDIDATE_BACKED_MODEL_COLUMNS
            continue
        if name not in CANDIDATE_FIELD_TO_MODEL_COLUMNS:
            msg = f"unknown field {name!r}"
            raise ValueError(msg)
        cols |= CANDIDATE_FIELD_TO_MODEL_COLUMNS[name]
    return frozenset(cols)
