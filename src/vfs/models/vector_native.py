"""The two native vector column types SQLAlchemy does not model: SQL Server's and MariaDB's.

pgvector ships its own SQLAlchemy type and Oracle's ``VECTOR`` is in the
tree; SQL Server 2025 and MariaDB 11.7+ have a native ``VECTOR(n)`` with
no upstream type, so each gets a column-spec-only ``UserDefinedType``
here. They carry no processors of their own: ``VectorType`` converts per
dialect — JSON text for SQL Server's driver, the packed float32 bytes
MariaDB stores natively — and selects these types from
``load_dialect_impl``. Nothing else imports this module.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.types import UserDefinedType


class MSSQLVector(UserDefinedType[Any]):
    """SQL Server 2025's ``VECTOR(n)``; the wire form is JSON text."""

    cache_ok = True

    def __init__(self, dimension: int) -> None:
        super().__init__()
        self.dimension = dimension

    def get_col_spec(self, **kw: Any) -> str:
        return f"VECTOR({self.dimension})"


class MariaDBVector(UserDefinedType[Any]):
    """MariaDB's ``VECTOR(n)``; the wire form is IEEE 754 float32 little-endian bytes."""

    cache_ok = True

    def __init__(self, dimension: int) -> None:
        super().__init__()
        self.dimension = dimension

    def get_col_spec(self, **kw: Any) -> str:
        return f"VECTOR({self.dimension})"
