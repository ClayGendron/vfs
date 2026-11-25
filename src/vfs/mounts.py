"""This module holds the :term:`mount`, the checks a mount change passes, and where a path lives.

A mount is one storage backend attached at one path. The file system keeps one :class:`Mount` for
each path that a storage is attached at, the root included. ``mounts()`` hands the same objects
back. Before the kernel's table changes, a mount change passes the checks here. They judge the path,
the mask, the posture, the caller's rights, the gate, the mount point and the table.
:class:`Location` and :class:`EdgeLocation` say where a path lives. What the listing verbs show at a
mount point is in ``vfs.listing``, which builds on this module.

```python
for mount in fs.mounts():
    print(mount.path, sorted(mount.caps))
    json.dumps(mount.to_payload())
```
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final, NamedTuple, Protocol, TypedDict

from vfs.authority import EVERYONE_NAME, Authority
from vfs.exceptions import MountError
from vfs.ops import FRONT_METHODS, GRANT_OPS, GRANT_WRITE_OPS, READ_OPS, RUNGS
from vfs.paths import METADATA_ROOT, ROOT, Path
from vfs.permissions import check_writable_composed
from vfs.results import ErrorKind, Result, classified
from vfs.results.kinds import TRASHED_KEY, kind_family
from vfs.storage import HOLDS, StorageBackend, SupportsGrants, SupportsHolds, SupportsRead, TransportError

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine, Iterable, Mapping, Sequence, Set

    from vfs.ops import Op
    from vfs.permissions import PermissionLayer, PermissionMap, PermissionsPayload
    from vfs.storage.grants import Posture

# The check of a mount point runs as the system actor, not as any caller.
_SYSTEM_AUTHORITY: Final = Authority.system()

# The ops a mask never refuses: the reads, and grants, which only lists the grant rows.
_UNMASKABLE_OPS: Final[frozenset[Op]] = READ_OPS | (GRANT_OPS - GRANT_WRITE_OPS)

# The methods every mounted storage is called through: the read verbs and capabilities().
_CALLED_MEMBERS: Final = tuple(
    name
    for protocol in (SupportsRead, StorageBackend)
    for name, member in vars(protocol).items()
    if callable(member) and not name.startswith("_")
)

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

    Policy lives on the mount and state lives on the storage. A posture, the level everyone holds, is
    state, so it is not a field here. It is read with ``grants`` at the mount's path.

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
    """Raise ``TypeError`` unless ``storage`` can be mounted, which needs callable read verbs and a name."""
    if not isinstance(storage, StorageBackend):
        msg = f"storage must implement the read family (see vfs.storage), got {type(storage).__name__}"
        raise TypeError(msg)
    flat = [name for name in _CALLED_MEMBERS if not callable(getattr(storage, name))]
    if flat:
        msg = f"storage members must be callable, and these are not: {', '.join(flat)}"
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
    know who the caller is. Only the operations the kernel knows to be reads are refused here: the
    read verbs, and ``grants``, which only lists. So a name the kernel does not know can still be
    masked. A front such as ``cli`` is no mount's operation, and masking it would do nothing, so it
    is refused too: a host turns the shell off through its policy or its tool list. The call raises
    ``ValueError`` that names the refused operations. It raises ``TypeError`` for a bare string,
    which would be read as a set of letters.
    """
    if isinstance(deny_ops, (str, bytes)):
        msg = f"deny_ops must be an iterable of op names, not a bare string: {deny_ops!r}"
        raise TypeError(msg)
    mask = frozenset(deny_ops)
    fronts = mask & FRONT_METHODS
    if fronts:
        msg = f"deny_ops may not mask a front, which is no mount's op: {', '.join(sorted(fronts))}"
        raise ValueError(msg)
    blocked = mask & _UNMASKABLE_OPS
    if blocked:
        msg = f"deny_ops may not mask read-family ops: {', '.join(sorted(blocked))}"
        raise ValueError(msg)
    return mask


def validate_posture(posture: object) -> Posture | None:
    """Return ``posture`` when it is ``None`` or one of the six levels, and raise ``ValueError`` when it is not.

    A posture is the level that everyone holds at a path and below. The levels run from ``none`` to
    ``read_write``, in the order of ``vfs.ops.RUNGS``. A level is a ``str``. A value of another type is
    refused with a message that names its type, even when it compares equal to a level, as
    ``set_posture`` refuses it.
    """
    if posture is None:
        return None
    if not isinstance(posture, str):
        msg = f"posture must be a string, got {type(posture).__name__}"
        raise ValueError(msg)
    for level in RUNGS:
        if posture == level:
            return level
    msg = f"posture must be one of {', '.join(RUNGS)}, or None, got {posture!r}"
    raise ValueError(msg)


