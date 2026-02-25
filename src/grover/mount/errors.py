"""Mount-level errors for protocol dispatch."""

from __future__ import annotations


class ProtocolConflictError(Exception):
    """Raised when two mount components implement the same dispatch protocol."""


class ProtocolNotAvailableError(Exception):
    """Raised when no mount component implements the requested dispatch protocol."""
