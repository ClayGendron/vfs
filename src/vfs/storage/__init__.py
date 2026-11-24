"""Storage: the backend protocol and the backends that implement it.

``protocol`` defines the ``StorageBackend`` capability protocols and
``storage_ops``; ``replace`` is the shared edit engine; concrete
implementations live under ``backends``.
"""

from vfs.storage.protocol import (
    HOLDS,
    TRAIT_KEYS,
    TRAIT_VALUES,
    RecordPlace,
    ResolvedPair,
    StorageBackend,
    SupportsClose,
    SupportsGrants,
    SupportsHolds,
    SupportsMutation,
    SupportsPatternSearch,
    SupportsRankedSearch,
    SupportsRead,
    SupportsRebuild,
    SupportsRecordPlace,
    SupportsRun,
    SupportsTraits,
    SupportsTraversal,
    TraitKey,
    TransportError,
    storage_ops,
    targets_of,
)

__all__ = [
    "HOLDS",
    "TRAIT_KEYS",
    "TRAIT_VALUES",
    "RecordPlace",
    "ResolvedPair",
    "StorageBackend",
    "SupportsClose",
    "SupportsGrants",
    "SupportsHolds",
    "SupportsMutation",
    "SupportsPatternSearch",
    "SupportsRankedSearch",
    "SupportsRead",
    "SupportsRebuild",
    "SupportsRecordPlace",
    "SupportsRun",
    "SupportsTraits",
    "SupportsTraversal",
    "TraitKey",
    "TransportError",
    "storage_ops",
    "targets_of",
]
