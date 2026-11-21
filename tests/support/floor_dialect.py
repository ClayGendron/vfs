"""An SQLite dialect under a name no profile tunes, so a storage built on it resolves to the generic floor.

The dialect is aiosqlite's under another name, registered with
SQLAlchemy at import, so a test reaches the floor through a real URL and
a real engine, and nothing in vfs is patched around.

    storage = DatabaseStorage(url=FLOOR_URL)   # served the generic floor; logs one warning
"""

from __future__ import annotations

from sqlalchemy.dialects import registry
from sqlalchemy.dialects.sqlite.aiosqlite import SQLiteDialect_aiosqlite

FLOOR_NAME = "vfsfloor"
"""The dialect's name, which no tuned profile carries."""

FLOOR_URL = f"{FLOOR_NAME}+aiosqlite:///:memory:"
"""A URL that builds an engine on the floor dialect; nothing connects until first touch."""


class FloorDialect(SQLiteDialect_aiosqlite):
    """aiosqlite's dialect under a name vfs has no profile for."""

    name = FLOOR_NAME


registry.register(f"{FLOOR_NAME}.aiosqlite", __name__, FloorDialect.__name__)