def mount_point_owner(mounts: Mapping[Path, Mount], mount_path: Path) -> Mount:
    """Return the :term:`mount` in ``mounts`` that stores the directory at ``mount_path``.

    That is the deepest mount above the path. The root mount stores its own. No storage is asked.
    """
    return mounts[max((p for p in mounts if p == ROOT or mount_path.startswith(p + "/")), key=len)]


class MountJudgement(NamedTuple):
    """What a check of a caller's rights judged, which must still be so when the :term:`mount` change commits.

    ``owner_path`` and ``owner`` are the path and the storage of the mount that holds the mount point,
    and that storage is the one that judged. A storage detached and attached again at another path
    judges another path there, so the path is kept as well as the storage. ``target`` is the storage
    of the mount at the mount point, or ``None`` when there was none.
    """

    owner_path: Path
    owner: StorageBackend
    target: StorageBackend | None

    @classmethod
    def of(cls, mounts: Mapping[Path, Mount], mount_path: Path) -> MountJudgement:
        """Return what ``mounts`` holds at the mount point ``mount_path`` and above it now. No storage is asked."""
        owner = mount_point_owner(mounts, mount_path)
        target = mounts.get(mount_path)
        return cls(owner.path, owner.storage, None if target is None else target.storage)


def require_judgement_stands(
    judged: MountJudgement | None, change: str, mount_path: Path, mounts: Mapping[Path, Mount]
) -> None:
    """Raise ``ValueError`` that asks for a retry when ``mounts`` no longer holds what was ``judged``.

    The :term:`mount` that holds the mount point must be the same storage at the same path. If a mount
    was at the mount point when the rights were judged, the same storage must be mounted there still.
    ``None`` stands for the system actor, who is not judged. ``change`` is the words the error uses. No
    storage is asked, so the caller holds the mount lock and commits with no await in between.
    """
    if judged is None:
        return
    now = MountJudgement.of(mounts, mount_path)
    moved = now.owner_path != judged.owner_path or now.owner is not judged.owner
    replaced = judged.target is not None and now.target is not judged.target
    if moved or replaced:
        msg = f"Cannot {change} {mount_path}: a mount at or above it changed while rights were checked, so retry"
        raise ValueError(msg)


@dataclass(slots=True)
class Removals:
    """The mounts whose ``remove_mount`` is still deleting their directory, and a count of removals by path.

    A mount added at a path reads :meth:`seen` before its site is checked and passes :meth:`refusal` when
    it is committed. A removal of that path that began or ended in between moves the count, and one in
    flight at the commit is in ``inflight``. Either way the site check may have read a directory that the
    removal deletes, so the mount is refused with a retry. ``count`` keeps one integer for each path that
    has lost a mount.
    """

    inflight: dict[Path, Mount] = field(default_factory=dict)
    count: dict[Path, int] = field(default_factory=dict)

    def begin(self, mount: Mount) -> None:
        """Record that the directory of ``mount`` is being deleted."""
        self.inflight[mount.path] = mount
        self.count[mount.path] = self.count.get(mount.path, 0) + 1

    def end(self, path: Path) -> None:
        """Record that the delete of the directory at ``path`` is done, however it ended."""
        if self.inflight.pop(path, None) is not None:
            self.count[path] = self.count.get(path, 0) + 1

    def seen(self, path: Path) -> int:
        """Return the count of removals at ``path``, for :meth:`refusal` to compare at the commit."""
        return self.count.get(path, 0)

    def refusal(self, mount: Mount, seen: int) -> str | None:
        """Return why ``mount``, whose attach read ``seen``, cannot be committed, or ``None`` when it can.

        Its storage object must not be one whose removal is in flight, so that ``close()`` never closes it
        as the storage of the mount being removed.
        """
        path = mount.path
        if path in self.inflight or self.count.get(path, 0) != seen:
            return f"Cannot mount at {path}: a mount there was being removed while this one was checked, so retry"
        leaving = next((gone.path for gone in self.inflight.values() if gone.storage is mount.storage), None)
        if leaving is not None:
            return f"Cannot mount at {path}: that storage object is still being removed from {leaving}, so retry"
        return None

    def drain(self) -> list[Mount]:
        """Return the mounts in flight and forget them, so that a second ``close()`` does not close them again."""
        drained = list(self.inflight.values())
        self.inflight.clear()
        return drained


def require_no_deeper_mount(mount_path: Path, deeper: Sequence[Mount]) -> None:
    """Raise ``ValueError`` when ``deeper``, the mounts beneath ``mount_path``, holds any, and name them.

    A mount is removed only once nothing is mounted beneath it, as ``umount`` asks. The paths are named
    in reverse path order, so a deeper mount is named before one above it.
    """
    if deeper:
        named = ", ".join(sorted((str(mount.path) for mount in deeper), reverse=True))
        msg = f"Cannot unmount {mount_path}: deeper mounts exist at {named}"
        raise ValueError(msg)


