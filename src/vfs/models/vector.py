"""Vector type — fixed-dimension vector with SQLAlchemy storage, and the engine's cosine kernel.

``Vector[1024]`` creates a dimension-specific subclass that validates length
on construction. ``VectorType`` is a SQLAlchemy ``TypeDecorator`` whose
portable path stores a vector as **packed little-endian float32** in a
binary column — four bytes a component on every engine, parsed by
``struct`` in microseconds — and whose native path (``native=True``,
a fixed dimension) takes the engine's own vector type wherever one
exists: pgvector's ``vector(<N>)`` on PostgreSQL, the in-tree ``VECTOR``
on Oracle, and ``VECTOR(<N>)`` on SQL Server 2025 and MariaDB. SQLite
keeps the packed column — sqlite-vec scores it as it is. The module
also owns the cosine top-k kernel (:func:`cosine_topk`), the referee
every dialect's in-engine ranking is pinned against.

Usage::

    from vfs.models.vector import Vector, VectorType

    # As a model field (any dimension):
    vector: Vector | None = Field(default=None, sa_type=VectorType())

    # As a runtime validator:
    v = Vector[3]([1.0, 2.0, 3.0])

    # With dimension enforcement in the DB layer:
    vector: Vector | None = Field(default=None, sa_type=VectorType(dimension=1024))

    # With the engine's native vector column where it has one:
    vector: Vector | None = Field(
        default=None, sa_type=VectorType(dimension=1536, native=True)
    )

    # With model name tracking:
    v = Vector[1536, "text-embedding-3-large"]([0.1] * 1536)
    v = Vector["text-embedding-3-large"]([0.1] * 1536)
"""

from __future__ import annotations

import json
from array import array
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, Literal, cast

from pydantic_core import core_schema
from sqlalchemy import LargeBinary
from sqlalchemy.dialects.oracle import VECTOR, VectorStorageFormat
from sqlalchemy.types import TypeDecorator, TypeEngine

from vfs.models.vector_codec import FLOAT32_BYTES, pack_vector, unpack_vector
from vfs.models.vector_native import MariaDBVector, MSSQLVector
from vfs.native import extension

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pydantic import GetCoreSchemaHandler
    from pydantic_core import CoreSchema
    from sqlalchemy.engine.interfaces import Dialect

__all__ = [
    "FLOAT32_BYTES",
    "NATIVE_VECTOR_DIALECTS",
    "NativeEmbeddingConfig",
    "Vector",
    "VectorType",
    "cosine_topk",
    "pack_vector",
    "unpack_vector",
]

NATIVE_VECTOR_DIALECTS: Final = frozenset({"postgresql", "oracle", "mssql", "mariadb"})
"""Dialects whose own vector column type carries a native-typed ``VectorType``."""


@dataclass(frozen=True)
class NativeEmbeddingConfig:
    """The native vector column and its index for a mount.

    Passed to ``DatabaseStorage`` at construction, or synthesised from
    the embedder's width. The mount shapes the ``embedding`` column of
    its chunk table as the engine's own vector type of this
    ``dimension`` where one exists, with the configured pgvector index
    on PostgreSQL; SQLite keeps the packed portable column.
    """

    dimension: int
    index_method: Literal["hnsw", "ivfflat"] = "hnsw"
    operator_class: str = "vector_cosine_ops"
    model_name: str | None = None


