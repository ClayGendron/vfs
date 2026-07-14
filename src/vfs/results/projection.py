"""Projection — which Observation fields an operation fetches and renders.

A projection is an ordered tuple of :class:`vfs.models.Observation` field
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

from vfs.models import Observation
from vfs.ops import MUTATING_OPS

# ---------------------------------------------------------------------------
# Field and function vocabularies
# ---------------------------------------------------------------------------

# The populated-field mask is metadata about the row, not a column: it is
# never projectable and never renders.
OBSERVATION_FIELDS: frozenset[str] = frozenset(Observation.model_fields) - {"populated"}
PROJECTION_SENTINELS: frozenset[str] = frozenset({"default", "all"})

# Arrangement groups. The envelope's ``op`` picks an arrangement; the
# mutation verbs share one — drawn from the dispatch gate so the rendering
# and permission vocabularies cannot drift apart.
ACTION_FUNCTIONS: frozenset[str] = MUTATING_OPS

FALLBACK_PROJECTION: tuple[str, ...] = ("path",)
"""Default projection for an op this client does not recognize."""

# Per-op default projection. Users override with ``--output`` on the
# CLI or the ``projection=`` kwarg on ``to_str``. Grep's default is
# ``matches`` rather than ``content``: each Match carries its own region
# text, so the full file content never needs to be fetched for the render.
_DEFAULT_PROJECTION: dict[str, tuple[str, ...]] = {
    "grep": ("path", "matches"),
    "glob": ("path",),
    "glean": ("path", "score"),
    "ls": ("path",),
    "tree": ("path",),
    "read": ("content",),
    "stat": ("path", "kind", "size_bytes", "updated_at"),
    "run": ("path",),
    "graph": ("path", "kind"),
}
for _fn in ACTION_FUNCTIONS:
    _DEFAULT_PROJECTION[_fn] = ("path",)

KNOWN_FUNCTIONS: frozenset[str] = frozenset(_DEFAULT_PROJECTION)
"""Every function name with a registered default projection."""


# ---------------------------------------------------------------------------
# Validation and resolution
# ---------------------------------------------------------------------------


def is_known_function(function: str) -> bool:
    """Return whether *function* is in the registered vocabulary."""
    return function in KNOWN_FUNCTIONS


def default_projection(function: str | None) -> tuple[str, ...]:
    """Return the default projection for *function*.

    Unknown op names — and ``None``, a cross-op merge — fall back to
    :data:`FALLBACK_PROJECTION`: the wire is forward-compatible, so an op
    this client does not know renders as a path list rather than failing.
    """
    if function is None:
        return FALLBACK_PROJECTION
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
    function: str | None,
    observations: list[Observation],
) -> tuple[str, ...]:
    """Expand ``default`` / ``all`` sentinels into concrete Observation field names.

    - ``default`` → ``default_projection(function)``
    - ``all`` → every field populated on at least one observation, read
      from the ``populated`` masks — a fetched-but-null column counts,
      a never-fetched one does not.
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
            populated = frozenset().union(*(o.populated for o in observations)) if observations else frozenset()
            for field in Observation.model_fields:
                if field in populated and field in OBSERVATION_FIELDS:
                    _add(field)
        else:
            _add(name)
    return tuple(out)
