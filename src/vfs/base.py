"""AsyncVirtualFileSystem — async router over one mount table of storage backends.

A mount attaches a **storage instance**, never another router: the table maps
``path -> Mount(path, storage, ...)``, the node's own backend is the
identity entry at ``/``, and longest-prefix matching resolves every path to
exactly one entry.  One ``AsyncVirtualFileSystem`` = one namespace = one policy
layer — the Linux shape, where a mount entry names a superblock and the VFS
layer exists once.

Namespace shape is *stored*, never synthesized: a mount-point directory is
an ordinary stored row in whichever storage owns the parent path, while the
mount lives only in this table.  A mount is attached onto an existing
empty directory (the ``graft_tree`` rule); ``add_mount`` makes that
directory when it is absent and then attaches; ``remove_mount`` detaches
and strictly rmdirs.  Composition with other routers happens through
storage too: an adapter presents a router as a ``StorageBackend`` (the
exportfs move), and MCP clients are wire-speaking backends.

The admin surface — ``add_mount``/``remove_mount``/``update_mount``/
``close`` — is control-plane state on this router and is not part of the
storage protocol: no dispatched verb can mutate a mount table.  Adding or
removing a mount still passes the gate, as the write it is at its mount
point.

Public methods are routers: resolve the entry, gate it (capability from the
entry's declared snapshot, then permission maps composed from ``/`` down —
most restrictive wins), dispatch through the one storage funnel, then
rebase, shadow-filter, and decorate on the way out.

Paths cross the public boundary as plain ``str``; the resolve gate mints
:class:`~vfs.paths.Path` once, and everything below it — routing, gating,
storage dispatch — carries the branded type.  Any path a storage method
receives is already proven.
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
from vfs.chain import glob_rows_in_hand, grep_rows_in_hand, judge_in_hand
from vfs.deadline import WALL_TIME_BUDGET, Deadline
from vfs.exceptions import MountError, raise_lone_or_group
from vfs.fanout import plan_scope, walks
from vfs.models import (
    MEASURE_OFFLOAD_BYTES,
    MEASURED_BODY,
    Edge,
    Entry,
    Observation,
    measure_bytes,
    measure_text,
)
from vfs.mounts import EdgeLocation, Location, Mount
from vfs.offload import call_offloaded, judge_rows, offload_pool, wall_truncation
from vfs.ops import (
    GRANT_OPS,
    MUTATING_OPS,
    READ_OPS,
    TRAVERSE_DEPTH_DEFAULT,
    TRAVERSE_LIMIT_DEFAULT,
    CaseMode,
    GrepOutputMode,
    TwoPathOperation,
)
from vfs.params import param_violation
from vfs.paths import (
    METADATA_ROOT,
    ROOT,
    Path,
    check_reserved_path,
    is_trash_path,
    resolve_path,
)
from vfs.pattern_matching import PatternError, ScopeChannel, compile_gates, expand_channel
from vfs.permissions import (
    Permission,
    PermissionLayer,
    PermissionMap,
    check_writable_composed,
    coerce_permissions,
)
from vfs.rerank import BM25Rerank, Reranker, fanout_depth, merge_ranked
from vfs.results import ErrorKind, Result, ResultError, classified, validation_message
from vfs.results.kinds import TRASHED_KEY, Severity, kind_family
from vfs.session import AsyncSession
from vfs.storage import (
    HOLDS,
    ResolvedPair,
    StorageBackend,
    SupportsClose,
    SupportsGrants,
    SupportsHolds,
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
    from collections.abc import Coroutine, Mapping, Sequence

    from vfs.fanout import ScopePlan
    from vfs.ops import Op
    from vfs.paths import ObjectKind, ResolvedPath
    from vfs.pattern_matching import GlobGates
    from vfs.storage.grants import GrantLevel, Posture

# Router-traversal depth budget for the current request: decremented once
# per router entered (adapters and wire hops re-enter), never per mount.
_hop_budget: ContextVar[int | None] = ContextVar("vfs_hop_budget", default=None)

# Single-path mutations whose addressed site the EBUSY guard protects:
# delete removes it, restore lands on it, sweep destroys beneath it.
_BUSY_GUARDED_OPS: frozenset[Op] = frozenset({"delete", "restore", "sweep"})

# The router's own control-plane storage calls (mount-site probes, the
# mount-point mkdir and rmdir) run as the system actor, not as any caller.
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
    """Where a routed path landed — a mount plus the residual path.

    ``mount`` names the entry that owns the path; ``rel`` is the path in
    that entry's own coordinates (``without_mount(mount.path)``).
    """

    mount: Mount
    rel: Path

    @property
    def full(self) -> Path:
        """The router-coordinate path this terminal resolved from."""
        return self.rel.with_mount(self.mount.path)


class _HopGrant(NamedTuple):
    """One hop-budget admission: exactly one of *token* / *refusal* is set.

    ``token`` restores the caller's budget on exit (``_exit_hop``);
    ``refusal`` is the classified ``budget_exhausted`` result.
    """

    token: Token[int | None] | None
    refusal: Result | None


class _Ranked(NamedTuple):
    """The ranked verb's fan-out policy: the query the merge rescores, the caller's bound, the per-mount depth."""

    query: str
    limit: int
    depth: int


class _FanoutPlan(NamedTuple):
    """One fan-out's classified inputs — an output-only plan.

    ``scoped`` maps mount path to the entry and its caller-named rels;
    ``unscoped`` holds the entries dispatched whole; ``skips`` are the
    incapable-entry coverage records, appended only after the merge so
    they never feed branch demotion.  ``refusal`` is the sole failure
    carrier: when set, the collections are empty and the caller returns
    it.  The plan never grows input fields — inputs stay arguments.
    """

    scoped: dict[Path, tuple[Mount, list[Path]]]
    unscoped: dict[Path, Mount]
    skips: list[ResultError]
    refusal: Result | None = None


class _PathFilters(NamedTuple):
    """The caller's structural path filters — the four-channel law of :class:`~vfs.pattern_matching.GlobGates`.

    The one fan-out argument the pattern-search verbs hand the router
    apart from the forwarded keywords. The two glob channels are
    rewritten per entry before they cross the seam — sent uncomposed
    beside the roots beneath the entry, composed and residuated into
    entry coordinates for the few roots that compose: ``admissions`` is
    glob's pattern (its brace-expanded arms) or grep's ``globs``,
    ``exclusions`` is ``globs_not`` on both verbs. The two ext channels
    cross verbatim and are read here only by the root probe's gate.
    """

    admissions: tuple[str, ...]
    exclusions: tuple[str, ...]
    ext: tuple[str, ...]
    ext_not: tuple[str, ...]


class _Dispatches(NamedTuple):
    """A pattern-search fan-out's built calls: the root probes, the entry branches, the coverage records."""

    probes: list[Coroutine[Any, Any, Result]]
    branches: list[tuple[Path, Coroutine[Any, Any, Result]]]
    skips: list[ResultError]


