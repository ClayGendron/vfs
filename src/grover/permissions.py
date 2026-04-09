"""Permission enforcement for Grover filesystems.

Mount-level ``read`` / ``read_write`` permissions are enforced at the
routing layer in :mod:`grover.base`.  Every mutating operation funnels
through one of five chokepoints (``_route_single``, ``_route_write_batch``,
``_route_two_path``, ``_dispatch_candidates``, or ``mkconn``) and each
one calls :func:`check_writable` on the resolved terminal filesystem
before touching storage.

The rejection message uses the prefix ``"Cannot write to read-only
mount"``, which the existing ``_classify_error`` mapping in
:mod:`grover.exceptions` already routes to :class:`WriteConflictError`
via its ``"Cannot write"`` substring rule — no new exception class is
needed.

Limitations
-----------

**Permissions are per-filesystem-instance, not per-storage.**  The
``permissions`` flag lives on a ``DatabaseFileSystem`` instance, not on
the SQL engine or table it points at.  Two ``DatabaseFileSystem``
instances that share the same underlying engine (or the same table in
the same engine) are independent from the permission system's point of
view.  If one is constructed with ``permissions="read"`` and another
with ``permissions="read_write"`` on the same engine, writes through
the writable instance will land in the bytes that the read-only
instance also reads from.

**Do not share engines or tables between mounts.**  Each mount should
own its own engine, or at minimum its own table, unless you are
intentionally exposing the same storage under two different namespaces
with compatible permissions.  The ``add_mount`` API encourages this
pattern — in typical usage each call constructs a fresh
``DatabaseFileSystem`` with its own engine — but the permission model
does not and cannot enforce it, because engine sharing is a legitimate
optimization when all readers agree on the same access level.

This trade-off mirrors Unix: file permissions are enforced by the
filesystem layer, but a process that has direct access to the
underlying block device can still write bytes.  Grover treats the SQL
engine as that block device.  If you need hard isolation between a
read-only view and a writable view of the same data, use separate
engines (or separate tables within one engine) — not two
``DatabaseFileSystem`` instances sharing one.

Future work
-----------

Directory-level and file-level permissions (``read_only_paths`` on a
mount, per-path ACLs, the ``grover_shares`` table, and the
``SupportsReBAC`` protocol from the design doc) are deferred to a
future iteration.  They will grow on top of the same
:func:`check_writable` chokepoint — the current mount-level check is
structured so that a path-aware version slots in without touching the
routing layer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from grover.base import GroverFileSystem
    from grover.results import GroverResult


Permission = Literal["read", "read_write"]
"""Mount-level permission value."""


MUTATING_OPS: frozenset[str] = frozenset(
    {"write", "edit", "delete", "mkdir", "mkconn", "move", "copy"},
)
"""Operation names that mutate the backing store.

Used by :func:`check_writable` to decide whether a routed op needs a
write-permission check.  Read-only operations (``read``, ``stat``, ``ls``,
``tree``, ``glob``, ``grep``, ``search``, graph traversal, centrality)
are intentionally excluded — they must keep working on read-only mounts.
"""


def validate_permission(value: str) -> Permission:
    """Validate and return a :data:`Permission` value.

    Raises :class:`ValueError` for anything other than ``"read"`` or
    ``"read_write"``.  Called from ``GroverFileSystem.__init__`` so
    invalid values fail at construction time, not at first mutation.
    """
    if value == "read":
        return "read"
    if value == "read_write":
        return "read_write"
    msg = f"permissions must be 'read' or 'read_write', got {value!r}"
    raise ValueError(msg)


def check_writable(
    fs: GroverFileSystem,
    op: str,
    path: str,
) -> GroverResult | None:
    """Return a classified error result if *op* mutates a read-only mount.

    Returns ``None`` when the operation is allowed (either because it is
    not a mutation or because the filesystem is writable).  Returns a
    failure :class:`GroverResult` — via ``fs._error(...)`` — when the
    operation would mutate a read-only mount.

    The returned result's error message begins with ``"Cannot write to
    read-only mount"``, which the existing ``_classify_error`` mapping
    routes to :class:`WriteConflictError`.  When the filesystem has
    ``raise_on_error=True``, ``fs._error(...)`` raises the classified
    exception directly instead of returning a result.
    """
    if op in MUTATING_OPS and fs._permissions == "read":
        return fs._error(f"Cannot write to read-only mount: {path}")
    return None
