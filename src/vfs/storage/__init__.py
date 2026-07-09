"""Storage: the backend protocol and the backends that implement it.

``protocol`` defines the ``StorageBackend`` capability protocols and
``storage_ops``; ``replace`` is the shared edit engine; concrete
implementations live under ``backends``.
"""

from vfs.storage.protocol import (
    ResolvedPair,
    StorageBackend,
    SupportsClose,
    SupportsGlean,
    SupportsGraph,
    SupportsMutation,
    SupportsPatternSearch,
    SupportsRead,
    SupportsRun,
    TransportError,
    storage_ops,
)

__all__ = [
    "ResolvedPair",
    "StorageBackend",
    "SupportsClose",
    "SupportsGlean",
    "SupportsGraph",
    "SupportsMutation",
    "SupportsPatternSearch",
    "SupportsRead",
    "SupportsRun",
    "TransportError",
    "storage_ops",
]
