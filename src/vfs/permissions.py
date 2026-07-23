"""Permission enforcement for VFS filesystems.

A mount-table entry may carry a :class:`PermissionMap`: one default
permission plus zero or more directory-prefix overrides.  Every mutating
operation funnels through a router dispatch chokepoint in
:mod:`vfs.base`, whose gate calls :func:`check_writable_composed` with
the maps of every entry on the path from ``/`` to the terminal — the
most restrictive layer wins (a read-only root makes the whole tree
read-only; restriction tightens, never loosens, like Linux's
``MNT_READONLY || SB_RDONLY``).

Resolution semantics
--------------------

Rules live in **mount-relative coordinates**: a rule on ``/synthesis``
matches the path ``/synthesis`` inside that mount, regardless of which
router-side path the mount sits under.  Each layer therefore resolves
against the path rebased into *its own* coordinates, and the rules stay
decoupled from the mount point.

To resolve a path:

1. Find the override whose prefix is the longest prefix of the
   requested path (``path == prefix`` or
   ``path.startswith(prefix + "/")``).
2. If one matches, use that override's permission.
3. Otherwise, use the default.
4. Then apply the :data:`MUTATING_OPS` check.

Sort order is established once at construction time, so resolution is
a single linear pass.  This is the same algorithm that ``_match_mount``
uses for routing — one mental model covers both.

The rejection is structured: the error carries ``kind=read_only``,
which :func:`vfs.exceptions.exception_for_kind` maps to
:class:`~vfs.exceptions.WriteConflictError` at the call boundary
(``raise_if_failed``).  No message inspection is involved.

Helpers
-------

Three idioms exist for declaring permissions:

* The string forms ``"read"`` and ``"read_write"`` — same as before.
  Internally normalized to a default-only :class:`PermissionMap`.
* :func:`read_only` and :func:`read_write` factory functions for the
  common "default plus a flat list of carve-outs" case.
* The explicit :class:`PermissionMap` constructor for nested overrides
  (a writable region inside a read-only region inside a writable
  default).

The factories take the *opposite* permission's exception list as a
keyword (``write=`` for :func:`read_only`, ``read=`` for
:func:`read_write`) because that's how the carve-outs read in English:
"a read-only mount with these writable holes".

Limitations
-----------

**Permissions are per-filesystem-instance, not per-storage.**  The
permission map lives on a ``DatabaseFileSystem`` instance, not on the
SQL engine or table it points at.  Two ``DatabaseFileSystem``
instances that share the same underlying engine (or the same table in
the same engine) are independent from the permission system's point of
view.  If one is constructed with ``permissions="read"`` and another
with ``permissions="read_write"`` on the same engine, writes through
the writable instance will land in the bytes that the read-only
instance also reads from.

**Do not share engines or tables between mounts.**  Each mount should
own its own engine, or at minimum its own table, unless you are
intentionally exposing the same storage under two different namespaces
with compatible permissions.

User scoping
------------

When ``DatabaseFileSystem`` is constructed with ``user_scoped=True``,
each call's path is rewritten to live under ``/{user_id}/...`` *inside
the impl*, after the permission check has already run.  Permission
rules therefore live in **unscoped logical coordinates**.

The right way to write a rule for a user-scoped filesystem is to name
the *logical* path that exists in every user's namespace:

>>> permissions.read_only(write=["/synthesis"])  # doctest: +SKIP

This applies to ``alice``'s ``/synthesis``, ``bob``'s ``/synthesis``,
and so on.  The rule is checked against the unscoped path
``/synthesis/page.md``, which the impl then rewrites to
``/alice/synthesis/page.md`` (or whoever the caller is) before storage.

The wrong way is to embed a user id in the rule path:

>>> permissions.read_only(write=["/alice/synthesis"])  # doctest: +SKIP

This rule is checked in unscoped coordinates, so ``bob`` can trigger it
by writing to ``/wiki/alice/synthesis/page.md``.  ``bob``'s data still
lands in ``/bob/alice/synthesis/page.md`` — there is no cross-user data
leak — but the rule is meaningless because it does not actually scope
to alice.  If you need per-user policy, use the share / ReBAC layer
(``SupportsReBAC``), not :class:`PermissionMap`.

This trade-off mirrors Unix: file permissions are enforced by the
filesystem layer, but a process that has direct access to the
underlying block device can still write bytes.  VFS treats the SQL
engine as that block device.  If you need hard isolation between a
read-only view and a writable view of the same data, use separate
engines (or separate tables within one engine) — not two
``DatabaseFileSystem`` instances sharing one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, NamedTuple, TypedDict

from vfs.ops import MUTATING_OPS
from vfs.paths import ROOT, Path, normalize_path
from vfs.results import Result, ResultError, VFSErrorKind

if TYPE_CHECKING:
    from collections.abc import Iterable


Permission = Literal["read", "read_write"]
"""Filesystem-level permission value."""


class PermissionsPayload(TypedDict):
    """JSON-native form of a :class:`PermissionMap` — what ``to_payload`` emits.

    ``overrides`` pairs are ``[prefix, permission]`` lists in the map's
    normalized order, so the payload is deterministic and feeds the
    constructor back verbatim at runtime.  Typed replay code converts the
    pairs explicitly — ``list[list[str]]`` is not statically assignable to
    the declared overrides tuple type; only ``__post_init__``'s runtime
    normalization accepts the payload as-is.
    """

    default: Permission
    overrides: list[list[str]]


def validate_permission(value: str) -> Permission:
    """Validate and return a :data:`Permission` value.

    Raises :class:`ValueError` for anything other than ``"read"`` or
    ``"read_write"``.
    """
    if value == "read":
        return "read"
    if value == "read_write":
        return "read_write"
    msg = f"permissions must be 'read' or 'read_write', got {value!r}"
    raise ValueError(msg)


class _Resolution(NamedTuple):
    """Outcome of resolving a path against a :class:`PermissionMap`."""

    permission: Permission
    rule_prefix: str | None  # None when only the default applied


class _Override(NamedTuple):
    """One normalized override rule: a directory prefix and its permission."""

    path: str
    permission: Permission


@dataclass(frozen=True, slots=True)
class PermissionMap:
    """Default permission plus directory-prefix overrides.

    Resolves a path to a :data:`Permission` via longest-prefix match
    against the override list, falling back to ``default``.

    All override paths are normalized at construction time and stored
    in descending length order so resolution is a single pass.
    Construction validates the default permission, normalizes each
    override path, rejects ``/`` (use ``default`` instead) and rejects
    duplicate override paths.
    """

    default: Permission = "read_write"
    overrides: tuple[tuple[str, Permission], ...] = field(default=())

    def __post_init__(self) -> None:
        normalized: list[_Override] = []
        seen: set[str] = set()
        for raw_path, perm in self.overrides:
            path = normalize_path(raw_path)
            if path == "/":
                msg = "PermissionMap override path must not be '/' — use 'default' instead"
                raise ValueError(msg)
            if path in seen:
                msg = f"Duplicate override path: {path!r}"
                raise ValueError(msg)
            seen.add(path)
            normalized.append(_Override(path, validate_permission(perm)))
        normalized.sort(key=lambda override: len(override.path), reverse=True)
        object.__setattr__(self, "overrides", tuple(normalized))
        object.__setattr__(self, "default", validate_permission(self.default))

    def resolve(self, path: str) -> Permission:
        """Resolve *path* to a :data:`Permission` via longest-prefix match."""
        return self._resolve(path).permission

    def to_payload(self) -> PermissionsPayload:
        """Serialize to a :class:`PermissionsPayload` in normalized order.

        The emitted dict survives ``json.dumps``/``loads`` unchanged and
        reconstructs this exact map when fed back to the constructor.
        """
        return PermissionsPayload(
            default=self.default,
            overrides=[[path, perm] for path, perm in self.overrides],
        )

    def _resolve(self, path: str) -> _Resolution:
        normalized = normalize_path(path)
        for prefix, perm in self.overrides:
            if normalized == prefix or normalized.startswith(prefix + "/"):
                return _Resolution(perm, prefix)
        return _Resolution(self.default, None)


def coerce_permissions(value: Permission | PermissionMap | str) -> PermissionMap:
    """Normalize a constructor argument into a :class:`PermissionMap`.

    Accepts the string forms ``"read"`` / ``"read_write"`` for
    backwards compatibility, or an explicit :class:`PermissionMap`.
    """
    if isinstance(value, PermissionMap):
        return value
    if isinstance(value, str):
        return PermissionMap(default=validate_permission(value))
    msg = f"permissions must be 'read', 'read_write', or a PermissionMap, got {type(value).__name__}"
    raise TypeError(msg)


def read_only(*, write: Iterable[str] = ()) -> PermissionMap:
    """Build a read-only :class:`PermissionMap` with writable carve-outs.

    The keyword names what the carve-outs *grant*, not what the default
    forbids: ``permissions.read_only(write=["/synthesis"])`` reads as
    "read-only with ``/synthesis`` writable".

    >>> read_only(write=["/synthesis"]).resolve("/synthesis/page.md")
    'read_write'
    >>> read_only(write=["/synthesis"]).resolve("/raw/page.md")
    'read'
    """
    overrides = tuple((path, "read_write") for path in write)
    return PermissionMap(default="read", overrides=overrides)


def read_write(*, read: Iterable[str] = ()) -> PermissionMap:
    """Build a writable :class:`PermissionMap` with read-only carve-outs.

    The keyword names what the carve-outs *grant*:
    ``permissions.read_write(read=["/.frozen"])`` reads as
    "read_write with ``/.frozen`` read-only".

    >>> read_write(read=["/.frozen"]).resolve("/.frozen/locked.toml")
    'read'
    >>> read_write(read=["/.frozen"]).resolve("/src/main.py")
    'read_write'
    """
    overrides = tuple((path, "read") for path in read)
    return PermissionMap(default="read_write", overrides=overrides)


class PermissionLayer(NamedTuple):
    """One gate layer: an entry's map, the path in that entry's coordinates, its prefix."""

    permission_map: PermissionMap
    rel: Path
    mount_prefix: Path


def check_writable_composed(layers: Iterable[PermissionLayer], op: str) -> Result | None:
    """Gate *op* against every entry layer from ``/`` to the terminal.

    The most restrictive layer wins: the first denial (walking outermost
    to terminal) is returned, so the reported rule is the shallowest one
    that forbids the write.  ``None`` when every layer allows.
    """
    for layer in layers:
        denied = check_writable(layer.permission_map, op, layer.rel, mount_prefix=layer.mount_prefix)
        if denied is not None:
            return denied
    return None


def check_writable(
    permission_map: PermissionMap,
    op: str,
    rel: Path,
    *,
    mount_prefix: Path = ROOT,
) -> Result | None:
    """Return a classified error result if *op* mutates a read-only path.

    *rel* is the gated path in this map's mount-relative coordinates;
    *mount_prefix* is the router-side prefix of the entry the map sits on
    (``/`` for the root entry — the rebase identity).  The error reports
    the reconstructed router-side path — in the message and as the
    structured ``path`` — so the caller sees the path they typed, while
    rule resolution stays in mount-relative coordinates.

    Returns ``None`` when the operation is allowed (either because it
    is not a mutation or because the resolved permission is
    ``"read_write"``); a failure :class:`Result` when the operation
    would mutate a read-only path.

    The error carries ``kind=read_only`` and reports *op* on the failed
    result's ``ops``; :func:`~vfs.exceptions.exception_for_kind`
    maps the kind to :class:`~vfs.exceptions.WriteConflictError` when a
    boundary caller applies ``raise_if_failed``.
    """
    if op not in MUTATING_OPS:
        return None
    first, *rest = _permission_candidates(rel)
    resolved = permission_map._resolve(first)
    for candidate in rest:
        alternate = permission_map._resolve(candidate)
        if alternate.rule_prefix is None:
            continue
        if resolved.rule_prefix is None or len(alternate.rule_prefix) > len(resolved.rule_prefix):
            resolved = alternate
    if resolved.permission == "read_write":
        return None
    full = rel.with_mount(mount_prefix)
    detail = "mount default" if resolved.rule_prefix is None else f"read-only by mount rule '{resolved.rule_prefix}'"
    return Result(
        ops=(op,),
        errors=[
            ResultError(
                kind=VFSErrorKind.read_only,
                message=f"Cannot write to read-only path '{full}' ({detail})",
                path=full,
            )
        ],
    )


def _permission_candidates(rel: str) -> tuple[str, ...]:
    """Return the rule-coordinate candidates for *rel*.

    Projected metadata lives under ``/.vfs`` but should still inherit
    rules declared on the logical source path (for example a writable
    hole at ``/synthesis`` must also allow writes under
    ``/.vfs/synthesis/...``). Keep the canonical metadata path first so
    explicit rules on ``/.vfs/...`` still win by longest-prefix match.
    """
    normalized = normalize_path(rel)
    if normalized.startswith("/.vfs/"):
        alias = normalized[len("/.vfs") :]
        return (normalized, alias or "/")
    return (normalized,)