class Vector(list[float]):
    """Fixed-dimension vector with optional model name tracking.

    Subscript forms:

    - ``Vector[1024]`` — dimension only
    - ``Vector["text-embedding-3-large"]`` — model name only
    - ``Vector[1024, "text-embedding-3-large"]`` — both

    Unsubscripted ``Vector()`` accepts any length with no model tracking.
    """

    _dimension: int | None = None
    _model_name: str | None = None

    def __class_getitem__(cls, params: int | str | tuple[int, str]) -> type[Vector]:  # ty: ignore[invalid-method-override]
        """Create a dimension/model-specific Vector subclass."""
        if isinstance(params, int):
            name, attrs = f"Vector[{params}]", {"_dimension": params, "_model_name": None}
        elif isinstance(params, str):
            name, attrs = f"Vector['{params}']", {"_dimension": None, "_model_name": params}
        elif isinstance(params, tuple):
            if len(params) != 2:
                msg = f"Vector[...] tuple must be (int, str), got {len(params)} elements"
                raise TypeError(msg)
            dim, model = params
            if not isinstance(dim, int) or not isinstance(model, str):
                msg = f"Vector[...] tuple must be (int, str), got ({type(dim).__name__}, {type(model).__name__})"
                raise TypeError(msg)
            name, attrs = f"Vector[{dim}, '{model}']", {"_dimension": dim, "_model_name": model}
        else:
            msg = f"Vector[...] requires int, str, or (int, str), got {type(params).__name__}"
            raise TypeError(msg)
        return cast("type[Vector]", type(name, (cls,), attrs))

    def __init__(self, data: list[float] | None = None) -> None:
        super().__init__(data or [])
        if self._dimension is not None and len(self) != self._dimension:
            msg = f"Expected {self._dimension} dimensions, got {len(self)}"
            raise ValueError(msg)

    @property
    def dimension(self) -> int | None:
        """Number of dimensions, or None if unconstrained."""
        return self._dimension

    @property
    def model_name(self) -> str | None:
        """Embedding model name, or None if unset."""
        return self._model_name

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        source_type: type,
        handler: GetCoreSchemaHandler,
    ) -> CoreSchema:
        return core_schema.no_info_plain_validator_function(
            cls._pydantic_validate,
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda v: list(v) if v is not None else None,
                info_arg=False,
            ),
        )

    @classmethod
    def _pydantic_validate(cls, value: object) -> Vector | None:
        if value is None:
            return None
        if isinstance(value, cls):
            return value
        if isinstance(value, Vector):
            return cls(list(value))
        if isinstance(value, list):
            return cls(value)  # ty: ignore[invalid-argument-type]
        msg = f"Expected list or Vector, got {type(value)}"
        raise ValueError(msg)


class VectorType(TypeDecorator[Vector]):
    """SQLAlchemy type: packed float32 bytes portably, the engine's vector type natively.

    Enforces dimension on BOTH read and write when ``dimension`` is set.
    Validates model name on write when ``model_name`` is set.

    With ``native=True`` (which requires a fixed dimension) the dialects
    in :data:`NATIVE_VECTOR_DIALECTS` take their own vector column and
    wire form — a float list for pgvector, ``array('f')`` for Oracle,
    JSON text for SQL Server, the packed bytes for MariaDB — and every
    other dialect keeps the portable binary column, so one table
    definition provisions everywhere.
    """

    impl = LargeBinary
    cache_ok = True

    def __init__(
        self,
        dimension: int | None = None,
        model_name: str | None = None,
        *,
        native: bool = False,
        postgres_index_method: str = "hnsw",
        postgres_operator_class: str = "vector_cosine_ops",
    ) -> None:
        super().__init__()
        if native and dimension is None:
            msg = "VectorType(native=True) requires a fixed dimension"
            raise ValueError(msg)
        self.dimension = dimension
        self.model_name = model_name
        self.native = native
        self.postgres_index_method = postgres_index_method
        self.postgres_operator_class = postgres_operator_class

    def copy(self, **kw: object) -> VectorType:
        return type(self)(
            dimension=self.dimension,
            model_name=self.model_name,
            native=self.native,
            postgres_index_method=self.postgres_index_method,
            postgres_operator_class=self.postgres_operator_class,
        )

    def is_native_on(self, dialect: Dialect) -> bool:
        """Whether *dialect* stores this column as its own vector type."""
        return self.native and dialect.name in NATIVE_VECTOR_DIALECTS

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[object]:
        if self.is_native_on(dialect):
            return dialect.type_descriptor(self.native_type_for(dialect.name))
        return dialect.type_descriptor(cast("TypeEngine[object]", LargeBinary()))

    def native_type_for(self, dialect_name: str) -> TypeEngine[object]:
        """The engine's own vector column type for *dialect_name*; requires a fixed dimension."""
        if self.dimension is None:
            msg = "Native vector columns require a fixed dimension"
            raise ValueError(msg)
        if dialect_name == "postgresql":
            return self.pgvector_sqlalchemy_type()
        if dialect_name == "oracle":
            return cast("TypeEngine[object]", VECTOR(self.dimension, storage_format=VectorStorageFormat.FLOAT32))
        if dialect_name == "mssql":
            return MSSQLVector(self.dimension)
        if dialect_name == "mariadb":
            return MariaDBVector(self.dimension)
        msg = f"{dialect_name!r} has no native vector column type"
        raise ValueError(msg)

    def pgvector_sqlalchemy_type(self) -> TypeEngine[object]:
        """Return the lazily imported pgvector SQLAlchemy type instance."""
        if self.dimension is None:
            msg = "Native pgvector columns require a fixed dimension"
            raise ValueError(msg)
        try:
            from pgvector.sqlalchemy import Vector as PGVector
        except ImportError as exc:  # pragma: no cover - exercised in Postgres integration env
            msg = "Native Postgres vectors require the 'pgvector' package. Install vfs-py[postgres]."
            raise RuntimeError(msg) from exc
        return PGVector(self.dimension)

    def _coerce_runtime_vector(self, value: list[float]) -> Vector:
        if self.dimension is not None and self.model_name is not None:
            return Vector[self.dimension, self.model_name](value)
        if self.dimension is not None:
            return Vector[self.dimension](value)
        if self.model_name is not None:
            return Vector[self.model_name](value)
        return Vector(value)

    def process_bind_param(self, value: list[float] | None, dialect: Dialect) -> object | None:
        if value is None:
            return None
        if self.dimension is not None and len(value) != self.dimension:
            msg = f"Vector bind: expected {self.dimension} dims, got {len(value)}"
            raise ValueError(msg)
        if (
            self.model_name is not None
            and isinstance(value, Vector)
            and value._model_name is not None
            and value._model_name != self.model_name
        ):
            msg = f"Vector bind: model name mismatch — column expects '{self.model_name}', got '{value._model_name}'"
            raise ValueError(msg)
        floats = [float(component) for component in value]
        if not self.is_native_on(dialect) or dialect.name == "mariadb":
            return pack_vector(floats)
        if dialect.name == "oracle":
            return array("f", floats)
        if dialect.name == "mssql":
            return json.dumps(floats)
        return floats

    def process_result_value(self, value: object | None, dialect: Dialect) -> Vector | None:
        if value is None:
            return None
        if not self.is_native_on(dialect) or dialect.name == "mariadb":
            if not isinstance(value, (bytes, bytearray, memoryview)):
                msg = f"Vector read: expected packed float32 bytes, got {type(value).__name__}"
                raise ValueError(msg)
            data = unpack_vector(bytes(value))
        elif dialect.name == "mssql":
            data = _native_floats(json.loads(value) if isinstance(value, (str, bytes, bytearray)) else value)
        else:
            data = _native_floats(value)
        if self.dimension is not None and len(data) != self.dimension:
            msg = f"Vector read: expected {self.dimension} dims, got {len(data)}"
            raise ValueError(msg)
        return self._coerce_runtime_vector(data)


