"""A :term:`mount` is one storage backend attached at one path. This module holds the mount and where a path lives.

The file system keeps one :class:`Mount` for each path that a storage is attached at, the root included.
``mounts()`` hands the same objects back. The checks a mount change passes before the kernel's table
changes are here too.

```python
for mount in fs.mounts():
    print(mount.path, sorted(mount.caps))
    json.dumps(mount.to_payload())
```
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, NamedTuple, TypedDict

from vfs.ops import GRANT_OPS, READ_OPS
from vfs.paths import METADATA_ROOT, ROOT, Path
from vfs.results import ErrorKind, Result, classified
from vfs.storage import HOLDS, StorageBackend, SupportsHolds, TransportError

if TYPE_CHECKING:
    from collections.abc import Iterable

    from vfs.authority import Authority
    from vfs.ops import Op
    from vfs.permissions import PermissionMap, PermissionsPayload

# ---------------------------------------------------------------------------
# The mount and its payload
# ---------------------------------------------------------------------------


class MountPayload(TypedDict):
    """The JSON form of a :class:`Mount`, which is what :meth:`Mount.to_payload` returns.

    Every value is a string, a boolean, ``None``, or a list or dict of these, so the payload comes back
    unchanged from ``json.dumps`` and ``json.loads``. The storage is named and never carried.
    ``storage_name``, ``storage_type`` and ``description`` stand in for the live object. ``caps`` and
    ``deny_ops`` are sorted lists. ``permissions`` is the payload of the mount's own permission map, or
    ``None`` when the mount has no rules of its own.
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
    """One :term:`mount`, a storage backend attached at a path with the policy its mounter set.

    Every path belongs to exactly one mount, the deepest one at or above it. The file system's own
    storage at ``/`` is an ordinary mount, and it answers when no deeper mount matches.

    Policy lives on the mount and state lives on the storage.

    - ``permissions`` holds rules written relative to the mount. ``None`` means it has no rules of its own.
    - ``deny_ops`` is the set of operations the mounter masked.
    - ``no_overlay`` refuses new mounts beneath this one. The mounts already there keep working, so a
      sealed subtree can lose mounts and never gain one.
    - ``owned`` says that ``close()`` disposes the storage.
    - ``declared_caps`` is what ``storage.capabilities()`` returned when the mount was added, before the
      mask.
    - ``caps`` is what the gate reads. It is computed once, when the mount is built, as
      ``declared_caps - deny_ops``.

    A mount is frozen and is always replaced whole, so ``caps`` cannot drift from the two it is computed
    from.

    A mount holds the live storage object, so it is not JSON-native. :meth:`to_payload` gives the form that is.
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
        """Return this mount as a :class:`MountPayload`, with the storage named in place of the object.

        The storage's ``name`` and ``description`` are read, and both are attributes and not calls.
        No storage I/O runs.
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
# The checks a mount change passes
# ---------------------------------------------------------------------------


def require_storage(storage: object) -> None:
    """Raise ``TypeError`` unless ``storage`` can be mounted, which needs the read verbs and a name."""
    if not isinstance(storage, StorageBackend):
        msg = f"storage must implement the read family (see vfs.storage), got {type(storage).__name__}"
        raise TypeError(msg)


def normalize_mount_path(path: str, *, allow_root: bool = False) -> Path:
    """Return ``path`` as a checked :class:`Path` that may hold a :term:`mount`.

    :class:`Path` does the general work. It makes the path absolute, drops ``.`` and ``..``, strips the
    white space around each segment, and refuses control characters and segments that are too long.
    Spaces inside a segment are kept, as in ``"/My Documents"``. A mount path has two more rules. It is
    never the root unless ``allow_root`` is true, which ``update_mount`` passes because the root is an
    ordinary mount. It never uses the reserved segment ``.vfs``. The call raises ``ValueError`` for a
    path that breaks a rule.
    """
    mount_path = Path(path)
    if mount_path == ROOT and not allow_root:
        msg = "Mount path must not be empty or root"
        raise ValueError(msg)
    meta_segment = METADATA_ROOT.strip("/")
    if meta_segment in mount_path.split("/")[1:]:
        msg = f"Mount path may not use the reserved metadata segment {meta_segment!r}: {path!r}"
        raise ValueError(msg)
    return mount_path


def validate_deny_ops(deny_ops: Iterable[Op]) -> frozenset[Op]:
    """Return ``deny_ops`` as a frozen set, after checking that it masks no read operation.

    A mask applies to every caller alike. Refusing a read is the job of the storage's rights, which
    know who the caller is. Only the known read operations are refused here, so a name the kernel does
    not know can still be masked. The call raises ``ValueError`` that names the read operations. It
    raises ``TypeError`` for a bare string, which would be read as a set of letters.
    """
    if isinstance(deny_ops, (str, bytes)):
        msg = f"deny_ops must be an iterable of op names, not a bare string: {deny_ops!r}"
        raise TypeError(msg)
    mask = frozenset(deny_ops)
    blocked = mask & READ_OPS
    if blocked:
        msg = f"deny_ops may not mask read-family ops: {', '.join(sorted(blocked))}"
        raise ValueError(msg)
    return mask


async def rights_refusal(owner: Mount, mount_path: Path, who: Authority) -> Result | None:
    """Return why ``who`` may not change the :term:`mount` at ``mount_path``, or ``None`` when they may.

    ``owner`` is the mount that stores the mount-point directory. Its storage says, through ``holds``,
    whether ``who`` holds ``read_write`` there. A storage that declares no grant verb keeps no rights
    to go around, so it refuses nobody. A storage that keeps grants and cannot answer refuses with
    ``unsupported``. A storage that cannot be reached refuses with ``backend_unavailable``.
    """
    storage = owner.storage
    if isinstance(storage, SupportsHolds):
        rel = mount_path.without_mount(owner.path)
        try:
            answer = await storage.holds(path=rel, level="read_write", authority=who)
        except TransportError as exc:
            fact = classified(ErrorKind.backend_unavailable, ROOT, detail=f"the transport failed: {exc}")
            answer = Result(ops=(HOLDS,), errors=[fact])
        return None if answer.success else answer.with_mount(owner.path)
    if owner.declared_caps & GRANT_OPS:
        detail = "the storage that holds the mount point keeps grants and cannot say what the caller holds"
        return Result(ops=(HOLDS,), errors=[classified(ErrorKind.unsupported, owner.path, detail=detail)])
    return None


# ---------------------------------------------------------------------------
# Where a path lives
# ---------------------------------------------------------------------------


class Location(NamedTuple):
    """Where a path lives, as ``locate`` reports it. Every field is JSON-native.

    ``mount`` is the path of the :term:`mount` that holds ``path``, the deepest one at or above it.
    ``storage_path`` is the same path as that storage sees it. The last three fields are filled only when
    the storage was asked. ``exists`` and ``kind`` are ``None`` when it was not asked or could not
    answer, and ``note`` then carries its message. Nothing here says whether a verb would accept the path.
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

    ``same_storage`` is the test ``mkedge`` applies before it dispatches. An edge never crosses from one
    :term:`mount` to another. ``reason`` is a sentence for a person that names the first thing in the
    edge's way, and it is never a classified error. ``None`` means nothing was found in the way.
    """

    source: Location
    target: Location
    same_storage: bool
    reason: str | None
