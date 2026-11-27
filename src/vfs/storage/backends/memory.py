"""In-memory storage — the database backend over an in-process SQLite engine.

One storage implementation, one semantics: the in-memory role (dev
default, test fixture, zero-infrastructure node) is served by
:class:`~vfs.storage.backends.sqlite.SQLiteStorage` over a private
``:memory:`` database, so every verb — including the trash arc —
behaves exactly as the conformance suite pins it, on the same code path
production engines run.

    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())     # tmpfs-like node

The database lives for the storage object's lifetime and vanishes at
``close()``. SQLAlchemy serves ``:memory:`` through a single shared
connection (``StaticPool``), and the engine host serializes sessions
on it — each op holds the host lock for its whole transaction, so
concurrent callers queue instead of colliding. Concurrency under real
rivals is exercised on the server engine legs.

A caller that is cancelled never costs the storage its database. Its
call runs out of reach of the cancellation, ends the statement it is in
and sends no other, and a call that was cancelled while it waited in the
queue sends nothing, though its caller is back only when its turn comes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vfs.deadline import WALL_TIME_BUDGET
from vfs.embedding import HashEmbeddingProvider
from vfs.storage.backends.sqlite import SQLiteStorage

if TYPE_CHECKING:
    from vfs.embedding import EmbeddingProvider

MEMORY_PATH = ":memory:"
"""The path SQLite reads as a database in memory, private to its one connection."""


class InMemoryStorage(SQLiteStorage):
    """An ``SQLiteStorage`` whose path is a private in-memory database.

    Construction-only subclass: every verb, capability, and trait comes
    from ``DatabaseStorage``. Each instance owns a fresh database — two
    instances never share state. The default embedder is the hashing
    provider — no key, no download — so ``rebuild`` fills vectors here
    exactly as it does on a server engine.

    A call can be cancelled at any moment, and the storage keeps every row
    afterwards. The call ends the statement it is in, sends no other, and
    its transaction is rolled back; the caller gets its ``CancelledError``
    then. A call that waits for its turn behind another, or on a worker
    thread as a grep does, ends that wait first. A write that is cancelled
    before its commit changes nothing, and a write that is cancelled later
    has landed whole. The caller cannot tell which, so it reads the file
    before it writes it again.

    A file system whose root is this storage keeps the kernel's own
    records in memory too, in a second database of their own with its own
    connection, and they end with the process.
    """

    def __init__(
        self,
        *,
        name: str = "memory",
        description: str = "In-memory storage",
        trash_days: int = 90,
        grep_wall_seconds: float = WALL_TIME_BUDGET,
        glob_wall_seconds: float = WALL_TIME_BUDGET,
        embedder: EmbeddingProvider | None = None,
    ) -> None:
        super().__init__(
            path=MEMORY_PATH,
            name=name,
            description=description,
            trash_days=trash_days,
            grep_wall_seconds=grep_wall_seconds,
            glob_wall_seconds=glob_wall_seconds,
            embedder=HashEmbeddingProvider() if embedder is None else embedder,
        )
