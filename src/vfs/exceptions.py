"""VFS exception hierarchy and the boundary raise adapter.

``Result`` is the only failure channel inside the mount tree — no
filesystem node ever raises these.  A caller who wants exceptions (an
ETL script populating the filesystem, where a silent failure reads as
"okay, it worked") opts in **once, at the call boundary**, via
:func:`raise_if_failed` or a raising client facade.  The original
``Result`` is attached to the exception as ``.result`` so callers can
inspect partial successes in batch operations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vfs.kinds import VFSErrorKind, kind_family

if TYPE_CHECKING:
    from vfs.results import Result, ResultError


class VFSError(Exception):
    """Base exception for all VFS errors."""

    def __init__(self, message: str, result: Result | None = None) -> None:
        super().__init__(message)
        self.result = result


class NotFoundError(VFSError):
    """A path does not exist or is not the expected kind."""


class MountError(VFSError, ValueError):
    """Mount administration failed — ``add_mount``/``remove_mount``.

    ``str()`` stays the prose (and ``ValueError`` keeps string-matching
    callers working); the structured evidence rides on ``errors`` — the
    ``ResultError`` list from the attached mkdir/rmdir result.
    """

    @property
    def errors(self) -> list[ResultError]:
        return list(self.result.errors) if self.result is not None else []


class WriteConflictError(VFSError):
    """Write rejected — file exists with overwrite=False, or target is invalid."""


class ValidationError(VFSError):
    """Invalid arguments, patterns, or missing configuration."""


class GraphError(VFSError):
    """A graph algorithm failed."""


class SchemaMismatchError(VFSError):
    """The live database schema does not match the in-memory table definitions."""


# Kind → exception class, keyed by the kind's resolved family. An unmapped
# family (``unavailable``/``timeout``/``cancelled``/``internal``) or a kind
# with no known prefix falls back to the base ``VFSError``.
_KIND_TO_EXC: dict[VFSErrorKind, type[VFSError]] = {
    VFSErrorKind.not_found: NotFoundError,
    VFSErrorKind.wrong_kind: NotFoundError,
    VFSErrorKind.exists: WriteConflictError,
    VFSErrorKind.not_empty: WriteConflictError,
    VFSErrorKind.conflict: WriteConflictError,
    VFSErrorKind.cross_mount: WriteConflictError,
    VFSErrorKind.permission_denied: WriteConflictError,
    VFSErrorKind.read_only: WriteConflictError,
    VFSErrorKind.invalid: ValidationError,
    VFSErrorKind.unsupported: ValidationError,
    VFSErrorKind.unrecognized: ValidationError,
}


def exception_for_kind(kind: VFSErrorKind | str) -> type[VFSError]:
    """Return the exception class for a structured error *kind*.

    Dispatches through :func:`kind_family` — no message inspection — so an
    unknown child kind from a newer peer degrades to its known parent's
    class before falling back to base ``VFSError``.  A kind with no known
    prefix raises as base ``VFSError``, never a narrower class that would
    misstate an unknown failure.
    """
    family = kind_family(kind)
    if family is None:
        return VFSError
    return _KIND_TO_EXC.get(family, VFSError)


def raise_if_failed(result: Result) -> Result:
    """Boundary adapter: turn a failed ``Result`` into its kind-mapped exception.

    The router never raises; callers who want loud failures wrap their calls
    (or use a raising client facade, which applies this to every verb).  A
    successful result passes through, so the call composes inline::

        entry = raise_if_failed(await fs.read("/a.txt")).one()

    Only **fatal** entries raise — success is derived, so a failed result
    always carries at least one, and warnings/info (loss on record,
    coverage notes) never become exceptions.  Each fatal entry raises as
    its kind's exception with the full result attached; multiple raise as
    an ``ExceptionGroup`` so a fan-out failure reports every downed
    terminal, not just the first.
    """
    if result.success:
        return result
    excs = [exception_for_kind(e.kind)(e.message, result) for e in result.failures]
    if len(excs) == 1:
        raise excs[0]
    raise ExceptionGroup("multiple VFS errors", excs)
