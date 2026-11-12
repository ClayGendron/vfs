"""Storage: the backend protocol and the backends that implement it.

``protocol`` defines the ``StorageBackend`` capability protocols and
``storage_ops``; ``replace`` is the shared edit engine; concrete
implementations live under ``backends``.
"""

from vfs.storage.protocol import (
    TRAIT_KEYS,
    TRAIT_VALUES,
    ResolvedPair,
    StorageBackend,
    SupportsClose,
    SupportsGrants,
    SupportsMutation,
    SupportsPatternSearch,
    SupportsRankedSearch,
    SupportsRead,
    SupportsReindex,
    SupportsRun,
    SupportsTraits,
    SupportsTraversal,
    TraitKey,
    TransportError,
    storage_ops,
    targets_of,
)

__all__ = [
    "TRAIT_KEYS",
    "TRAIT_VALUES",
    "ResolvedPair",
    "StorageBackend",
    "SupportsClose",
    "SupportsGrants",
    "SupportsMutation",
    "SupportsPatternSearch",
    "SupportsRankedSearch",
    "SupportsRead",
    "SupportsReindex",
    "SupportsRun",
    "SupportsTraits",
    "SupportsTraversal",
    "TraitKey",
    "TransportError",
    "storage_ops",
    "targets_of",
]
