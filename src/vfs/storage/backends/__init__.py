"""VFS storage backends.

Only the in-memory reference backend lives here today.  The pre-refactor
database backends (``database``, ``mssql``, ``postgres``) are parked in
``src2/`` for reference and return here as they are ported.
"""

from vfs.storage.backends.memory import InMemoryStorage

__all__ = ["InMemoryStorage"]
