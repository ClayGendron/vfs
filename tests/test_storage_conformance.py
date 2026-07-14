"""Conformance-suite instantiations — one subclass per backend.

The contract itself lives in ``storage_conformance.StorageContract``;
this file only wires backends in. ``DatabaseStorage(sqlite)`` joins when
it lands; Postgres rides behind the integration marker.
"""

from __future__ import annotations

import pytest

from storage_conformance import StorageContract
from vfs.storage.backends.memory import InMemoryStorage


class TestMemoryConformance(StorageContract):
    @pytest.fixture
    def storage(self) -> InMemoryStorage:
        return InMemoryStorage()
