"""VFS storage backends.

``DatabaseStorage`` is the one storage implementation. ``SQLiteStorage``
and ``PostgresStorage`` name it on the two engines vfs supports, and
``InMemoryStorage`` is an ``SQLiteStorage`` over a private in-memory
database. Any other SQLAlchemy dialect is served by ``DatabaseStorage``
on the generic floor, which is fit for testing only.
"""

from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.memory import InMemoryStorage
from vfs.storage.backends.postgres import PostgresStorage
from vfs.storage.backends.sqlite import SQLiteStorage

__all__ = ["DatabaseStorage", "InMemoryStorage", "PostgresStorage", "SQLiteStorage"]