async def _authored_entry(path: Path, content: str | None, data: bytes | None) -> Entry:
    """The entry a path write authors; a body past the offload threshold is measured off the loop.

    The hash of a small body costs less than a thread hop, so it is taken
    inline by the model's own validator. A large body is measured on the
    process pool first and handed to the validator through its
    measured-body door, so one caller's 16 MB write never stalls every
    other coroutine on the host for the length of a sha256.
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
    """*result* with each ``grants=`` row's prefix re-rooted from storage to router coordinates.

    Grant rows ride as an extra, which the funnel's rebase does not
    reach. A prefix that is not a lawful path is left as the peer sent it.
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
    """The asynchronous kernel; ``VirtualFileSystem`` is its synchronous face."""

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
        if not isinstance(storage, StorageBackend):
            msg = f"storage must implement the read family (see vfs.storage), got {type(storage).__name__}"
            raise TypeError(msg)
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
        self._stranded_disposals: dict[int, StorageBackend] = {}
        root = Mount(
            path=ROOT,
            storage=storage,
            permissions=coerce_permissions(permissions),
            deny_ops=self._validate_deny_ops(deny_ops),
            no_overlay=no_overlay,
            owned=True,
            declared_caps=frozenset(storage.capabilities()),
        )
        self._mounts: dict[Path, Mount] = {ROOT: root}
        self._sorted_mount_paths: list[Path] = [ROOT]
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
        deny_ops: Iterable[Op] = (),
        no_overlay: bool = False,
        owned: bool = True,
        authority: Authority | None = None,
    ) -> None:
        """Attach *storage* at *path* as a :term:`mount`, making the mount-point directory when it is absent.

        The caller must hold ``read_write`` at the mount point, and the
        storage that holds the mount point says whether it does. *authority*
        names the caller. With none, the caller is the file system's default
        authority, or else the anonymous caller, as for any verb.

        The mount point is an **empty directory** in the storage owning
        the parent path.  It is created when absent (an ordinary gated
        mkdir against the owning mount — parents must exist unless
        ``parents=True``), then the mount commits over it.  An existing
        directory is fine when empty (the mount-again-after-restart
        shape), and a directory a removed mount deleted is restored; an
        occupied site or a file classifies through the mkdir or the site
        check and raises.  A failed attach leaves the directory behind —
        a plain empty directory is a valid future mount site, not damage
        to roll back.  The mount itself is runtime-only table state;
        nothing about it is stored.

        A mount is a write at its mount point, and the gate treats it as
        one: it is refused where the mount above would refuse a ``mkdir``
        there — a read-only parent, or one whose storage or mask does not
        allow ``mkdir`` — even when the directory already exists.

        Rejected too when the path already has a mount, sits beneath a
        ``no_overlay`` mount, would sit above an existing deeper mount, or
        when *storage* is already mounted elsewhere in this table
        (aliasing — one object, one path).  *permissions* installs
        mount-relative rules; *deny_ops* masks mutating/exec ops out of
        the mount's effective capabilities (read-family ops cannot be
        masked); *owned* says ``close()`` disposes this storage.

        *path* is optional: when omitted, the storage's ``name`` names the
        mount point (``add_mount(InMemoryStorage(name="data"))`` lands at
        ``/data``).
        """
        mount_name = path or storage.name
        if not mount_name:
            msg = "add_mount needs a path or a named storage"
            raise ValueError(msg)
        mount_path = self._normalize_mount_path(mount_name)
        # Validated before the mkdir — a rejected mask must not mint the site.
        mask = self._validate_deny_ops(deny_ops)
        await self._require_mount_rights("mount at", mount_path, authority)

        made = await self.mkdir(str(mount_path), parents=parents, exist_ok=True, authority=_ADMIN_AUTHORITY)
        if not made.success and _is_tombstoned_site(made, mount_path):
            made = await self.restore(str(mount_path), authority=_ADMIN_AUTHORITY)
        if not made.success:
            detail = made.error_message or "storage refused the mount-point directory"
            msg = f"Cannot mount at {mount_path}: {detail}"
            raise MountError(msg, result=made)
        await self._attach_mount(
            storage, str(mount_path), permissions=permissions, deny_ops=mask, no_overlay=no_overlay, owned=owned
        )

    async def remove_mount(self, path: str, *, authority: Authority | None = None) -> Mount:
        """Detach the :term:`mount` at *path*, remove its directory, and return the mount.

        The caller must hold ``read_write`` at the mount point, as for
        :meth:`add_mount`, and nothing changes when it does not.

        Removing a mount is a write at its mount point: it is refused,
        and the mount stays, where the mount above would refuse a
        ``delete`` there.  The mount's own permissions have no say in
        that.  Past the gate the mount is dropped (table surgery under
        the lock), then
        the mount-point directory is removed with a strict, non-recursive
        delete against whichever storage owns the parent path — the empty
        directory row parks in trash like any deleted row, and retention
        reclaims it.  Never a cascade: on shared or persistent storage the
        directory may have gained rows this router never saw, and removing
        a mount must not destroy them.  A failed rmdir leaves the mount
        removed and raises — the namespace keeps a plain directory, loud
        and recoverable.  Rejected while deeper mounts still sit beneath
        *path* — remove depth-first, as ``umount`` does.

        Storage lifecycle is untouched: removing a mount never disposes an
        engine or session.  The returned mount carries the storage, so the
        caller can close the one it owns.
        """
        mount_path = self._normalize_mount_path(path)
        self._require_mount(mount_path)
        await self._require_mount_rights("unmount", mount_path, authority)
        mount = await self._detach_mount(str(mount_path))
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
        """Change the policy of the :term:`mount` at *path* in place.

        The caller must hold ``read_write`` at the mount point, as for
        :meth:`add_mount`. The storage of ``/`` judges for the root mount.

        ``None`` means "leave unchanged" everywhere — so ``deny_ops=()``
        (clear the mask) is distinct from ``deny_ops=None`` (keep it), and
        passing no changes at all is a no-op, not an error.  The mount is
        replaced under the mount lock with a new one; no moment exists
        where the path has no mount, and no storage I/O runs — the one
        storage call is ``refresh_caps=True`` re-snapshotting
        ``storage.capabilities()`` (taken before the lock, committed under
        it): the remedy for a reconnected wire backend whose tool set
        changed.  A replaced or cleared mask recomputes effective caps from
        the stored unmasked snapshot, so previously masked ops come back
        without asking the storage.

        Root is an ordinary mount: ``update_mount("/")`` is how you tighten
        the whole namespace.  Loosening is permitted, as on Linux — a parent
        layer's map still gates every path beneath (most restrictive wins),
        so ``update_mount`` can never grant more than the chain above allows.

        ``no_overlay=True`` seals with **future-only** effect: existing
        deeper mounts stay and keep dispatching; only *new* mounts beneath
        this one are refused.  Because removing a mount never consults
        the flag, the sealed subtree is a one-way ratchet — it can shrink
        but never grow.  Unknown path raises :class:`ValueError`, as
        ``remove_mount`` does.
        """
        mount_path = self._normalize_mount_path(path, allow_root=True)
        mask = None if deny_ops is None else self._validate_deny_ops(deny_ops)
        new_map = None if permissions is None else coerce_permissions(permissions)
        self._require_mount(mount_path)
        await self._require_mount_rights("update the mount at", mount_path, authority)

        # The one call to the mount's storage, taken before the lock is acquired.
        fresh_caps: frozenset[str] | None = None
        probed_storage: StorageBackend | None = None
        if refresh_caps:
            probed_storage = self._require_mount(mount_path).storage
            fresh_caps = frozenset(probed_storage.capabilities())

        async with self._mount_lock:
            mount = self._require_mount(mount_path)
            if probed_storage is not None and mount.storage is not probed_storage:
                msg = f"Mount at {mount_path} changed while it was being updated — retry"
                raise ValueError(msg)
            self._mounts[mount_path] = replace(
                mount,
                permissions=mount.permissions if new_map is None else new_map,
                deny_ops=mount.deny_ops if mask is None else mask,
                no_overlay=mount.no_overlay if no_overlay is None else no_overlay,
                declared_caps=mount.declared_caps if fresh_caps is None else fresh_caps,
            )

    async def close(self) -> None:
        """Release every resource this process holds for the namespace.

        Snapshot-and-clear the table under the lock (synchronously — a
        cancelled close never leaves a closed storage reachable), then
        dispose outside it: each distinct ``owned`` storage that exposes
        ``close`` is closed once (identity-deduped — the same object can
        never be double-closed), concurrently, each under the per-backend
        timeout.  Closing may end this client's own sessions — that is a
        wire message — but never mutates a remote router's table.

        Failures are collected so one bad disposal cannot strand a
        sibling's engine; undisposed storages are parked on the router and
        ``SupportsClose`` is idempotent by contract, so a second ``close()``
        after cancellation finishes the job.
        """
        async with self._mount_lock:
            mounts = list(self._mounts.values())
            self._mounts = {}
            self._sorted_mount_paths = []

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
        """Every :term:`mount` in the table, in path order — replayable.

        The mount at ``/`` comes first (it is an ordinary mount); a closed
        filesystem returns ``()``.  No storage I/O, and no lock: this reads
        one dict snapshot synchronously, and the table can change the
        instant a lock would drop anyway.  A mount is frozen, so what is
        returned is what the gates read, not a copy to keep in step.

        Each mount carries the policy its mounter set — ``permissions``,
        ``deny_ops``, ``no_overlay``, ``owned`` — and its storage, so the
        tuple is enough to rebuild the namespace: give the root mount's
        storage to the constructor, add every other mount bare through
        :meth:`add_mount`, then apply each mount's policy **last** through
        :meth:`update_mount`.  A mount that is read-only, masks ``mkdir``
        or is sealed with ``no_overlay`` refuses new mounts beneath it, so
        a table tightened after its mounts were added cannot replay with
        the policy passed to ``add_mount``.  :meth:`Mount.to_payload`
        gives each one's JSON-native form.
        """
        return tuple(self._mounts[mount_path] for mount_path in sorted(self._mounts))

    async def locate(self, path: str, *, exists: bool = False, authority: Authority | None = None) -> Location:
        """Where *path* lives: the mount that owns it and its storage-local path.

        The router's own resolution — longest prefix, the deepest mount
        under a nested mount, the root entry as the fallback — read from
        one table snapshot with no lock. With *exists* off no storage is
        asked anything; permissions and capabilities are never consulted,
        so the answer does not depend on a user. With *exists* on the
        owning storage is asked to stat the storage-local path directly
        (no router gate) under *authority* — the same one a ``stat``
        would run as — so a row the caller cannot see reads as absent,
        never as a leaked fact. The row carries ``exists`` and ``kind``,
        or ``note`` when the storage could not answer. A non-canonical
        path is canonicalised; a structurally invalid one raises
        ``ValueError`` as :class:`Path` does, and so does a closed
        filesystem, whose table is empty.
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
        """Where an edge's two endpoints live, and whether one storage holds both.

        :meth:`locate` twice plus the verdict ``mkedge`` would reach: an
        edge never crosses a mount boundary, so ``same_storage`` is the
        two mounts being one. ``reason`` names the first blocker — the
        boundary, or with *exists* an endpoint the storage does not hold;
        the row is an answer, not a refusal.
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
        """Open an authority-scoped facade: the verbs without the identity argument.

        Sugar over the funnel — every session verb is the same call with
        ``authority=`` filled in, so the gate stays authority-*presence*
        at ingress and a session-mediated result equals the direct one.
        Each call makes a new session; use it with ``async with`` or close
        it yourself, and closed is final.
        """
        return AsyncSession(self, authority)

    def capabilities(self) -> frozenset[str]:
        """Operations this namespace answers — the union of entry snapshots.

        Each mount's set was declared by its storage when it was mounted
        (``storage.capabilities()``), so the union is self-declaration all
        the way down: an adapter forwards its wrapped router's set, a wire
        backend advertises the far side's tools, and nothing is inferred
        from method surfaces.
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
        deny_ops: Iterable[Op] = (),
        no_overlay: bool = False,
        owned: bool = True,
    ) -> None:
        """Commit a mount of *storage* at *path*, onto a directory that already exists.

        The site must already exist as an **empty directory** in the storage
        owning the parent path (the ``graft_tree`` rule: exists, is a
        directory, has no children) — which is what makes mounting again
        after a restart work on a persistent backend, and makes a
        crash-orphaned mount-point directory a valid future site instead
        of poison.  :meth:`add_mount` states what is rejected.

        The site probe is storage I/O and runs outside the mount lock; the
        table is re-checked, gated and committed under it with no await
        between.  The gate is asked here, not left to the caller's mkdir,
        so no path to a mount goes around it.
        """
        if not isinstance(storage, StorageBackend):
            msg = f"storage must implement the read family (see vfs.storage), got {type(storage).__name__}"
            raise TypeError(msg)
        mount_path = self._normalize_mount_path(path)
        mask = self._validate_deny_ops(deny_ops)

        probed = await self._probe_mount_site(mount_path)
        if probed is not None:
            msg = f"Cannot mount at {mount_path}: {probed}"
            raise ValueError(msg)

        mount = Mount(
            path=mount_path,
            storage=storage,
            permissions=None if permissions is None else coerce_permissions(permissions),
            deny_ops=mask,
            no_overlay=no_overlay,
            owned=owned,
            declared_caps=frozenset(storage.capabilities()),
        )
        async with self._mount_lock:
            # Re-checked under the lock: close() may have emptied the table
            # while the site probe's storage I/O was suspended.
            if not self._mounts:
                msg = f"Cannot mount at {mount_path}: filesystem is closed"
                raise ValueError(msg)
            refusal = self._gate_mount_site("mkdir", mount_path)
            if refusal is not None:
                msg = f"Cannot mount at {mount_path}: {refusal.error_message}"
                raise MountError(msg, result=refusal)
            if mount_path in self._mounts:
                msg = f"Mount already exists at: {mount_path}"
                raise ValueError(msg)
            for existing in self._sorted_mount_paths:
                if existing.startswith(mount_path + "/"):
                    msg = f"Cannot mount at {mount_path}: a deeper mount already sits at {existing}"
                    raise ValueError(msg)
                if existing != ROOT and mount_path.startswith(existing + "/") and self._mounts[existing].no_overlay:
                    msg = f"Cannot mount at {mount_path}: the mount at {existing} does not allow mounts beneath it"
                    raise ValueError(msg)
            if self._mounts[ROOT].no_overlay:
                msg = f"{self._class_name} does not allow child mounts"
                raise ValueError(msg)
            if any(m.storage is storage for m in self._mounts.values()):
                msg = f"Cannot mount at {mount_path}: that storage object is already mounted in this table"
                raise ValueError(msg)
            self._mounts[mount_path] = mount
            self._rebuild_sorted_mounts()

    async def _detach_mount(self, path: str) -> Mount:
        """Drop the mount at *path*, leaving its stored directory in place.

        Pure table surgery under the lock, no storage I/O, so it succeeds
        even against a dead or wedged backend.  Returns the removed mount
        so the caller can dispose the storage it owns.  Rejected while
        deeper mounts still sit beneath *path*, and where the gate would
        refuse a ``delete`` of the mount-point directory.
        """
        mount_path = self._normalize_mount_path(path)
        async with self._mount_lock:
            mount = self._require_mount(mount_path)
            deeper = [p for p in self._sorted_mount_paths if p.startswith(mount_path + "/")]
            if deeper:
                msg = f"Cannot unmount {mount_path}: deeper mounts exist at {', '.join(map(str, deeper))}"
                raise ValueError(msg)
            refusal = self._gate_mount_site("delete", mount_path)
            if refusal is not None:
                msg = f"Cannot unmount {mount_path}: {refusal.error_message}"
                raise MountError(msg, result=refusal)
            del self._mounts[mount_path]
            self._rebuild_sorted_mounts()
            return mount

    async def _probe_mount_site(self, mount_path: Path) -> str | None:
        """Prove the mount site is an existing empty directory, else say why.

        Storage I/O — runs outside the mount lock.  The owning entry is
        whichever mount holds the parent region; on a shared backend the
        answer can change before commit (unsynchronized shared admin), and
        the resulting states are the ordinary classified ones.  Failures
        dispatch on the error kind, not the bit: only ``not_found`` earns
        the mkdir advice — a dead backend surfaces its transport failure
        instead of advising a mkdir that cannot help.
        """
        if not self._mounts:
            return "filesystem is closed"
        terminal = self._resolve_terminal(mount_path)
        advice = f"no directory stored at the mount point (mkdir it, or add_mount(..., parents=True)): {mount_path}"
        stat = await self._call_storage(terminal.mount, "stat", path=terminal.rel, authority=_ADMIN_AUTHORITY)
        if not stat.success:
            blocker = next((f for f in stat.failures if kind_family(f.kind) is not ErrorKind.not_found), None)
            if blocker is None:
                return advice
            return blocker.message or f"could not stat the mount point: {mount_path}"
        row = next((o for o in stat.observations if o.path == terminal.rel), None)
        if row is None:
            return advice
        if row.kind != "directory":
            return f"the mount point is stored as {row.kind!r}, not a directory: {mount_path}"
        listed = await self._call_storage(terminal.mount, "ls", path=terminal.rel, authority=_ADMIN_AUTHORITY)
        if not listed.success:
            return listed.error_message or f"could not list the mount point: {mount_path}"
        if any(o.path != terminal.rel for o in listed.observations):
            return f"the mount-point directory is not empty: {mount_path}"
        return None

    @staticmethod
    def _normalize_mount_path(path: str, *, allow_root: bool = False) -> Path:
        """Canonicalize and validate a mount path through the :class:`Path` gate.

        The gate does the normalization and structural validation (make
        absolute, drop ``.``/``..``, strip per-segment whitespace, reject
        control characters and over-long segments).  A mount path adds only
        two policy rules the generic gate cannot know: it is never the root
        (except for ``update_mount``, which targets existing mounts and admits
        ``/`` via *allow_root* — root is an ordinary entry), and it never
        uses the reserved metadata segment (``".vfs"``).  Stray whitespace
        is canonicalized like any other path, not rejected; interior spaces
        (``"/My Documents"``) are preserved.
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

    @staticmethod
    def _validate_deny_ops(deny_ops: Iterable[Op]) -> frozenset[Op]:
        """Validate a mount-policy op mask — mutating/exec ops only.

        Read-family ops cannot be masked: mount policy is principal-blind,
        and read denial lives in the permission plane, where a principal is
        in scope.  The check is closed over the known read-family names, so
        unknown op names stay maskable if the vocabulary ever widens.
        Raises :class:`ValueError` naming the offending ops.
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

    def _rebuild_sorted_mounts(self) -> None:
        """Rebuild the pre-sorted mount path list, longest prefix first.

        Reverse-lexicographic is enough: only paths matching the same
        target need relative order, and those are always prefix-chains,
        where the proper prefix sorts strictly lower — so ``/`` lands last,
        the universal fallback.
        """
        self._sorted_mount_paths = sorted(self._mounts.keys(), reverse=True)

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
        """Write one file (*path* + *content* or *data*) or a batch of *entries*.

        Batch entries route by their own paths — grouped per entry,
        rebased, and gated per row before anything dispatches. *entries*
        and the single form are mutually exclusive, as are *content* (a
        text body) and *data* (a bytes body, whose text is a rendering
        the rebuild pass derives). The single form is sugar: this gate
        constructs the validated :class:`Entry`, and storage only ever
        receives entries — raw content never crosses the storage seam.

        *entries* is any iterable of :class:`Entry`, walked once here
        into a list; each storage then receives its own depth-sorted
        slice of it, never the iterable. An exception the iterable
        raises while it is walked propagates to the caller unchanged;
        nothing has been dispatched at that point.

        The parent chain must already exist as directories;
        ``parents=True`` mints the missing ancestors, ``mkdir -p`` style,
        and applies per call — every entry in a batch shares it.
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
        """Apply find-and-replace edits — a multi-edit verb by contract.

        *edits* is the native input: applied sequentially (each edit sees
        the content left by the previous one) and atomically (one failed
        match applies nothing) — guarantees the backend impl must honor.
        The *old*/*new* pair is sugar wrapping a one-item list; supplying
        both forms is a caller error.
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
        """Delete *path* (or each observation row) — always recoverable.

        Delete is reversible; sweep is not; agents only get the first.
        A deleted row stays where it is with a tombstone: it reads as
        absent everywhere (a refusal at its path carries the
        ``vfs.trashed`` hint), the ``/.vfs/trash`` view lists it at its
        own path, ``restore`` brings it back, and a ``write`` at its
        path revives it and keeps the body it replaced as a version.
        Each observation reports ``deleted_at``. A covered target rides
        with its covering root: restore the root, and the covered rows
        return with it. A live mount site is ``busy``: a mounted path, or
        a region holding mounted paths, must be unmounted before it can
        be deleted — the EBUSY rule.
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
        """Restore a deleted entry at its own path.

        *path* is the entry's path — the one the delete reported, since
        a deleted row never moves. Only the row a delete named restores,
        and everything deleted with it returns too; a row inside a
        deleted tree classifies ``not_found`` naming the root to restore.
        A live row at the site classifies ``exists`` — no verb displaces
        an occupant; the caller deletes it and restores again. A backend
        that keeps no trash classifies ``unsupported``. Like delete, a
        live mount site at the address is ``busy``.
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
        """Destroy at *path* — retention cleanup at a trash view, purge elsewhere.

        Delete is reversible; sweep is not; agents only get the first:
        sweep is a developer-plane verb, never registered on any
        agent-facing tool surface. The trash view's address runs
        retention — every row deleted longer ago than the mount's
        ``trash_days`` is destroyed with everything deleted alongside
        it. Any other address purges that subtree wholesale,
        immediately, regardless of retention age. The default address
        sweeps the root mount's trash; pass ``/m/.vfs/trash`` to sweep
        the mount at ``/m``. Explicit and idempotent — storage owns no
        background work.
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
        """Create a directory at *path* — pathlib-shaped flags, POSIX defaults.

        Strict by default: every ancestor must already exist as a
        directory, and an occupied site classifies ``exists``.
        ``parents=True`` mints the missing chain; ``exist_ok=True`` forgives
        an existing *directory* only — a file at the site stays ``exists``.
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
        """Create or touch typed edges — batch-native, touch/upsert.

        *edges* is the native input (validated :class:`Edge` models, so
        ``weight``/``distance`` are reachable); the *source*/*target*/
        *edge_type* triple is sugar constructing one ``Edge`` at this
        gate — the two forms are mutually exclusive. An existing
        identity is touched, its payload refreshed, and reports
        ``updated``; a duplicate identity within one batch refuses
        ``invalid``. Each edge's endpoints must resolve into the same
        mount (``cross_mount`` otherwise — cross-backend edges are a
        later story), and the write is permission-gated at both endpoint
        paths. *provenance* names the author class stamped on every edge
        in the call; ``extracted`` is reserved to the rebuild extractor.
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
        """Remove typed edges by their exact creating coordinates.

        The mirror of :meth:`mkedge`: batch-native with the triple as
        sugar, both endpoint paths permission-gated, cross-mount pairs
        refused. A missing edge is a per-row ``not_found`` warning,
        never a batch error — removing what is already gone leaves the
        same end state. The reserved ``"fs"`` type is unaddressable
        here, so the hierarchy mirror cannot be removed.
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
        """Match *pattern* against the namespace — unscoped calls reach every entry.

        Segment-aware semantics: ``*`` matches within one path segment,
        ``**`` spans segments, ``{a,b}`` alternates (expanded before
        anything else sees the pattern); any ``/`` anchors the pattern
        at each scope root (the namespace root when unscoped) while a
        slash-free pattern matches leaf names at any depth. A row is
        admitted by *pattern* and rejected by any *globs_not* glob, the
        *ext*/*ext_not* facts, and a *kind* mismatch. Scoping crosses
        the storage seam in one shape: each root rides beside the
        uncomposed :term:`arms <arm>` into the entry that owns it, so the plan and the
        SQL grow with roots plus arms rather than their product. A root
        that names an entry whole, or sits above one, composes into one
        spatial pattern instead, and residuation puts those members in
        each entry's own coordinates. Each entry answers its whole set
        in one call, as the same roots and arms composed would —
        so the match *set* is invariant to mount placement.
        Roots are find operands: a concurrent probe asserts each one
        (missing is a loud per-root error beside the healthy roots'
        rows) and serves the root's own row when the pattern matches it
        and no exclusion, ext fact, or kind fact rejects it. Each stage
        that matches rows (each entry's storage glob, the planning walk,
        each root probe) runs under the wall-time budget; a stage that
        reaches it returns what it finished and one ``truncated`` warning
        naming what shrinks it. Row order
        is merge order, and a *max_count* prefix of it can therefore
        differ across layouts.

        With *observations*, glob is a filter over the rows in hand:
        the path gates judge every row in one batch on the process's
        worker pool, under the wall-time budget (a call that reaches it
        returns the rows judged and one ``truncated`` warning), and rows
        serve exactly as held (columns, staleness, and input order
        included). Storage is
        touched only when *kind* is asked of a row that does not carry
        it — those rows are statted in one batch, a row that cannot be
        statted classifies loudly beside the healthy rows — chain into
        ``stat`` for fresh rows, or pass row paths to *paths* to search
        under them.

        *max_count* (>= 1) bounds each entry's answer **and** the merged
        result: a fan-out over N entries still returns at most
        *max_count* rows, kept in merge order — entries named via *paths*
        first, then mount-table order.
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
            filters=_PathFilters(admissions=arms, exclusions=globs_not, ext=ext, ext_not=ext_not),
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
        """Search content for *pattern* — unscoped calls reach every entry.

        *globs*/*globs_not* use glob's segment-aware pattern language:
        ``*`` within a segment, ``**`` across, any ``/`` anchors at the
        root, slash-free patterns match leaf names. Scoping crosses the
        storage seam the way glob's does — each root beside the
        uncomposed globs in the entry that owns it, the ``globs``
        channels entry-wide and residuated into each entry's
        coordinates — with a concurrent probe
        asserting the roots (a missing root is a loud per-root error beside the
        healthy roots' rows; a root's own content joins the scan when
        the caller's globs pass its path). *pattern* is content-only
        and never composes with paths.

        With *observations*, grep is a filter over the rows in hand:
        gates and matching run in memory, content is fetched (through
        each row's own entry, classifying loudly) only for rows that
        lack it, and a row whose known kind carries no content never
        matches. The index tier is not involved, so *allow_scan* and
        the refusal gate do not apply. The glob gates judge every row in
        one batch, and each distinct body is matched once, in batches,
        both on the process's worker pool, each stage under the
        storage tier's wall-time budget; a call that reaches it returns
        the matches found so far and one ``truncated`` warning.

        *max_count* caps matches **per file** (ripgrep's ``-m``), not the
        row count — a fan-out returns one row per matching file regardless.
        *allow_scan* opts into an index-refusing backend's scan tier;
        scan-tier backends accept it as a no-op.
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
            filters=_PathFilters(admissions=globs, exclusions=globs_not, ext=ext, ext_not=ext_not),
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
        """Ranked search: text in, one fused ranked list out.

        The caller never picks a retrieval strategy — backends index by
        vector, lexical, and graph signals and fuse the rankings however
        they see fit.  One answering entry's order and scores stand as
        the answer, trimmed to *limit*.  When more than one entry can
        answer, each is asked for ``min(3 * limit, 256)`` rows and the
        union is merged by :func:`vfs.rerank.merge_ranked`: one BM25 over
        the returned chunk texts on corpus-wide statistics puts the rows
        on one scale, and the order law keeps every entry's own order —
        an entry's rows never swap places, so each contributes a prefix
        of its own answer.  The merged scores are min-max scaled to the
        unit interval; a ``legs`` extra explains the merge.

        Scope is grep's: *globs*/*globs_not* use glob's segment-aware
        pattern language and *ext*/*ext_not* filter by extension;
        *paths* compose into the ``globs`` channel per scope root and
        residuate into each entry's coordinates before crossing the
        seam, with a concurrent probe asserting the roots.
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
        return await self._route_fanout(
            "search",
            paths=paths,
            observations=observations,
            ranked=_Ranked(query, limit, fanout_depth(limit)),
            filters=_PathFilters(globs, globs_not, ext, ext_not),
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
        """Walk the edges from the seeds — ``inbound``, ``outbound``, ``neighborhood`` — or ``meet`` them.

        A path routes to one entry; observations group by entry and each
        backend walks its own graph, so a walk can never follow an edge
        out of its storage. *depth* is the hops from the nearest seed
        (``None`` walks until nothing new is reached); *edge_types* selects
        the types followed (empty: every authored type, never ``fs`` unless
        named); *limit* bounds the node rows per storage, nearest first,
        and a cut is a ``truncated`` warning; *minimal* prunes a ``meet``
        to the nodes that keep the seeds connected. The answer carries the
        nodes with their ``depth`` and every selected edge among them.
        *method* is validated against the traversal vocabulary before any
        dispatch; the envelope reports the one ``traverse`` op — traversal is
        the whole verb, and analytics are index-time data, not queries.
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
        """Execute the tool at *path* with *arguments* — the execution verb.

        ``read``/``stat``/``ls`` discover a tool's definition; ``run`` is the only
        verb that executes it. Not a namespace mutation, so it takes no
        write-authorization gate.
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
        """Give *principal* — a user's ``sub`` or a ``group:<name>`` id — *level* at *path* and below.

        *level* is a rung of the ladder: ``list`` (names and kinds),
        ``read``, ``add`` (create, and alter one's own rows),
        ``contribute`` (also overwrite and edit anyone's), ``read_write``
        (also trash, move, restore and grant). Grants only widen: there
        is no deny row. The caller must hold
        ``read_write`` at *path* and everywhere beneath it for every subject
        it acts for, so nobody grants more than it holds. A grant replaces the principal's
        earlier row at the same path; the answer rides as ``grants=``.
        """
        refusal = self._gate_params("grant", path=path, principal=principal, level=level, authority=authority)
        if refusal is not None:
            return refusal
        return await self._route_grant("grant", path, principal=principal, level=level, authority=authority)

    async def revoke(self, path: str, principal: str, *, authority: Authority | None = None) -> Result:
        """Remove *principal*'s grant at exactly *path*, under the same gate as :meth:`grant`.

        A grant on an ancestor is untouched; revoke the row where it was
        granted. The caller needs ``read_write`` at *path* and everywhere
        beneath it, since the row reaches that far. A missing row answers
        with a warning, not a failure.
        """
        refusal = self._gate_params("revoke", path=path, principal=principal, authority=authority)
        if refusal is not None:
            return refusal
        return await self._route_grant("revoke", path, principal=principal, authority=authority)

    async def grants(self, path: str, *, authority: Authority | None = None) -> Result:
        """The grants that decide access at *path*: the rows on it and on its ancestors.

        A caller holding ``read_write`` at *path* sees every row; any
        other caller sees only its own, its groups', and the everyone
        rows. A path the caller cannot see answers ``not_found``.
        """
        refusal = self._gate_params("grants", path=path, authority=authority)
        if refusal is not None:
            return refusal
        return await self._route_grant("grants", path, authority=authority)

    async def set_posture(self, path: str, posture: Posture, *, authority: Authority | None = None) -> Result:
        """Set what everyone holds at *path* and below, named by the rung everyone holds.

        The posture words are the ladder's own: ``none`` gives everyone
        nothing, ``list`` the names, ``read`` the contents, ``add`` the
        right to create, ``contribute`` to edit anyone's rows,
        ``read_write`` everything (a fresh mount's default); grants still
        widen on top. The deepest posture covering a path decides it. A
        developer-plane verb: it reshapes a mount's policy.
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
        """Make *member* a direct member of *group* on the mount holding *path*.

        Groups nest: a *member* may itself be a ``group:`` id, up to a
        fixed depth, and a cycle is refused. Membership is mount-wide,
        so *path* only picks the mount. The system actor only.
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
        """Remove *member*'s direct membership of *group* on the mount holding *path*.

        The system actor only; a missing membership answers with a
        warning, not a failure.
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
        """Materialize a batch input (observations/entries/pairs) to a list, or
        ``None`` if it is not a batch — a non-iterable, or a bare ``str``/``bytes``.

        Materializing once rejects a non-iterable without leaking ``TypeError``,
        and lets the batch be walked more than once: a generator would otherwise
        be exhausted by the validation pass and vanish before dispatch.
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
        """Route a single-path or observation-based operation.

        With observations: group by entry, dispatch in parallel.  With
        path: resolve one entry and dispatch once.  Exactly one of *path* /
        *observations* arrives — the verb's params gate enforced the shape
        before delegating here.
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

        if op == "tree":
            return await self._tree_region(terminal, authority=authority, **kwargs)
        return await self._dispatch_entry(terminal.mount, op, path=terminal.rel, authority=authority, **kwargs)

    async def _dispatch_grouped_observations(
        self,
        op: Op,
        observations: list[Observation],
        *,
        ranked: _Ranked | None = None,
        authority: Authority | None = None,
        **kwargs: object,
    ) -> Result:
        """Route pre-grouped observation operations to their entries.

        Every input shape resolves against the same storage truth — a
        directory row classifies for a mutation exactly as the equivalent
        single-path call would.  Reads classify per row where the backend
        supports it; mutations are rejected whole at the gate.  Each row
        resolves once: the validated path both routes to its entry and
        rebases the row into entry coordinates.
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
        results = await self._gather_settled(
            self._dispatch_entry(mount, op, observations=group, authority=authority, **kwargs)
            for mount, group in groups.values()
        )
        merged = Result.merge(results, op=op)
        if ranked is None:
            return merged
        answers = list(zip((mount.path for mount, _group in groups.values()), results, strict=True))
        return await self._rank_fanout(ranked, answers, merged)

    def _observation_rows(self, op: Op, observations: object) -> tuple[list[Observation], Result | None]:
        """Materialize and type-check an observations batch, or refuse it whole."""
        rows = self._as_list(observations)
        if rows is None:
            detail = f"observations must be an iterable of Observation, got {type(observations).__name__}"
            return [], self._error(ErrorKind.invalid, op=op, detail=detail)
        for obs in rows:
            if not isinstance(obs, Observation):
                detail = f"observations must be Observation instances, got {type(obs).__name__}"
                return [], self._error(ErrorKind.invalid, op=op, detail=detail)
        return rows, None

    async def _tree_region(
        self,
        terminal: ResolvedTerminal,
        *,
        max_depth: int | None = None,
        columns: frozenset[str] | None = None,
        authority: Authority | None = None,
    ) -> Result:
        """Tree over a region: the owning entry's subtree plus descents into the mounts beneath it.

        The owning storage answers its own shape (mount-point directories
        are stored rows; rows under deeper mounts are shadow-filtered).  Each
        mount at segment distance ``s`` beneath the target then answers
        ``tree("/", max_depth - s)`` — skipped when the remaining budget is
        ``<= 0`` (its stored directory row stays) and skipped with an
        info-severity coverage record when incapable, as in an unscoped
        fan-out.  Descents merge under the zero-progress rule: a dead
        descent among live rows demotes to a warning; the named target
        itself failing stays a loud failure.  *max_depth* arrives gated
        (integer ``>= 1`` or ``None``) — the depth rule is the router's,
        declared in the params table.
        """
        grant = self._enter_hop(op="tree")
        if grant.refusal is not None:
            return grant.refusal
        try:
            full = terminal.full
            own = await self._dispatch_entry(
                terminal.mount, "tree", path=terminal.rel, max_depth=max_depth, columns=columns, authority=authority
            )
            if not own.success:
                return own

            descents: list[tuple[Mount, int | None]] = []
            skips: list[ResultError] = []
            for mount in self._mounts_beneath(full):
                tail = mount.path.without_mount(full)
                distance = len(tail.strip("/").split("/"))
                budget = None if max_depth is None else max_depth - distance
                if budget is not None and budget <= 0:
                    continue
                if "tree" not in mount.caps:
                    skips.append(self._skip_entry("tree", mount))
                    continue
                descents.append((mount, budget))

            results: list[Result] = [own]
            results.extend(
                await self._gather_settled(
                    self._dispatch_entry(
                        mount, "tree", path=ROOT, max_depth=budget, columns=columns, authority=authority
                    )
                    for mount, budget in descents
                )
            )
            return self._with_skips(Result.merge_branches(results, op="tree"), skips)
        finally:
            self._exit_hop(grant.token)

    async def _route_grant(self, op: Op, path: str, *, authority: Authority | None, **kwargs: Any) -> Result:
        """Route a grant verb to the mount holding *path*, and rebase the rows it answers with.

        The grant verbs address a prefix, not a row, so no mutation path
        rule applies (the root takes a posture like any path); the
        writing ones pass the mount's permission layers. The membership
        verbs use *path* only to pick the mount.
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
        filters: _PathFilters | None = None,
        authority: Authority | None = None,
        **kwargs: object,
    ) -> Result:
        """Route a namespace-wide query: everywhere, a scope subset, or rows.

        *kwargs* forwards to storage verbatim — this function strips and
        peeks nothing (:meth:`_glob_dispatches` reads ``kind`` and
        ``columns`` for its root probe, forwarding both untouched), with
        one declared exception: the ranked verb (*ranked* set) forwards
        ``limit`` as the fan-out depth when more than one entry may
        answer, and its rows merge through :meth:`_rank_fanout` instead
        of the row cap.
        *filters* is the pattern-search verbs' one typed
        argument: the dispatch builders compose and residuate its glob
        channels per scope root and forward its ext channels as-is.

        With observations: reuse grouped dispatch.  With scope paths: group
        the scopes by entry — a scoped entry that cannot answer errors
        ``unsupported``, like the single shape.  A scope with mounts
        beneath it names a *region*, not an entry: it expands to the owning
        entry scoped to it plus every mount strictly beneath it dispatched
        unscoped, under the unscoped capability rule.  With neither: every
        entry in table order.  An unscoped entry that cannot answer is
        skipped with an info-severity coverage record — one incapable
        catalog must not fail a region query, but the gap goes on record.

        Unscoped branches merge under the zero-progress rule
        (``merge_branches``): a dead entry among answering ones demotes to
        a warning; all dead stays a failure.  Entries the caller named
        merge plain — scoped dispatch never demotes, so a named entry
        fails loudly whatever its siblings produced.  That pin survives
        subsumption: when a sibling region also covers a named entry, the
        entry dispatches once (unscoped) but its result still merges
        plain.  The pattern-search verbs build their dispatches apart
        (:meth:`_glob_dispatches` / :meth:`_grep_dispatches`): scoping
        crosses the seam in one shape, roots beside the arms and the
        pattern channels entry-wide, one batched call per entry,
        with root assertions on a concurrent probe that no dispatch
        shape can drop.  *row_cap*
        re-applies the caller's result bound after the merge on every
        input shape, keeping merge order, so it cannot multiply by entry
        count; the bound arrives gated (integer ``>= 1`` or ``None``).

        *paths* / *observations* exclusivity and the *row_cap* bound are
        enforced by the verbs' params gate before delegation.
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
            plan = self._classify_fanout_scopes(op, paths)
            if plan.refusal is not None:
                return plan.refusal
            if ranked is not None and len({*plan.scoped, *plan.unscoped}) > 1:
                kwargs = {**kwargs, "limit": ranked.depth}

            if filters is not None:
                if op == "glob":
                    built = await self._glob_dispatches(plan, paths, filters, authority=authority, **kwargs)
                else:
                    built = await self._grep_dispatches(plan, paths, filters, op=op, authority=authority, **kwargs)
                if built is None:
                    return self._closed_error(op)
                named_coros, branches, skips = built
            else:
                # Unscoped subsumes a narrower scope into the same entry.
                named_coros = [
                    self._dispatch_entry(mount, op, paths=tuple(dict.fromkeys(rels)), authority=authority, **kwargs)
                    for key, (mount, rels) in plan.scoped.items()
                    if key not in plan.unscoped
                ]
                branches = [
                    (mount.path, self._dispatch_entry(mount, op, paths=(), authority=authority, **kwargs))
                    for mount in plan.unscoped.values()
                ]
                skips = plan.skips
            if not named_coros and not branches:
                return self._with_skips(Result(ops=(op,)), skips)
            results = await self._gather_settled([*named_coros, *(coro for _, coro in branches)])
            named = results[: len(named_coros)]
            branch_results = list(zip((path for path, _ in branches), results[len(named_coros) :], strict=True))
            merged = self._merge_fanout(named, branch_results, frozenset(plan.scoped), op)
            if ranked is not None:
                return self._with_skips(await self._rank_fanout(ranked, branch_results, merged), skips)
            return self._with_skips(self._cap_rows(merged, op, row_cap), skips)
        finally:
            self._exit_hop(grant.token)

    def _classify_fanout_scopes(self, op: Op, paths: tuple[str, ...]) -> _FanoutPlan:
        """Classify a fan-out's targets into the entries that will answer.

        No paths: every entry in table order — capable entries dispatch
        whole, incapable ones become skip records.  A path with mounts
        beneath it (or the root) names a *region*: the owning entry
        answers its scope, deeper mounts answer whole, both under the
        recorded-skip rule.  A plain path names one entry, which is
        gated — a scoped entry that cannot answer refuses loudly, like
        the single shape.  Refusals (invalid path, gate denial) come
        back on the plan; the collections are then empty.
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
                terminal = self._resolve_terminal(full)
                beneath = self._mounts_beneath(full)
                if full == ROOT or beneath:
                    if op not in terminal.mount.caps:
                        skipped.setdefault(terminal.mount.path, self._skip_entry(op, terminal.mount))
                    elif terminal.rel == ROOT:
                        unscoped.setdefault(terminal.mount.path, terminal.mount)
                    else:
                        _b, rels = scoped.setdefault(terminal.mount.path, (terminal.mount, []))
                        rels.append(terminal.rel)
                    for mount in beneath:
                        if op in mount.caps:
                            unscoped.setdefault(mount.path, mount)
                        else:
                            skipped.setdefault(mount.path, self._skip_entry(op, mount))
                    continue
                err = self._gate_entry(terminal.mount, op, write_rels=(terminal.rel,))
                if err is not None:
                    return _FanoutPlan({}, {}, [], refusal=err)
                _b, rels = scoped.setdefault(terminal.mount.path, (terminal.mount, []))
                rels.append(terminal.rel)
        else:
            for mount in self._mounts.values():
                if op in mount.caps:
                    unscoped[mount.path] = mount
                else:
                    skipped.setdefault(mount.path, self._skip_entry(op, mount))

        return _FanoutPlan(scoped=scoped, unscoped=unscoped, skips=list(skipped.values()))

    async def _glob_dispatches(
        self,
        plan: _FanoutPlan,
        paths: tuple[str, ...],
        filters: _PathFilters,
        *,
        authority: Authority | None,
        **kwargs: object,
    ) -> _Dispatches | None:
        """Build glob's dispatches: scoping crosses the seam in one shape, an entry's roots beside the uncomposed arms.

        The caller's pattern arrives brace-expanded as the filters'
        *admissions* (its arms) and ``globs_not`` as their *exclusions*;
        every step below is per-arm with any-arm admission and
        any-exclusion rejection. An entry receives every root strictly
        beneath it beside the uncomposed arms as its ``scope=`` channel,
        and storage reads the law (a row beneath a root, its remainder
        or its name matching an arm) without composing. Two bounded
        kinds of root compose each arm into one spatial pattern instead
        (name arm goes ``root/**/pattern``, path arm anchors under the
        root): a root whose joined text must be read whole, and a root
        above a nested entry, which reaches that entry and never an
        ancestor's shadowed region. Residuation derives those members in
        entry-local coordinates, exclusions composing per root
        identically, so one can never reach another root's subtree, and
        each entry receives its whole deduped set in the same one call.
        That planning walk, :mod:`vfs.fanout`'s, runs in one hop on the
        process pool under its own wall; a walk
        that reaches it dispatches the roots it planned whole and says
        so. Root assertions ride a separate concurrent
        probe grouped by owning entry (:meth:`_root_probe`),
        structurally immune to any dispatch optimization; it judges a
        root's own row against the name arms alone, since a path arm
        composed under a root needs one more segment than the root has,
        and honors every channel, so a root row is never served past a
        filter the caller stated. A dead residual set is routing, not a
        capability gap: the entry is not dispatched and no skip is
        minted; capability skips survive only where some arm can reach
        the entry's rows. ``None`` answers a ``close()`` that landed
        during a hop: nothing is read from the cleared table, and nothing
        is dispatched.
        """
        arms, exclusions, ext, ext_not = filters
        roots = tuple(dict.fromkeys(root for raw in paths if (root := resolve_path(raw).path) is not None))
        capable = {**plan.unscoped, **{key: mount for key, (mount, _rels) in plan.scoped.items()}}
        owners = {root: self._resolve_terminal(root).mount.path for root in roots}
        skip_paths = tuple(skip.path for skip in plan.skips if skip.path is not None)
        name_arms = tuple(arm for arm in arms if "/" not in arm)
        gates = compile_gates(name_arms, exclusions, ext=ext, ext_not=ext_not) if name_arms else None
        scope = await self._planned(owners, tuple(capable), skip_paths, roots, arms, exclusions, arms, frozenset())
        if not self._mounts:
            return None  # a close() landed during the hop: no table read, no dispatch
        kind = cast("str | None", kwargs.get("kind"))
        columns = cast("frozenset[str] | None", kwargs.get("columns"))
        probes, unverifiable = self._root_probes(roots, gates, kind, columns, authority=authority)
        branches: list[tuple[Path, Coroutine[Any, Any, Result]]] = [
            (
                key,
                self._dispatch_entry(
                    capable[key],
                    "glob",
                    patterns=tuple(sorted(live or ())),
                    globs_not=tuple(sorted(scope.exclusions[key])),
                    ext=ext,
                    ext_not=ext_not,
                    authority=authority,
                    **_scoped(scope, key),
                    **kwargs,
                ),
            )
            for key, live in scope.members.items()
            if live or key in scope.scopes
        ]
        return _Dispatches(probes, branches, self._scope_skips(plan, scope, unverifiable))

    async def _grep_dispatches(
        self,
        plan: _FanoutPlan,
        paths: tuple[str, ...],
        filters: _PathFilters,
        *,
        op: Op = "grep",
        authority: Authority | None,
        **kwargs: object,
    ) -> _Dispatches | None:
        """Build grep's dispatches (search's too): scoping crosses the seam in one shape, roots beside the globs.

        Glob's dispatch shape on grep's filters (*admissions* is the
        caller's ``globs``, *exclusions* its ``globs_not``, the ext
        channels forward as-is): each scope
        root rides its entry's ``scope=`` channel beside the caller's globs
        (no caller globs → the one arm ``**``), exclusions ride beside them so
        one can never reach another root's subtree, and a root whose path passes
        the caller's globs rides the ``globs`` batch as its own literal path — find's
        operand law; the content test can only happen at storage, so for
        grep the root row joins the scan, not the probe. Those admissions
        are judged once per call, every distinct root in one hop on the
        process pool; no globs admit every root. Residuation, the owner
        gate, dead-entry skips, the planning walk, the two bounded kinds
        of root that compose into the ``globs`` batch (each root's literal
        staying on that batch too) and the root probe are the glob
        machinery; the probe serves no rows, only classifications.
        ``None`` answers a ``close()`` that landed during a hop.
        """
        globs, exclusions, ext, ext_not = filters
        roots = tuple(dict.fromkeys(root for raw in paths if (root := resolve_path(raw).path) is not None))
        capable = {**plan.unscoped, **{key: mount for key, (mount, _rels) in plan.scoped.items()}}
        owners = {root: self._resolve_terminal(root).mount.path for root in roots}
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
        scope = await self._planned(
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
                    self._dispatch_entry(
                        mount,
                        op,
                        globs=tuple(sorted(members)) if members else (),
                        globs_not=tuple(sorted(scope.exclusions[key])),
                        ext=ext,
                        ext_not=ext_not,
                        authority=authority,
                        **_scoped(scope, key),
                        **kwargs,
                    ),
                )
            )
        probes, unverifiable = self._root_probes(roots, None, None, None, authority=authority)
        return _Dispatches(probes, branches, self._scope_skips(plan, scope, [*records, *unverifiable]))

    @staticmethod
    async def _planned(
        owners: dict[Path, Path],
        keys: tuple[Path, ...],
        skip_paths: tuple[Path, ...],
        roots: tuple[Path, ...],
        patterns: tuple[str, ...],
        exclusions: tuple[str, ...],
        reach: tuple[str, ...],
        literals: frozenset[Path],
    ) -> ScopePlan:
        """The fan-out's scope plan: the residual walk in one hop under its wall, or in place when nothing residuates.

        A call with no root, no path-arm pattern and no capability skip
        only copies its name arms to each entry, linear in its arms, so it
        is planned in place; every other walk leaves the loop.
        """
        if not walks(roots, patterns, exclusions, skip_paths):
            return plan_scope(owners, keys, skip_paths, roots, patterns, exclusions, reach, literals, Deadline.never())
        deadline = Deadline.after(WALL_TIME_BUDGET)
        walk = partial(plan_scope, owners, keys, skip_paths, roots, patterns, exclusions, reach, literals, deadline)
        return await call_offloaded(offload_pool(), walk)

    @staticmethod
    def _scope_skips(plan: _FanoutPlan, scope: ScopePlan, records: list[ResultError]) -> list[ResultError]:
        """The coverage records a fan-out carries: the reached skips, the stage records, and a planning stop."""
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
        authority: Authority | None,
    ) -> tuple[list[Coroutine[Any, Any, Result]], list[ResultError]]:
        """One point-read probe per owning entry, asserting its named roots.

        The namespace root is exempt — it is the namespace itself, never
        a row. An entry that cannot answer ``stat`` leaves its roots
        honestly undeterminable: a warning on record, never coerced to
        absent, never a silent pass. *gates* judge the roots' own rows
        (``None``: no row is served), on the process pool.
        """
        grouped: dict[Path, tuple[Mount, list[Path]]] = {}
        unverifiable: list[ResultError] = []
        for root in roots:
            if root == ROOT:
                continue
            terminal = self._resolve_terminal(root)
            if "stat" not in terminal.mount.caps:
                unverifiable.append(
                    classified(
                        ErrorKind.unsupported,
                        root,
                        severity=Severity.warning,
                        source=terminal.mount.path,
                        detail="the root is unverifiable: the storage mounted here does not support stat",
                    )
                )
                continue
            _b, rels = grouped.setdefault(terminal.mount.path, (terminal.mount, []))
            rels.append(terminal.rel)
        coros: list[Coroutine[Any, Any, Result]] = [
            self._root_probe(mount, rels, gates, kind, columns, authority=authority) for mount, rels in grouped.values()
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
        authority: Authority | None,
    ) -> Result:
        """Assert scope roots with one batched point-read against their entry.

        A missing root classifies loud through the entry's own descent
        ladder; *gates* decide whether a present root's row joins the
        result — glob serves it when a name arm matches and no
        exclusion, ext fact or *kind* rejects it (find semantics:
        operands are tested, never exempt), grep serves none (a root's
        content test can only happen at storage). The rows are judged in
        one hop under a wall read when judging starts; a hop that did
        not finish serves only the rows it judged, with one warning.
        """
        probe = [Observation(path=rel) for rel in dict.fromkeys(rels)]
        result = await self._dispatch_entry(mount, "stat", observations=probe, columns=columns, authority=authority)
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
        """Merge fan-out answers under the pinning rule — a pure function.

        Branches whose mount path the caller also *named* (subsumed
        scopes) merge plain: the caller asked after that entry, so its
        failure stays loud whatever its siblings produced.  Only the
        unpinned branches enter the zero-progress demotion pool.
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
        """Route src/dest pair mutations, gating every pair before any dispatch.

        Pairs arrive as caller-facing :class:`TwoPathOperation` and dispatch
        as gated, entry-relative :class:`ResolvedPair` groups.  Both
        endpoints of a pair must resolve to the same **entry** — a pair
        spanning entries is ``cross_mount`` (the EXDEV rule; no silent
        copy-and-delete), and a pair that would move a mount site is
        ``busy``.  ``move`` mutates both endpoints, so both are write-gated;
        ``copy`` only writes ``dest``.

        All pairs are *validated* up front: a single bad pair rejects the
        whole batch with nothing dispatched.  Atomicity stops at validation
        — once per-entry dispatch begins, entries run concurrently and a
        runtime failure in one does not roll back another.
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

        results = await self._gather_settled(
            self._dispatch_entry(mount, op, operations=group, authority=authority, **kwargs)
            for mount, group in groups.values()
        )
        return Result.merge(results, op=op)

    @staticmethod
    def _coerce_two_path(item: object) -> TwoPathOperation | None:
        """Coerce a batch item to a ``TwoPathOperation``, or ``None`` if malformed.

        Accepts a ``TwoPathOperation`` as-is or a 2-tuple/list of two strings.
        Anything else — wrong arity, non-string members, a stray ``str`` that
        a ``Sequence`` iteration would splatter into characters — is rejected
        so the caller sees ``invalid`` instead of a raw ``TypeError``.
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
        """Shared move/copy front: normalize the src/dest-or-batch input, then route.

        The verb's params gate enforced src/dest-xor-batch before delegating;
        each batch item is coerced through :meth:`_coerce_two_path`, so a
        malformed pair is an ``invalid`` result rather than an uncaught
        ``TypeError``.
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
        """Route a batch write, grouping entries by owning entry via each path.

        The entry-path analogue of grouped-observation dispatch: every
        entry's path is mutation-resolved and write-gated before anything
        dispatches, then each entry group is rebased into local coordinates
        via :meth:`Entry.without_mount`.

        Each group dispatches parents-before-children (stable depth sort),
        so backends adjudicate the batch as a set — "can all of this be
        written together" — never as a sequence the caller had to order.
        A directory entry therefore satisfies the parent gate for deeper
        entries in the same batch regardless of caller order, while
        duplicate targets keep caller order and last-write-wins.
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

        results = await self._gather_settled(
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
        """Route an edge batch, grouped by the mount owning both endpoints.

        The edge analogue of the write batch: every edge's endpoints are
        resolved and both must be writable before anything dispatches;
        the rebased models cross the seam. Endpoint eligibility is a
        path fact and outranks the mount fact — the same bad endpoint
        classifies alike on any topology — and a duplicate identity
        within one batch refuses ``invalid``: last-write-wins would hide
        caller bugs.
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
        results = await self._gather_settled(
            self._dispatch_entry(mount, op, edges=group, authority=authority, **extra)
            for mount, group in groups.values()
        )
        return Result.merge(results, op=op)

    # -------------------------------------------------------------------
    # hop budget — loops survived, not detected
    # -------------------------------------------------------------------

    def _enter_hop(self, *, op: Op) -> _HopGrant:
        """Decrement the per-request router-traversal budget, or refuse.

        The budget is a request-scoped context value shared across every
        router the request passes through (adapters re-enter in the same
        context; the wire dialect carries it across processes).  Opaque
        storages make cycle *detection* impossible by design, so the
        unbounded verbs are made finite instead — exhaustion classifies as
        ``budget_exhausted`` rather than hanging.
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
        """Restore the caller's budget on the way out of a routed request."""
        if token is not None:
            _hop_budget.reset(token)

    # -------------------------------------------------------------------
    # resolution — one table, longest prefix
    # -------------------------------------------------------------------

    def _match_mount(self, path: Path) -> Mount | None:
        """Longest-prefix mount for *path* — ``None`` only when closed."""
        for mount_path in self._sorted_mount_paths:
            if mount_path == ROOT or path == mount_path or path.startswith(mount_path + "/"):
                return self._mounts[mount_path]
        return None

    def _resolve_terminal(self, path: Path) -> ResolvedTerminal:
        """Resolve a gated :class:`Path` to its owning entry plus residual.

        A single longest-prefix match — nested mounts are ordinary deeper
        rows in the same table, so there is nothing to recurse into.  The
        root identity entry backstops every path; callers guard the
        closed-table case before resolving.
        """
        mount = self._match_mount(path)
        assert mount is not None, "resolve on a closed filesystem"
        return ResolvedTerminal(mount=mount, rel=path.without_mount(mount.path))

    async def _probe_location(self, terminal: ResolvedTerminal, row: Location, authority: Authority) -> Location:
        """*row* with the storage's answer about the entry — direct stat under *authority*, no router gate."""
        stat = await self._call_storage(terminal.mount, "stat", path=terminal.rel, authority=authority)
        if not stat.success:
            blocker = next((f for f in stat.failures if kind_family(f.kind) is not ErrorKind.not_found), None)
            if blocker is None:
                return row._replace(exists=False)
            return row._replace(note=blocker.message or f"could not stat {row.path}")
        found = next((o for o in stat.observations if o.path == terminal.rel), None)
        if found is None:
            return row._replace(exists=False)
        return row._replace(exists=True, kind=found.kind)

    def _locate_terminal(self, path: str) -> ResolvedTerminal:
        """Gate a caller path and resolve it, raising where no row can answer."""
        resolved = resolve_path(path)
        if resolved.path is None:
            raise ValueError(resolved.error)
        mount = self._match_mount(resolved.path)
        if mount is None:
            msg = f"Cannot locate {resolved.path}: filesystem is closed"
            raise ValueError(msg)
        return ResolvedTerminal(mount=mount, rel=resolved.path.without_mount(mount.path))

    def _mounts_beneath(self, path: Path) -> list[Mount]:
        """The mounts strictly beneath *path* (router coordinates).

        Routing state, not visibility: region expansion, tree descents, the
        busy guard, and shadow filtering all read it.
        """
        if path == ROOT:
            return [b for p, b in self._mounts.items() if p != ROOT]
        return [b for p, b in self._mounts.items() if p.startswith(path + "/")]

    # -------------------------------------------------------------------
    # gates — capability snapshot, then composed permissions
    # -------------------------------------------------------------------

    def _gate_params(self, op: Op, /, **params: object) -> Result | None:
        """Refuse type, domain, and input-shape garbage before anything else.

        The rules live in the per-op table (``vfs.params``); a violation
        classifies ``invalid`` naming the parameter.  Caller-input facts
        outrank every router-state fact, so this gate runs first at every
        public verb — a bad parameter reports ``invalid`` even on a closed
        table or a busy path.  Identity is not gated here: a call that
        names no authority runs as the default or as anonymous (see
        :meth:`_admitted`), and a mount whose posture wants a name is the
        one that refuses.
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
        """Capability → grammar → permission, in the pinned order.

        Every dispatch chokepoint runs this gate on its resolved entry
        before touching it.  The order is a contract: an incapable entry
        reads as ``unsupported``, never as a policy denial.  Existence and
        kind are storage truth, classified by the backend at dispatch — the
        gate holds only what the router itself knows.

        A capability failure is an entry-level fact and reports the entry's
        mount path.  *write_rels* are the entry-relative paths a mutation
        targets (empty when the write target is derived later, as in
        mkedge's pre-derivation gate): each passes the reserved-space
        grammar in the mount's own coordinates — the global gate cannot
        see a trash view beneath a mount — and then the permission
        layers; each refusal reports its own router-side path.
        *read_rels* are the paths a mutation reads without writing (a
        copy's source): they pass the grammar alone, so a transfer out of
        the trash view is ``invalid`` at the path the caller sent, never
        the storage's ``not_found`` at a view head it holds no row for.
        With *subtree*, a written path is also refused when a ``read``
        rule of any layer lies beneath it, for a verb whose effect
        reaches beneath its path.
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
        """The permission maps governing *full*, outermost entry first.

        Every entry whose path prefixes *full* contributes its map (when it
        has one), with the path rebased into that entry's own coordinates —
        restriction composes downward and can only tighten.
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

    def _gate_mount_site(self, op: Op, mount_path: Path) -> Result | None:
        """Gate a mount change as the write it is at its mount point: ``mkdir`` to attach, ``delete`` to detach.

        The mount-point directory is stored by the mount above
        *mount_path*, so that mount's capabilities and every permission
        map above the site decide: a parent that is read-only there, or
        that masks the op, keeps its mount table as it is.  The mount at
        *mount_path* itself has no say — its map governs what is beneath
        it, never its own site.  No storage I/O; the caller holds the
        mount lock and has refused a closed table.
        """
        owner = self._mount_point_owner(mount_path)
        if op not in owner.caps:
            return self._error(
                ErrorKind.unsupported,
                op=op,
                path=owner.path,
                detail=f"operation {op!r} is not declared by the storage that holds the mount point",
            )
        above = [layer for layer in self._permission_layers(mount_path) if layer.mount_prefix != mount_path]
        return check_writable_composed(above, op)

    def _require_mount(self, mount_path: Path) -> Mount:
        """The mount at *mount_path*, or a ``ValueError`` when there is none."""
        mount = self._mounts.get(mount_path)
        if mount is None:
            msg = f"No mount at: {mount_path!r}"
            raise ValueError(msg)
        return mount

    def _mount_point_owner(self, mount_path: Path) -> Mount:
        """The mount whose storage holds the directory at *mount_path*. The root mount holds its own."""
        return next(self._mounts[p] for p in self._sorted_mount_paths if p == ROOT or mount_path.startswith(p + "/"))

    async def _require_mount_rights(self, change: str, mount_path: Path, authority: Authority | None) -> None:
        """Raise unless the caller holds ``read_write`` at the mount point at *mount_path*.

        The storage that holds the mount point judges. The system actor
        holds every level, so no storage is asked for it. A storage that
        declares no grant verb keeps no rights to go around, and one that
        keeps grants and cannot answer refuses. This is storage I/O, so it
        runs before the mount lock is taken and before anything changes.
        """
        who = self._admitted(authority)
        if who.is_system or not self._mounts:
            return
        owner = self._mount_point_owner(mount_path)
        storage, refusal = owner.storage, None
        if isinstance(storage, SupportsHolds):
            rel = mount_path.without_mount(owner.path)
            try:
                answer = await storage.holds(path=rel, level="read_write", authority=who)
            except TransportError as exc:
                detail = f"the transport failed: {exc}"
                answer = self._error(ErrorKind.backend_unavailable, op=HOLDS, path=ROOT, detail=detail)
            refusal = None if answer.success else answer.with_mount(owner.path)
        elif owner.declared_caps & GRANT_OPS:
            detail = "the storage that holds the mount point keeps grants and cannot say what the caller holds"
            refusal = self._error(ErrorKind.unsupported, op=HOLDS, path=owner.path, detail=detail)
        if refusal is not None:
            msg = f"Cannot {change} {mount_path}: {refusal.error_message}"
            raise MountError(msg, result=refusal)

    def _busy_guard(self, op: Op, full: Path, *, subtree: bool) -> Result | None:
        """Refuse a data-plane mutation that targets a live mount site.

        The EBUSY rule: a mounted path (or, with *subtree*, a region holding
        mounted paths) may not be deleted or moved out from under its mount
        — a dangling mount whose stored site is gone would be worse than
        the refusal.  Unmount first.
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
        """Dispatch *op* to an entry and bring the result back to router coordinates.

        The single outbound/inbound seam: call the entry's storage, rebase
        under the entry path, then drop rows shadowed by deeper mounts.
        Every routed dispatch — single, grouped, paired, fan-out, tree —
        funnels through here.
        """
        result = await self._call_storage(mount, op, authority=authority, **kwargs)
        result = result.with_mount(mount.path)
        return self._shadow_filter(result, mount)

    async def _call_storage(
        self,
        mount: Mount,
        op: Op,
        *,
        authority: Authority | None = None,
        **kwargs: Any,
    ) -> Result:
        """The exhaustive op → typed-method match beneath the funnel.

        The chokepoints upstream carry *op* as a variable, so this match is
        where the op meets a typed method: one boring arm per op, ending in
        ``assert_never``, so adding a verb to ``ops.py`` fails ``ty`` until
        the funnel routes it.  A family the backend does not satisfy
        classifies ``unsupported`` — reachable only when a declared
        capability over-claims the implementation, never a raw
        ``AttributeError``.  A :class:`TransportError` — a wire backend's
        dead peer — normalizes to ``backend_unavailable``; any other raw
        exception is a backend bug and propagates.

        The seam invariant for every entry-level failure minted here: the
        error is in entry coordinates, anchored at the entry root
        (``path=ROOT``), and the funnel's rebase turns that anchor into
        the mount path on the way out (identity for the root entry).

        Transactions live behind these methods: a backend opens and commits
        its own session inside each op — the router never sees one.

        Storage always receives an authority: the call's own, else the
        configured default, else anonymous (see :meth:`_admitted`).
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
        """The authority the funnel hands storage.

        The call's own; else the configured ``default_authority`` (the
        ETL shape, ``Authority.system()``); else the anonymous principal,
        which holds only what each mount's posture gives everyone.
        Absence is a name, never a blank: storage and the audit always
        see an actor.
        """
        if authority is not None:
            return authority
        if self._default_authority is not None:
            return self._default_authority
        return _ANONYMOUS_AUTHORITY

    def _backend_unsupported(self, op: Op) -> Result:
        """The funnel's narrowing miss: the backend lacks *op*'s family.

        Entry-anchored under the funnel's seam invariant (see
        :meth:`_call_storage`): ``path=ROOT`` rebases to the mount path.
        """
        return self._error(ErrorKind.unsupported, op=op, path=ROOT, detail=f"the storage does not implement {op!r}")

    def _shadow_filter(self, result: Result, mount: Mount) -> Result:
        """Drop rows a deeper mount shadows — the full-shadow mount rule.

        A row strictly under a deeper mount path belongs to that mount's
        storage, whatever the shallower storage happens to hold there
        (crash orphans, rows written by another client of shared storage).
        The row *at* the mount path survives: it is the stored mount-point
        directory, visible in listings like any other.
        """
        deeper = [b.path for b in self._mounts_beneath(mount.path)]
        if not deeper or not result.observations:
            return result
        kept = [o for o in result.observations if not any(o.path.startswith(p + "/") for p in deeper)]
        if len(kept) == len(result.observations):
            return result
        return result.model_copy(update={"observations": kept})

    # -------------------------------------------------------------------
    # settlement and merging
    # -------------------------------------------------------------------

    @staticmethod
    async def _gather_settled(coros: Iterable[Coroutine[Any, Any, Result]]) -> list[Result]:
        """Run dispatch coroutines to completion — every sibling settles.

        ``Result`` is the only failure channel a verb has, so an exception
        here is an impl bug (or cancellation, which re-raises untouched).  A
        bug propagates only *after* all siblings finish: a partial batch can
        never keep mutating behind a caller who already saw a failure, and
        any retry logic upstream sees a settled world.

        Precedence is deliberate: cancellation outranks impl bugs.  When a
        settled batch holds both, the ``CancelledError`` re-raises and the
        bug is dropped — suppressing cancellation to surface a bug would
        break task-teardown semantics, and everything has settled either way.
        """
        settled = await asyncio.gather(*coros, return_exceptions=True)
        bugs: list[Exception] = []
        for item in settled:
            if isinstance(item, BaseException) and not isinstance(item, Exception):
                raise item
            if isinstance(item, Exception):
                bugs.append(item)
        raise_lone_or_group(bugs, "impl errors during dispatch")
        return [item for item in settled if isinstance(item, Result)]

    def _skip_entry(self, op: Op, mount: Mount) -> ResultError:
        """Info-severity coverage record for an entry an unscoped fan-out
        or tree descent skipped as incapable — recorded, never a failure.

        Minted in router coordinates above the rebase seam, so the mount
        path is stamped as both anchor (``path``) and provenance
        (``source``) here.
        """
        return classified(
            ErrorKind.unsupported,
            mount.path,
            severity=Severity.info,
            source=mount.path,
            detail=f"skipped: operation {op!r} is not declared by the storage mounted here",
        )

    @staticmethod
    def _with_skips(result: Result, skips: list[ResultError]) -> Result:
        """Append capability-skip records after the merge — coverage facts
        must never feed the zero-progress rule's branch arithmetic."""
        if not skips:
            return result
        return result.model_copy(update={"errors": [*result.errors, *skips]})

    async def _rank_fanout(self, ranked: _Ranked, answers: list[tuple[Path, Result]], merged: Result) -> Result:
        """Order the ranked verb's rows: one answering entry stands; several merge under the order law.

        *answers* pairs each entry's mount path with its rebased result in
        dispatch order; *merged* is their envelope.  The merge's rows
        replace the envelope's, its records append, and its explanation
        rides as the ``legs`` extra.
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
        """Re-apply the caller's result bound after a merge.

        Merge order stands (named scopes first, then mount-table order),
        untouched by stray scores; the ranked verb never arrives here —
        its merge trims by its own law.  Errors and warnings are never
        trimmed.
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
        """Compose a failed ``Result`` from a fact.  The router never raises —
        values in, ``Result`` out; raising is the call boundary's job
        (``raise_if_failed``).

        Pass the structured *kind* and the producing *op* — the router
        always knows its verb and a failure always reports it — plus the
        locus, the second entry and a path-free *detail* as the fact has
        them; the words come from the contract table.  The verdict is
        derived from the entries, never stored.  Callers that already hold
        a shaped ``Result`` should return it directly.
        """
        fact = classified(kind, path, target=target, detail=detail, severity=severity, data=data)
        return Result(ops=(op,), errors=[fact])

    def _invalid_path(self, resolved: ResolvedPath, raw: str, op: Op) -> Result:
        """Classify a failed path resolution — the one invalid-path mint.

        Total: called only in the ``resolved.path is None`` branch, so the
        resolve idiom keeps its narrowing; prefers the gate's own prose.
        """
        return self._error(
            ErrorKind.invalid, op=op, detail=resolved.error or "the path did not resolve", data={"raw": str(raw)}
        )

    def _closed_error(self, op: Op) -> Result:
        """Classified answer for a dispatch attempted after ``close()``."""
        return self._error(ErrorKind.backend_unavailable, op=op, detail="the filesystem is closed")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _reaches_beneath(op: Op, rel: Path, kwargs: Mapping[str, Any]) -> bool:
    """Whether *op* at *rel* acts on every path beneath it: a cascading delete, a live sweep, a move, a copy.

    A strict delete, a restore and a trash-view sweep only finish or undo
    an earlier delete, so the map judges them at their path alone.
    """
    if op in ("move", "copy"):
        return True
    if op == "delete":
        return bool(kwargs.get("cascade", True))
    return op == "sweep" and not is_trash_path(str(rel))


def _is_tombstoned_site(result: Result, path: Path) -> bool:
    """Whether the refused *result* names *path* itself as a deleted row — the one refusal ``restore`` answers."""
    error = result.errors[0]
    return error.kind is ErrorKind.not_found and error.path == path and bool((error.data or {}).get(TRASHED_KEY))


def _scoped(plan: ScopePlan, key: Path) -> dict[str, ScopeChannel]:
    """The ``scope=`` keyword an entry's dispatch carries: its scope channel, or nothing with no root beneath it."""
    channel = plan.scopes.get(key)
    return {} if channel is None else {"scope": channel}
