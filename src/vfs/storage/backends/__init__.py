"""VFS storage backends.

``DatabaseStorage`` is the one storage implementation — it runs on any
SQLAlchemy-compatible database. ``InMemoryStorage`` is its thin
in-memory face: the same backend pinned to a private
``sqlite+aiosqlite:///:memory:`` database.
"""

from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.memory import InMemoryStorage

__all__ = ["DatabaseStorage", "InMemoryStorage"]
