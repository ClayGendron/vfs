"""Conformance-suite instantiations — one subclass per backend.

The contract itself lives in ``storage_conformance.StorageContract``;
this file only wires backends in. The sqlite leg runs the families
``DatabaseStorage`` declares so far — capability gating skips the rest,
and each mutation slice landing flips its rows from skipped to enforced.
Postgres rides behind the integration marker when its slice lands.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from storage_conformance import StorageContract
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.memory import InMemoryStorage

if TYPE_CHECKING:
    import pathlib
    from collections.abc import AsyncIterator


class TestMemoryConformance(StorageContract):
    @pytest.fixture
    def storage(self) -> InMemoryStorage:
        return InMemoryStorage()


class TestSqliteConformance(StorageContract):
    @pytest.fixture
    async def storage(self, tmp_path: pathlib.Path) -> AsyncIterator[DatabaseStorage]:
        storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{tmp_path}/vfs.sqlite")
        yield storage
        await storage.close()
