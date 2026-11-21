"""The cosine distance expression per dialect — the one thing the vector leg's statement varies.

Both supported engines have cosine in the engine; only its spelling
differs. The query binds through the column's own ``VectorType``, so
the type does the per-dialect conversion (a float list for pgvector,
packed float32 bytes for SQLite) and this module names the function:

    order = cosine_distance("sqlite", chunks.c.embedding, query)
    select(chunks.c.id).order_by(order).limit(k)

A dialect with no distance function (the generic floor) has no
expression here; the capability gate withholds ``search`` from it
before a statement is ever built.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Float, bindparam, func

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy import Column, ColumnElement


def cosine_distance(dialect_name: str, column: Column[object], query: Sequence[float]) -> ColumnElement[float]:
    """Cosine *distance* (0 is identical) between *column* and *query* on *dialect_name*."""
    bound = bindparam("query_vector", list(query), type_=column.type, unique=True)
    if dialect_name == "postgresql":
        return column.op("<=>", return_type=Float)(bound)
    if dialect_name == "sqlite":
        return func.vec_distance_cosine(column, bound, type_=Float)
    msg = f"{dialect_name!r} has no cosine distance function; the capability gate withholds search from it"
    raise ValueError(msg)


def has_cosine_distance(dialect_name: str) -> bool:
    """Whether :func:`cosine_distance` can spell the function for *dialect_name*."""
    return dialect_name in ("postgresql", "sqlite")
