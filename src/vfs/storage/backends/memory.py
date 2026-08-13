"""In-memory storage — the database backend over an in-process SQLite engine.

One storage implementation, one semantics: the in-memory role (dev
default, test fixture, zero-infrastructure node) is served by
:class:`~vfs.storage.backends.database.DatabaseStorage` pointed at a
private ``sqlite+aiosqlite:///:memory:`` database, so every verb —
including the trash arc — behaves exactly as the conformance suite
pins it, on the same code path production engines run.

    fs = VirtualFileSystem(storage=InMemoryStorage())     # tmpfs-like node

The database lives for the storage object's lifetime and vanishes at
``close()``. SQLAlchemy serves ``:memory:`` through a single shared
connection (``StaticPool``), and the engine host serializes sessions
on it — each op holds the host lock for its whole transaction, so
concurrent callers queue instead of colliding. Concurrency under real
rivals is exercised on the server engine legs.
"""

from __future__ import annotations

from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database.grep import WALL_TIME_BUDGET


class InMemoryStorage(DatabaseStorage):
    """A ``DatabaseStorage`` pinned to a private in-memory SQLite database.

    Construction-only subclass: every verb, capability, and trait comes
    from ``DatabaseStorage``. Each instance owns a fresh database — two
    instances never share state.
    """

    def __init__(
        self,
        *,
        name: str = "memory",
        description: str = "In-memory storage",
        trash_days: int = 90,
        grep_wall_seconds: float = WALL_TIME_BUDGET,
    ) -> None:
        super().__init__(
            url="sqlite+aiosqlite:///:memory:",
            name=name,
            description=description,
            trash_days=trash_days,
            grep_wall_seconds=grep_wall_seconds,
        )
