"""AsyncVirtualFileSystem is the :term:`kernel` of VFS. It sends each call to the storage that holds the path.

The kernel is the file system that a caller holds. It keeps one table of mounts. A :term:`mount` attaches
a storage backend at a path, and never another kernel. The kernel's own storage is the mount at ``/``.
Every path belongs to exactly one mount, the deepest one at or above it. One kernel is one file tree and
one layer of policy. Linux has the same shape, where a mount names a superblock and the VFS layer exists
once.

```python
fs = AsyncVirtualFileSystem()
await fs.add_mount(InMemoryStorage(), "/data")
await fs.write(path="/data/a.txt", content="hello")
```

The shape of the file tree is stored and never made up. A mount point is an ordinary empty directory,
stored by whichever storage holds the path above it. The mount itself lives only in the table. One kernel
joins another only through storage, as a storage backend that wraps a kernel or reaches one over a wire.
This package ships no such backend yet.

Every public verb takes the same steps.

- It checks its arguments.
- It finds the mount that holds the path.
- It asks the gate. The gate is the two checks the kernel makes before a storage is called. The first is
  the mount's capabilities, which are the operations its storage declares, less the ones its mounter
  masked. The second is every permission map from ``/`` down to the mount. A permission map says which
  paths are read-only, and the most restrictive map wins.
- It calls the storage, through one method.
- On the way out it puts the mount's path back in front of each path, and it drops the rows that a deeper
  mount hides. A listing shows the root of the mounted storage at each mount point.

The gate does not know who is calling. The storage decides who may see or change a row, from the authority
the kernel hands it. A call that names no authority runs as the kernel's default authority, or else as the
anonymous caller.

A verb returns a :class:`~vfs.results.Result` and never raises for a refusal. The refusal is carried on
the result. ``add_mount``, ``remove_mount``, ``update_mount`` and ``close`` manage the table, and they
raise. They are not part of the storage protocol, so no verb that a storage runs can change a mount table.
A mount change still passes the gate, as the write it is at its mount point.

A path enters a public method as a plain ``str``. It is checked once and becomes a
:class:`~vfs.paths.Path`, and everything below carries that type. Any path that a storage method receives
has already been checked.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from contextvars import ContextVar, Token
from dataclasses import replace
from functools import partial
from typing import TYPE_CHECKING, Any, Final, Literal, NamedTuple, assert_never, cast

from pydantic import ValidationError

from vfs.authority import Authority
from vfs.chain import admit_rows_in_hand, glob_rows_in_hand, grep_rows_in_hand, judge_in_hand
from vfs.deadline import WALL_TIME_BUDGET, Deadline
from vfs.exceptions import MountError, raise_lone_or_group
from vfs.fanout import planned_scope, scope_argument
from vfs.listing import MountListing, PathFilters, gather_settled, skip_record
from vfs.models import (
    MEASURE_OFFLOAD_BYTES,
    MEASURED_BODY,
    Edge,
    Entry,
    Observation,
    measure_bytes,
    measure_text,
)
from vfs.mounts import (
    EdgeLocation,
    Location,
    Mount,
    MountJudgement,
    is_tombstoned_site,
    mount_point_owner,
    mount_table_refusal,
    normalize_mount_path,
    require_gate_allows,
    require_judgement_stands,
    require_mount_site,
    require_posture_kept,
    require_storage,
    rights_refusal,
    set_mount_posture,
    validate_deny_ops,
    validate_posture,
)
from vfs.offload import call_offloaded, judge_rows, offload_pool, wall_truncation
from vfs.ops import (
    MUTATING_OPS,
    TRAVERSE_DEPTH_DEFAULT,
    TRAVERSE_LIMIT_DEFAULT,
    CaseMode,
    GrepOutputMode,
    TwoPathOperation,
)
from vfs.params import param_violation
from vfs.paths import (
    ROOT,
    Path,
    check_reserved_path,
    is_trash_path,
    resolve_path,
)
from vfs.pattern_matching import PatternError, compile_gates, expand_channel
from vfs.permissions import (
    Permission,
    PermissionLayer,
    PermissionMap,
    check_writable_composed,
    coerce_permissions,
)
from vfs.rerank import BM25Rerank, Reranker, fanout_depth, merge_ranked
from vfs.results import ErrorKind, Result, ResultError, classified, validation_message
from vfs.results.kinds import Severity
from vfs.session import AsyncSession
from vfs.storage import (
    ResolvedPair,
    StorageBackend,
    SupportsClose,
    SupportsGrants,
    SupportsMutation,
    SupportsPatternSearch,
    SupportsRankedSearch,
    SupportsRun,
    SupportsTraversal,
    TransportError,
)
from vfs.storage.backends.memory import InMemoryStorage
from vfs.storage.replace import EditOperation

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine, Mapping, Sequence

    from vfs.fanout import ScopePlan
    from vfs.ops import Op
    from vfs.paths import ObjectKind, ResolvedPath
    from vfs.pattern_matching import GlobGates
    from vfs.storage.grants import GrantLevel, Posture

# How many more kernels the current request may enter. One is spent per
# kernel entered and never per mount.
_hop_budget: ContextVar[int | None] = ContextVar("vfs_hop_budget", default=None)

# Single-path mutations whose addressed site the EBUSY guard protects:
# delete removes it, restore lands on it, sweep destroys beneath it.
_BUSY_GUARDED_OPS: frozenset[Op] = frozenset({"delete", "restore", "sweep"})

# The kernel's own storage calls for a mount change (the mount-point check
# and the delete of its directory) run as the system actor, not as any caller.
_ADMIN_AUTHORITY: Final = Authority.system()

# The truncation advice of a fan-out's glob stages: its root probe and
# admissions, and its planning walk.
_SCOPED_REFINE_GUIDANCE: Final = "narrow the patterns, or scope with fewer paths"
_PLANNING_REFINE_GUIDANCE: Final = "scope with fewer paths, or send fewer patterns or brace arms"

# The grant verbs that change membership rows: mount-wide, so they carry no path.
_MEMBERSHIP_OPS: frozenset[Op] = frozenset({"add_member", "remove_member"})

# A call that names nobody runs as the named nobody: it holds only what a
# mount's posture gives everyone, and the audit still has an actor.
_ANONYMOUS_AUTHORITY: Final = Authority.anonymous()


class ResolvedTerminal(NamedTuple):
    """Where a path landed, as the :term:`mount` that holds it and the path inside that mount.

    ``mount`` is the mount that holds the path. ``rel`` is the same path as that mount's storage sees
    it, which is ``without_mount(mount.path)``.
    """

    mount: Mount
    rel: Path

    @property
    def full(self) -> Path:
        """The path as the kernel sees it, with the mount's path in front."""
        return self.rel.with_mount(self.mount.path)


class _HopGrant(NamedTuple):
    """Whether one more hop is allowed. Exactly one of ``token`` and ``refusal`` is set.

    ``token`` gives the caller its budget back on exit, through ``_exit_hop``. ``refusal`` is the
    ``budget_exhausted`` result.
    """

    token: Token[int | None] | None
    refusal: Result | None


class _Ranked(NamedTuple):
    """What ``search`` needs to merge several mounts. It holds the query, the caller's limit, and how deep to ask."""

    query: str
    limit: int
    depth: int


class _FanoutPlan(NamedTuple):
    """The plan of one call that reaches several mounts. It is built once and only read.

    ``scoped`` maps a mount's path to the :term:`mount` and the paths the caller named inside it.
    ``unscoped`` holds the mounts that are asked whole. ``skips`` records each mount that cannot answer
    the verb. They are added after the merge, so a skipped mount never lowers another mount's answer.
    ``refusal`` is the only way a failure travels. When it is set, the collections are empty and the
    caller returns it. The plan holds results only, and the inputs stay arguments.
    """

    scoped: dict[Path, tuple[Mount, list[Path]]]
    unscoped: dict[Path, Mount]
    skips: list[ResultError]
    refusal: Result | None = None


class _Dispatches(NamedTuple):
    """The calls built for one ``glob`` or ``grep`` over several mounts.

    It holds the probes of the roots, one call for each mount, and the records of the mounts that were skipped.
    ``settle`` takes the answers of the probes and of the mounts, and returns the answers of the probes to merge.
    """

    probes: list[Coroutine[Any, Any, Result]]
    branches: list[tuple[Path, Coroutine[Any, Any, Result]]]
    skips: list[ResultError]
    settle: Callable[[list[Result], list[tuple[Path, Result]]], Coroutine[Any, Any, list[Result]]] | None = None


async def _authored_entry(path: Path, content: str | None, data: bytes | None) -> Entry:
    """Build the :term:`entry` that a write to one path makes.

    A small body is hashed in place by the model's own validator, because the hash costs less than a hop
    to another thread. A body at or past ``MEASURE_OFFLOAD_BYTES`` is measured on the process pool first
    and handed to the validator already measured. One caller's 16 MB write then never stalls every other
    coroutine for the length of a SHA-256.
    """
    body: str | bytes | None = data if data is not None else content
    if body is None or len(body) < MEASURE_OFFLOAD_BYTES:
        return Entry(path=str(path), content=content, data=data)
    if isinstance(body, bytes):
        metrics = await call_offloaded(offload_pool(), partial(measure_bytes, body))
    else:
        metrics = await call_offloaded(offload_pool(), partial(measure_text, body))
    return Entry.model_validate({"path": str(path), "content": content, "data": data}, context={MEASURED_BODY: metrics})


def _rebase_grant_rows(result: Result, mount: Path) -> Result:
    """Return ``result`` with the mount's path put in front of the prefix of each ``grants=`` row.

    Grant rows travel as an extra field, which the usual step that restores paths does not reach. A
    prefix that is not a valid path is left as the storage sent it.
    """
    rows = (result.model_extra or {}).get("grants")
    if mount == ROOT or not isinstance(rows, list):
        return result
    rebased: list[object] = []
    for row in rows:
        prefix = row.get("path_prefix") if isinstance(row, dict) else None
        local = resolve_path(prefix).path if isinstance(prefix, str) else None
        rebased.append(row if local is None else {**row, "path_prefix": str(local.with_mount(mount))})
    return result.model_copy(update={"grants": rebased})