def require_gate_allows(
    mounts: Mapping[Path, Mount], layers: Sequence[PermissionLayer], change: str, mount_path: Path, *ops: Op
) -> None:
    """Raise :class:`MountError` when the gate refuses a mount change, as the write it is at its mount point.

    ``ops`` are the writes the change stands for. Attaching a :term:`mount` is a ``mkdir``, detaching
    one is a ``delete``, and changing one in place is both. ``change`` is the words the error uses.
    ``layers`` are the permission maps that govern ``mount_path`` in the table ``mounts``, with the map
    of ``/`` first. The mount-point directory is stored by the mount above ``mount_path``, so that
    mount's capabilities and every permission map above the mount point decide. A mount above that is
    read-only there, or that masks one of ``ops``, keeps its mount table as it is. The mount at
    ``mount_path`` itself has no say. Its map governs what is beneath it and never its own mount
    point. No storage is asked. The caller has already refused a closed kernel. It holds the mount
    lock, or runs no ``await`` between this check and the reservation of the storage object.
    """
    owner = mount_point_owner(mounts, mount_path)
    above = [layer for layer in layers if layer.mount_prefix != mount_path]
    for op in ops:
        refusal = check_writable_composed(above, op)
        if op not in owner.caps:
            detail = f"operation {op!r} is not declared by the storage that holds the mount point"
            refusal = Result(ops=(op,), errors=[classified(ErrorKind.unsupported, owner.path, detail=detail)])
        if refusal is not None:
            msg = f"Cannot {change} {mount_path}: {refusal.error_message}"
            raise MountError(msg, result=refusal)


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


def is_tombstoned_site(result: Result, path: Path) -> bool:
    """Return whether ``result`` was refused because ``path`` itself holds a deleted row.

    That is the one refusal that a ``restore`` can put right.
    """
    error = result.errors[0]
    return error.kind is ErrorKind.not_found and error.path == path and bool((error.data or {}).get(TRASHED_KEY))


def posture_refusal(storage: StorageBackend, declared_caps: frozenset[str], mount_path: Path) -> Result | None:
    """Return why no posture can be set on ``storage`` mounted at ``mount_path``, or ``None`` when one can.

    A storage keeps a posture when ``declared_caps`` holds ``set_posture`` and it has the grant methods.
    The capabilities it declared decide, and the mask of the mount does not. A storage that keeps no
    grants serves every row to every caller, so a closed posture there would look closed and be open.
    """
    if "set_posture" in declared_caps and isinstance(storage, SupportsGrants):
        return None
    detail = "the storage keeps no posture, so add_mount cannot set one"
    return Result(ops=("set_posture",), errors=[classified(ErrorKind.unsupported, mount_path, detail=detail)])


def require_posture_kept(storage: StorageBackend, declared_caps: frozenset[str], mount_path: Path) -> None:
    """Raise :class:`MountError` that carries the refusal of :func:`posture_refusal`, when it refuses."""
    kept = posture_refusal(storage, declared_caps, mount_path)
    if kept is not None:
        msg = f"Cannot mount at {mount_path}: {kept.error_message}"
        raise MountError(msg, result=kept)


class AskStorage(Protocol):
    """The kernel's call on the storage of one :term:`mount`, whose result carries the storage's own paths."""

    def __call__(
        self, mount: Mount, op: Op, *, authority: Authority | None = None, **kwargs: Any
    ) -> Coroutine[Any, Any, Result]:
        """Call ``op`` on the storage of ``mount`` and return its result as the storage gave it."""
        ...


async def mount_site_refusal(ask: AskStorage, owner: Mount | None, mount_path: Path) -> str | None:
    """Return why ``mount_path`` cannot hold a :term:`mount`, or ``None`` when it is an empty directory.

    ``owner`` is the mount that holds the path, or ``None`` when the kernel is closed. Its storage is
    asked to ``stat`` and then to ``ls`` the path, through ``ask`` and as the system actor. This is
    storage I/O, and it runs before the mount lock is taken. On shared storage the answer can change
    before the mount is committed, and the mount then succeeds or fails in the ordinary ways. Only a
    ``not_found`` earns the advice to make the directory. Any other failure is reported as the storage
    gave it, so a dead storage is reported as dead and is not answered with advice that cannot help.
    """
    if owner is None:
        return "filesystem is closed"
    rel = mount_path.without_mount(owner.path)
    advice = f"no directory stored at the mount point (mkdir it, or add_mount(..., parents=True)): {mount_path}"
    stat = await ask(owner, "stat", path=rel, authority=_SYSTEM_AUTHORITY)
    if not stat.success:
        blocker = next((f for f in stat.failures if kind_family(f.kind) is not ErrorKind.not_found), None)
        if blocker is None:
            return advice
        return blocker.message or f"could not stat the mount point: {mount_path}"
    row = next((o for o in stat.observations if o.path == rel), None)
    if row is None:
        return advice
    if row.kind != "directory":
        return f"the mount point is stored as {row.kind!r}, not a directory: {mount_path}"
    listed = await ask(owner, "ls", path=rel, authority=_SYSTEM_AUTHORITY)
    if not listed.success:
        return listed.error_message or f"could not list the mount point: {mount_path}"
    if any(o.path != rel for o in listed.observations):
        return f"the mount-point directory is not empty: {mount_path}"
    return None


