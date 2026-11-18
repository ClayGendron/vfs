"""Mount — one storage backend attached at one path, and its JSON-native form.

The file system keeps one :class:`Mount` for each path a storage is
attached at, the root included, and hands the same objects back from
``mounts()``:

    for mount in fs.mounts():
        print(mount.path, sorted(mount.caps))
        json.dumps(mount.to_payload())
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, NamedTuple, TypedDict

if TYPE_CHECKING:
    from vfs.paths import Path
    from vfs.permissions import PermissionMap, PermissionsPayload
    from vfs.storage import StorageBackend

# ---------------------------------------------------------------------------
# The mount and its payload
# ---------------------------------------------------------------------------


class MountPayload(TypedDict):
    """JSON-native form of a :class:`Mount` — what :meth:`Mount.to_payload` emits.

    Every value is a JSON fixed point (str, bool, None, or lists and dicts
    of these), so the payload survives ``json.dumps``/``loads`` unchanged.
    The storage is named, never carried: *storage_name*, *storage_type*
    and *description* stand in for the live object.  *caps* and *deny_ops*
    are sorted lists; *permissions* is the map's own payload, or ``None``
    when the mount has no rules of its own.
    """

    path: str
    storage_name: str
    storage_type: str
    description: str
    caps: list[str]
    deny_ops: list[str]
    permissions: PermissionsPayload | None
    no_overlay: bool
    owned: bool


@dataclass(frozen=True, slots=True)
class Mount:
    """One :term:`mount`: *storage* attached at *path*, with the policy its mounter set.

    Every path resolves to exactly one mount, the deepest one at or above
    it.  The file system's own storage at ``/`` is an ordinary mount, and
    it is the fallback when no deeper one matches.

    Policy lives on the mount, state lives on the storage: *permissions*
    holds mount-relative rules (``None`` — no rules of its own),
    *deny_ops* is the mounter's op mask, *no_overlay* refuses **new**
    mounts beneath this one (the ones already there keep dispatching, so
    a sealed subtree can shrink but never grow), *owned* says ``close()``
    disposes the storage, and *declared_caps* is the unmasked capability
    snapshot taken from ``storage.capabilities()`` when the mount was
    added.  *caps* — what every gate reads — is computed once, when the
    mount is built, as ``declared_caps - deny_ops``; a mount is frozen and
    is always replaced whole, so the three cannot drift.

    A mount holds the live storage object, so it is not JSON-native;
    :meth:`to_payload` is the form that is.
    """

    path: Path
    storage: StorageBackend
    permissions: PermissionMap | None = None
    deny_ops: frozenset[str] = frozenset()
    no_overlay: bool = False
    owned: bool = True
    declared_caps: frozenset[str] = frozenset()
    caps: frozenset[str] = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "caps", self.declared_caps - self.deny_ops)

    def to_payload(self) -> MountPayload:
        """Serialize to a :class:`MountPayload`, with the storage named in place of the object.

        The one live read is ``description`` (attribute access, not a
        call); everything else is the mount's own fields.  No storage I/O.
        """
        return MountPayload(
            path=str(self.path),
            storage_name=self.storage.name,
            storage_type=type(self.storage).__name__,
            description=self.storage.description,
            caps=sorted(self.caps),
            deny_ops=sorted(self.deny_ops),
            permissions=None if self.permissions is None else self.permissions.to_payload(),
            no_overlay=self.no_overlay,
            owned=self.owned,
        )


# ---------------------------------------------------------------------------
# Where a path lives
# ---------------------------------------------------------------------------


class Location(NamedTuple):
    """Where a path lives, as ``locate`` reports it. Every field is JSON-native.

    *mount* is the path of the :term:`mount` that holds *path*, the
    deepest one at or above it, and *storage_path* is the same path as
    that storage sees it. The last three fields are filled only when the
    storage was asked. ``exists`` and ``kind`` are ``None`` when it was
    not asked or could not answer, and ``note`` then carries its message.
    Nothing here says whether a verb would accept the path.
    """

    path: str
    mount: str
    storage_name: str
    storage_type: str
    storage_path: str
    exists: bool | None = None
    kind: str | None = None
    note: str | None = None


class EdgeLocation(NamedTuple):
    """Where the two ends of an edge live, as ``locate_edge`` reports it.

    ``same_storage`` is the test ``mkedge`` applies before it dispatches.
    An edge never crosses from one :term:`mount` to another. ``reason`` is
    a sentence for a person that names the first thing in the edge's way,
    and it is never a classified error. ``None`` means nothing was found
    in the way.
    """

    source: Location
    target: Location
    same_storage: bool
    reason: str | None
