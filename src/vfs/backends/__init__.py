"""VFS storage backends.

Only the v2 in-memory reference backend is exported here.  The
pre-refactor database backends (``database``, ``mssql``, ``postgres``)
are mid-rebuild and import against retired names — reach them by direct
module import once ported; eagerly importing them here would poison the
whole package.
"""

from vfs.backends.memory import InMemoryStorage

__all__ = ["InMemoryStorage"]