async def require_mount_site(ask: AskStorage, owner: Mount | None, mount_path: Path) -> None:
    """Raise ``ValueError`` that gives the reason of :func:`mount_site_refusal`, when it refuses."""
    probed = await mount_site_refusal(ask, owner, mount_path)
    if probed is not None:
        msg = f"Cannot mount at {mount_path}: {probed}"
        raise ValueError(msg)


def mount_table_refusal(
    mounts: Mapping[Path, Mount], deepest_first: Sequence[Path], mount: Mount, reserved: Set[int], kernel: str
) -> str | None:
    """Return why the table ``mounts`` cannot take ``mount``, or ``None`` when it can.

    The path must hold no mount and lie above none. No mount above it, the root included, may be sealed
    with ``no_overlay``. The storage object must be in no other mount, and its ``id`` not in
    ``reserved``, which holds the storages whose posture a call in flight is writing. ``deepest_first``
    is the paths of ``mounts`` in the order the kernel keeps them, a deeper path before one above it.
    The paths are read in that order and not sorted again. ``kernel`` is the name of the kernel's
    class, which a sealed root's refusal names. No storage is asked.
    """
    mount_path = mount.path
    if mount_path in mounts:
        return f"Mount already exists at: {mount_path}"
    for existing in deepest_first:
        if existing.startswith(mount_path + "/"):
            return f"Cannot mount at {mount_path}: a deeper mount already sits at {existing}"
        if existing != ROOT and mount_path.startswith(existing + "/") and mounts[existing].no_overlay:
            return f"Cannot mount at {mount_path}: the mount at {existing} does not allow mounts beneath it"
    if mounts[ROOT].no_overlay:
        return f"{kernel} does not allow child mounts"
    if any(m.storage is mount.storage for m in mounts.values()):
        return f"Cannot mount at {mount_path}: that storage object is already mounted in this table"
    if id(mount.storage) in reserved:
        return f"Cannot mount at {mount_path}: another call is mounting that storage object, so retry"
    return None


def everyone_holds(answer: Result, posture: Posture) -> bool:
    """Return whether ``answer``, a read of the grants at a storage's root, gives everyone ``posture`` there.

    That needs a row for ``*`` at ``/`` whose level is ``posture``. A failed read never does.
    """
    rows = (answer.model_extra or {}).get("grants") if answer.success else None
    return isinstance(rows, list) and any(
        row.get("principal_id") == EVERYONE_NAME and row.get("path_prefix") == ROOT and row.get("level") == posture
        for row in rows
        if isinstance(row, dict)
    )


async def set_mount_posture(
    ask: AskStorage, mount: Mount, posture: Posture, authority: Authority | None, check: Callable[[], None]
) -> None:
    """Set ``posture`` at the root of the storage of ``mount``, as ``authority``, unless it is there already.

    ``mount`` is in no table yet. ``ask`` calls its storage, and gives a call with no authority the
    kernel's default, or else the anonymous caller. If the storage declares ``grants``, the grants at
    its root are read first, and nothing is written when everyone already holds ``posture``. Both calls
    run as the caller, so the storage judges the write as it judges ``set_posture``. The read is never
    made as the system actor, which would tell a caller who holds nothing whether a guess matched.
    ``check`` runs the table checks again, and it is called with no ``await`` before the write. The
    table can change while the grants are read, and a table that no longer takes the mount is then
    refused before the storage is written.

    The call raises :class:`MountError` that carries the storage's refusal, with the mount's path in
    front of its paths. A storage that cannot be reached is refused with ``backend_unavailable``. Any
    other exception is a fault in the storage and is raised as it is. What ``check`` raises is raised
    as it is.
    """
    if "grants" in mount.declared_caps:
        held = await ask(mount, "grants", path=ROOT, authority=authority)
        if everyone_holds(held, posture):
            return
    check()
    answer = await ask(mount, "set_posture", path=ROOT, posture=posture, authority=authority)
    if answer.success:
        return
    refusal = answer.with_mount(mount.path)
    msg = f"Cannot mount at {mount.path}: {refusal.error_message or 'the storage refused the posture'}"
    raise MountError(msg, result=refusal)


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
