"""The result envelope: what comes back from every VFS operation.

``envelope`` defines ``Result``/``ResultError``; ``kinds`` is the error
vocabulary; ``render`` and ``projection`` shape results for output.
"""

from vfs.results.envelope import (
    Result,
    ResultError,
    already_exists,
    classified,
    validation_message,
    wrong_kind,
)
from vfs.results.kinds import (
    KIND_CONTRACTS,
    KindContract,
    RetryClass,
    Severity,
    VFSErrorKind,
    kind_family,
)

__all__ = [
    "KIND_CONTRACTS",
    "KindContract",
    "Result",
    "ResultError",
    "RetryClass",
    "Severity",
    "VFSErrorKind",
    "already_exists",
    "classified",
    "kind_family",
    "validation_message",
    "wrong_kind",
]