class AsyncVirtualFileSystem:
    """The :term:`kernel` of VFS, with calls you ``await``.

    ``VirtualFileSystem`` is the same kernel with plain calls.

    ``storage`` is the storage of the root :term:`mount`. With none, the kernel makes an
    :class:`InMemoryStorage`. The kernel owns its root storage and closes it. ``permissions``,
    ``deny_ops`` and ``no_overlay`` are the policy of the root mount, as :meth:`add_mount` takes them.
    ``name``, ``title`` and ``description`` say what this kernel is, and the kernel only keeps them.
    ``hop_budget`` is how many kernels one call may pass through before it is refused with
    ``budget_exhausted``. ``close_timeout`` is how many seconds ``close()`` waits for each storage.
    ``rerankers`` are the stages that ``search`` runs, in order, over the results of several mounts.
    ``default_authority`` is the caller for a call that names none. Without it, such a call runs as the
    anonymous caller.

    A ``storage`` that cannot be read, or a reranker with no ``rerank`` method, raises ``TypeError``. A
    ``deny_ops`` that masks a read operation raises ``ValueError``.

    Every verb takes ``authority``, which names the caller. With none, the caller is
    ``default_authority``, or else the anonymous caller. Every verb returns a :class:`Result` and never
    raises for a refusal. The refusal is carried on the result, with the path it concerns. Any verb can
    be refused in these ways.

    - ``invalid`` means an argument or a path is wrong, and the caller can fix it.
    - ``unsupported`` means the storage of the mount does not declare the verb, or its mounter masked it.
    - ``unauthenticated`` means the mount gives an unnamed caller nothing there, so the call needs an
      authority.
    - ``not_found`` means the path holds nothing, or nothing the caller may see.
    - ``permission_denied`` means the caller is known and may see the path, and may not do this to it.
    - ``backend_unavailable`` means the storage could not be reached, or the kernel is closed.

    A verb that changes something can also be refused with ``read_only``, when a permission map forbids
    the change whoever the caller is.
    """

    def __init__(
        self,
        *,
        name: str | None = None,
        title: str | None = None,
        description: str | None = None,
        storage: StorageBackend | None = None,
        permissions: Permission | PermissionMap = "read_write",
        deny_ops: Iterable[Op] = (),
        no_overlay: bool = False,
        hop_budget: int = 16,
        close_timeout: float = 10.0,
        rerankers: Iterable[Reranker] = (BM25Rerank(),),
        default_authority: Authority | None = None,
    ) -> None:
        if storage is None:
            storage = InMemoryStorage()
        require_storage(storage)
        self._rerankers = tuple(rerankers)
        for stage in self._rerankers:
            if not isinstance(stage, Reranker):
                msg = f"rerankers must implement rerank(query, candidates, *, limit), got {type(stage).__name__}"
                raise TypeError(msg)
        self.name = name
        self.title = title
        self.description = description
        self._hop_budget_default = hop_budget
        self._close_timeout = close_timeout
        self._default_authority = default_authority
        self._mount_lock = asyncio.Lock()
        self._posture_writes: set[int] = set()
        self._stranded_disposals: dict[int, StorageBackend] = {}
        root = Mount(
            path=ROOT,
            storage=storage,
            permissions=coerce_permissions(permissions),
            deny_ops=validate_deny_ops(deny_ops),
            no_overlay=no_overlay,
            owned=True,
            declared_caps=frozenset(storage.capabilities()),
        )
        self._mounts: dict[Path, Mount] = {ROOT: root}
        self._rebuild_sorted_mounts()
        self._class_name = self.__class__.__name__

    # -------------------------------------------------------------------
    # mount administration
    # -------------------------------------------------------------------

    async def add_mount(
        self,
        storage: StorageBackend,
        path: str | None = None,
        *,
        parents: bool = False,
        permissions: Permission | PermissionMap | None = None,
        posture: Posture | None = None,
        deny_ops: Iterable[Op] = (),
        no_overlay: bool = False,
        owned: bool = True,
        authority: Authority | None = None,
    ) -> None:
        """Attach ``storage`` at ``path`` as a :term:`mount`.

        The mount point is an empty directory in the storage that holds the path above it. If it is
        absent, it is made by the caller's own ``mkdir``, so a caller who may not make the directory may
        not mount there. Its parents must exist unless ``parents`` is true. If it exists and is empty, it
        is used as it is, which is how a mount is added again after a restart. If a removed mount deleted
        it, it is restored. The mount itself lives only in the kernel's table, and nothing about it is stored.

        If ``path`` is omitted, the storage's ``name`` names the mount point, so
        ``add_mount(InMemoryStorage(name="data"))`` mounts at ``/data``. ``permissions`` sets rules
        written relative to the mount. ``deny_ops`` masks operations out of the mount's capabilities. An
        operation that changes or runs something can be masked, and a read operation cannot.
        ``no_overlay`` refuses later mounts beneath this one. ``owned`` says that ``close()`` disposes
        this storage.

        ``posture`` is the level that everyone holds at the root of ``storage`` and below, as
        :meth:`set_posture` sets it. If ``posture`` is ``None``, the storage is asked nothing and keeps the
        posture it holds, and a new storage gives everyone ``read_write``. If ``posture`` is given, it is in
        force before the mount can be reached, so no caller meets the mount under another posture. The
        kernel sets it as the caller, who must hold ``read_write`` at the root of the storage, as everyone
        does in a new storage. It first reads the grants at the root, and writes nothing when everyone
        holds ``posture`` there. It writes when the storage holds another level, when it does not declare
        ``grants``, and when the read fails. The postures set deeper in the storage are kept, and so are
        its grants. The mask in ``deny_ops`` and the mount's own ``permissions`` do not stop it. The
        caller gets no grant in the storage. After the storage is asked the mount point is checked again.

        ``authority`` names the caller. With none, the caller is the kernel's default authority, or
        else the anonymous caller. The caller must hold ``read_write`` at the mount point, and the
        storage that holds the mount point says whether it does. A mount is also a write at its mount
        point, so the gate must allow a ``mkdir`` there, even when the directory already exists.

        The call returns nothing. It raises :class:`MountError`, which carries the refusal, in these cases.

        - The caller does not hold ``read_write`` at the mount point.
        - The mount above is read-only there, or its storage or mask does not allow ``mkdir``.
        - The directory cannot be made, or the path holds a file.
        - ``posture`` is given and ``storage`` declares no ``set_posture`` or lacks the grant methods.
          Nothing has been made.
        - The storage refuses the posture, or cannot be reached. The directory stays and the mount is not added.

        It raises ``ValueError`` when ``posture`` is not a level, when the directory is not empty, when
        the path already has a mount, when it lies beneath a ``no_overlay`` mount, when it would lie above
        a deeper mount, when ``storage`` is already mounted somewhere else in this table, and when another
        call is mounting the same storage object. One storage object has one path. It also raises
        ``ValueError`` when a mount above was added or removed while the caller's rights were checked,
        because they were judged for a place that has changed. Retry in that case. It raises
        ``TypeError`` when ``storage`` cannot be read, before anything is made. If the call fails after
        the directory was made, the directory stays. A plain empty directory is a valid mount point for
        later. If the call fails after the posture was set, the posture stays.
        """
        require_storage(storage)
        mount_name = path or storage.name
        if not mount_name:
            msg = "add_mount needs a path or a named storage"
            raise ValueError(msg)
        mount_path = normalize_mount_path(mount_name)
        # Validated before the mkdir, so a rejected mask or posture leaves no directory behind.
        mask = validate_deny_ops(deny_ops)
        posture = validate_posture(posture)
        if posture is not None:
            require_posture_kept(storage, frozenset(storage.capabilities()), mount_path)
        judge = await self._require_mount_rights("mount at", mount_path, authority)

        made = await self.mkdir(str(mount_path), parents=parents, exist_ok=True, authority=authority)
        if not made.success and is_tombstoned_site(made, mount_path):
            made = await self.restore(str(mount_path), authority=authority)
        if not made.success:
            detail = made.error_message or "storage refused the mount-point directory"
            msg = f"Cannot mount at {mount_path}: {detail}"
            raise MountError(msg, result=made)
        await self._attach_mount(
            storage,
            str(mount_path),
            permissions=permissions,
            posture=posture,
            deny_ops=mask,
            no_overlay=no_overlay,
            owned=owned,
            judged=judge,
            authority=authority,
        )

    async def remove_mount(self, path: str, *, authority: Authority | None = None) -> Mount:
        """Detach the :term:`mount` at ``path``, delete its directory, and return the mount.

        The mount is dropped from the kernel's table first. Then the mount-point directory is deleted
        in the storage that holds the path above it. The delete never cascades. The empty directory goes
        to the trash like any deleted row, and retention reclaims it. Removing a mount does not close
        its storage. The returned mount carries the storage, so the caller can close the one it owns.

        ``authority`` names the caller, as for :meth:`add_mount`. The caller must hold ``read_write``
        at the mount point. Removing a mount is also a write at its mount point, so the gate must allow
        a ``delete`` there. The mount's own permissions have no say in that.

        The call raises :class:`MountError`, which carries the refusal, when the caller lacks
        ``read_write`` or the gate refuses the ``delete``. Nothing has changed at that point, and the
        mount stays. It raises ``ValueError`` when ``path`` has no mount, and while deeper mounts still
        lie beneath it. Remove the deepest first, as ``umount`` does. It also raises ``ValueError``, and
        the mount stays, when a mount at or above ``path`` changed while the rights were checked. Retry.

        If the directory cannot be deleted, the call raises :class:`MountError` and the mount stays
        removed. This happens when the directory has gained rows that this kernel never saw, on shared
        or persistent storage, and removing a mount must not destroy them. The file tree keeps a plain
        directory, which is easy to see and to recover from.
        """
        mount_path = normalize_mount_path(path)
        self._require_mount(mount_path)
        judged = await self._require_mount_rights("unmount", mount_path, authority)
        mount = await self._detach_mount(str(mount_path), judged=judged)
        removed = await self.delete(path=str(mount_path), cascade=False, authority=_ADMIN_AUTHORITY)
        if not removed.success:
            detail = removed.error_message or "storage refused the delete"
            msg = f"Unmounted {mount_path}, but removing its directory failed: {detail}"
            raise MountError(msg, result=removed)
        return mount

    async def update_mount(
        self,
        path: str,
        *,
        permissions: Permission | PermissionMap | None = None,
        deny_ops: Iterable[Op] | None = None,
        no_overlay: bool | None = None,
        refresh_caps: bool = False,
        authority: Authority | None = None,
    ) -> None:
        """Change the policy of the :term:`mount` at ``path`` in place.

        The mount is replaced with a new one, so at no moment does the path have no mount. The root is
        an ordinary mount, and ``update_mount("/")`` is how the whole file tree is tightened.

        ``None`` means "leave unchanged" for ``permissions``, ``deny_ops`` and ``no_overlay``. So
        ``deny_ops=()`` clears the mask and ``deny_ops=None`` keeps it. A call that changes nothing does
        nothing and is not an error.

        If ``permissions`` loosens the mount, the maps of the mounts above still gate every path beneath
        them and the most restrictive one wins. The call can never allow more than the mounts above
        allow. If ``deny_ops`` is replaced or cleared, the capabilities are computed again from the set
        the storage declared, so operations that were masked come back without asking the storage. If
        ``no_overlay`` is true, the mount is sealed for the future only. The deeper mounts that exist
        stay and keep working, and only new mounts beneath this one are refused. Removing a mount never
        reads the flag, so a sealed subtree can lose mounts and never gain one. If ``refresh_caps`` is
        true, ``storage.capabilities()`` is read again, for a storage whose set changed after it was
        mounted. Apart from the check of the caller's rights, it is the only call made to a storage.

        ``authority`` names the caller, as for :meth:`add_mount`. The caller must hold ``read_write``
        at the mount point. The storage of ``/`` judges for the root mount. The gate is then asked for a
        ``delete`` and a ``mkdir`` at the mount point and for nothing more. That is less than a remove
        and an add would ask, so a mount beneath a ``no_overlay`` mount can be changed in place. The root
        has no mount above it, and the gate is not asked for it.

        The call returns nothing. It raises :class:`MountError`, which carries the refusal, when the
        caller lacks ``read_write`` or the gate refuses. It raises ``ValueError`` when ``path`` has no mount, when
        ``deny_ops`` masks a read operation, and when a mount at or above ``path`` changed while the rights
        were checked or ``refresh_caps`` was reading. Retry in that case. Nothing has changed in any of these cases.
        """
        mount_path = normalize_mount_path(path, allow_root=True)
        mask = None if deny_ops is None else validate_deny_ops(deny_ops)
        new_map = None if permissions is None else coerce_permissions(permissions)
        current = self._require_mount(mount_path)
        judged = await self._require_mount_rights("update the mount at", mount_path, authority)
        # The one call to the mount's storage, taken before the lock is acquired.
        fresh_caps = frozenset(current.storage.capabilities()) if refresh_caps else None

        async with self._mount_lock:
            mount = self._require_mount(mount_path)
            if refresh_caps and mount.storage is not current.storage:
                msg = f"Mount at {mount_path} changed while it was being updated — retry"
                raise ValueError(msg)
            require_judgement_stands(judged, "update the mount at", mount_path, self._mounts)
            # The root has no mount above it, so nothing above can refuse a change to it.
            if mount_path != ROOT:
                layers = self._permission_layers(mount_path)
                require_gate_allows(self._mounts, layers, "update the mount at", mount_path, "delete", "mkdir")
            self._mounts[mount_path] = replace(
                mount,
                permissions=mount.permissions if new_map is None else new_map,
                deny_ops=mount.deny_ops if mask is None else mask,
                no_overlay=mount.no_overlay if no_overlay is None else no_overlay,
                declared_caps=mount.declared_caps if fresh_caps is None else fresh_caps,
            )
            self._rebuild_sorted_mounts()

    async def close(self) -> None:
        """Release every resource this process holds for the file tree.

        The mount table is emptied first, so every later verb is refused as closed. Each storage that a
        :term:`mount` owns and that has a ``close`` is then closed once, however many mounts hold the
        same object. The storages are closed at the same time, each within ``close_timeout`` seconds.
        A storage that speaks to a remote kernel may end its own sessions there, which is a message
        over the wire. Closing never changes the mount table of a remote kernel.

        The call returns nothing. If one storage fails to close, the others are still closed and the
        error is raised at the end. Several errors are raised together as a group. A storage that was
        not closed because the call was cancelled is kept, and ``SupportsClose`` promises that closing
        twice is safe. So a second ``close()`` after a cancelled one finishes the job.
        """
        async with self._mount_lock:
            mounts = list(self._mounts.values())
            self._mounts = {}
            self._rebuild_sorted_mounts()

        targets = dict(self._stranded_disposals)
        for mount in mounts:
            if mount.owned and isinstance(mount.storage, SupportsClose):
                targets.setdefault(id(mount.storage), mount.storage)
        # Parked before disposal so a cancelled gather leaves the snapshot
        # reachable — the retry drains it instead of leaking the engines.
        self._stranded_disposals = targets
        if not targets:
            return

        async def _close_one(storage: StorageBackend) -> None:
            assert isinstance(storage, SupportsClose)
            await asyncio.wait_for(storage.close(), timeout=self._close_timeout)

        settled = await asyncio.gather(*(_close_one(s) for s in targets.values()), return_exceptions=True)
        self._stranded_disposals = {}
        errors = [item for item in settled if isinstance(item, Exception)]
        for item in settled:
            if isinstance(item, BaseException) and not isinstance(item, Exception):
                raise item
        raise_lone_or_group(errors, "errors while closing storages")

    def mounts(self) -> tuple[Mount, ...]:
        """Return every :term:`mount` in the table, in path order.

        The mount at ``/`` comes first. A closed kernel returns ``()``. No storage is asked anything. A
        mount is frozen, so what is returned is what the gate reads, and it cannot go out of step.
        :meth:`Mount.to_payload` gives the JSON-native form of a mount.

        The tuple is enough to build the same table again. Each mount carries its storage and the policy
        its mounter set, which is ``permissions``, ``deny_ops``, ``no_overlay`` and ``owned``. Give the
        root mount's storage to the constructor. Add every other mount bare through :meth:`add_mount`.
        Then set each mount's policy last, through :meth:`update_mount`. A mount that is read-only,
        that masks ``mkdir`` or that is sealed with ``no_overlay`` refuses new mounts beneath it. So a
        table that was tightened after its mounts were added cannot be rebuilt with the policy passed
        to ``add_mount``.
        """
        return tuple(self._mounts[mount_path] for mount_path in sorted(self._mounts))

    async def locate(self, path: str, *, exists: bool = False, authority: Authority | None = None) -> Location:
        """Return where ``path`` lives, as the :term:`mount` that holds it and the path inside that mount.

        The deepest mount at or above the path holds it, and the root mount holds a path that no deeper
        mount does. A path that is not in its normal form is put into it.

        If ``exists`` is false, no storage is asked anything. Permissions and capabilities are never
        read, so the answer does not depend on who asks. If ``exists`` is true, the storage that holds
        the path is asked to ``stat`` it directly, past the gate, as ``authority``. That is the
        authority a ``stat`` would run as, so a row the caller cannot see reads as absent and nothing
        leaks.

        The call returns a :class:`Location`. With ``exists``, it carries ``exists`` and ``kind``, or
        ``note`` when the storage could not answer. The call raises ``ValueError`` for a path that is
        not valid, as :class:`Path` does, and for a closed kernel.
        """
        terminal = self._locate_terminal(path)
        mount = terminal.mount
        row = Location(
            path=str(terminal.full),
            mount=str(mount.path),
            storage_name=mount.storage.name,
            storage_type=type(mount.storage).__name__,
            storage_path=str(terminal.rel),
        )
        return await self._probe_location(terminal, row, self._admitted(authority)) if exists else row

    async def locate_edge(
        self, source: str, target: str, *, exists: bool = False, authority: Authority | None = None
    ) -> EdgeLocation:
        """Return where the two ends of an edge live, and whether one storage holds both.

        This is :meth:`locate` for ``source`` and for ``target``, and the answer ``mkedge`` would reach.
        An edge never crosses from one :term:`mount` to another, so ``same_storage`` says whether the
        two mounts are one.

        The call returns an :class:`EdgeLocation`. Its ``reason`` names the first thing in the way. That
        is the two mounts being different, or with ``exists`` an end that the storage does not hold.
        The result is an answer and never a refusal. The call raises ``ValueError`` as :meth:`locate`
        does.
        """
        src = await self.locate(source, exists=exists, authority=authority)
        tgt = await self.locate(target, exists=exists, authority=authority)
        same = src.mount == tgt.mount
        reason = None
        if not same:
            reason = (
                f"an edge cannot cross a mount boundary; the source lives on {src.mount} and the target on {tgt.mount}"
            )
        elif src.exists is False:
            reason = f"the source does not exist: {src.path}"
        elif tgt.exists is False:
            reason = f"the target does not exist: {tgt.path}"
        return EdgeLocation(source=src, target=tgt, same_storage=same, reason=reason)

    def open_session(self, authority: Authority) -> AsyncSession:
        """Open a session, which is the kernel's verbs for one caller.

        Every verb of the session is the same call on the :term:`kernel` with ``authority`` filled in,
        so a result through a session equals the direct one. The call returns a new
        :class:`AsyncSession` each time. Use it with ``async with`` or close it yourself. A closed
        session stays closed.
        """
        return AsyncSession(self, authority)

    def capabilities(self) -> frozenset[str]:
        """Return the operations this kernel can answer, which is every capability of every :term:`mount`.

        The set of a mount is what its storage declared when it was mounted, less the operations its
        mounter masked. Nothing is worked out from the methods a storage happens to have. A storage that
        wraps a kernel, in this process or over a wire, declares the set of the kernel it wraps.
        """
        caps: set[str] = set()
        for mount in self._mounts.values():
            caps |= mount.caps
        return frozenset(caps)

    async def _attach_mount(
        self,
        storage: StorageBackend,
        path: str,
        *,
        permissions: Permission | PermissionMap | None = None,
        posture: Posture | None = None,
        deny_ops: Iterable[Op] = (),
        no_overlay: bool = False,
        owned: bool = True,
        judged: MountJudgement | None = None,
        authority: Authority | None = None,
    ) -> None:
        """Commit a :term:`mount` of ``storage`` at ``path``, on a directory that already exists.

        The mount point must be an empty directory in the storage that holds the path above it. That
        is what lets a mount be added again after a restart on a persistent storage. It also makes a
        mount-point directory that a crash left behind a valid mount point, and not damage.
        :meth:`add_mount` says what is refused and what is raised.

        The gate is asked here and not left to the caller's ``mkdir``, so no way to a mount goes around
        it. The check of the mount point is storage I/O and runs before the mount lock is taken. Under
        the lock the table is checked again, the gate is asked and the mount is committed, with no
        await in between. ``judged`` is what the check of the caller's rights judged. If the mount that
        holds the mount point is no longer the same storage at the same path, the call raises
        ``ValueError`` and the caller retries.

        If ``posture`` is given, it is set as ``authority`` after the check of the mount point and before
        the lock is taken. The table is checked before the grants are read, just before the write, and
        under the lock, and no other call may mount ``storage`` while the write runs. A read or a write
        can take as long as a relabel, so after them the table and the mount point are checked again,
        written or not. The window before the commit is then as narrow as it is with no posture.
        """
        require_storage(storage)
        mount_path = normalize_mount_path(path)
        mask = validate_deny_ops(deny_ops)
        posture = validate_posture(posture)
        await require_mount_site(self._call_storage, self._match_mount(mount_path), mount_path)

        mount = Mount(
            path=mount_path,
            storage=storage,
            permissions=None if permissions is None else coerce_permissions(permissions),
            deny_ops=mask,
            no_overlay=no_overlay,
            owned=owned,
            declared_caps=frozenset(storage.capabilities()),
        )
        if posture is not None:
            require_posture_kept(storage, mount.declared_caps, mount_path)
            # Checked and reserved with no await between, so no other call mounts the storage during the write.
            self._check_mount_table(mount, judged)
            self._posture_writes.add(id(storage))
        try:
            if posture is not None:
                recheck = partial(self._check_mount_table, mount, judged, reserved_here=True)
                await set_mount_posture(self._call_storage, mount, posture, authority, recheck)
                recheck()
                await require_mount_site(self._call_storage, self._match_mount(mount_path), mount_path)
            async with self._mount_lock:
                self._check_mount_table(mount, judged, reserved_here=posture is not None)
                self._mounts[mount_path] = mount
                self._rebuild_sorted_mounts()
        finally:
            if posture is not None:
                self._posture_writes.discard(id(storage))

    async def _detach_mount(self, path: str, *, judged: MountJudgement | None = None) -> Mount:
        """Drop the :term:`mount` at ``path`` from the table and return it. Its directory stays.

        Only the table changes and no storage is asked, so the call succeeds even when a storage is
        dead or stuck. It raises ``ValueError`` when ``path`` has no mount, while deeper mounts lie
        beneath it, and when the table no longer holds what ``judged`` saw. It raises :class:`MountError`
        when the gate would refuse a ``delete`` of the mount-point directory.
        """
        mount_path = normalize_mount_path(path)
        async with self._mount_lock:
            mount = self._require_mount(mount_path)
            require_judgement_stands(judged, "unmount", mount_path, self._mounts)
            deeper = [p for p in self._sorted_mount_paths if p.startswith(mount_path + "/")]
            if deeper:
                msg = f"Cannot unmount {mount_path}: deeper mounts exist at {', '.join(map(str, deeper))}"
                raise ValueError(msg)
            require_gate_allows(self._mounts, self._permission_layers(mount_path), "unmount", mount_path, "delete")
            del self._mounts[mount_path]
            self._rebuild_sorted_mounts()
            return mount

    def _check_mount_table(self, mount: Mount, judged: MountJudgement | None, *, reserved_here: bool = False) -> None:
        """Raise unless the table can take ``mount`` now. No storage is asked.

        The call raises ``ValueError`` for a closed kernel, and then for a judgement in ``judged`` that no
        longer stands. It then asks the gate, which raises :class:`MountError`. Last, it raises
        ``ValueError`` when the table cannot take the mount. A call that breaks two rules meets the first.
        ``reserved_here`` says that this call holds the reservation of the storage object, which then
        does not count against it.
        """
        if not self._mounts:
            msg = f"Cannot mount at {mount.path}: filesystem is closed"
            raise ValueError(msg)
        require_judgement_stands(judged, "mount at", mount.path, self._mounts)
        require_gate_allows(self._mounts, self._permission_layers(mount.path), "mount at", mount.path, "mkdir")
        held = self._posture_writes - {id(mount.storage)} if reserved_here else self._posture_writes
        refusal = mount_table_refusal(self._mounts, self._sorted_mount_paths, mount, held, self._class_name)
        if refusal is not None:
            raise ValueError(refusal)

    def _rebuild_sorted_mounts(self) -> None:
        """Sort the mount paths again, so that a deeper path comes before a path above it.

        The reverse order of the strings is enough. Only the paths that match one target need an order
        among themselves, and those always lie one above another. The path above sorts lower, so it
        comes later. ``/`` comes last and matches when nothing deeper does. What the listing verbs
        show at the mount points is worked out again, from a copy of the same table.
        """
        self._sorted_mount_paths: list[Path] = sorted(self._mounts.keys(), reverse=True)
        self._listing = MountListing(self._mounts)

    # -------------------------------------------------------------------
    # public methods — reads
    # -------------------------------------------------------------------

    async def read(
        self,
        path: str | None = None,
        observations: list[Observation] | None = None,
        *,
        columns: frozenset[str] | None = None,
        authority: Authority | None = None,
    ) -> Result:
        """Read the content of one file, or of each file in ``observations``.

        Pass ``path``, or pass ``observations`` from an earlier result, and never both. Each row of
        ``observations`` goes to the :term:`mount` that holds its path, and the mounts are asked at the
        same time. ``columns`` names the fields of an observation to return. With none, the verb's
        usual fields are returned.

        The call returns a :class:`Result` with an observation for each file that was read. A path that holds
        nothing, or nothing the caller may see, is refused with ``not_found``. A directory is ``wrong_kind``.
        """
        refusal = self._gate_params("read", path=path, observations=observations, columns=columns, authority=authority)
        if refusal is not None:
            return refusal
        return await self._route_single("read", path, observations, columns=columns, authority=authority)

    async def stat(
        self,
        path: str | None = None,
        observations: list[Observation] | None = None,
        *,
        columns: frozenset[str] | None = None,
        authority: Authority | None = None,
    ) -> Result:
        """Return what is stored about one :term:`entry`, or about each row in ``observations``.

        The arguments are those of :meth:`read`. The call returns a :class:`Result` with one
        observation for each entry. A path that holds nothing, or nothing the caller may see, is
        refused with ``not_found``. A directory that lies above a :term:`mount` is never refused so.
        A caller who holds nothing on it gets a bare row, with only ``path`` and ``kind``. The call is
        refused with ``budget_exhausted`` when it has passed through more kernels than ``hop_budget``
        allows, as :meth:`ls` and :meth:`tree` are.
        """
        refusal = self._gate_params("stat", path=path, observations=observations, columns=columns, authority=authority)
        if refusal is not None:
            return refusal
        return await self._route_single("stat", path, observations, columns=columns, authority=authority)

    async def ls(
        self,
        path: str | None = None,
        observations: list[Observation] | None = None,
        *,
        columns: frozenset[str] | None = None,
        authority: Authority | None = None,
    ) -> Result:
        """List what is directly inside one directory, or inside each directory in ``observations``.

        The arguments are those of :meth:`read`. The call returns a :class:`Result` with one
        observation for each :term:`entry` in the directory that the caller may see. A path that holds
        nothing, or nothing the caller may see, is refused with ``not_found``.

        A :term:`mount` in the directory shows as the root of its storage, which is the row ``stat``
        of its path returns. Its name is never hidden. A caller who holds nothing in the mount sees a
        bare row, with only ``path`` and ``kind``. A mount whose storage fails also shows bare, and a
        warning names it. A directory that leads to a mount always shows, at least as a bare row. A
        directory named in ``observations`` that holds or leads to a mount is listed after the others
        that the same mount holds, once for each time it is named.
        """
        refusal = self._gate_params("ls", path=path, observations=observations, columns=columns, authority=authority)
        if refusal is not None:
            return refusal
        return await self._route_single("ls", path, observations, columns=columns, authority=authority)

    async def tree(
        self,
        path: str,
        max_depth: int | None = None,
        *,
        columns: frozenset[str] | None = None,
        authority: Authority | None = None,
    ) -> Result:
        """List every :term:`entry` beneath ``path``, down to ``max_depth`` levels.

        If ``max_depth`` is ``None``, the whole subtree is listed. A :term:`mount` beneath ``path`` is
        listed too, by its own storage, within the depth that is left when the listing reaches it. A
        mount within ``max_depth`` shows as the root of its storage, as in :meth:`ls`, and every
        directory between it and ``path`` shows too. A mount exactly at ``max_depth`` shows its row and
        is not listed. ``columns`` names the fields of an observation to return.

        The call returns a :class:`Result` with one observation for each entry. If ``path`` itself
        cannot be listed, the call fails. A mount beneath it that cannot answer ``tree`` is skipped and
        noted on the result. A mount beneath it that fails while others answer is reported as a
        warning. Both still show their row. The call is refused with ``budget_exhausted`` when it has
        passed through more kernels than ``hop_budget`` allows.
        """
        refusal = self._gate_params("tree", path=path, max_depth=max_depth, columns=columns, authority=authority)
        if refusal is not None:
            return refusal
        return await self._route_single("tree", path, None, max_depth=max_depth, columns=columns, authority=authority)

    # -------------------------------------------------------------------
    # public methods — mutations
    # -------------------------------------------------------------------

    async def write(
        self,
        entries: Iterable[Entry] | None = None,
        *,
        path: str | None = None,
        content: str | None = None,
        data: bytes | None = None,
        overwrite: bool = True,
        parents: bool = False,
        authority: Authority | None = None,
    ) -> Result:
        """Write one file, or a batch of entries.

        Pass ``entries``, or pass ``path`` with ``content`` or ``data``. ``content`` is a text body and
        ``data`` is a bytes body. The two forms cannot be mixed, and neither can ``content`` and
        ``data``. The single form builds the same :term:`entry` that a batch of one would hold. The
        text of a bytes body is rendered later, by ``rebuild``.

        ``entries`` is any iterable of :class:`Entry`, and it is read once. Each entry goes to the
        :term:`mount` that holds its path. Within a mount a parent is written before its child, so a
        directory in the batch serves the entries beneath it whatever order the caller gave. When two
        entries name one path, the later one wins.

        If ``overwrite`` is false, a write to a path that already holds a file is refused. If
        ``parents`` is false, every parent directory must already exist. If ``parents`` is true, the
        missing parents are made, as ``mkdir -p`` makes them. Both apply to every entry in the call.

        The call returns a :class:`Result`. Every entry passes the gate before any storage is called,
        so a path that is not valid, or a mount that is read-only there, refuses the whole call. Each
        mount then writes its own entries, so one mount can succeed where another fails. An exception
        that the ``entries`` iterable raises while it is read reaches the caller unchanged, and nothing
        has been written at that point.
        """
        refusal = self._gate_params(
            "write",
            entries=entries,
            path=path,
            content=content,
            data=data,
            overwrite=overwrite,
            parents=parents,
            authority=authority,
        )
        if refusal is not None:
            return refusal
        if entries is not None:
            return await self._route_entry_batch(entries, overwrite=overwrite, parents=parents, authority=authority)
        if path is None or (content is None and data is None):
            return self._error(
                ErrorKind.invalid, op="write", detail="write requires path and content or data, or entries"
            )
        resolved = resolve_path(path, mutation=True)
        if resolved.path is None:
            return self._invalid_path(resolved, path, "write")
        try:
            entry = await _authored_entry(resolved.path, content, data)
        except ValidationError as exc:
            return self._error(ErrorKind.invalid, op="write", detail=validation_message(exc))
        return await self._route_entry_batch([entry], overwrite=overwrite, parents=parents, authority=authority)

    async def edit(
        self,
        path: str | None = None,
        old: str | None = None,
        new: str | None = None,
        edits: list[EditOperation] | None = None,
        observations: list[Observation] | None = None,
        replace_all: bool = False,
        *,
        authority: Authority | None = None,
    ) -> Result:
        """Replace text in one file, or in each file in ``observations``.

        Pass ``path`` or ``observations`` for the files, as :meth:`read` takes them. Pass ``edits``, or
        pass ``old`` and ``new``, and never both. ``edits`` is a list of :class:`EditOperation`. The
        edits are applied in order, and each one sees the text that the one before it left. They are
        all or nothing. If one edit finds no match, none is applied. Every storage must keep both
        promises. ``old`` and ``new`` are short for a list of one edit, and ``replace_all`` then
        replaces every match of ``old``.

        The call returns a :class:`Result`. An ``edits`` that is not a list of :class:`EditOperation`
        is refused with ``invalid``.
        """
        refusal = self._gate_params(
            "edit",
            path=path,
            old=old,
            new=new,
            edits=edits,
            observations=observations,
            replace_all=replace_all,
            authority=authority,
        )
        if refusal is not None:
            return refusal
        if edits is not None:
            ops = self._as_list(edits)
            if ops is None or not all(isinstance(e, EditOperation) for e in ops):
                return self._error(
                    ErrorKind.invalid, op="edit", detail="edit edits must be an iterable of EditOperation"
                )
            edits = ops
        else:
            assert old is not None and new is not None
            edits = [EditOperation(old=old, new=new, replace_all=replace_all)]
        return await self._route_single("edit", path, observations, edits=edits, authority=authority)

    async def delete(
        self,
        path: str | None = None,
        observations: list[Observation] | None = None,
        *,
        cascade: bool = True,
        authority: Authority | None = None,
    ) -> Result:
        """Delete the :term:`entry` at ``path``, or each row in ``observations``. A delete can be undone.

        A deleted row stays where it is and is marked as deleted. It reads as absent everywhere, and a
        refusal at its path carries the ``vfs.trashed`` hint. The ``/.vfs/trash`` view lists it at its
        own path. :meth:`restore` brings it back. A ``write`` at its path revives it and keeps the body
        it replaced as a version. If ``cascade`` is true, a directory is deleted with everything
        beneath it, and all of it comes back when the directory is restored. Only :meth:`sweep`
        destroys, and it is a developer's verb.

        The call returns a :class:`Result` whose observations each report ``deleted_at``. A path that
        is a mount point, or that holds one, is refused with ``busy``, and the :term:`mount` must be
        removed first. If ``cascade`` is false, a directory that is not empty is refused with
        ``not_empty``.
        """
        refusal = self._gate_params(
            "delete", path=path, observations=observations, cascade=cascade, authority=authority
        )
        if refusal is not None:
            return refusal
        return await self._route_single(
            "delete",
            path,
            observations,
            cascade=cascade,
            authority=authority,
        )

    async def restore(
        self,
        path: str | None = None,
        observations: list[Observation] | None = None,
        *,
        authority: Authority | None = None,
    ) -> Result:
        """Bring back a deleted :term:`entry` at its own path.

        ``path`` is the path the delete reported, because a deleted row never moves. Only a row that a
        delete named can be restored, and everything deleted with it comes back too.

        The call returns a :class:`Result`. A row inside a deleted directory is refused with
        ``not_found``, and the refusal names the directory to restore. A path that now holds a live row
        is refused with ``exists``. No verb pushes out what is there, so the caller deletes it and
        restores again. A storage that keeps no trash refuses with ``unsupported``. A path that is a
        mount point, or that holds one, is refused with ``busy``.
        """
        refusal = self._gate_params("restore", path=path, observations=observations, authority=authority)
        if refusal is not None:
            return refusal
        return await self._route_single("restore", path, observations, authority=authority)

    async def sweep(
        self,
        path: str = "/.vfs/trash",
        *,
        authority: Authority | None = None,
    ) -> Result:
        """Destroy what is at ``path``. A sweep cannot be undone.

        ``sweep`` is a developer's verb, meant to be left off the tools an agent is given. If
        ``path`` is a trash view, the call runs retention. Every row deleted longer ago than the
        mount's ``trash_days`` is destroyed, with everything that was deleted alongside it. If ``path``
        is anything else, that whole subtree is destroyed at once, whatever its age. The default path
        sweeps the trash of the root :term:`mount`. Pass ``/m/.vfs/trash`` to sweep the mount at
        ``/m``. A storage does no work in the background, so nothing is destroyed until this is
        called, and calling it twice is safe.

        The call returns a :class:`Result`. A path that is a mount point, or that holds one, is refused
        with ``busy``.
        """
        refusal = self._gate_params("sweep", path=path, authority=authority)
        if refusal is not None:
            return refusal
        return await self._route_single("sweep", path, None, authority=authority)

    async def mkdir(
        self,
        path: str,
        *,
        parents: bool = False,
        exist_ok: bool = False,
        authority: Authority | None = None,
    ) -> Result:
        """Make a directory at ``path``.

        If ``parents`` is false, every directory above ``path`` must already exist. If ``parents`` is
        true, the missing ones are made. If ``exist_ok`` is true, a directory that is already there is
        accepted.

        The call returns a :class:`Result`. A path that already holds something is refused with
        ``exists``. ``exist_ok`` forgives only a directory, so a file there is still refused.
        """
        refusal = self._gate_params("mkdir", path=path, parents=parents, exist_ok=exist_ok, authority=authority)
        if refusal is not None:
            return refusal
        return await self._route_single("mkdir", path, None, parents=parents, exist_ok=exist_ok, authority=authority)

    async def mkedge(
        self,
        edges: Sequence[Edge] | None = None,
        *,
        source: str | None = None,
        target: str | None = None,
        edge_type: str | None = None,
        provenance: Literal["user", "agent", "system"] = "system",
        authority: Authority | None = None,
    ) -> Result:
        """Make typed edges between entries, or refresh the ones that exist.

        Pass ``edges``, or pass ``source``, ``target`` and ``edge_type``, and never both. ``edges`` is a
        sequence of :class:`Edge`, which can also carry a ``weight`` and a ``distance``. The three
        names are short for one edge. ``provenance`` says what kind of author made the edges, and it
        is stamped on every edge in the call. The value ``extracted`` is kept for ``rebuild``.

        The call returns a :class:`Result`. An edge that already exists is refreshed and reported as
        ``updated``. The two ends of an edge must lie in one :term:`mount`, or the edge is refused with
        ``cross_mount``. The same edge given twice in one call is refused with ``invalid``. The gate
        must allow a write at the path of each end.
        """
        refusal = self._gate_params(
            "mkedge",
            edges=edges,
            source=source,
            target=target,
            edge_type=edge_type,
            provenance=provenance,
            authority=authority,
        )
        if refusal is not None:
            return refusal
        return await self._route_edge_batch(
            "mkedge",
            edges,
            source=source,
            target=target,
            edge_type=edge_type,
            authority=authority,
            provenance=provenance,
        )

    async def rmedge(
        self,
        edges: Sequence[Edge] | None = None,
        *,
        source: str | None = None,
        target: str | None = None,
        edge_type: str | None = None,
        authority: Authority | None = None,
    ) -> Result:
        """Remove typed edges, each named exactly as it was made.

        The arguments are those of :meth:`mkedge`, without ``provenance``. The reserved edge type
        ``fs`` cannot be named here, so the edges that mirror the directory tree cannot be removed.

        The call returns a :class:`Result`. An edge that is not there is a ``not_found`` warning on its
        own row and never fails the call, because the end state is the same. The two ends must lie in
        one :term:`mount`, or the edge is refused with ``cross_mount``. The gate must allow a write at
        the path of each end.
        """
        refusal = self._gate_params(
            "rmedge", edges=edges, source=source, target=target, edge_type=edge_type, authority=authority
        )
        if refusal is not None:
            return refusal
        return await self._route_edge_batch(
            "rmedge", edges, source=source, target=target, edge_type=edge_type, authority=authority
        )

    async def move(
        self,
        src: str | None = None,
        dest: str | None = None,
        moves: Sequence[TwoPathOperation | tuple[str, str]] | None = None,
        *,
        authority: Authority | None = None,
    ) -> Result:
        """Move one :term:`entry`, or each pair in ``moves``, to a new path.

        Pass ``src`` and ``dest``, or pass ``moves``, and never both. ``moves`` is a sequence of pairs,
        each a :class:`TwoPathOperation` or a tuple of two strings. A directory moves with everything
        beneath it.

        The call returns a :class:`Result`. Both paths of a pair must lie in one :term:`mount`, or the
        pair is refused with ``cross_mount``. A move is never turned into a copy and a delete. A path
        that is a mount point, or that holds one, is refused with ``busy``. Every pair is checked
        before any storage is called, so one bad pair refuses the whole call. After that each mount
        moves its own pairs, so one mount can succeed where another fails.
        """
        refusal = self._gate_params("move", src=src, dest=dest, moves=moves, authority=authority)
        if refusal is not None:
            return refusal
        return await self._route_pairs("move", src, dest, moves, authority=authority)

    async def copy(
        self,
        src: str | None = None,
        dest: str | None = None,
        copies: Sequence[TwoPathOperation | tuple[str, str]] | None = None,
        *,
        authority: Authority | None = None,
    ) -> Result:
        """Copy one :term:`entry`, or each pair in ``copies``, to a new path.

        The arguments are those of :meth:`move`, with ``copies`` in place of ``moves``. The source is
        only read, so the gate must allow a write at ``dest`` alone.

        The call returns a :class:`Result`, and it is refused as :meth:`move` is. Only a ``dest`` that
        is a mount point, or that holds one, is ``busy``.
        """
        refusal = self._gate_params("copy", src=src, dest=dest, copies=copies, authority=authority)
        if refusal is not None:
            return refusal
        return await self._route_pairs("copy", src, dest, copies, authority=authority)

    # -------------------------------------------------------------------
    # public methods — find
    # -------------------------------------------------------------------

    async def glob(
        self,
        pattern: str,
        *,
        paths: tuple[str, ...] = (),
        observations: list[Observation] | None = None,
        ext: tuple[str, ...] = (),
        ext_not: tuple[str, ...] = (),
        globs_not: tuple[str, ...] = (),
        kind: ObjectKind | None = None,
        max_count: int | None = None,
        columns: frozenset[str] | None = None,
        authority: Authority | None = None,
    ) -> Result:
        """Find entries whose path matches ``pattern``. A call with no ``paths`` reaches every :term:`mount`.

        In a pattern, ``*`` matches inside one segment of a path, ``**`` matches across segments, and
        ``{a,b}`` matches either choice. A pattern with choices is first expanded into its
        :term:`arms <arm>`. A pattern with a ``/`` in it is matched from each root in ``paths``, or from
        ``/`` when there is none. A pattern with no ``/`` matches the name of an :term:`entry` at any
        depth.

        An entry is kept when ``pattern`` matches it. It is dropped when a pattern in ``globs_not``
        matches it, when ``ext`` or ``ext_not`` rules its extension out, or when it is not of ``kind``.
        ``paths`` are the roots to search beneath. Each root is checked while the search runs. The
        root's own row is returned when the pattern matches it and nothing drops it. A :term:`mount`
        point that matches is returned as the root of its storage, as in :meth:`ls`.

        If ``observations`` is given, the call filters those rows and searches nothing. The rows that
        pass come back exactly as they were given, in the order given, however old they are. A storage
        is asked only when ``kind`` is wanted for a row that does not carry it. Those rows are looked
        up in one batch, and a row that cannot be looked up is an error beside the rows that can. To
        get fresh rows, pass the result to ``stat``. To search beneath the rows, pass their paths as
        ``paths``.

        ``max_count`` must be at least 1. It limits the answer of each mount and the merged result, so
        the call returns at most ``max_count`` rows. The rows are in merge order. The roots and the
        mount points that match come first, then the mounts that ``paths`` names, and then the other
        mounts in table order.

        The call returns a :class:`Result`. The set of matches is the same wherever the mounts are
        placed. The order is not, so the first ``max_count`` rows can differ from one layout to
        another. A root that is not there is an error for that root, beside the rows of the roots that
        are. Each stage that matches rows runs within a time budget. A stage that reaches it returns
        what it finished, with one ``truncated`` warning that says what would shrink the search. A
        pattern that cannot be parsed is refused with ``invalid``.
        """
        refusal = self._gate_params(
            "glob",
            pattern=pattern,
            paths=paths,
            observations=observations,
            ext=ext,
            ext_not=ext_not,
            globs_not=globs_not,
            kind=kind,
            max_count=max_count,
            columns=columns,
            authority=authority,
        )
        if refusal is not None:
            return refusal
        try:
            arms = expand_channel("pattern", (pattern,))
            globs_not = expand_channel("globs_not", globs_not)
        except PatternError as exc:
            return self._error(ErrorKind.invalid, op="glob", detail=str(exc))
        if observations is not None:
            if not self._mounts:
                return self._closed_error("glob")
            deadline = Deadline.after(WALL_TIME_BUDGET)
            rows, invalid = self._observation_rows("glob", observations)
            if invalid is not None:
                return invalid
            filtered = await glob_rows_in_hand(
                self,
                rows,
                arms=arms,
                ext=ext,
                ext_not=ext_not,
                globs_not=globs_not,
                kind=kind,
                deadline=deadline,
                authority=authority,
            )
            return self._cap_rows(filtered, "glob", max_count)
        return await self._route_fanout(
            "glob",
            paths=paths,
            row_cap=max_count,
            filters=PathFilters(admissions=arms, exclusions=globs_not, ext=ext, ext_not=ext_not),
            kind=kind,
            max_count=max_count,
            columns=columns,
            authority=authority,
        )

    async def grep(
        self,
        pattern: str,
        *,
        paths: tuple[str, ...] = (),
        observations: list[Observation] | None = None,
        ext: tuple[str, ...] = (),
        ext_not: tuple[str, ...] = (),
        globs: tuple[str, ...] = (),
        globs_not: tuple[str, ...] = (),
        case_mode: CaseMode = "sensitive",
        fixed_strings: bool = False,
        word_regexp: bool = False,
        invert_match: bool = False,
        before_context: int = 0,
        after_context: int = 0,
        output_mode: GrepOutputMode = "lines",
        max_count: int | None = None,
        allow_scan: bool = False,
        columns: frozenset[str] | None = None,
        authority: Authority | None = None,
    ) -> Result:
        """Search the content of files for ``pattern``. A call with no ``paths`` reaches every :term:`mount`.

        ``pattern`` is a regular expression, or plain text when ``fixed_strings`` is true. It is matched
        against content only and never against a path. ``case_mode`` says how letter case is treated.
        ``word_regexp`` matches whole words only. ``invert_match`` reports the lines that do not match.
        ``before_context`` and ``after_context`` add that many lines around each match. ``output_mode``
        picks what comes back for each file. ``max_count`` limits the matches in each file, as the
        ``-m`` of ripgrep does. It does not limit the rows, and the call returns one row for each file
        that matches.

        ``globs`` and ``globs_not`` choose the files by path, in the pattern language of :meth:`glob`.
        ``ext`` and ``ext_not`` choose them by extension. ``paths`` are the roots to search beneath,
        and each root is checked as :meth:`glob` checks it. A root that is a file is searched too,
        when the globs pass its path.

        A storage with an index refuses a pattern that its index cannot serve. If ``allow_scan`` is
        true, it reads every file for that pattern. A storage that always reads every file ignores
        ``allow_scan``.

        If ``observations`` is given, the call filters those rows and uses no index, so ``allow_scan``
        does nothing. The content of a row that lacks it is fetched from the mount that holds the row,
        and a failure to fetch is an error on the result. A row whose kind holds no content never
        matches.

        The call returns a :class:`Result`. A root that is not there is an error for that root, beside
        the rows of the roots that are. Each stage runs within a time budget. A stage that reaches it
        returns the matches found so far, with one ``truncated`` warning. A pattern in ``globs`` or
        ``globs_not`` that cannot be parsed is refused with ``invalid``.
        """
        refusal = self._gate_params(
            "grep",
            pattern=pattern,
            paths=paths,
            observations=observations,
            ext=ext,
            ext_not=ext_not,
            globs=globs,
            globs_not=globs_not,
            case_mode=case_mode,
            fixed_strings=fixed_strings,
            word_regexp=word_regexp,
            invert_match=invert_match,
            before_context=before_context,
            after_context=after_context,
            output_mode=output_mode,
            max_count=max_count,
            allow_scan=allow_scan,
            columns=columns,
            authority=authority,
        )
        if refusal is not None:
            return refusal
        try:
            globs = expand_channel("globs", globs)
            globs_not = expand_channel("globs_not", globs_not)
        except PatternError as exc:
            return self._error(ErrorKind.invalid, op="grep", detail=str(exc))
        if observations is not None:
            if not self._mounts:
                return self._closed_error("grep")
            rows, invalid = self._observation_rows("grep", observations)
            if invalid is not None:
                return invalid
            return await grep_rows_in_hand(
                self,
                rows,
                pattern=pattern,
                ext=ext,
                ext_not=ext_not,
                globs=globs,
                globs_not=globs_not,
                case_mode=case_mode,
                fixed_strings=fixed_strings,
                word_regexp=word_regexp,
                invert_match=invert_match,
                before_context=before_context,
                after_context=after_context,
                output_mode=output_mode,
                max_count=max_count,
                columns=columns,
                authority=authority,
            )
        return await self._route_fanout(
            "grep",
            paths=paths,
            filters=PathFilters(admissions=globs, exclusions=globs_not, ext=ext, ext_not=ext_not),
            pattern=pattern,
            case_mode=case_mode,
            fixed_strings=fixed_strings,
            word_regexp=word_regexp,
            invert_match=invert_match,
            before_context=before_context,
            after_context=after_context,
            output_mode=output_mode,
            max_count=max_count,
            allow_scan=allow_scan,
            columns=columns,
            authority=authority,
        )

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        paths: tuple[str, ...] = (),
        observations: list[Observation] | None = None,
        ext: tuple[str, ...] = (),
        ext_not: tuple[str, ...] = (),
        globs: tuple[str, ...] = (),
        globs_not: tuple[str, ...] = (),
        columns: frozenset[str] | None = None,
        authority: Authority | None = None,
    ) -> Result:
        """Search for ``query`` and return one ranked list of entries.

        The caller does not pick how the search is done. Each storage ranks by the signals it keeps,
        which can be vectors, words and links, and joins them as it sees fit. ``limit`` is the most
        rows returned. ``globs``, ``globs_not``, ``ext`` and ``ext_not`` choose the files as they do
        for :meth:`grep`, and ``paths`` are the roots to search beneath, checked as :meth:`glob` checks
        them.

        If one :term:`mount` answers, its order and its scores are the answer, cut to ``limit``. If
        more than one can answer, each is asked for ``min(3 * limit, 256)`` rows and the kernel merges
        them. The merge puts every row on one scale, with one BM25 over the text that came back. It
        never changes the order a mount gave its own rows, so each mount contributes the first rows of
        its own answer. The merged scores are scaled to lie between 0 and 1.

        If ``observations`` is given, the search is limited to those rows. The four file filters are applied first, to
        the path that each row carries, as :meth:`grep` applies them to rows. Only the rows that pass are sent on, each
        to the mount that holds it, and a mount that holds none of them is not asked. The call then answers as it would
        if only those rows had been given. A row that a filter drops is never ranked, never checked and never reported.
        A row that passes is ranked only if its storage can rank it. An ordinary directory or a path that is not there
        is left out without an error. The row of a mount point or of the root makes the call fail with ``invalid``.
        A row that passes in a mount that cannot search refuses the call with ``unsupported``.

        The call returns a :class:`Result`. After a merge, its ``legs`` extra says how the merge was
        made. A root that is not there is an error for that root, beside the rows of the roots that are.
        A pattern in ``globs`` or ``globs_not`` that cannot be parsed is refused with ``invalid``. The
        filtering of ``observations`` runs within a time budget. If it reaches the budget, the rows it has
        not judged are left out, with one ``truncated`` warning.
        """
        refusal = self._gate_params(
            "search",
            query=query,
            limit=limit,
            paths=paths,
            observations=observations,
            ext=ext,
            ext_not=ext_not,
            globs=globs,
            globs_not=globs_not,
            columns=columns,
            authority=authority,
        )
        if refusal is not None:
            return refusal
        if observations is not None:
            try:
                globs = expand_channel("globs", globs)
                globs_not = expand_channel("globs_not", globs_not)
            except PatternError as exc:
                return self._error(ErrorKind.invalid, op="search", detail=str(exc))
            if not self._mounts:
                return self._closed_error("search")
            rows, invalid = self._observation_rows("search", observations)
            if invalid is not None:
                return invalid
            kept, records = await admit_rows_in_hand(rows, globs=globs, globs_not=globs_not, ext=ext, ext_not=ext_not)
            answer = await self._route_fanout(
                "search",
                observations=kept,
                ranked=_Ranked(query, limit, fanout_depth(limit)),
                query=query,
                limit=limit,
                columns=columns,
                authority=authority,
            )
            return self._with_skips(answer, records)
        return await self._route_fanout(
            "search",
            paths=paths,
            ranked=_Ranked(query, limit, fanout_depth(limit)),
            filters=PathFilters(globs, globs_not, ext, ext_not),
            query=query,
            limit=limit,
            columns=columns,
            authority=authority,
        )

    async def traverse(
        self,
        method: str,
        path: str | None = None,
        observations: list[Observation] | None = None,
        *,
        depth: int | None = TRAVERSE_DEPTH_DEFAULT,
        edge_types: tuple[str, ...] = (),
        edge_types_not: tuple[str, ...] = (),
        minimal: bool = False,
        limit: int | None = TRAVERSE_LIMIT_DEFAULT,
        columns: frozenset[str] | None = None,
        authority: Authority | None = None,
    ) -> Result:
        """Walk the edges from one or more starting entries.

        ``method`` is ``inbound``, ``outbound`` or ``neighborhood`` to walk, or ``meet`` to find what
        connects the starts. Pass ``path`` for one start, or ``observations`` for several. Each
        :term:`mount` walks its own edges, so a walk never follows an edge out of its storage.

        ``depth`` is the number of hops from the nearest start, and ``None`` walks until nothing new is
        reached. ``edge_types`` names the types to follow. If it is empty, every type that an author
        made is followed, and the ``fs`` type is followed only when it is named. ``edge_types_not``
        names types to leave out. ``limit`` is the most node rows from each storage, nearest first. If
        ``minimal`` is true, a ``meet`` keeps only the nodes that hold the starts together.

        The call returns a :class:`Result` with the nodes, each with its ``depth``, and every chosen
        edge among them. The result names one operation, ``traverse``, whatever the method. A walk
        that ``limit`` cut short carries a ``truncated`` warning. A ``method`` that is not one of the
        four is refused with ``invalid`` before any storage is called.
        """
        kwargs: dict[str, Any] = {
            "method": method,
            "depth": depth,
            "edge_types": edge_types,
            "edge_types_not": edge_types_not,
            "minimal": minimal,
            "limit": limit,
            "columns": columns,
        }
        refusal = self._gate_params("traverse", path=path, observations=observations, authority=authority, **kwargs)
        if refusal is not None:
            return refusal
        return await self._route_single("traverse", path, observations, authority=authority, **kwargs)

    # -------------------------------------------------------------------
    # public methods — execution
    # -------------------------------------------------------------------

    async def run(
        self,
        path: str,
        *,
        arguments: dict[str, Any] | None = None,
        authority: Authority | None = None,
    ) -> Result:
        """Run the tool at ``path`` with ``arguments``.

        ``read``, ``stat`` and ``ls`` show what a tool is, and ``run`` is the only verb that runs it. It
        does not change the file tree, so the permission maps are not asked.

        The call returns a :class:`Result`.
        """
        refusal = self._gate_params("run", path=path, arguments=arguments, authority=authority)
        if refusal is not None:
            return refusal
        return await self._route_single("run", path, None, arguments=arguments, authority=authority)

    # -------------------------------------------------------------------
    # public methods — grants
    # -------------------------------------------------------------------

    async def grant(
        self,
        path: str,
        principal: str,
        level: GrantLevel,
        *,
        authority: Authority | None = None,
    ) -> Result:
        """Give ``principal`` the level ``level`` at ``path`` and everything below it.

        ``principal`` is the ``sub`` of a user, or a group id of the form ``group:<name>``. ``level`` is
        one rung of the ladder. ``list`` shows names and kinds. ``read`` reads. ``add`` creates, and
        changes the caller's own rows. ``contribute`` also overwrites and edits the rows of others.
        ``read_write`` also deletes, moves, restores and grants. A grant only adds access, and no grant
        takes access away. A grant replaces the earlier grant of the same principal at the same path.

        The call returns a :class:`Result` that carries the grant as ``grants=``. The caller must hold
        ``read_write`` at ``path`` and everywhere beneath it, for every subject it acts for, so nobody
        grants more than it holds.
        """
        refusal = self._gate_params("grant", path=path, principal=principal, level=level, authority=authority)
        if refusal is not None:
            return refusal
        return await self._route_grant("grant", path, principal=principal, level=level, authority=authority)

    async def revoke(self, path: str, principal: str, *, authority: Authority | None = None) -> Result:
        """Remove the grant of ``principal`` at exactly ``path``.

        A grant on a path above is not touched, so revoke a grant at the path where it was given.

        The call returns a :class:`Result`. The caller must hold ``read_write`` at ``path`` and
        everywhere beneath it, as for :meth:`grant`, because the grant reaches that far. A grant that
        is not there is a warning and not a failure.
        """
        refusal = self._gate_params("revoke", path=path, principal=principal, authority=authority)
        if refusal is not None:
            return refusal
        return await self._route_grant("revoke", path, principal=principal, authority=authority)

    async def grants(self, path: str, *, authority: Authority | None = None) -> Result:
        """Return the grants that decide access at ``path``, which are the ones on it and on the paths above.

        The call returns a :class:`Result` that carries the rows as ``grants=``. A caller that holds
        ``read_write`` at ``path`` sees every row. Any other caller sees its own rows, the rows of its
        groups, and the rows for everyone. A path the caller cannot see is refused with ``not_found``.
        """
        refusal = self._gate_params("grants", path=path, authority=authority)
        if refusal is not None:
            return refusal
        return await self._route_grant("grants", path, authority=authority)

    async def set_posture(self, path: str, posture: Posture, *, authority: Authority | None = None) -> Result:
        """Set the level that everyone holds at ``path`` and below.

        ``posture`` is one rung of the ladder. ``none`` gives everyone nothing, ``list`` the names,
        ``read`` the contents, ``add`` the right to create, ``contribute`` the right to edit the rows
        of others, and ``read_write`` everything. A fresh :term:`mount` starts at ``read_write``, unless
        :meth:`add_mount` set another. Grants still add access on top. The deepest posture that covers a
        path decides what everyone holds there. Only a developer calls this verb, because it changes the
        policy of a whole mount.

        The call returns a :class:`Result`. The caller must hold ``read_write`` at ``path``.
        """
        refusal = self._gate_params("set_posture", path=path, posture=posture, authority=authority)
        if refusal is not None:
            return refusal
        return await self._route_grant("set_posture", path, posture=posture, authority=authority)

    async def add_member(
        self,
        group: str,
        member: str,
        *,
        path: str = "/",
        authority: Authority | None = None,
    ) -> Result:
        """Make ``member`` a direct member of ``group``, on the :term:`mount` that holds ``path``.

        ``member`` may itself be a group id, so groups nest, down to a fixed depth. Membership belongs
        to a whole mount, so ``path`` only picks the mount.

        The call returns a :class:`Result`. Only the system actor may call it. A membership that would
        make a group a member of itself is refused.
        """
        refusal = self._gate_params("add_member", group=group, member=member, path=path, authority=authority)
        if refusal is not None:
            return refusal
        return await self._route_grant("add_member", path, group=group, member=member, authority=authority)

    async def remove_member(
        self,
        group: str,
        member: str,
        *,
        path: str = "/",
        authority: Authority | None = None,
    ) -> Result:
        """Remove the direct membership of ``member`` in ``group``, on the :term:`mount` that holds ``path``.

        The call returns a :class:`Result`. Only the system actor may call it. A membership that is
        not there is a warning and not a failure.
        """
        refusal = self._gate_params("remove_member", group=group, member=member, path=path, authority=authority)
        if refusal is not None:
            return refusal
        return await self._route_grant("remove_member", path, group=group, member=member, authority=authority)

    # -------------------------------------------------------------------
    # dispatch shapes — single, fan-out, paired, batch
    # -------------------------------------------------------------------

    @staticmethod
    def _as_list(items: object) -> list[Any] | None:
        """Return a batch argument as a list, or ``None`` when it is not a batch.

        A value that cannot be iterated is not a batch, and neither is a bare ``str`` or ``bytes``.
        Making the list once means such a value is refused and no ``TypeError`` escapes. It also means
        the batch can be read more than once. A generator would otherwise be used up by the checks
        and be empty when the storage is called.
        """
        if isinstance(items, (str, bytes)) or not isinstance(items, Iterable):
            return None
        return list(items)

    async def _route_single(
        self,
        op: Op,
        path: str | None,
        observations: list[Observation] | None,
        *,
        authority: Authority | None = None,
        **kwargs: Any,
    ) -> Result:
        """Send a verb that names one path, or a batch of observations, to the storage that holds it.

        Exactly one of ``path`` and ``observations`` arrives, because the verb's check of its arguments
        has already refused anything else. With ``observations``, the rows are grouped by
        :term:`mount` and the mounts are asked at the same time. With ``path``, one mount is found and
        the gate is asked. The storage is then called once, unless a listing reaches the mounts beneath
        the path, as :meth:`_dispatch_read` says. A delete, a restore or a sweep is refused with
        ``busy`` first when the path is a mount point or holds one.
        """
        if not self._mounts:
            return self._closed_error(op)
        if observations is not None:
            return await self._dispatch_grouped_observations(op, observations, authority=authority, **kwargs)

        assert path is not None
        resolved = resolve_path(path, mutation=op in MUTATING_OPS)
        if resolved.path is None:
            return self._invalid_path(resolved, path, op)
        full = resolved.path

        if op in _BUSY_GUARDED_OPS:
            busy = self._busy_guard(op, full, subtree=True)
            if busy is not None:
                return busy

        terminal = self._resolve_terminal(full)
        subtree = _reaches_beneath(op, terminal.rel, kwargs)
        err = self._gate_entry(terminal.mount, op, write_rels=(terminal.rel,), subtree=subtree)
        if err is not None:
            return err
        return await self._dispatch_read(terminal.mount, op, path=terminal.rel, authority=authority, **kwargs)

    async def _dispatch_grouped_observations(
        self,
        op: Op,
        observations: list[Observation],
        *,
        ranked: _Ranked | None = None,
        authority: Authority | None = None,
        **kwargs: object,
    ) -> Result:
        """Send a batch of observations to the mounts that hold them, and merge the answers.

        Each row is checked once. Its path finds the :term:`mount`, and the row is then rewritten as
        that mount's storage sees it. Every row passes the path check, the ``busy`` check and the gate
        before any storage is called, so a batch that the gate refuses is refused whole. A directory
        row is treated for a mutation exactly as the same call with ``path`` would treat it. A read
        answers row by row where the storage does so. With ``ranked``, each mount is asked for
        ``ranked.depth`` rows when more than one mount answers, and the merged answer is ranked again.
        """
        rows, invalid = self._observation_rows(op, observations)
        if invalid is not None:
            return invalid
        groups: dict[Path, tuple[Mount, list[Observation]]] = {}
        for obs in rows:
            resolved = resolve_path(obs.path, mutation=op in MUTATING_OPS)
            if resolved.path is None:
                return self._invalid_path(resolved, obs.path, op)
            if op in _BUSY_GUARDED_OPS:
                busy = self._busy_guard(op, resolved.path, subtree=True)
                if busy is not None:
                    return busy
            mount = self._resolve_terminal(resolved.path).mount
            _b, obs_list = groups.setdefault(mount.path, (mount, []))
            obs_list.append(obs.without_mount(mount.path))
        if not groups:
            return Result(ops=(op,))

        # All gates run before any dispatch, so a batch touching a bad
        # entry is rejected whole per the facts visible in this table.
        for mount, group in groups.values():
            subtree = any(_reaches_beneath(op, o.path, kwargs) for o in group)
            err = self._gate_entry(mount, op, write_rels=[o.path for o in group], subtree=subtree)
            if err is not None:
                return err

        if ranked is not None and len(groups) > 1:
            kwargs = {**kwargs, "limit": ranked.depth}
        results = await gather_settled(
            self._dispatch_read(mount, op, self._listing, observations=group, authority=authority, **kwargs)
            for mount, group in groups.values()
        )
        merged = Result.merge(results, op=op)
        if ranked is None:
            return merged
        answers = list(zip((mount.path for mount, _group in groups.values()), results, strict=True))
        return await self._rank_fanout(ranked, answers, merged)

    def _observation_rows(self, op: Op, observations: object) -> tuple[list[Observation], Result | None]:
        """Return ``observations`` as a list with no refusal, or no rows and an ``invalid`` refusal."""
        rows = self._as_list(observations)
        if rows is None:
            detail = f"observations must be an iterable of Observation, got {type(observations).__name__}"
            return [], self._error(ErrorKind.invalid, op=op, detail=detail)
        for obs in rows:
            if not isinstance(obs, Observation):
                detail = f"observations must be Observation instances, got {type(obs).__name__}"
                return [], self._error(ErrorKind.invalid, op=op, detail=detail)
        return rows, None

    async def _route_grant(self, op: Op, path: str, *, authority: Authority | None, **kwargs: Any) -> Result:
        """Send a grant verb to the :term:`mount` that holds ``path``, and restore the paths in its answer.

        A grant verb names a prefix and not a row, so the path rules for a mutation do not apply, and
        the root takes a posture like any other path. A grant verb that writes passes the mount's
        permission maps. The membership verbs use ``path`` only to pick the mount.
        """
        if not self._mounts:
            return self._closed_error(op)
        resolved = resolve_path(path)
        if resolved.path is None:
            return self._invalid_path(resolved, path, op)
        terminal = self._resolve_terminal(resolved.path)
        err = self._gate_entry(terminal.mount, op, write_rels=(terminal.rel,))
        if err is not None:
            return err
        if op not in _MEMBERSHIP_OPS:
            kwargs["path"] = terminal.rel
        result = await self._dispatch_entry(terminal.mount, op, authority=authority, **kwargs)
        return _rebase_grant_rows(result, terminal.mount.path)

    async def _route_fanout(
        self,
        op: Op,
        *,
        paths: tuple[str, ...] = (),
        observations: list[Observation] | None = None,
        row_cap: int | None = None,
        ranked: _Ranked | None = None,
        filters: PathFilters | None = None,
        authority: Authority | None = None,
        **kwargs: object,
    ) -> Result:
        """Send a search to every mount, to the mounts under some paths, or over a batch of rows.

        ``kwargs`` reach the storage unchanged, with one exception. For ``search``, which sets
        ``ranked``, ``limit`` is replaced by the depth to ask of each mount when more than one mount
        may answer, and the rows are merged by :meth:`_rank_fanout` in place of the row cap.
        ``filters`` is the one typed argument of ``glob`` and ``grep``. The builders of their calls,
        :meth:`_glob_dispatches` and :meth:`_grep_dispatches`, rewrite its two glob channels for each
        root and pass its ``ext`` channels on as they are.

        With ``observations``, the batch is sent as :meth:`_dispatch_grouped_observations` sends it.
        With ``paths``, the roots are grouped by :term:`mount`. A mount that a root names and that
        cannot answer is refused with ``unsupported``, as a call with one path would be. A root with
        mounts beneath it names a region and not one mount. It becomes the mount that holds it,
        searched beneath the root, and every mount beneath it, searched whole. With neither, every
        mount is asked, in table order. A mount that is asked whole and cannot answer is skipped, and
        a record of severity ``info`` says so. One mount that cannot search must not fail the search
        of a region, and the gap still goes on record.

        The answers of mounts asked whole are merged by ``merge_branches``. A mount that fails among
        mounts that answer becomes a warning, and the call fails only if all of them fail. The answers
        of mounts that the caller named are merged plainly, so a named mount that fails always fails
        the call, whatever the others returned. That holds even when a region also covers a named
        mount. The mount is then asked once, whole, and its answer is still merged plainly.
        ``row_cap`` applies the caller's limit again after the merge, in merge order, so the limit is
        not multiplied by the number of mounts.

        The verb's check of its arguments has already refused ``paths`` together with
        ``observations``, and a ``row_cap`` that is neither ``None`` nor at least 1. The call takes
        one copy of the mount table when it starts, and the plan, the probes, the calls on the
        storages and the merge all read it, so a mount changed meanwhile changes only later calls.
        """
        if not self._mounts:
            return self._closed_error(op)
        if observations is not None:
            merged = await self._dispatch_grouped_observations(
                op, observations, ranked=ranked, authority=authority, **kwargs
            )
            return merged if ranked is not None else self._cap_rows(merged, op, row_cap)

        grant = self._enter_hop(op=op)
        if grant.refusal is not None:
            return grant.refusal
        try:
            listing = self._listing
            plan = self._classify_fanout_scopes(op, paths, listing)
            if plan.refusal is not None:
                return plan.refusal
            if ranked is not None and len({*plan.scoped, *plan.unscoped}) > 1:
                kwargs = {**kwargs, "limit": ranked.depth}

            if filters is not None:
                if op == "glob":
                    built = await self._glob_dispatches(plan, listing, paths, filters, authority=authority, **kwargs)
                else:
                    built = await self._grep_dispatches(
                        plan, listing, paths, filters, op, authority=authority, **kwargs
                    )
                if built is None:
                    return self._closed_error(op)
                named_coros, branches, skips, settle = built
            else:
                settle, entry = None, partial(listing.called, self._call_storage)
                # Unscoped subsumes a narrower scope into the same entry.
                named_coros = [
                    entry(mount, op, paths=tuple(dict.fromkeys(rels)), authority=authority, **kwargs)
                    for key, (mount, rels) in plan.scoped.items()
                    if key not in plan.unscoped
                ]
                branches = [
                    (mount.path, entry(mount, op, paths=(), authority=authority, **kwargs))
                    for mount in plan.unscoped.values()
                ]
                skips = plan.skips
            if not named_coros and not branches:
                return self._with_skips(Result(ops=(op,)), skips)
            results = await gather_settled([*named_coros, *(coro for _, coro in branches)])
            named = results[: len(named_coros)]
            branch_results = list(zip((path for path, _ in branches), results[len(named_coros) :], strict=True))
            named = named if settle is None else await settle(named, branch_results)
            merged = self._merge_fanout(named, branch_results, frozenset(plan.scoped), op)
            if ranked is not None:
                return self._with_skips(await self._rank_fanout(ranked, branch_results, merged), skips)
            return self._with_skips(self._cap_rows(merged, op, row_cap), skips)
        finally:
            self._exit_hop(grant.token)

    def _classify_fanout_scopes(self, op: Op, paths: tuple[str, ...], listing: MountListing) -> _FanoutPlan:
        """Work out which mounts will answer a search, from the copy ``listing`` of the table, and return the plan.

        With no ``paths``, every :term:`mount` is taken in table order. A mount that can answer is
        asked whole, and one that cannot is recorded as skipped. A path that is the root, or that has
        mounts beneath it, names a region. The mount that holds the path answers beneath it, the deeper
        mounts answer whole, and a mount that cannot answer is recorded as skipped. Any other path
        names one mount, which must pass the gate. If the gate refuses it, or the path is not valid,
        the plan carries the refusal and its collections are empty.
        """
        scoped: dict[Path, tuple[Mount, list[Path]]] = {}
        unscoped: dict[Path, Mount] = {}
        skipped: dict[Path, ResultError] = {}

        if paths:
            for raw in paths:
                resolved = resolve_path(raw)
                if resolved.path is None:
                    return _FanoutPlan({}, {}, [], refusal=self._invalid_path(resolved, raw, op))
                full = resolved.path
                terminal = self._resolve_terminal(full, listing)
                beneath = listing.beneath(full)
                if full == ROOT or beneath:
                    if op not in terminal.mount.caps:
                        skipped.setdefault(terminal.mount.path, skip_record(op, terminal.mount))
                    elif terminal.rel == ROOT:
                        unscoped.setdefault(terminal.mount.path, terminal.mount)
                    else:
                        _b, rels = scoped.setdefault(terminal.mount.path, (terminal.mount, []))
                        rels.append(terminal.rel)
                    for mount in beneath:
                        if op in mount.caps:
                            unscoped.setdefault(mount.path, mount)
                        else:
                            skipped.setdefault(mount.path, skip_record(op, mount))
                    continue
                err = self._gate_entry(terminal.mount, op, write_rels=(terminal.rel,))
                if err is not None:
                    return _FanoutPlan({}, {}, [], refusal=err)
                _b, rels = scoped.setdefault(terminal.mount.path, (terminal.mount, []))
                rels.append(terminal.rel)
        else:
            for mount in listing.mounts.values():
                if op in mount.caps:
                    unscoped[mount.path] = mount
                else:
                    skipped.setdefault(mount.path, skip_record(op, mount))

        return _FanoutPlan(scoped=scoped, unscoped=unscoped, skips=list(skipped.values()))

    async def _glob_dispatches(
        self,
        plan: _FanoutPlan,
        listing: MountListing,
        paths: tuple[str, ...],
        filters: PathFilters,
        *,
        authority: Authority | None,
        **kwargs: object,
    ) -> _Dispatches | None:
        """Build the calls for one ``glob``. Return ``None`` if the kernel was closed while they were built.

        The caller's pattern arrives as ``filters.admissions``, already expanded into its
        :term:`arms <arm>`, and ``globs_not`` arrives as ``filters.exclusions``. A row is kept when any
        arm matches it, and dropped when any exclusion does.

        A :term:`mount` receives every root that lies beneath it, beside the arms as they were
        written, in its ``scope=`` argument. Its storage applies the rule itself. A row matches when
        it lies beneath a root and its name, or the rest of its path, matches an arm. Two kinds of
        root are joined to each arm in one pattern instead. A name arm becomes ``root/**/pattern``,
        and a path arm is anchored under the root. The first kind is a root whose joined text must be
        read whole. The second is a root above a nested mount. It reaches that mount, and it never
        reaches the part of a mount above that the nested mount hides. The joined patterns are then
        cut down to the part inside each mount, and the exclusions are joined and cut the same way.
        One root's pattern can therefore never reach beneath another root. Each mount receives its
        whole set, with no repeats, in the same one call.

        :mod:`vfs.fanout` does that planning, in one hop to the process pool, within its own time
        budget. If it reaches the budget, the roots it has planned are sent whole and the result says
        so.

        The roots are checked by a separate probe that runs at the same time, grouped by the mount
        that holds each root, in :meth:`_root_probe`. No change to the calls above can drop it. It
        judges a root's own row against the name arms alone, because a path arm joined under a root
        needs one more segment than the root has. It applies every filter, so a root's row is never
        returned past a filter the caller gave.

        :meth:`MountListing.matched <vfs.listing.MountListing.matched>` judges the mount points at the
        same time, and ``settle`` drops those whose own directory a storage refused to list. The whole
        call reads ``listing``, the one copy of the mount table that :meth:`_route_fanout` took.

        A mount whose set of patterns comes out empty is not called, and no skip is recorded for it.
        That is a matter of where the patterns reach, and not of what the mount can do. A skip for a
        mount that cannot ``glob`` is kept only where some arm can reach the rows of that mount.
        """
        arms, exclusions, ext, ext_not = filters
        roots = tuple(dict.fromkeys(root for raw in paths if (root := resolve_path(raw).path) is not None))
        capable = {**plan.unscoped, **{key: mount for key, (mount, _rels) in plan.scoped.items()}}
        owners = {root: self._resolve_terminal(root, listing).mount.path for root in roots}
        skip_paths = tuple(skip.path for skip in plan.skips if skip.path is not None)
        name_arms = tuple(arm for arm in arms if "/" not in arm)
        gates = compile_gates(name_arms, exclusions, ext=ext, ext_not=ext_not) if name_arms else None
        scope = await planned_scope(owners, tuple(capable), skip_paths, roots, arms, exclusions, arms, frozenset())
        if not self._mounts:
            return None  # a close() landed during the hop: no table read, no dispatch
        kind = cast("str | None", kwargs.get("kind"))
        columns = cast("frozenset[str] | None", kwargs.get("columns"))
        cap = cast("int | None", kwargs.get("max_count"))
        probes, unverifiable = self._root_probes(roots, gates, kind, columns, listing=listing, authority=authority)
        points = listing.matched(self._call_storage, roots, filters, kind, columns, cap, authority=authority)
        branches: list[tuple[Path, Coroutine[Any, Any, Result]]] = [
            (
                key,
                listing.called(
                    self._call_storage,
                    capable[key],
                    "glob",
                    patterns=tuple(sorted(live or ())),
                    globs_not=tuple(sorted(scope.exclusions[key])),
                    ext=ext,
                    ext_not=ext_not,
                    authority=authority,
                    **scope_argument(scope, key),
                    **kwargs,
                ),
            )
            for key, live in scope.members.items()
            if live or key in scope.scopes
        ]
        skips = self._scope_skips(plan, scope, unverifiable)
        settle = partial(listing.shown, self._call_storage, roots, columns, cap, authority)
        return _Dispatches([*probes, points], branches, skips, settle)

    async def _grep_dispatches(
        self,
        plan: _FanoutPlan,
        listing: MountListing,
        paths: tuple[str, ...],
        filters: PathFilters,
        op: Op,
        *,
        authority: Authority | None,
        **kwargs: object,
    ) -> _Dispatches | None:
        """Build the calls for one ``grep`` or ``search``. Return ``None`` if the kernel was closed meanwhile.

        The calls have the shape that :meth:`_glob_dispatches` gives them, with the filters of ``grep``.
        ``filters.admissions`` is the caller's ``globs``, ``filters.exclusions`` is its ``globs_not``,
        and the ``ext`` channels are passed on as they are. Each root goes to its :term:`mount` in the
        ``scope=`` argument, beside the caller's globs, or beside the one arm ``**`` when the caller
        gave none. The exclusions go beside them, so one root's pattern can never reach beneath
        another root.

        A root that is itself a file must be searched, and only a storage can test content. So a root
        whose path passes the caller's globs is added to the ``globs`` of its mount as its own exact
        path, and its row joins the search and not the probe. The roots are judged against the globs
        once for the call, all in one hop to the process pool. With no globs, every root passes.

        Everything else is as for ``glob``. That is the cutting of patterns to each mount, the skipping
        of a mount whose set comes out empty, the planning, the two kinds of root that are joined to
        the globs, and the probe of the roots. Here the probe returns no rows and only reports errors.
        The whole call reads ``listing``, as a ``glob`` does.
        """
        globs, exclusions, ext, ext_not = filters
        roots = tuple(dict.fromkeys(root for raw in paths if (root := resolve_path(raw).path) is not None))
        capable = {**plan.unscoped, **{key: mount for key, (mount, _rels) in plan.scoped.items()}}
        owners = {root: self._resolve_terminal(root, listing).mount.path for root in roots}
        skip_paths = tuple(skip.path for skip in plan.skips if skip.path is not None)
        patterns = (globs or ("**",)) if roots else globs
        operands = tuple(root for root in roots if root != ROOT)
        records: list[ResultError] = []
        admitted = operands
        if globs and operands:
            gates = compile_gates(globs)
            deadline = Deadline.after(WALL_TIME_BUDGET)
            judged = [(str(root), root.name) for root in operands]
            verdicts, completed = await judge_rows(offload_pool(), gates, judged, deadline=deadline)
            admitted = tuple(
                root for root, verdict in zip(operands, verdicts, strict=True) if gates.admits(verdict, None)
            )
            if not completed:
                records.append(wall_truncation(_SCOPED_REFINE_GUIDANCE))
        reach = globs or ("**",)
        scope = await planned_scope(
            owners, tuple(capable), skip_paths, roots, patterns, exclusions, reach, frozenset(admitted)
        )
        if not self._mounts:
            return None  # a close() landed during a hop: no table read, no dispatch
        branches: list[tuple[Path, Coroutine[Any, Any, Result]]] = []
        for key, mount in capable.items():
            if key not in scope.members:
                continue
            members = scope.members[key]
            if members is not None and not members and key not in scope.scopes:
                continue
            branches.append(
                (
                    key,
                    listing.called(
                        self._call_storage,
                        mount,
                        op,
                        globs=tuple(sorted(members)) if members else (),
                        globs_not=tuple(sorted(scope.exclusions[key])),
                        ext=ext,
                        ext_not=ext_not,
                        authority=authority,
                        **scope_argument(scope, key),
                        **kwargs,
                    ),
                )
            )
        probes, unverifiable = self._root_probes(roots, None, None, None, listing=listing, authority=authority)
        return _Dispatches(probes, branches, self._scope_skips(plan, scope, [*records, *unverifiable]))

    @staticmethod
    def _scope_skips(plan: _FanoutPlan, scope: ScopePlan, records: list[ResultError]) -> list[ResultError]:
        """Return the records a search carries about what it did not cover.

        They are the skipped mounts that the patterns could reach, the records that the stages made,
        and one more when the planning stopped at its time budget.
        """
        skips = [skip for skip in plan.skips if skip.path is None or skip.path in scope.skips]
        if not scope.completed:
            skips.append(wall_truncation(_PLANNING_REFINE_GUIDANCE))
        return [*skips, *records]

    def _root_probes(
        self,
        roots: tuple[Path, ...],
        gates: GlobGates | None,
        kind: str | None,
        columns: frozenset[str] | None,
        *,
        listing: MountListing,
        authority: Authority | None,
    ) -> tuple[list[Coroutine[Any, Any, Result]], list[ResultError]]:
        """Build one probe for each :term:`mount` that holds roots the caller named.

        The call returns the probes, and a warning for each root that cannot be checked, as
        :meth:`MountListing.probed <vfs.listing.MountListing.probed>` groups them. ``gates`` judge the
        roots' own rows, on the process pool. With ``None``, no row is returned. The probes read
        ``listing``, the copy of the mount table the rest of the call reads.
        """
        grouped, unverifiable = listing.probed(roots)
        coros: list[Coroutine[Any, Any, Result]] = [
            self._root_probe(mount, rels, gates, kind, columns, listing=listing, authority=authority)
            for mount, rels in grouped.values()
        ]
        return coros, unverifiable

    async def _root_probe(
        self,
        mount: Mount,
        rels: list[Path],
        gates: GlobGates | None,
        kind: str | None,
        columns: frozenset[str] | None,
        *,
        listing: MountListing,
        authority: Authority | None,
    ) -> Result:
        """Check the roots that one :term:`mount` holds, with one ``stat`` of all of them.

        The ``stat`` takes no hop of the call's budget, because the search holds one already. A root
        that is not there is reported as an error by the storage itself. ``gates`` decide whether the
        row of a root that is there joins the result. For ``glob`` it joins when a name arm matches and no
        exclusion, extension filter or ``kind`` drops it. A root is tested like any other row and is
        never let through untested. For ``grep``, ``gates`` is ``None`` and no row joins, because
        only a storage can test content. The rows are judged in one hop, within a time budget that
        starts when the judging starts. If the hop does not finish, only the rows it judged are
        returned, with one warning.
        """
        probe = [Observation(path=rel) for rel in dict.fromkeys(rels)]
        result = await listing.listed(
            self._call_storage, mount, "stat", observations=probe, columns=columns, authority=authority
        )
        kept: list[Observation] = []
        records: list[ResultError] = []
        if gates is not None:
            deadline = Deadline.after(WALL_TIME_BUDGET)
            judged, completed = await judge_in_hand(gates, list(result.observations), deadline)
            kept = [row for row in judged if kind is None or row.kind == kind]
            if not completed:
                records.append(wall_truncation(_SCOPED_REFINE_GUIDANCE))
        # The probe answers for the caller's verb, not as a verb of its own:
        # an op-less envelope merges without leaking ``stat`` into the result.
        return result.model_copy(update={"ops": (), "observations": kept, "errors": [*result.errors, *records]})

    @staticmethod
    def _merge_fanout(
        named: list[Result],
        branch_results: list[tuple[Path, Result]],
        scoped_keys: frozenset[Path],
        op: Op,
    ) -> Result:
        """Merge the answers of a search over several mounts.

        A mount that the caller named is merged plainly, even when it was asked whole because a region
        covered it. The caller asked about that mount, so its failure fails the call, whatever the
        others returned. Only the other mounts are merged so that one that fails, among several that
        answer, becomes a warning.
        """
        pinned = [r for p, r in branch_results if p in scoped_keys]
        demotable = [r for p, r in branch_results if p not in scoped_keys]
        branches = Result.merge_branches(demotable, op=op)
        return Result.merge([*named, *pinned, branches], op=op)

    async def _route_two_path(
        self,
        op: Op,
        operations: list[TwoPathOperation],
        *,
        authority: Authority | None = None,
        **kwargs: object,
    ) -> Result:
        """Send the pairs of a move or a copy to the mounts that hold them, after checking every pair.

        The pairs arrive as :class:`TwoPathOperation` and reach the storage as :class:`ResolvedPair`,
        with both paths as the mount's storage sees them. Both paths of a pair must lie in one
        :term:`mount`. A pair that crosses mounts is refused with ``cross_mount``, and it is never
        turned into a copy and a delete. A pair that would move a mount point, or write over one, is
        refused with ``busy``. A move changes both paths, so the gate must allow a write at both. A
        copy writes only ``dest`` and reads ``src``.

        Every pair is checked before any storage is called, so one bad pair refuses the whole batch.
        Nothing is undone after that. The mounts run at the same time, and a failure in one does not
        undo another.
        """
        if not self._mounts:
            return self._closed_error(op)
        if not operations:
            return Result(ops=(op,))

        groups: dict[Path, tuple[Mount, list[ResolvedPair]]] = {}
        for pair in operations:
            src = resolve_path(pair.src, mutation=op == "move")
            if src.path is None:
                return self._invalid_path(src, pair.src, op)
            dest = resolve_path(pair.dest, mutation=True)
            if dest.path is None:
                return self._invalid_path(dest, pair.dest, op)
            src_full, dest_full = src.path, dest.path

            if op == "move":
                busy = self._busy_guard(op, src_full, subtree=True)
                if busy is not None:
                    return busy
            busy = self._busy_guard(op, dest_full, subtree=True)
            if busy is not None:
                return busy

            src_terminal = self._resolve_terminal(src_full)
            dest_terminal = self._resolve_terminal(dest_full)
            if src_terminal.mount.path != dest_terminal.mount.path:
                return self._error(ErrorKind.cross_mount, op=op, path=src_full, target=dest_full)
            write_rels = (src_terminal.rel, dest_terminal.rel) if op == "move" else (dest_terminal.rel,)
            read_rels = () if op == "move" else (src_terminal.rel,)
            subtree = _reaches_beneath(op, dest_terminal.rel, {})
            err = self._gate_entry(src_terminal.mount, op, write_rels=write_rels, read_rels=read_rels, subtree=subtree)
            if err is not None:
                return err

            _b, pairs = groups.setdefault(src_terminal.mount.path, (src_terminal.mount, []))
            pairs.append(ResolvedPair(src=src_terminal.rel, dest=dest_terminal.rel))

        results = await gather_settled(
            self._dispatch_entry(mount, op, operations=group, authority=authority, **kwargs)
            for mount, group in groups.values()
        )
        return Result.merge(results, op=op)

    @staticmethod
    def _coerce_two_path(item: object) -> TwoPathOperation | None:
        """Return ``item`` as a :class:`TwoPathOperation`, or ``None`` when it is not a pair of two strings.

        A :class:`TwoPathOperation` is returned as it is, and a tuple or a list of two strings is
        converted. Anything else returns ``None``, so the caller answers ``invalid`` and no
        ``TypeError`` escapes. That covers a pair of the wrong length, a member that is not a string,
        and a bare string, which would otherwise be read letter by letter.
        """
        if isinstance(item, TwoPathOperation):
            return item
        if isinstance(item, (tuple, list)) and len(item) == 2:
            src, dest = item
            if isinstance(src, str) and isinstance(dest, str):
                return TwoPathOperation(src=src, dest=dest)
        return None

    async def _route_pairs(
        self,
        op: Op,
        src: str | None,
        dest: str | None,
        batch: Sequence[TwoPathOperation | tuple[str, str]] | None,
        *,
        authority: Authority | None,
    ) -> Result:
        """Turn the arguments of a move or a copy into a list of pairs, and send the pairs on.

        The verb's check of its arguments has already made sure that ``src`` and ``dest`` arrived, or
        ``batch``, and not both. Each item of ``batch`` goes through :meth:`_coerce_two_path`, so an
        item that is not a pair is refused with ``invalid`` and raises nothing.
        """
        if batch is not None:
            pairs = self._as_list(batch)
            if pairs is None:
                detail = f"{op} batch must be an iterable of (src, dest) pairs, got {type(batch).__name__}"
                return self._error(ErrorKind.invalid, op=op, detail=detail)
        else:
            assert src is not None and dest is not None
            pairs = [TwoPathOperation(src=src, dest=dest)]
        operations: list[TwoPathOperation] = []
        for item in pairs:
            pair = self._coerce_two_path(item)
            if pair is None:
                return self._error(
                    ErrorKind.invalid, op=op, detail=f"{op} pair must be (src, dest) of two strings: {item!r}"
                )
            operations.append(pair)
        return await self._route_two_path(op, operations, authority=authority)

    async def _route_entry_batch(
        self,
        entries: Iterable[Entry],
        *,
        overwrite: bool = True,
        parents: bool = False,
        authority: Authority | None = None,
    ) -> Result:
        """Send a batch of entries to the mounts that hold them, after checking every entry.

        Every :term:`entry` has its path checked and passes the gate before any storage is called. Each
        entry is then rewritten as its mount's storage sees it, through :meth:`Entry.without_mount`.

        Each :term:`mount` receives its entries sorted so that a parent comes before its child. A
        storage can then judge the batch as a set, and the caller does not have to order it. A
        directory in the batch serves as the parent of deeper entries in the same batch, whatever
        order the caller gave. Two entries for one path keep the caller's order, and the later one wins.
        """
        if not self._mounts:
            return self._closed_error("write")
        rows = self._as_list(entries)
        if rows is None:
            detail = f"write entries must be an iterable of Entry, got {type(entries).__name__}"
            return self._error(ErrorKind.invalid, op="write", detail=detail)
        if not rows:
            return Result(ops=("write",))

        groups: dict[Path, tuple[Mount, list[Entry]]] = {}
        for entry in rows:
            if not isinstance(entry, Entry):
                detail = f"write entries must be Entry instances, got {type(entry).__name__}"
                return self._error(ErrorKind.invalid, op="write", detail=detail)
            resolved = resolve_path(entry.path, mutation=True)
            if resolved.path is None:
                return self._invalid_path(resolved, entry.path, "write")
            terminal = self._resolve_terminal(resolved.path)
            err = self._gate_entry(terminal.mount, "write", write_rels=(terminal.rel,))
            if err is not None:
                return err
            _b, entry_group = groups.setdefault(terminal.mount.path, (terminal.mount, []))
            entry_group.append(entry.without_mount(terminal.mount.path))

        results = await gather_settled(
            self._dispatch_entry(
                mount,
                "write",
                entries=sorted(group, key=lambda e: e.path.depth),
                overwrite=overwrite,
                parents=parents,
                authority=authority,
            )
            for mount, group in groups.values()
        )
        return Result.merge(results, op="write")

    async def _route_edge_batch(
        self,
        op: Literal["mkedge", "rmedge"],
        edges: Sequence[Edge] | None,
        *,
        source: str | None,
        target: str | None,
        edge_type: str | None,
        authority: Authority | None,
        provenance: str | None = None,
    ) -> Result:
        """Send a batch of edges to the mounts that hold them, after checking every edge.

        Both ends of every edge are checked, and the gate must allow a write at both, before any
        storage is called. The edges reach the storage with both paths as the mount's storage sees
        them. A path that is not valid is refused before the two mounts are compared, so the same bad
        end is refused the same way however the mounts are laid out. The same edge twice in one batch
        is refused with ``invalid``. Letting the later one win would hide a mistake in the caller.
        """
        if not self._mounts:
            return self._closed_error(op)
        if edges is None:
            assert source is not None and target is not None and edge_type is not None
            rows: list[tuple[str, str, str, float | None, float | None]] = [(source, target, edge_type, None, None)]
        else:
            listed = self._as_list(edges)
            if listed is None or not all(isinstance(edge, Edge) for edge in listed):
                return self._error(ErrorKind.invalid, op=op, detail=f"{op} edges must be an iterable of Edge")
            if not listed:
                return Result(ops=(op,))
            rows = [(str(e.source), str(e.target), e.edge_type, e.weight, e.distance) for e in listed]

        groups: dict[Path, tuple[Mount, list[Edge]]] = {}
        seen: set[tuple[Path, Path, str]] = set()
        for raw_source, raw_target, raw_type, weight, distance in rows:
            src = resolve_path(raw_source)
            if src.path is None:
                return self._invalid_path(src, raw_source, op)
            tgt = resolve_path(raw_target)
            if tgt.path is None:
                return self._invalid_path(tgt, raw_target, op)
            identity = (src.path, tgt.path, raw_type)
            if identity in seen:
                return self._error(
                    ErrorKind.invalid,
                    op=op,
                    path=src.path,
                    target=tgt.path,
                    detail=f"duplicate {raw_type} edge in batch",
                )
            seen.add(identity)
            src_terminal = self._resolve_terminal(src.path)
            tgt_terminal = self._resolve_terminal(tgt.path)
            try:
                edge = Edge(
                    source=src_terminal.rel,
                    target=tgt_terminal.rel,
                    edge_type=raw_type,
                    weight=weight,
                    distance=distance,
                )
            except ValidationError as exc:
                return self._error(ErrorKind.invalid, op=op, detail=validation_message(exc))
            if src_terminal.mount.path != tgt_terminal.mount.path:
                return self._error(
                    ErrorKind.cross_mount,
                    op=op,
                    path=src.path,
                    target=tgt.path,
                    detail="the edge's endpoints resolve to different mounts",
                )
            # An edge write mutates both endpoints' metadata sets, so
            # both endpoint paths must be writable.
            err = self._gate_entry(src_terminal.mount, op, write_rels=(src_terminal.rel, tgt_terminal.rel))
            if err is not None:
                return err
            _b, group = groups.setdefault(src_terminal.mount.path, (src_terminal.mount, []))
            group.append(edge)

        extra = {"provenance": provenance} if provenance is not None else {}
        results = await gather_settled(
            self._dispatch_entry(mount, op, edges=group, authority=authority, **extra)
            for mount, group in groups.values()
        )
        return Result.merge(results, op=op)

    # -------------------------------------------------------------------
    # hop budget — loops survived, not detected
    # -------------------------------------------------------------------

    def _enter_hop(self, *, op: Op) -> _HopGrant:
        """Take one hop from the call's budget, or refuse when none is left.

        The budget belongs to one call and is shared by every :term:`kernel` the call passes through.
        A storage that wraps a kernel enters it in the same context, and one that speaks over a wire
        carries the budget across. A storage is opaque, so a loop of mounts cannot be found. The budget
        makes a call that could go round for ever end with ``budget_exhausted``, where it would hang.

        A search over several mounts takes a hop, and so do ``tree``, ``ls`` and ``stat``. A listing
        asks each mount in it for the row of its root, so those three can reach a loop. ``read`` and
        the verbs that change something take none. Only a verb's own entry takes a hop, so the probe
        of a search's roots, which runs inside the search's hop, takes none.
        """
        budget = _hop_budget.get()
        if budget is None:
            budget = self._hop_budget_default
        if budget <= 0:
            refusal = self._error(
                ErrorKind.budget_exhausted,
                op=op,
                detail=f"the hop budget ran out routing {op!r}: a mount loop, or a composition deeper than the budget",
            )
            return _HopGrant(token=None, refusal=refusal)
        return _HopGrant(token=_hop_budget.set(budget - 1), refusal=None)

    @staticmethod
    def _exit_hop(token: Token[int | None] | None) -> None:
        """Give the caller its budget back on the way out of a call."""
        if token is not None:
            _hop_budget.reset(token)

    # -------------------------------------------------------------------
    # resolution — one table, longest prefix
    # -------------------------------------------------------------------

    def _match_mount(self, path: Path, listing: MountListing | None = None) -> Mount | None:
        """Return the deepest :term:`mount` at or above ``path``, or ``None`` when the kernel is closed.

        ``listing`` is the copy of the table to read, and the table as it is now when it is ``None``.
        """
        return (self._listing if listing is None else listing).holder(path)

    def _resolve_terminal(self, path: Path, listing: MountListing | None = None) -> ResolvedTerminal:
        """Return the :term:`mount` that holds ``path`` in ``listing``, and the path inside that mount.

        One walk up the path is enough. A nested mount is an ordinary deeper row of the same table,
        so there is nothing to descend into. The root mount holds every path that no deeper mount
        does. The caller checks for a closed kernel first.
        """
        mount = self._match_mount(path, listing)
        assert mount is not None, "resolve on a closed filesystem"
        return ResolvedTerminal(mount=mount, rel=path.without_mount(mount.path))

    async def _probe_location(self, terminal: ResolvedTerminal, row: Location, authority: Authority) -> Location:
        """Return ``row`` with the storage's answer about the path.

        :meth:`MountListing.located <vfs.listing.MountListing.located>` asks the storage, by the rule
        ``stat`` applies, so ``locate`` and ``stat`` agree on a directory that lies above a mount point.
        """
        return await self._listing.located(self._call_storage, terminal.mount, terminal.rel, row, authority)

    def _locate_terminal(self, path: str) -> ResolvedTerminal:
        """Check a caller's path and return where it lands.

        The call raises ``ValueError`` for a path that is not valid, and for a closed kernel.
        """
        resolved = resolve_path(path)
        if resolved.path is None:
            raise ValueError(resolved.error)
        mount = self._match_mount(resolved.path)
        if mount is None:
            msg = f"Cannot locate {resolved.path}: filesystem is closed"
            raise ValueError(msg)
        return ResolvedTerminal(mount=mount, rel=resolved.path.without_mount(mount.path))

    def _mounts_beneath(self, path: Path) -> list[Mount]:
        """Return the mounts that lie strictly beneath ``path`` in the table as it is now.

        :meth:`MountListing.beneath <vfs.listing.MountListing.beneath>` answers. The ``busy`` check reads it.
        """
        return self._listing.beneath(path)

    # -------------------------------------------------------------------
    # gates — capability snapshot, then composed permissions
    # -------------------------------------------------------------------

    def _gate_params(self, op: Op, /, **params: object) -> Result | None:
        """Check the arguments of a verb, and return the refusal for one that is wrong, or ``None``.

        The rules for each verb are in the table in ``vfs.params``. A wrong argument is refused with
        ``invalid``, and the refusal names the argument. This check runs first in every public verb,
        so a wrong argument is reported as ``invalid`` even on a closed kernel or a path that is
        ``busy``. Who is calling is not checked here. A call that names no authority runs as the
        default authority or as the anonymous caller, as :meth:`_admitted` says, and a mount whose
        posture wants a name is what refuses it.
        """
        problem = param_violation(op, params)
        if problem is None:
            return None
        return self._error(ErrorKind.invalid, op=op, detail=problem)

    def _gate_entry(
        self,
        mount: Mount,
        op: Op,
        *,
        write_rels: Sequence[Path] = (),
        read_rels: Sequence[Path] = (),
        subtree: bool = False,
    ) -> Result | None:
        """Ask the gate whether ``op`` may run on ``mount``, and return the refusal, or ``None``.

        The capability check comes first. If the :term:`mount` does not have ``op`` among its
        capabilities, the refusal is ``unsupported`` and names the mount's path. The paths are then
        taken in turn, the read paths first. Under an ``op`` that changes something, each path must
        stay out of the reserved space, which is the ``.vfs`` paths the kernel keeps for itself, or
        the refusal is ``invalid`` at the path the caller sent. A written path must then pass every
        permission map from ``/`` down. The first check that fails is the refusal.

        ``write_rels`` holds the paths that the operation writes, each as the mount's storage sees
        it. It is empty when the path is worked out later. ``read_rels`` holds the paths that a
        mutation reads and does not write, such as the source of a copy. They skip the permission
        maps. If ``subtree`` is true, a written path is also refused when a ``read`` rule lies beneath
        it. A verb whose effect reaches beneath its path passes it.

        The order is a promise. A mount that cannot run the operation answers ``unsupported`` and
        never a refusal of permission. The reserved space is checked on the path inside the mount,
        because a check on the full path cannot see a trash view beneath a mount. A read path is
        checked too, so a copy out of a trash view is ``invalid`` at the path the caller sent, and
        not the storage's ``not_found``. The gate does not ask whether a path exists or what kind it
        is. Only the storage knows that, and it answers when it is called.
        """
        if op not in mount.caps:
            return self._error(
                ErrorKind.unsupported,
                op=op,
                path=mount.path,
                detail=f"operation {op!r} is not declared by the storage mounted here",
            )
        gated = [(rel, False) for rel in read_rels] + [(rel, True) for rel in write_rels]
        for rel, written in gated:
            full = rel.with_mount(mount.path)
            if op in MUTATING_OPS:
                ok, reason = check_reserved_path(rel, head_ok=op == "sweep")
                if not ok:
                    return self._error(ErrorKind.invalid, op=op, path=full, detail=reason)
            if not written:
                continue
            err = check_writable_composed(self._permission_layers(full), op, subtree=subtree)
            if err is not None:
                return err
        return None

    def _permission_layers(self, full: Path) -> list[PermissionLayer]:
        """Return the permission maps that govern ``full``, with the map of ``/`` first.

        Every :term:`mount` at or above ``full`` that has a map contributes it, with the path as that
        mount's storage sees it. Each map can only tighten what the maps above it allow.
        """
        layers: list[PermissionLayer] = []
        for mount_path in reversed(self._sorted_mount_paths):
            if mount_path != ROOT and full != mount_path and not full.startswith(mount_path + "/"):
                continue
            permission_map = self._mounts[mount_path].permissions
            if permission_map is None:
                continue
            layers.append(
                PermissionLayer(
                    permission_map=permission_map,
                    rel=full.without_mount(mount_path),
                    mount_prefix=mount_path,
                )
            )
        return layers

    def _require_mount(self, mount_path: Path) -> Mount:
        """Return the :term:`mount` at ``mount_path``. Raise ``ValueError`` when there is none."""
        mount = self._mounts.get(mount_path)
        if mount is None:
            msg = f"No mount at: {mount_path!r}"
            raise ValueError(msg)
        return mount

    async def _require_mount_rights(
        self, change: str, mount_path: Path, authority: Authority | None
    ) -> MountJudgement | None:
        """Raise :class:`MountError` unless the caller holds ``read_write`` at the mount point ``mount_path``.

        The storage that holds the mount point judges, through ``holds``. The system actor holds every
        level, so no storage is asked for it. A storage that declares no grant verb keeps no rights to
        go around. A storage that keeps grants and cannot answer refuses. ``change`` is the words the
        error uses for the change. This is storage I/O, so it runs before the mount lock is taken and
        before anything changes. The call returns what was judged, taken before the storage was asked,
        or ``None`` for the system actor and for a closed kernel.
        """
        who = self._admitted(authority)
        if who.is_system or not self._mounts:
            return None
        judged = MountJudgement.of(self._mounts, mount_path)
        owner = mount_point_owner(self._mounts, mount_path)
        refusal = await rights_refusal(owner, mount_path, who)
        if refusal is not None:
            msg = f"Cannot {change} {mount_path}: {refusal.error_message}"
            raise MountError(msg, result=refusal)
        return judged

    def _busy_guard(self, op: Op, full: Path, *, subtree: bool) -> Result | None:
        """Return a ``busy`` refusal when ``full`` is a mount point, or ``None``.

        A path that holds a :term:`mount` may not be deleted or moved out from under it. If
        ``subtree`` is true, neither may a path with a mount anywhere beneath it. A mount whose
        directory is gone would be worse than the refusal, so the mount must be removed first.
        """
        at_mount = full != ROOT and full in self._mounts
        beneath = self._mounts_beneath(full) if subtree else []
        if not at_mount and not beneath:
            return None
        return self._error(ErrorKind.busy, op=op, path=full, detail="a mount point, or contains one; unmount first")

    # -------------------------------------------------------------------
    # the funnel — one seam from op to storage, one seam back out
    # -------------------------------------------------------------------

    async def _dispatch_entry(
        self, mount: Mount, op: Op, *, authority: Authority | None = None, **kwargs: Any
    ) -> Result:
        """Call ``op`` on the storage of ``mount``, and return its result with the kernel's own paths.

        The storage is called, the mount's path is put back in front of each path in the result, and
        the rows that a deeper :term:`mount` hides are dropped. A verb calls a storage here or through
        :meth:`_dispatch_read`, and only ``locate`` and the check of a mount point call it directly.
        """
        return await self._listing.called(self._call_storage, mount, op, authority=authority, **kwargs)

    async def _dispatch_read(self, mount: Mount, op: Op, listing: MountListing | None = None, **kwargs: Any) -> Result:
        """Send ``op`` to ``mount`` as :meth:`_dispatch_entry` does, and let the listing verbs read the mount table.

        ``ls``, ``stat`` and ``tree`` show the mounts beneath a directory, so each takes one hop of the
        call's budget and is refused with ``budget_exhausted`` when none is left. ``listing`` is the
        copy of the table to read, and the table as it is now when it is ``None``.
        """
        listing = self._listing if listing is None else listing
        if op == "ls" or op == "stat" or op == "tree":
            grant = self._enter_hop(op=op)
            if grant.refusal is not None:
                return grant.refusal
            try:
                return await listing.listed(self._call_storage, mount, op, **kwargs)
            finally:
                self._exit_hop(grant.token)
        return await listing.called(self._call_storage, mount, op, **kwargs)

    async def _call_storage(
        self,
        mount: Mount,
        op: Op,
        *,
        authority: Authority | None = None,
        **kwargs: Any,
    ) -> Result:
        """Call the method of the storage that carries out ``op``, and return its result.

        The code above carries ``op`` as a value, and this is where it meets a typed method. There is
        one branch for each operation and the last is ``assert_never``, so a verb added to ``ops.py``
        fails the type check until it has a branch here. A storage always receives an authority, which
        is the one :meth:`_admitted` gives. A storage opens and commits its own transaction inside
        each method, and the kernel never sees one.

        If the storage lacks the family of methods that ``op`` belongs to, the result is
        ``unsupported``. That happens only when a storage declares a capability it does not have, and
        no ``AttributeError`` escapes. A :class:`TransportError`, which is a wire backend whose far
        side is dead, becomes ``backend_unavailable``. Any other exception is a fault in the storage
        and is raised.

        An error made here names the root of the :term:`mount` as the storage sees it. The step that
        restores paths then turns that into the mount's path.
        """
        storage = mount.storage
        authority = self._admitted(authority)
        try:
            match op:
                case "read":
                    return await storage.read(authority=authority, **kwargs)
                case "stat":
                    return await storage.stat(authority=authority, **kwargs)
                case "ls":
                    return await storage.ls(authority=authority, **kwargs)
                case "tree":
                    return await storage.tree(authority=authority, **kwargs)
                case "glob":
                    if not isinstance(storage, SupportsPatternSearch):
                        return self._backend_unsupported(op)
                    return await storage.glob(authority=authority, **kwargs)
                case "grep":
                    if not isinstance(storage, SupportsPatternSearch):
                        return self._backend_unsupported(op)
                    return await storage.grep(authority=authority, **kwargs)
                case "search":
                    if not isinstance(storage, SupportsRankedSearch):
                        return self._backend_unsupported(op)
                    return await storage.search(authority=authority, **kwargs)
                case "write":
                    if not isinstance(storage, SupportsMutation):
                        return self._backend_unsupported(op)
                    return await storage.write(authority=authority, **kwargs)
                case "edit":
                    if not isinstance(storage, SupportsMutation):
                        return self._backend_unsupported(op)
                    return await storage.edit(authority=authority, **kwargs)
                case "delete":
                    if not isinstance(storage, SupportsMutation):
                        return self._backend_unsupported(op)
                    return await storage.delete(authority=authority, **kwargs)
                case "restore":
                    if not isinstance(storage, SupportsMutation):
                        return self._backend_unsupported(op)
                    return await storage.restore(authority=authority, **kwargs)
                case "sweep":
                    if not isinstance(storage, SupportsMutation):
                        return self._backend_unsupported(op)
                    return await storage.sweep(authority=authority, **kwargs)
                case "mkdir":
                    if not isinstance(storage, SupportsMutation):
                        return self._backend_unsupported(op)
                    return await storage.mkdir(authority=authority, **kwargs)
                case "move":
                    if not isinstance(storage, SupportsMutation):
                        return self._backend_unsupported(op)
                    return await storage.move(authority=authority, **kwargs)
                case "copy":
                    if not isinstance(storage, SupportsMutation):
                        return self._backend_unsupported(op)
                    return await storage.copy(authority=authority, **kwargs)
                case "traverse":
                    if not isinstance(storage, SupportsTraversal):
                        return self._backend_unsupported(op)
                    return await storage.traverse(authority=authority, **kwargs)
                case "mkedge":
                    if not isinstance(storage, SupportsMutation):
                        return self._backend_unsupported(op)
                    return await storage.mkedge(authority=authority, **kwargs)
                case "rmedge":
                    if not isinstance(storage, SupportsMutation):
                        return self._backend_unsupported(op)
                    return await storage.rmedge(authority=authority, **kwargs)
                case "run":
                    if not isinstance(storage, SupportsRun):
                        return self._backend_unsupported(op)
                    return await storage.run(authority=authority, **kwargs)
                case "grant":
                    if not isinstance(storage, SupportsGrants):
                        return self._backend_unsupported(op)
                    return await storage.grant(authority=authority, **kwargs)
                case "revoke":
                    if not isinstance(storage, SupportsGrants):
                        return self._backend_unsupported(op)
                    return await storage.revoke(authority=authority, **kwargs)
                case "grants":
                    if not isinstance(storage, SupportsGrants):
                        return self._backend_unsupported(op)
                    return await storage.grants(authority=authority, **kwargs)
                case "set_posture":
                    if not isinstance(storage, SupportsGrants):
                        return self._backend_unsupported(op)
                    return await storage.set_posture(authority=authority, **kwargs)
                case "add_member":
                    if not isinstance(storage, SupportsGrants):
                        return self._backend_unsupported(op)
                    return await storage.add_member(authority=authority, **kwargs)
                case "remove_member":
                    if not isinstance(storage, SupportsGrants):
                        return self._backend_unsupported(op)
                    return await storage.remove_member(authority=authority, **kwargs)
                case _:
                    assert_never(op)
        except TransportError as exc:
            return self._error(ErrorKind.backend_unavailable, op=op, path=ROOT, detail=f"the transport failed: {exc}")

    def _admitted(self, authority: Authority | None) -> Authority:
        """Return the authority that a storage is handed for a call.

        It is the call's own authority when it names one. Otherwise it is the kernel's
        ``default_authority``, which a bulk load sets to ``Authority.system()``. Otherwise it is the
        anonymous caller, who holds only what the posture of each :term:`mount` gives everyone. A
        call always has a named caller, so a storage and its audit always see one.
        """
        if authority is not None:
            return authority
        if self._default_authority is not None:
            return self._default_authority
        return _ANONYMOUS_AUTHORITY

    def _backend_unsupported(self, op: Op) -> Result:
        """Return the ``unsupported`` refusal for a storage that lacks the methods ``op`` needs.

        The refusal names the root of the mount as the storage sees it, as :meth:`_call_storage`
        says, and the mount's path is put in front of it on the way out.
        """
        return self._error(ErrorKind.unsupported, op=op, path=ROOT, detail=f"the storage does not implement {op!r}")

    # -------------------------------------------------------------------
    # merging
    # -------------------------------------------------------------------

    @staticmethod
    def _with_skips(result: Result, skips: list[ResultError]) -> Result:
        """Return ``result`` with the records of skipped mounts added after the merge.

        They are added last, so a skipped mount is never counted as one that failed.
        """
        if not skips:
            return result
        return result.model_copy(update={"errors": [*result.errors, *skips]})

    async def _rank_fanout(self, ranked: _Ranked, answers: list[tuple[Path, Result]], merged: Result) -> Result:
        """Order the rows of a ``search``, and return the result that carries them.

        If one :term:`mount` answered, its order is kept. If several did, their rows are merged, and
        the order each mount gave its own rows is never changed. ``answers`` pairs the path of each
        mount with its result, in the order the mounts were called. ``merged`` is the result that
        holds them all. The merged rows replace its rows, the records of the merge are added to its
        errors, and what the merge did is carried as the ``legs`` extra.
        """
        ranking = await merge_ranked(
            ranked.query, answers, limit=ranked.limit, depth=ranked.depth, rerankers=self._rerankers
        )
        update: dict[str, Any] = {"observations": ranking.observations, "errors": [*merged.errors, *ranking.records]}
        if ranking.legs:
            update["legs"] = ranking.legs
        return merged.model_copy(update=update)

    @staticmethod
    def _cap_rows(result: Result, op: Op, row_cap: int | None) -> Result:
        """Return ``result`` cut to the caller's limit of ``row_cap`` rows, after a merge.

        The rows keep merge order, which is the mounts the caller named first and then table order.
        Scores do not change it. ``search`` never comes here, because its merge cuts by its own
        rule. Errors and warnings are never cut.
        """
        if row_cap is None or len(result.observations) <= row_cap:
            return result
        return result.model_copy(update={"observations": list(result.observations[:row_cap])})

    # -------------------------------------------------------------------
    # errors
    # -------------------------------------------------------------------

    def _error(
        self,
        kind: ErrorKind,
        *,
        op: str,
        path: Path | None = None,
        target: Path | None = None,
        detail: str | None = None,
        severity: Severity = Severity.error,
        data: dict[str, Any] | None = None,
    ) -> Result:
        """Return a failed :class:`Result` that carries one error.

        A verb never raises for a refusal. It returns a result, and the caller turns that into an
        exception with ``raise_if_failed`` when it wants one. ``kind`` says what went wrong and ``op``
        names the verb, which the :term:`kernel` always knows. ``path`` is where it went wrong,
        ``target`` is the second path when there is one, and ``detail`` adds words that name no path.
        The message is built from the table of error kinds. A caller that already holds a result
        returns that result and does not come here.
        """
        fact = classified(kind, path, target=target, detail=detail, severity=severity, data=data)
        return Result(ops=(op,), errors=[fact])

    def _invalid_path(self, resolved: ResolvedPath, raw: str, op: Op) -> Result:
        """Return the ``invalid`` refusal for a path that did not pass the path check.

        Every such refusal is made here. It is called only when ``resolved.path`` is ``None``, and it
        uses the words of the path check when there are any. ``raw`` is the path as the caller wrote it.
        """
        return self._error(
            ErrorKind.invalid, op=op, detail=resolved.error or "the path did not resolve", data={"raw": str(raw)}
        )

    def _closed_error(self, op: Op) -> Result:
        """Return the ``backend_unavailable`` refusal for a verb called after ``close()``."""
        return self._error(ErrorKind.backend_unavailable, op=op, detail="the filesystem is closed")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _reaches_beneath(op: Op, rel: Path, kwargs: Mapping[str, Any]) -> bool:
    """Return whether ``op`` at ``rel`` acts on every path beneath it.

    A delete that cascades does, and so do a move, a copy and a sweep outside a trash view. A delete
    that does not cascade, a restore and a sweep of a trash view only finish or undo an earlier
    delete, so a permission map judges them at their own path alone.
    """
    if op in ("move", "copy"):
        return True
    if op == "delete":
        return bool(kwargs.get("cascade", True))
    return op == "sweep" and not is_trash_path(str(rel))
