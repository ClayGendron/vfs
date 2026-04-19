"""VFS exception hierarchy.

When ``VirtualFileSystem`` is constructed with ``raises=True``, the
``_error()`` method raises one of these exceptions instead of returning
``VFSResult(success=False)``.  The original ``VFSResult`` is
attached to the exception as ``.result`` so callers can inspect partial
successes in batch operations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vfs.results import VFSResult


class VFSError(Exception):
    """Base exception for all VFS errors."""

    def __init__(self, message: str, result: VFSResult | None = None) -> None:
        super().__init__(message)
        self.result = result


class NotFoundError(VFSError):
    """A path does not exist or is not the expected kind."""


class MountError(VFSError):
    """No mount found for the given path."""


class WriteConflictError(VFSError):
    """Write rejected — file exists with overwrite=False, or target is invalid."""


class ValidationError(VFSError):
    """Invalid arguments, patterns, or missing configuration."""


class GraphError(VFSError):
    """A graph algorithm failed."""


def _classify_error(
    message: str,
    errors: list[str],
    result: VFSResult,
) -> VFSError:
    """Map error messages to the appropriate exception type."""
    first = errors[0] if errors else message
    if "Not found:" in first or "Not a directory:" in first:
        return NotFoundError(message, result)
    if "No mount found" in first:
        return MountError(message, result)
    if "Already exists" in first or "Cannot write" in first or "Cannot delete" in first:
        return WriteConflictError(message, result)
    if "failed:" in first:
        return GraphError(message, result)
    if any(kw in first for kw in ("requires", "Invalid", "Duplicate", "Source not found")):
        return ValidationError(message, result)
    return VFSError(message, result)
