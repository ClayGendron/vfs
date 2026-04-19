"""Text renderer for query results.

Thin wrapper around ``VFSResult.to_str`` — the arrangement logic lives on
the result type, keyed off ``result.function``.  ``plan.projection`` is
forwarded verbatim; when it is ``None``, ``to_str`` falls back to the
per-function default projection.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vfs.query.ast import QueryPlan
    from vfs.results import VFSResult


def render_query_result(result: VFSResult, plan: QueryPlan) -> str:
    """Render *result* into a human-readable text response."""
    return result.to_str(projection=plan.projection)