def _native_floats(value: object) -> list[float]:
    """The floats of a native vector result — a list, a tuple, an array with ``tolist``, or any iterable."""
    if isinstance(value, (list, tuple)):
        raw_items = cast("list[object] | tuple[object, ...]", value)
    elif hasattr(value, "tolist"):
        raw_items = cast("list[object]", cast("Any", value).tolist())
    elif isinstance(value, (str, bytes, bytearray)):
        msg = f"Vector read: expected iterable native vector value, got {type(value).__name__}"
        raise ValueError(msg)
    else:
        try:
            raw_items = list(cast("Any", value))
        except TypeError as exc:
            msg = f"Vector read: expected iterable native vector value, got {type(value).__name__}"
            raise ValueError(msg) from exc
    data: list[float] = []
    for item in raw_items:
        if not isinstance(item, (int, float, str)):
            msg = f"Vector read: expected numeric vector element, got {type(item).__name__}"
            raise ValueError(msg)
        data.append(float(item))
    return data


# ---------------------------------------------------------------------------
# Cosine top-K — the engine
# ---------------------------------------------------------------------------


def cosine_topk(query: Sequence[float], ids: Sequence[int], vectors: bytes, k: int) -> list[tuple[int, float]]:
    """The ``k`` rows of one page nearest ``query`` by cosine, as ``(id, score)`` — from the engine.

    ``vectors`` is ``len(ids)`` packed little-endian float32 vectors of
    ``len(query)`` components concatenated in ``ids`` order — the portable
    column's bytes, one row after another. Stored vectors and the query
    are unit vectors, so cosine similarity *is* the dot product, and that
    is what the engine computes: ``query`` crosses the seam as float32,
    and each product accumulates in float32 from the first component to
    the last, so a score is bit-reproducible across pages, processes and
    machines. The answer holds ``min(k, len(ids))`` rows ordered ``score
    DESC, id ASC`` — a total order, so the top ``k`` of any two pages
    merge deterministically. Refused with ``ValueError``: an empty query,
    and a ``vectors`` length other than ``len(ids) * len(query) * 4``.

    The referee of the vector leg: every dialect's in-engine ranking is
    pinned against this exact order.
    """
    return extension().vector_topk(pack_vector(list(query)), array("q", ids).tobytes(), vectors, k)
