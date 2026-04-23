"""Vector type — fixed-dimension vector with SQLAlchemy storage.

``Vector[1024]`` creates a dimension-specific subclass that validates length
on construction. ``VectorType`` is a SQLAlchemy ``TypeDecorator`` that
serializes vectors as JSON text by default, and can switch to a native
PostgreSQL ``vector(<N>)`` column when ``postgres_native=True``.

Usage::

    from vfs.vector import Vector, VectorType

    # As a model field (any dimension):
    vector: Vector | None = Field(default=None, sa_type=VectorType())

    # As a runtime validator:
    v = Vector[3]([1.0, 2.0, 3.0])

    # With dimension enforcement in the DB layer:
    vector: Vector | None = Field(default=None, sa_type=VectorType(dimension=1024))

    # With native pgvector on PostgreSQL:
    vector: Vector | None = Field(
        default=None,
        sa_type=VectorType(dimension=1536, postgres_native=True),
    )

    # With model name tracking:
    v = Vector[1536, "text-embedding-3-large"]([0.1] * 1536)
    v = Vector["text-embedding-3-large"]([0.1] * 1536)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, cast

from pydantic_core import core_schema
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator, TypeEngine

if TYPE_CHECKING:
    from pydantic import GetCoreSchemaHandler
    from pydantic_core import CoreSchema
    from sqlalchemy.engine.interfaces import Dialect


@dataclass(frozen=True)
class NativeEmbeddingConfig:
    """Postgres-native pgvector column configuration for a filesystem mount.

    Passed to :class:`vfs.backends.postgres.PostgresFileSystem` at
    construction. The filesystem uses it to shape the ``embedding`` column
    of its minted entry-table class so that the column is a true
    ``vector(<N>)`` with the configured pgvector index.
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
    """SQLAlchemy type: stores Vector as JSON text by default.

    Enforces dimension on BOTH read and write when ``dimension`` is set.
    Validates model name on write when ``model_name`` is set.

    When ``postgres_native=True``, PostgreSQL uses ``pgvector``'s native
    ``vector(<N>)`` type while other dialects keep the portable JSON path.
    """

    impl = Text
    cache_ok = True

    def __init__(
        self,
        dimension: int | None = None,
        model_name: str | None = None,
        *,
        postgres_native: bool = False,
        postgres_index_method: str = "hnsw",
        postgres_operator_class: str = "vector_cosine_ops",
    ) -> None:
        super().__init__()
        if postgres_native and dimension is None:
            msg = "VectorType(postgres_native=True) requires a fixed dimension"
            raise ValueError(msg)
        self.dimension = dimension
        self.model_name = model_name
        self.postgres_native = postgres_native
        self.postgres_index_method = postgres_index_method
        self.postgres_operator_class = postgres_operator_class

    def copy(self, **kw: object) -> VectorType:
        return type(self)(
            dimension=self.dimension,
            model_name=self.model_name,
            postgres_native=self.postgres_native,
            postgres_index_method=self.postgres_index_method,
            postgres_operator_class=self.postgres_operator_class,
        )

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[object]:
        if self.postgres_native and dialect.name == "postgresql":
            return dialect.type_descriptor(self.pgvector_sqlalchemy_type())
        return dialect.type_descriptor(cast("TypeEngine[object]", Text()))

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
        if self.postgres_native and getattr(dialect, "name", None) == "postgresql":
            return list(value)
        return json.dumps(list(value))

    def process_result_value(self, value: object | None, dialect: Dialect) -> Vector | None:
        if value is None:
            return None
        if self.postgres_native and getattr(dialect, "name", None) == "postgresql":
            if isinstance(value, (list, tuple)):
                raw_items = cast("list[object] | tuple[object, ...]", value)
            elif hasattr(value, "tolist"):
                raw_items = cast("list[object]", cast("Any", value).tolist())
            elif isinstance(value, (str, bytes, bytearray)):
                msg = f"Vector read: expected iterable pgvector value, got {type(value).__name__}"
                raise ValueError(msg)
            else:
                try:
                    raw_items = list(cast("Any", value))
                except TypeError as exc:
                    msg = f"Vector read: expected iterable pgvector value, got {type(value).__name__}"
                    raise ValueError(msg) from exc
        else:
            if not isinstance(value, (str, bytes, bytearray)):
                msg = f"Vector read: expected JSON text, got {type(value).__name__}"
                raise ValueError(msg)
            decoded = json.loads(value)
            if not isinstance(decoded, list):
                msg = f"Vector read: expected JSON array, got {type(decoded).__name__}"
                raise ValueError(msg)
            raw_items = decoded
        data: list[float] = []
        for item in raw_items:
            if not isinstance(item, (int, float, str)):
                msg = f"Vector read: expected numeric vector element, got {type(item).__name__}"
                raise ValueError(msg)
            data.append(float(item))
        if self.dimension is not None and len(data) != self.dimension:
            msg = f"Vector read: expected {self.dimension} dims, got {len(data)}"
            raise ValueError(msg)
        return self._coerce_runtime_vector(data)
