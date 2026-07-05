"""Spike: a composed ``StorageBackend`` protocol fails at the definition site.

The same omission as ``spike_inherited.py`` — a backend missing its read
impl — is a ``ty`` error the moment the object is handed to the router,
before anything runs.  Provider inheritance (Database -> Postgres -> MSSQL
overriding individual methods) lives *inside* the backend family and is
untouched by the seam.

Run: ``uv run ty check <this file>`` — fails on the marked line.
"""

from __future__ import annotations

from typing import Protocol

from vfs.results2 import Result


class StorageBackend(Protocol):
    """Sketch of the composed seam — two ops stand in for the op families."""

    async def read(self, *, path: str, user_id: str | None = None) -> Result: ...

    async def stat(self, *, path: str, user_id: str | None = None) -> Result: ...


class ForgetfulStorage:
    """The same bug as ForgetfulFS: stat exists, read was never written."""

    async def stat(self, *, path: str, user_id: str | None = None) -> Result:
        return Result(function="stat", observations=[])


class DatabaseStorage:
    """Complete backend — and the base of a provider family, as today."""

    async def read(self, *, path: str, user_id: str | None = None) -> Result:
        return Result(function="read", observations=[])

    async def stat(self, *, path: str, user_id: str | None = None) -> Result:
        return Result(function="stat", observations=[])


class PostgresStorage(DatabaseStorage):
    """Provider override of one method — inheritance inside the family."""

    async def stat(self, *, path: str, user_id: str | None = None) -> Result:
        return Result(function="stat", observations=[])


def mount_point(storage: StorageBackend) -> StorageBackend:
    """Stands in for ``VirtualFileSystem(storage=...)`` accepting the protocol."""
    return storage


complete: StorageBackend = mount_point(DatabaseStorage())
provider: StorageBackend = mount_point(PostgresStorage())
broken: StorageBackend = mount_point(ForgetfulStorage())  # ty: invalid-argument-type
