"""VirtualFileSystem — async router over one mount table of storage backends.

A mount binds a **storage instance**, never another router: the table maps
``path -> Binding(path, storage, meta)``, the node's own backend is the
identity entry at ``/``, and longest-prefix matching resolves every path to
exactly one entry.  One ``VirtualFileSystem`` = one namespace = one policy
layer — the Linux shape, where a mount entry binds a superblock and the VFS
layer exists once.

Namespace shape is *stored*, never synthesized: a mount-point directory is
an ordinary stored row in whichever storage owns the parent path, while the
binding lives only in this table.  ``bind`` is the primitive (onto an
existing empty directory — the ``graft_tree`` rule); ``add_mount`` fuses a
convenience mkdir-if-absent in front of it; ``remove_mount`` unbinds and
strictly rmdirs.  Composition with other routers happens through storage
too: an adapter presents a router as a ``StorageBackend`` (the exportfs
move), and MCP clients are wire-speaking backends.

The admin surface — ``bind``/``unbind``/``add_mount``/``remove_mount``/
``close`` — is control-plane state on this router and is not part of the
storage protocol: no dispatched verb can mutate a mount table.

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
import re
from collections.abc import Iterable
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, NamedTuple, assert_never, cast

from pydantic import ValidationError

from vfs.exceptions import MountError, raise_lone_or_group
from vfs.models import CONTENT_KINDS, Edge, Entry, Observation
from vfs.ops import MUTATING_OPS, READ_OPS, CaseMode, GrepOutputMode, TwoPathOperation
from vfs.params import param_violation
from vfs.paths import METADATA_ROOT, ROOT, Path, extract_extension, normalize_ext_channel, resolve_path
from vfs.pattern_matching import (
    GLOB_CHANNEL_LABELS,
    MAX_PATTERN_ARMS,
    compile_filter,
    compile_verifier,
    composed_pattern,
    effective_pattern,
    escape_glob,
    expand_pattern,
    filter_candidates,
    glob_defect,
    match_texts,
    passes_filters,
    render_residual,
    residuals,
)
from vfs.permissions import (
    Permission,
    PermissionLayer,
    PermissionMap,
    check_writable_composed,
    coerce_permissions,
)
from vfs.results import Result, ResultError, VFSErrorKind, validation_message
from vfs.results.kinds import Severity, kind_family
from vfs.storage import (
    ResolvedPair,
    StorageBackend,
    SupportsClose,
    SupportsGlean,
    SupportsGraph,
    SupportsMutation,
    SupportsPatternSearch,
    SupportsRun,
    TransportError,
)
from vfs.storage.backends.memory import InMemoryStorage
from vfs.storage.replace import EditOperation

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine, Sequence

    from vfs.ops import Op
    from vfs.paths import ObjectKind, ResolvedPath
    from vfs.pattern_matching import GrepHit
    from vfs.permissions import PermissionsPayload

# Router-traversal depth budget for the current request: decremented once
# per router entered (adapters and wire hops re-enter), never per mount.
_hop_budget: ContextVar[int | None] = ContextVar("vfs_hop_budget", default=None)

# Single-path mutations whose addressed site the EBUSY guard protects:
# delete removes it, restore lands on it, sweep destroys beneath it.
_BUSY_GUARDED_OPS: frozenset[Op] = frozenset({"delete", "restore", "sweep"})


@dataclass(slots=True)
class MountMeta:
    """Per-entry policy and lifecycle facts — the ``mnt_flags`` of a binding.

    Policy lives on the entry, state lives on the storage: *permission_map*
    holds mount-relative rules (``None`` — no local rules), *no_overlay*
    refuses **new** binds beneath this entry (existing children are
    grandfathered and keep dispatching; since ``unbind`` never consults the
    flag, a sealed subtree can shrink but never grow), *owned* says
    ``close()`` disposes the storage, *declared_caps* is the unmasked
    capability snapshot taken from ``storage.capabilities()``, and
    *deny_ops* is the mounter's op mask.  *caps* — what every gate reads —
    is derived at construction as ``declared_caps - deny_ops``; a meta is
    always replaced whole, never field-mutated, so the three can't drift.
    """

    permission_map: PermissionMap | None = None
    no_overlay: bool = False
    owned: bool = True
    declared_caps: frozenset[str] = frozenset()
    deny_ops: frozenset[str] = frozenset()
    caps: frozenset[str] = field(init=False)

    def __post_init__(self) -> None:
        self.caps = self.declared_caps - self.deny_ops


class Binding(NamedTuple):
    """One mount-table fact: *storage* bound at *path* under *meta* policy.

    The identity binding — the node's own storage at ``/`` — is an ordinary
    entry: every path resolves to exactly one binding, and the root entry
    is simply the longest-prefix fallback.
    """

    path: Path
    storage: StorageBackend
    meta: MountMeta


class MountInfo(NamedTuple):
    """One ``mounts()`` row — table facts and bind-time snapshots, JSON-native.

    Every field is a JSON fixed point (str, bool, None, or containers of
    these), so ``json.dumps(row._asdict())`` always succeeds.  Mounter-
    imposed policy is echoed verbatim — *permissions* (the serialized local
    map; ``None`` when a child bind stored none), *deny_ops* (the stored
    mask, sorted; ``()`` when unmasked), *no_overlay*, *owned* — which is
    what makes the rows replayable: they rebuild the namespace given the
    storages (see :meth:`VirtualFileSystem.mounts` for the seal-last
    recipe).  *caps* is the **effective** post-mask set, sorted;
    *description* is a live attribute read, everything else is table fact
    or bind-time snapshot.  ``no_overlay=True`` means "no *new* binds
    beneath" — a sealed entry may still show child rows.
    """

    path: str
    storage_name: str
    storage_type: str
    description: str
    caps: tuple[str, ...]
    deny_ops: tuple[str, ...]
    permissions: PermissionsPayload | None
    no_overlay: bool
    owned: bool


class ResolvedTerminal(NamedTuple):
    """Where a routed path landed — a binding plus the residual path.

    ``binding`` names the entry that owns the path; ``rel`` is the path in
    that entry's own coordinates (``without_mount(binding.path)``).
    """

    binding: Binding
    rel: Path

    @property
    def full(self) -> Path:
        """The router-coordinate path this terminal resolved from."""
        return self.rel.with_mount(self.binding.path)


class _HopGrant(NamedTuple):
    """One hop-budget admission: exactly one of *token* / *refusal* is set.

    ``token`` restores the caller's budget on exit (``_exit_hop``);
    ``refusal`` is the classified ``budget_exhausted`` result.
    """

    token: Token[int | None] | None
    refusal: Result | None


class _FanoutPlan(NamedTuple):
    """One fan-out's classified inputs — an output-only plan.

    ``scoped`` maps bind path to the entry and its caller-named rels;
    ``unscoped`` holds the entries dispatched whole; ``skips`` are the
    incapable-entry coverage records, appended only after the merge so
    they never feed branch demotion.  ``refusal`` is the sole failure
    carrier: when set, the collections are empty and the caller returns
    it.  The plan never grows input fields — inputs stay arguments.
    """

    scoped: dict[Path, tuple[Binding, list[Path]]]
    unscoped: dict[Path, Binding]
    skips: list[ResultError]
    refusal: Result | None = None


def _path_covers(ancestor: Path, descendant: Path) -> bool:
    """Whether *descendant* sits at or beneath *ancestor* in the namespace."""
    if ancestor in (descendant, ROOT):
        return True
    return str(descendant).startswith(str(ancestor) + "/")


class VirtualFileSystem:
    """Async router base class for all VFS filesystems."""

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
    ) -> None:
        if storage is None:
            storage = InMemoryStorage()
        if not isinstance(storage, StorageBackend):
            msg = f"storage must implement the read family (see vfs.storage), got {type(storage).__name__}"
            raise TypeError(msg)
        self.name = name
        self.title = title
        self.description = description
        self._hop_budget_default = hop_budget
        self._close_timeout = close_timeout
        self._mount_lock = asyncio.Lock()
        self._stranded_disposals: dict[int, StorageBackend] = {}
        root_meta = MountMeta(
            permission_map=coerce_permissions(permissions),
            no_overlay=no_overlay,
            owned=True,
            declared_caps=frozenset(storage.capabilities()),
            deny_ops=self._validate_deny_ops(deny_ops),
        )
        self._bindings: dict[Path, Binding] = {ROOT: Binding(path=ROOT, storage=storage, meta=root_meta)}
        self._sorted_mount_paths: list[Path] = [ROOT]
        self._class_name = self.__class__.__name__

    # -------------------------------------------------------------------
    # mount administration
    # -------------------------------------------------------------------

    async def bind(
        self,
        storage: StorageBackend,
        path: str,
        *,
        permissions: Permission | PermissionMap | None = None,
        deny_ops: Iterable[Op] = (),
        no_overlay: bool = False,
        owned: bool = True,
    ) -> None:
        """Bind *storage* at *path* — the mount primitive.

        The site must already exist as an **empty directory** in the storage
        owning the parent path (the ``graft_tree`` rule: exists, is a
        directory, has no children) — which is what makes rebinding after a
        restart work on a persistent backend, and makes a crash-orphaned
        mount-point directory a valid future site instead of poison.  The
        binding itself is runtime-only table state; nothing about the bind
        is stored.

        Rejected when the path is already bound, sits beneath a
        ``no_overlay`` entry, would sit above an existing deeper binding, or
        when *storage* is already bound elsewhere in this table (aliasing —
        one object, one path).  *permissions* installs mount-relative rules
        on the entry; *deny_ops* masks mutating/exec ops out of the entry's
        effective capabilities (read-family ops cannot be masked); *owned*
        says ``close()`` disposes this storage.

        The site probe is storage I/O and runs outside the mount lock; the
        table is re-checked and committed under it with no await between.
        """
        if not isinstance(storage, StorageBackend):
            msg = f"storage must implement the read family (see vfs.storage), got {type(storage).__name__}"
            raise TypeError(msg)
        mount_path = self._normalize_mount_path(path)
        mask = self._validate_deny_ops(deny_ops)

        probed = await self._probe_bind_site(mount_path)
        if probed is not None:
            msg = f"Cannot bind at {mount_path}: {probed}"
            raise ValueError(msg)

        meta = MountMeta(
            permission_map=None if permissions is None else coerce_permissions(permissions),
            no_overlay=no_overlay,
            owned=owned,
            declared_caps=frozenset(storage.capabilities()),
            deny_ops=mask,
        )
        async with self._mount_lock:
            # Re-checked under the lock: close() may have emptied the table
            # while the site probe's storage I/O was suspended.
            if not self._bindings:
                msg = f"Cannot bind at {mount_path}: filesystem is closed"
                raise ValueError(msg)
            if mount_path in self._bindings:
                msg = f"Mount already exists at: {mount_path}"
                raise ValueError(msg)
            for existing in self._sorted_mount_paths:
                if existing.startswith(mount_path + "/"):
                    msg = f"Cannot bind at {mount_path}: a deeper mount already sits at {existing}"
                    raise ValueError(msg)
                if (
                    existing != ROOT
                    and mount_path.startswith(existing + "/")
                    and self._bindings[existing].meta.no_overlay
                ):
                    msg = f"Cannot bind at {mount_path}: the mount at {existing} does not allow binds beneath it"
                    raise ValueError(msg)
            if self._bindings[ROOT].meta.no_overlay:
                msg = f"{self._class_name} does not allow child mounts"
                raise ValueError(msg)
            if any(b.storage is storage for b in self._bindings.values()):
                msg = f"Cannot bind at {mount_path}: that storage object is already bound in this table"
                raise ValueError(msg)
            self._bindings[mount_path] = Binding(path=mount_path, storage=storage, meta=meta)
            self._rebuild_sorted_mounts()

    async def unbind(self, path: str) -> Binding:
        """Drop the binding at *path*, leaving its stored directory in place.

        The lazy-unmount half: pure table surgery under the lock, no storage
        I/O, so it succeeds even against a dead or wedged backend.  Returns
        the removed binding so the caller can dispose the storage it owns.
        Rejected while deeper bindings still sit beneath *path* — unmount
        depth-first, as ``umount`` does.
        """
        mount_path = self._normalize_mount_path(path)
        async with self._mount_lock:
            binding = self._bindings.get(mount_path)
            if binding is None:
                msg = f"No mount at: {mount_path!r}"
                raise ValueError(msg)
            deeper = [p for p in self._sorted_mount_paths if p.startswith(mount_path + "/")]
            if deeper:
                msg = f"Cannot unmount {mount_path}: deeper mounts exist at {', '.join(map(str, deeper))}"
                raise ValueError(msg)
            del self._bindings[mount_path]
            self._rebuild_sorted_mounts()
            return binding

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
    ) -> None:
        """Mount *storage* at *path* — mkdir-if-absent + bind, fused.

        The udisks convenience over the :meth:`bind` primitive: the
        mount-point directory is created when absent (an ordinary gated
        mkdir against the owning entry — parents must exist unless
        ``parents=True``), then the binding commits over it.  An existing
        directory is fine when empty (the rebind-after-restart shape); an
        occupied site or a file classifies through mkdir/bind and raises.
        A failed bind leaves the directory behind — a plain empty directory
        is a valid future mount site, not damage to roll back.

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

        made = await self.mkdir(str(mount_path), parents=parents, exist_ok=True)
        if not made.success:
            detail = made.error_message or "storage refused the mount-point directory"
            msg = f"Cannot mount at {mount_path}: {detail}"
            raise MountError(msg, result=made)
        await self.bind(
            storage, str(mount_path), permissions=permissions, deny_ops=mask, no_overlay=no_overlay, owned=owned
        )

    async def remove_mount(self, path: str) -> None:
        """Unmount *path* — unbind + strict rmdir, fused.

        The binding is dropped first (table surgery under the lock), then
        the mount-point directory is removed with a strict, non-recursive
        delete against whichever storage owns the parent path — the empty
        directory row parks in trash like any deleted row, and retention
        reclaims it.  Never a cascade: on shared or persistent storage the
        directory may have gained rows this router never saw, and unmount
        must not destroy them.  A failed rmdir leaves the unbind standing
        and raises — the namespace keeps a plain directory, loud and
        recoverable.

        Storage lifecycle is untouched: unbinding never disposes an engine
        or session.  Dispose through ``close()`` or by closing a retained
        reference to the storage.
        """
        mount_path = self._normalize_mount_path(path)
        await self.unbind(str(mount_path))
        removed = await self.delete(path=str(mount_path), cascade=False)
        if not removed.success:
            detail = removed.error_message or "storage refused the delete"
            msg = f"Unmounted {mount_path}, but removing its directory failed: {detail}"
            raise MountError(msg, result=removed)

    async def remount(
        self,
        path: str,
        *,
        permissions: Permission | PermissionMap | None = None,
        deny_ops: Iterable[Op] | None = None,
        no_overlay: bool | None = None,
        refresh_caps: bool = False,
    ) -> None:
        """Change the entry's policy at *path* in place — atomic, no I/O.

        ``None`` means "leave unchanged" everywhere — so ``deny_ops=()``
        (clear the mask) is distinct from ``deny_ops=None`` (keep it), and
        passing no changes at all is a no-op, not an error.  The binding is
        replaced under the mount lock with a new meta; no moment exists
        where the path is unbound, and no storage I/O runs — the one
        storage call is ``refresh_caps=True`` re-snapshotting
        ``storage.capabilities()`` (taken before the lock, committed under
        it): the remedy for a reconnected wire backend whose tool set
        changed.  A replaced or cleared mask recomputes effective caps from
        the stored unmasked snapshot, so previously masked ops come back
        without asking the storage.

        Root is an ordinary entry: ``remount("/")`` is how you tighten the
        whole namespace.  Loosening is permitted, as on Linux — a parent
        layer's map still gates every path beneath (most restrictive wins),
        so ``remount`` can never grant more than the chain above allows.

        ``no_overlay=True`` seals with **future-only** effect: existing
        deeper bindings stay bound and dispatching; only *new* binds
        beneath the entry are refused.  Because ``unbind`` never consults
        the flag, the sealed subtree is a one-way ratchet — it can shrink
        but never grow.  Unknown path raises :class:`ValueError`, as
        ``unbind`` does.
        """
        mount_path = self._normalize_mount_path(path, allow_root=True)
        mask = None if deny_ops is None else self._validate_deny_ops(deny_ops)
        new_map = None if permissions is None else coerce_permissions(permissions)

        # The one storage call, taken outside the lock (capabilities() is
        # synchronous per protocol — "outside" means before acquiring).
        fresh_caps: frozenset[str] | None = None
        probed_storage: StorageBackend | None = None
        if refresh_caps:
            probing = self._bindings.get(mount_path)
            if probing is None:
                msg = f"No mount at: {mount_path!r}"
                raise ValueError(msg)
            probed_storage = probing.storage
            fresh_caps = frozenset(probed_storage.capabilities())

        async with self._mount_lock:
            binding = self._bindings.get(mount_path)
            if binding is None:
                msg = f"No mount at: {mount_path!r}"
                raise ValueError(msg)
            if probed_storage is not None and binding.storage is not probed_storage:
                msg = f"Mount at {mount_path} changed while remounting — retry"
                raise ValueError(msg)
            meta = binding.meta
            new_meta = MountMeta(
                permission_map=meta.permission_map if new_map is None else new_map,
                no_overlay=meta.no_overlay if no_overlay is None else no_overlay,
                owned=meta.owned,
                declared_caps=meta.declared_caps if fresh_caps is None else fresh_caps,
                deny_ops=meta.deny_ops if mask is None else mask,
            )
            self._bindings[mount_path] = binding._replace(meta=new_meta)

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
            bindings = list(self._bindings.values())
            self._bindings = {}
            self._sorted_mount_paths = []

        targets = dict(self._stranded_disposals)
        for binding in bindings:
            if binding.meta.owned and isinstance(binding.storage, SupportsClose):
                targets.setdefault(id(binding.storage), binding.storage)
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

    def mounts(self) -> tuple[MountInfo, ...]:
        """The mount table, one JSON-native row per binding — replayable.

        Rows are ordered by bind path, root identity entry first (it is an
        ordinary entry); a closed filesystem returns ``()``.  Values are
        table facts and bind-time snapshots — no storage I/O, and no lock:
        this reads one dict snapshot synchronously, and the table can
        change the instant a lock would drop anyway.  The single live read
        is ``description`` (attribute access, not a call).

        Mounter-imposed policy is echoed verbatim on each row —
        ``permissions``, ``deny_ops``, ``no_overlay``, ``owned`` — never
        left to be derived, so the rows carry enough to rebuild the
        namespace given the storages: replay the root row through the
        constructor and every other row through :meth:`bind`, applying
        ``no_overlay=True`` rows **seal-last** via :meth:`remount` — a
        sealed entry refuses the child binds beneath it, so a subtree
        grandfathered by ``remount(no_overlay=True)`` cannot replay with
        the flag passed at bind time.  Replay keyed by ``storage_name``
        assumes the mounter keeps names unique; the table itself never
        requires that.
        """
        rows = []
        for mount_path in sorted(self._bindings):
            binding = self._bindings[mount_path]
            meta = binding.meta
            rows.append(
                MountInfo(
                    path=str(mount_path),
                    storage_name=binding.storage.name,
                    storage_type=type(binding.storage).__name__,
                    description=binding.storage.description,
                    caps=tuple(sorted(meta.caps)),
                    deny_ops=tuple(sorted(meta.deny_ops)),
                    permissions=None if meta.permission_map is None else meta.permission_map.to_payload(),
                    no_overlay=meta.no_overlay,
                    owned=meta.owned,
                )
            )
        return tuple(rows)

    def capabilities(self) -> frozenset[str]:
        """Operations this namespace answers — the union of entry snapshots.

        Each entry's set was declared by its storage at bind
        (``storage.capabilities()``), so the union is self-declaration all
        the way down: an adapter forwards its wrapped router's set, a wire
        backend advertises the far side's tools, and nothing is inferred
        from method surfaces.
        """
        caps: set[str] = set()
        for binding in self._bindings.values():
            caps |= binding.meta.caps
        return frozenset(caps)

    async def _probe_bind_site(self, mount_path: Path) -> str | None:
        """Prove the bind site is an existing empty directory, else say why.

        Storage I/O — runs outside the mount lock.  The owning entry is
        whichever binding holds the parent region; on a shared backend the
        answer can change before commit (unsynchronized shared admin), and
        the resulting states are the ordinary classified ones.  Failures
        dispatch on the error kind, not the bit: only ``not_found`` earns
        the mkdir advice — a dead backend surfaces its transport failure
        instead of advising a mkdir that cannot help.
        """
        if not self._bindings:
            return "filesystem is closed"
        terminal = self._resolve_terminal(mount_path)
        advice = f"no directory stored at the mount point (mkdir it, or add_mount(..., parents=True)): {mount_path}"
        stat = await self._call_storage(terminal.binding, "stat", path=terminal.rel)
        if not stat.success:
            blocker = next((f for f in stat.failures if kind_family(f.kind) is not VFSErrorKind.not_found), None)
            if blocker is None:
                return advice
            return blocker.message or f"could not stat the mount point: {mount_path}"
        row = next((o for o in stat.observations if o.path == terminal.rel), None)
        if row is None:
            return advice
        if row.kind != "directory":
            return f"the mount point is stored as {row.kind!r}, not a directory: {mount_path}"
        listed = await self._call_storage(terminal.binding, "ls", path=terminal.rel)
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
        (except for ``remount``, which targets existing entries and admits
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
        """Rebuild the pre-sorted binding path list, longest prefix first.

        Reverse-lexicographic is enough: only paths matching the same
        target need relative order, and those are always prefix-chains,
        where the proper prefix sorts strictly lower — so ``/`` lands last,
        the universal fallback.
        """
        self._sorted_mount_paths = sorted(self._bindings.keys(), reverse=True)

    # -------------------------------------------------------------------
    # public methods — reads
    # -------------------------------------------------------------------

    async def read(
        self,
        path: str | None = None,
        observations: list[Observation] | None = None,
        *,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result:
        refusal = self._gate_params("read", path=path, observations=observations, columns=columns, user_id=user_id)
        if refusal is not None:
            return refusal
        return await self._route_single("read", path, observations, columns=columns, user_id=user_id)

    async def stat(
        self,
        path: str | None = None,
        observations: list[Observation] | None = None,
        *,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result:
        refusal = self._gate_params("stat", path=path, observations=observations, columns=columns, user_id=user_id)
        if refusal is not None:
            return refusal
        return await self._route_single("stat", path, observations, columns=columns, user_id=user_id)

    async def ls(
        self,
        path: str | None = None,
        observations: list[Observation] | None = None,
        *,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result:
        refusal = self._gate_params("ls", path=path, observations=observations, columns=columns, user_id=user_id)
        if refusal is not None:
            return refusal
        return await self._route_single("ls", path, observations, columns=columns, user_id=user_id)

    async def tree(
        self,
        path: str,
        max_depth: int | None = None,
        *,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result:
        refusal = self._gate_params("tree", path=path, max_depth=max_depth, columns=columns, user_id=user_id)
        if refusal is not None:
            return refusal
        return await self._route_single("tree", path, None, max_depth=max_depth, columns=columns, user_id=user_id)

    # -------------------------------------------------------------------
    # public methods — mutations
    # -------------------------------------------------------------------

    async def write(
        self,
        entries: Sequence[Entry] | None = None,
        *,
        path: str | None = None,
        content: str | None = None,
        overwrite: bool = True,
        parents: bool = False,
        user_id: str | None = None,
    ) -> Result:
        """Write one file (*path* + *content*) or a batch of *entries*.

        Batch entries route by their own paths — grouped per entry,
        rebased, and gated per row before anything dispatches. *entries*
        and *path*/*content* are mutually exclusive. The single form is
        sugar: this gate constructs the validated :class:`Entry`, and
        storage only ever receives entries — raw content never crosses
        the storage seam.

        The parent chain must already exist as directories;
        ``parents=True`` mints the missing ancestors, ``mkdir -p`` style,
        and applies per call — every entry in a batch shares it.
        """
        refusal = self._gate_params(
            "write", entries=entries, path=path, content=content, overwrite=overwrite, parents=parents, user_id=user_id
        )
        if refusal is not None:
            return refusal
        if entries is not None:
            return await self._route_entry_batch(entries, overwrite=overwrite, parents=parents, user_id=user_id)
        if path is None or content is None:
            return self._error(
                "write requires path and content, or entries",
                kind=VFSErrorKind.invalid,
                op="write",
            )
        resolved = resolve_path(path, mutation=True)
        if resolved.path is None:
            return self._invalid_path(resolved, path, "write")
        try:
            entry = Entry(path=str(resolved.path), content=content)
        except ValidationError as exc:
            return self._error(validation_message(exc), kind=VFSErrorKind.invalid, op="write")
        return await self._route_entry_batch([entry], overwrite=overwrite, parents=parents, user_id=user_id)

    async def edit(
        self,
        path: str | None = None,
        old: str | None = None,
        new: str | None = None,
        edits: list[EditOperation] | None = None,
        observations: list[Observation] | None = None,
        replace_all: bool = False,
        *,
        user_id: str | None = None,
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
            user_id=user_id,
        )
        if refusal is not None:
            return refusal
        if edits is not None:
            ops = self._as_list(edits)
            if ops is None or not all(isinstance(e, EditOperation) for e in ops):
                return self._error(
                    "edit edits must be an iterable of EditOperation",
                    kind=VFSErrorKind.invalid,
                    op="edit",
                )
            edits = ops
        else:
            assert old is not None and new is not None
            edits = [EditOperation(old=old, new=new, replace_all=replace_all)]
        return await self._route_single("edit", path, observations, edits=edits, user_id=user_id)

    async def delete(
        self,
        path: str | None = None,
        observations: list[Observation] | None = None,
        *,
        cascade: bool = True,
        user_id: str | None = None,
    ) -> Result:
        """Delete *path* (or each observation row) — always recoverable.

        Delete is reversible; sweep is not; agents only get the first.
        Every successful delete reparents its target into the trash,
        and each observation's ``trash_path`` reports where its row now
        lives. A covered target's address derives from its covering
        root: restore accepts the covering root's ``trash_path``, and
        covered rows ride back with it. What cannot be trashed — the
        active trash chain — refuses ``invalid``. A live
        bind site is ``busy``: a bound path, or a region holding bound
        paths, must be unmounted before it can be deleted — the EBUSY
        rule.
        """
        refusal = self._gate_params("delete", path=path, observations=observations, cascade=cascade, user_id=user_id)
        if refusal is not None:
            return refusal
        return await self._route_single(
            "delete",
            path,
            observations,
            cascade=cascade,
            user_id=user_id,
        )

    async def restore(
        self,
        path: str | None = None,
        observations: list[Observation] | None = None,
        *,
        overwrite: bool = False,
        user_id: str | None = None,
    ) -> Result:
        """Restore a trashed entry to its original site.

        *path* is either the entry's pre-delete path (the newest matching
        trash row wins) or its exact trash-side path — the address a
        delete result reports. An occupied site classifies ``exists``
        unless *overwrite*; a backend that keeps no trash classifies
        ``unsupported``. Like delete, a live bind site at the address is
        ``busy``.
        """
        refusal = self._gate_params(
            "restore", path=path, observations=observations, overwrite=overwrite, user_id=user_id
        )
        if refusal is not None:
            return refusal
        return await self._route_single("restore", path, observations, overwrite=overwrite, user_id=user_id)

    async def sweep(
        self,
        path: str = "/.vfs/trash",
        *,
        user_id: str | None = None,
    ) -> Result:
        """Destroy at *path* — retention cleanup at a trash root, purge elsewhere.

        Delete is reversible; sweep is not; agents only get the first:
        sweep is a developer-plane verb, never registered on any
        agent-facing tool surface. A trash-root address runs retention —
        expired hour-buckets drop wholesale (foreign rows inside them
        included); non-bucket rows are skipped and surfaced as warnings.
        Any other address purges that subtree wholesale, immediately,
        regardless of retention age. The default address sweeps the root
        mount's trash; pass ``/m/.vfs/trash`` to sweep the mount at
        ``/m``. Explicit and idempotent — storage owns no background
        work.
        """
        refusal = self._gate_params("sweep", path=path, user_id=user_id)
        if refusal is not None:
            return refusal
        return await self._route_single("sweep", path, None, user_id=user_id)

    async def mkdir(
        self,
        path: str,
        *,
        parents: bool = False,
        exist_ok: bool = False,
        user_id: str | None = None,
    ) -> Result:
        """Create a directory at *path* — pathlib-shaped flags, POSIX defaults.

        Strict by default: every ancestor must already exist as a
        directory, and an occupied site classifies ``exists``.
        ``parents=True`` mints the missing chain; ``exist_ok=True`` forgives
        an existing *directory* only — a file at the site stays ``exists``.
        """
        refusal = self._gate_params("mkdir", path=path, parents=parents, exist_ok=exist_ok, user_id=user_id)
        if refusal is not None:
            return refusal
        return await self._route_single("mkdir", path, None, parents=parents, exist_ok=exist_ok, user_id=user_id)

    async def mkedge(
        self,
        source: str,
        target: str,
        edge_type: str,
        *,
        user_id: str | None = None,
    ) -> Result:
        """Create a typed edge from *source* to *target*.

        Both endpoints must resolve to the same entry (``cross_mount``
        otherwise — cross-backend edges are a later story).  An edge is
        entry-scoped metadata on both endpoints, so the write is
        permission-gated at both endpoint paths; the ``Edge`` model is the
        validation door for endpoint eligibility and the edge type.
        """
        refusal = self._gate_params("mkedge", source=source, target=target, edge_type=edge_type, user_id=user_id)
        if refusal is not None:
            return refusal
        if not self._bindings:
            return self._closed_error("mkedge")
        src = resolve_path(source)
        if src.path is None:
            return self._invalid_path(src, source, "mkedge")
        tgt = resolve_path(target)
        if tgt.path is None:
            return self._invalid_path(tgt, target, "mkedge")

        src_terminal = self._resolve_terminal(src.path)
        tgt_terminal = self._resolve_terminal(tgt.path)
        # Endpoint eligibility is a path fact and outranks the table fact
        # below — the same bad endpoint classifies alike on any topology.
        try:
            Edge(source=src_terminal.rel, target=tgt_terminal.rel, edge_type=edge_type)
        except ValidationError as exc:
            return self._error(validation_message(exc), kind=VFSErrorKind.invalid, op="mkedge")
        if src_terminal.binding.path != tgt_terminal.binding.path:
            return self._error(
                f"Cross-mount edges are not supported: {src.path} and {tgt.path} resolve to different mounts",
                kind=VFSErrorKind.cross_mount,
                op="mkedge",
            )
        binding = src_terminal.binding
        err = self._gate_entry(binding, "mkedge")
        if err is not None:
            return err

        # An edge write mutates both endpoints' metadata sets, so both
        # endpoint paths must be writable in global coordinates.
        for terminal in (src_terminal, tgt_terminal):
            full = terminal.rel.with_mount(binding.path)
            denied = check_writable_composed(self._permission_layers(full), "mkedge")
            if denied is not None:
                return denied
        return await self._dispatch_entry(
            binding,
            "mkedge",
            source=src_terminal.rel,
            target=tgt_terminal.rel,
            edge_type=edge_type,
            user_id=user_id,
        )

    async def move(
        self,
        src: str | None = None,
        dest: str | None = None,
        moves: Sequence[TwoPathOperation | tuple[str, str]] | None = None,
        *,
        overwrite: bool = True,
        user_id: str | None = None,
    ) -> Result:
        refusal = self._gate_params("move", src=src, dest=dest, moves=moves, overwrite=overwrite, user_id=user_id)
        if refusal is not None:
            return refusal
        return await self._route_pairs("move", src, dest, moves, overwrite=overwrite, user_id=user_id)

    async def copy(
        self,
        src: str | None = None,
        dest: str | None = None,
        copies: Sequence[TwoPathOperation | tuple[str, str]] | None = None,
        *,
        overwrite: bool = True,
        user_id: str | None = None,
    ) -> Result:
        refusal = self._gate_params("copy", src=src, dest=dest, copies=copies, overwrite=overwrite, user_id=user_id)
        if refusal is not None:
            return refusal
        return await self._route_pairs("copy", src, dest, copies, overwrite=overwrite, user_id=user_id)

    # -------------------------------------------------------------------
    # public methods — search
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
        user_id: str | None = None,
    ) -> Result:
        """Match *pattern* against the namespace — unscoped calls reach every entry.

        Segment-aware semantics: ``*`` matches within one path segment,
        ``**`` spans segments, ``{a,b}`` alternates (expanded before
        anything else sees the pattern); any ``/`` anchors the pattern
        at each scope root (the namespace root when unscoped) while a
        slash-free pattern matches leaf names at any depth. A row is
        admitted by *pattern* and rejected by any *globs_not* glob, the
        *ext*/*ext_not* facts, and a *kind* mismatch. Scoping crosses
        the storage seam only as pattern text: each root composes into
        one spatial pattern, residuation puts every entry's members in
        its own coordinates, and each entry answers its whole set in
        one call — so the match *set* is invariant to mount placement.
        Roots are find operands: a concurrent probe asserts each one
        (missing is a loud per-root error beside the healthy roots'
        rows) and serves the root's own row when the pattern matches it
        and no exclusion, ext fact, or kind fact rejects it. Row order
        is merge order, and a *max_count* prefix of it can therefore
        differ across layouts.

        With *observations*, glob is a filter over the rows in hand:
        the path gates run in memory and rows serve exactly as held
        (columns, staleness, and input order included). Storage is
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
            user_id=user_id,
        )
        if refusal is not None:
            return refusal
        arms, refused = self._expanded_arms("glob", GLOB_CHANNEL_LABELS["pattern"], pattern)
        if refused is not None:
            return refused
        globs_not, refused = self._expanded_channel("glob", GLOB_CHANNEL_LABELS["globs_not"], globs_not)
        if refused is not None:
            return refused
        if observations is not None:
            if not self._bindings:
                return self._closed_error("glob")
            return await self._glob_rows_in_hand(
                observations,
                arms=arms,
                ext=ext,
                ext_not=ext_not,
                globs_not=globs_not,
                kind=kind,
                max_count=max_count,
                user_id=user_id,
            )
        return await self._route_fanout(
            "glob",
            paths=paths,
            row_cap=max_count,
            patterns=arms,
            not_arms=globs_not,
            ext=ext,
            ext_not=ext_not,
            kind=kind,
            max_count=max_count,
            columns=columns,
            user_id=user_id,
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
        user_id: str | None = None,
    ) -> Result:
        """Search content for *pattern* — unscoped calls reach every entry.

        *globs*/*globs_not* use glob's segment-aware pattern language:
        ``*`` within a segment, ``**`` across, any ``/`` anchors at the
        root, slash-free patterns match leaf names. Scoping crosses the
        storage seam the way glob's does — as pattern text on the
        ``globs`` channels, composed per scope root and residuated into
        each entry's coordinates, with a concurrent probe asserting the
        roots (a missing root is a loud per-root error beside the
        healthy roots' rows; a root's own content joins the scan when
        the caller's globs pass its path). *pattern* is content-only
        and never composes with paths.

        With *observations*, grep is a filter over the rows in hand:
        gates and matching run in memory, content is fetched (through
        each row's own entry, classifying loudly) only for rows that
        lack it, and a row whose known kind carries no content never
        matches. The index tier is not involved, so *allow_scan* and
        the refusal gate do not apply.

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
            user_id=user_id,
        )
        if refusal is not None:
            return refusal
        globs, refused = self._expanded_channel("grep", GLOB_CHANNEL_LABELS["globs"], globs)
        if refused is not None:
            return refused
        globs_not, refused = self._expanded_channel("grep", GLOB_CHANNEL_LABELS["globs_not"], globs_not)
        if refused is not None:
            return refused
        if observations is not None:
            if not self._bindings:
                return self._closed_error("grep")
            return await self._grep_rows_in_hand(
                observations,
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
                user_id=user_id,
            )
        return await self._route_fanout(
            "grep",
            paths=paths,
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
            allow_scan=allow_scan,
            columns=columns,
            user_id=user_id,
        )

    async def glean(
        self,
        query: str,
        *,
        limit: int = 10,
        paths: tuple[str, ...] = (),
        observations: list[Observation] | None = None,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result:
        """Ranked search: text in, one fused ranked list out.

        The caller never picks a retrieval strategy — backends index by
        vector, lexical, and graph signals and fuse the rankings however
        they see fit.  The router passes *query* and *limit* through
        opaquely.  *limit* bounds each entry's answer **and** the merged
        result, trimmed by score — with the caveat that cross-entry
        scores are only loosely comparable (each entry ranks by its own
        scorer).
        """
        refusal = self._gate_params(
            "glean", query=query, limit=limit, paths=paths, observations=observations, columns=columns, user_id=user_id
        )
        if refusal is not None:
            return refusal
        return await self._route_fanout(
            "glean",
            paths=paths,
            observations=observations,
            row_cap=limit,
            query=query,
            limit=limit,
            columns=columns,
            user_id=user_id,
        )

    async def graph(
        self,
        method: str,
        path: str | None = None,
        observations: list[Observation] | None = None,
        *,
        depth: int | None = None,
        user_id: str | None = None,
    ) -> Result:
        """Run the graph traversal *method* — each entry answers over its own subgraph.

        A path routes to one entry; observations group by entry and each
        backend runs the algorithm on its own graph, so a walk can never
        follow an edge out of its storage.  *method* is validated against
        the traversal vocabulary before any dispatch; the envelope reports
        the one ``graph`` op — traversal is the whole verb, and analytics
        are index-time data, not queries.
        """
        refusal = self._gate_params(
            "graph", method=method, path=path, observations=observations, depth=depth, user_id=user_id
        )
        if refusal is not None:
            return refusal
        return await self._route_single("graph", path, observations, method=method, depth=depth, user_id=user_id)

    # -------------------------------------------------------------------
    # public methods — execution
    # -------------------------------------------------------------------

    async def run(
        self,
        path: str,
        *,
        arguments: dict[str, Any] | None = None,
        user_id: str | None = None,
    ) -> Result:
        """Execute the tool at *path* with *arguments* — the execution verb.

        ``read``/``stat``/``ls`` discover a tool's definition; ``run`` is the only
        verb that executes it. Not a namespace mutation, so it takes no
        write-authorization gate.
        """
        refusal = self._gate_params("run", path=path, arguments=arguments, user_id=user_id)
        if refusal is not None:
            return refusal
        return await self._route_single("run", path, None, arguments=arguments, user_id=user_id)

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
        user_id: str | None = None,
        **kwargs: Any,
    ) -> Result:
        """Route a single-path or observation-based operation.

        With observations: group by entry, dispatch in parallel.  With
        path: resolve one entry and dispatch once.  Exactly one of *path* /
        *observations* arrives — the verb's params gate enforced the shape
        before delegating here.
        """
        if not self._bindings:
            return self._closed_error(op)
        if observations is not None:
            return await self._dispatch_grouped_observations(op, observations, user_id=user_id, **kwargs)

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
        err = self._gate_entry(terminal.binding, op, write_rels=(terminal.rel,))
        if err is not None:
            return err

        if op == "tree":
            return await self._tree_region(terminal, user_id=user_id, **kwargs)
        return await self._dispatch_entry(terminal.binding, op, path=terminal.rel, user_id=user_id, **kwargs)

    async def _dispatch_grouped_observations(
        self,
        op: Op,
        observations: list[Observation],
        *,
        user_id: str | None = None,
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
        groups: dict[Path, tuple[Binding, list[Observation]]] = {}
        for obs in rows:
            resolved = resolve_path(obs.path, mutation=op in MUTATING_OPS)
            if resolved.path is None:
                return self._invalid_path(resolved, obs.path, op)
            if op in _BUSY_GUARDED_OPS:
                busy = self._busy_guard(op, resolved.path, subtree=True)
                if busy is not None:
                    return busy
            binding = self._resolve_terminal(resolved.path).binding
            _b, obs_list = groups.setdefault(binding.path, (binding, []))
            obs_list.append(obs.without_mount(binding.path))
        if not groups:
            return Result(ops=(op,))

        # All gates run before any dispatch, so a batch touching a bad
        # entry is rejected whole per the facts visible in this table.
        for binding, group in groups.values():
            err = self._gate_entry(binding, op, write_rels=[o.path for o in group])
            if err is not None:
                return err

        results = await self._gather_settled(
            self._dispatch_entry(binding, op, observations=group, user_id=user_id, **kwargs)
            for binding, group in groups.values()
        )
        return Result.merge(results, op=op)

    def _observation_rows(self, op: Op, observations: object) -> tuple[list[Observation], Result | None]:
        """Materialize and type-check an observations batch, or refuse it whole."""
        rows = self._as_list(observations)
        if rows is None:
            return [], self._error(
                f"observations must be an iterable of Observation, got {type(observations).__name__}",
                kind=VFSErrorKind.invalid,
                op=op,
            )
        for obs in rows:
            if not isinstance(obs, Observation):
                return [], self._error(
                    f"observations must be Observation instances, got {type(obs).__name__}",
                    kind=VFSErrorKind.invalid,
                    op=op,
                )
        return rows, None

    def _expanded_arms(self, op: Op, label: str, pattern: str) -> tuple[tuple[str, ...], Result | None]:
        """Defect-gate and brace-expand one pattern, or refuse the call.

        Twice-gated: ``glob_defect`` covers raw brace structure and
        every expansion arm's component defects; the cap refusal names
        the fix instead of fanning out an oversized expansion.
        """
        defect = glob_defect(pattern)
        if defect is not None:
            return (), self._error(f"{label} {pattern!r}: {defect}", kind=VFSErrorKind.invalid, op=op)
        arms = expand_pattern(pattern)
        if len(arms) > MAX_PATTERN_ARMS:
            message = (
                f"{label} {pattern!r} expands past the arm cap ({MAX_PATTERN_ARMS}) — "
                "narrow the alternation or split the call"
            )
            return (), self._error(message, kind=VFSErrorKind.invalid, op=op)
        return arms, None

    def _expanded_channel(self, op: Op, label: str, patterns: tuple[str, ...]) -> tuple[tuple[str, ...], Result | None]:
        """Expand every pattern of a glob channel; the cap applies per pattern."""
        expanded: list[str] = []
        for pattern in patterns:
            arms, refused = self._expanded_arms(op, label, pattern)
            if refused is not None:
                return (), refused
            expanded.extend(arms)
        return tuple(dict.fromkeys(expanded)), None

    async def _glob_rows_in_hand(
        self,
        observations: list[Observation],
        *,
        arms: tuple[str, ...],
        ext: tuple[str, ...],
        ext_not: tuple[str, ...],
        globs_not: tuple[str, ...],
        kind: ObjectKind | None,
        max_count: int | None,
        user_id: str | None,
    ) -> Result:
        """Chained glob: filter rows in hand, fetching only a missing kind fact.

        The path gates run in memory over the rows as held — admission
        by any expanded arm, rejection by exclusion globs and the ext
        facts, no meta rule, duplicates and order preserved. A *kind*
        filter judged against a row that carries no kind stats exactly
        those rows in one batch — the load-bearing fact is fetched,
        never guessed — and a row that cannot be statted classifies
        loudly beside the healthy rows.
        """
        rows, invalid = self._observation_rows("glob", observations)
        if invalid is not None:
            return invalid
        gates = [compile_filter(arm, ()) for arm in arms]
        not_gates = [compile_filter(glob, ()) for glob in globs_not]
        wanted = normalize_ext_channel(ext)
        unwanted = normalize_ext_channel(ext_not)
        kept = [row for row in rows if passes_filters(row.path, gates, not_gates, wanted, unwanted)]
        errors: list[ResultError] = []
        if kind is not None:
            lacking = [row for row in kept if row.kind is None]
            fetched: dict[str, str | None] = {}
            if lacking:
                stat = await self.stat(observations=lacking, columns=frozenset(), user_id=user_id)
                errors = list(stat.errors)
                fetched = {str(row.path): row.kind for row in stat.observations}
            kept = [row for row in kept if (row.kind if row.kind is not None else fetched.get(str(row.path))) == kind]
        return self._cap_rows(Result(ops=("glob",), observations=kept, errors=errors), "glob", max_count)

    async def _grep_rows_in_hand(
        self,
        observations: list[Observation],
        *,
        pattern: str,
        ext: tuple[str, ...],
        ext_not: tuple[str, ...],
        globs: tuple[str, ...],
        globs_not: tuple[str, ...],
        case_mode: CaseMode,
        fixed_strings: bool,
        word_regexp: bool,
        invert_match: bool,
        before_context: int,
        after_context: int,
        output_mode: GrepOutputMode,
        max_count: int | None,
        columns: frozenset[str] | None,
        user_id: str | None,
    ) -> Result:
        """Chained grep: filter the rows in hand, fetching only absent content.

        Path gates and the match run in memory over the rows as held. A
        row without content is read through its own entry — a row that
        cannot be read classifies loudly beside the healthy rows'
        matches — while a row whose known kind carries no content never
        matches and is skipped without error, a filter's non-match. The
        index tier is never involved, so the refusal gate and
        ``allow_scan`` have no meaning on this path.
        """
        rows, invalid = self._observation_rows("grep", observations)
        if invalid is not None:
            return invalid
        try:
            verifier = compile_verifier(
                pattern, fixed_strings=fixed_strings, word_regexp=word_regexp, case_mode=case_mode
            )
        except re.error as exc:
            return self._error(f"grep pattern {pattern!r}: {exc}", kind=VFSErrorKind.invalid, op="grep")
        keep = set(
            filter_candidates([row.path for row in rows], ext=ext, ext_not=ext_not, globs=globs, globs_not=globs_not)
        )
        candidates = [row for row in rows if row.path in keep]
        absent = [row for row in candidates if row.content is None and (row.kind is None or row.kind in CONTENT_KINDS)]
        errors: list[ResultError] = []
        contents: dict[str, str] = {}
        if absent:
            read = await self.read(observations=absent, columns=frozenset({"content"}), user_id=user_id)
            errors = list(read.errors)
            contents = {str(row.path): row.content for row in read.observations if row.content is not None}
        texted: list[tuple[Observation, str]] = []
        for row in candidates:
            text = row.content if row.content is not None else contents.get(str(row.path))
            if text is not None:
                texted.append((row, text))
        hits = match_texts(
            [(row.path, text) for row, text in texted],
            verifier,
            invert=invert_match,
            before=before_context,
            after=after_context,
            mode=output_mode,
            cap=max_count,
        )
        matched = [
            self._hit_row(row, text, hit, mode=output_mode, columns=columns)
            for (row, text), hit in zip(texted, hits, strict=True)
            if hit is not None
        ]
        return Result(ops=("grep",), observations=matched, errors=errors)

    @staticmethod
    def _hit_row(
        row: Observation,
        text: str,
        hit: GrepHit,
        *,
        mode: GrepOutputMode,
        columns: frozenset[str] | None,
    ) -> Observation:
        """One chained-grep hit: the row as held, match facts attached.

        ``files`` mode carries neither content nor matches; fetched
        content attaches only when the caller projected it.
        """
        populated = set(row.populated)
        update: dict[str, object] = {}
        if mode == "files":
            update["content"] = None
            populated.discard("content")
        elif row.content is None and columns is not None and "content" in columns:
            update["content"] = text
            populated.add("content")
        if hit.matches is not None:
            update["matches"] = hit.matches
            populated.add("matches")
        if hit.score is not None:
            update["score"] = hit.score
            populated.add("score")
        update["populated"] = frozenset(populated)
        return row.model_copy(update=update)

    async def _tree_region(
        self,
        terminal: ResolvedTerminal,
        *,
        max_depth: int | None = None,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result:
        """Tree over a region: the owning entry's subtree plus bound descents.

        The owning storage answers its own shape (mount-point directories
        are stored rows; rows under deeper binds are shadow-filtered).  Each
        binding at segment distance ``s`` beneath the target then answers
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
                terminal.binding, "tree", path=terminal.rel, max_depth=max_depth, columns=columns, user_id=user_id
            )
            if not own.success:
                return own

            descents: list[tuple[Binding, int | None]] = []
            skips: list[ResultError] = []
            for binding in self._bindings_beneath(full):
                tail = binding.path.without_mount(full)
                distance = len(tail.strip("/").split("/"))
                budget = None if max_depth is None else max_depth - distance
                if budget is not None and budget <= 0:
                    continue
                if "tree" not in binding.meta.caps:
                    skips.append(self._skip_entry("tree", binding))
                    continue
                descents.append((binding, budget))

            results: list[Result] = [own]
            results.extend(
                await self._gather_settled(
                    self._dispatch_entry(binding, "tree", path=ROOT, max_depth=budget, columns=columns, user_id=user_id)
                    for binding, budget in descents
                )
            )
            return self._with_skips(Result.merge_branches(results, op="tree"), skips)
        finally:
            self._exit_hop(grant.token)

    async def _route_fanout(
        self,
        op: Op,
        *,
        paths: tuple[str, ...] = (),
        observations: list[Observation] | None = None,
        row_cap: int | None = None,
        user_id: str | None = None,
        **kwargs: object,
    ) -> Result:
        """Route a namespace-wide query: everywhere, a scope subset, or rows.

        With observations: reuse grouped dispatch.  With scope paths: group
        the scopes by entry — a scoped entry that cannot answer errors
        ``unsupported``, like the single shape.  A scope with bindings
        beneath it names a *region*, not an entry: it expands to the owning
        entry scoped to it plus every binding strictly beneath it dispatched
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
        crosses the seam as pattern text, one batched call per entry,
        with root assertions on a concurrent probe that no dispatch
        shape can drop.  *row_cap*
        re-applies the caller's result bound after the
        merge on every input shape — ``glean`` trims by score, everything
        else keeps merge order — so it cannot multiply by entry count;
        the bound arrives gated (integer ``>= 1`` or ``None``).

        *paths* / *observations* exclusivity and the *row_cap* bound are
        enforced by the verbs' params gate before delegation.
        """
        if not self._bindings:
            return self._closed_error(op)
        if observations is not None:
            merged = await self._dispatch_grouped_observations(op, observations, user_id=user_id, **kwargs)
            return self._cap_rows(merged, op, row_cap)

        grant = self._enter_hop(op=op)
        if grant.refusal is not None:
            return grant.refusal
        try:
            plan = self._classify_fanout_scopes(op, paths)
            if plan.refusal is not None:
                return plan.refusal

            patterns = kwargs.get("patterns")
            if op == "glob" and isinstance(patterns, tuple):
                rest = {key: value for key, value in kwargs.items() if key not in ("patterns", "not_arms")}
                arms = cast("tuple[str, ...]", patterns)
                not_arms = cast("tuple[str, ...]", kwargs.get("not_arms", ()))
                named_coros, branches, skips = self._glob_dispatches(
                    plan, paths, arms, not_arms, user_id=user_id, **rest
                )
            elif op == "grep":
                globs = cast("tuple[str, ...]", kwargs.get("globs", ()))
                globs_not = cast("tuple[str, ...]", kwargs.get("globs_not", ()))
                rest = {key: value for key, value in kwargs.items() if key not in ("globs", "globs_not")}
                named_coros, branches, skips = self._grep_dispatches(
                    plan, paths, globs, globs_not, user_id=user_id, **rest
                )
            else:
                # Unscoped subsumes a narrower scope into the same entry.
                named_coros = [
                    self._dispatch_entry(binding, op, paths=tuple(dict.fromkeys(rels)), user_id=user_id, **kwargs)
                    for key, (binding, rels) in plan.scoped.items()
                    if key not in plan.unscoped
                ]
                branches = [
                    (binding.path, self._dispatch_entry(binding, op, paths=(), user_id=user_id, **kwargs))
                    for binding in plan.unscoped.values()
                ]
                skips = plan.skips
            if not named_coros and not branches:
                return self._with_skips(Result(ops=(op,)), skips)
            results = await self._gather_settled([*named_coros, *(coro for _, coro in branches)])
            named = results[: len(named_coros)]
            branch_results = list(zip((path for path, _ in branches), results[len(named_coros) :], strict=True))
            merged = self._merge_fanout(named, branch_results, frozenset(plan.scoped), op)
            return self._with_skips(self._cap_rows(merged, op, row_cap), skips)
        finally:
            self._exit_hop(grant.token)

    def _classify_fanout_scopes(self, op: Op, paths: tuple[str, ...]) -> _FanoutPlan:
        """Classify a fan-out's targets into the entries that will answer.

        No paths: every entry in table order — capable entries dispatch
        whole, incapable ones become skip records.  A path with bindings
        beneath it (or the root) names a *region*: the owning entry
        answers its scope, deeper bindings answer whole, both under the
        recorded-skip rule.  A plain path names one entry, which is
        gated — a scoped entry that cannot answer refuses loudly, like
        the single shape.  Refusals (invalid path, gate denial) come
        back on the plan; the collections are then empty.
        """
        scoped: dict[Path, tuple[Binding, list[Path]]] = {}
        unscoped: dict[Path, Binding] = {}
        skipped: dict[Path, ResultError] = {}

        if paths:
            for raw in paths:
                resolved = resolve_path(raw)
                if resolved.path is None:
                    return _FanoutPlan({}, {}, [], refusal=self._invalid_path(resolved, raw, op))
                full = resolved.path
                terminal = self._resolve_terminal(full)
                beneath = self._bindings_beneath(full)
                if full == ROOT or beneath:
                    if op not in terminal.binding.meta.caps:
                        skipped.setdefault(terminal.binding.path, self._skip_entry(op, terminal.binding))
                    elif terminal.rel == ROOT:
                        unscoped.setdefault(terminal.binding.path, terminal.binding)
                    else:
                        _b, rels = scoped.setdefault(terminal.binding.path, (terminal.binding, []))
                        rels.append(terminal.rel)
                    for binding in beneath:
                        if op in binding.meta.caps:
                            unscoped.setdefault(binding.path, binding)
                        else:
                            skipped.setdefault(binding.path, self._skip_entry(op, binding))
                    continue
                err = self._gate_entry(terminal.binding, op, write_rels=(terminal.rel,))
                if err is not None:
                    return _FanoutPlan({}, {}, [], refusal=err)
                _b, rels = scoped.setdefault(terminal.binding.path, (terminal.binding, []))
                rels.append(terminal.rel)
        else:
            for binding in self._bindings.values():
                if op in binding.meta.caps:
                    unscoped[binding.path] = binding
                else:
                    skipped.setdefault(binding.path, self._skip_entry(op, binding))

        return _FanoutPlan(scoped=scoped, unscoped=unscoped, skips=list(skipped.values()))

    def _glob_dispatches(
        self,
        plan: _FanoutPlan,
        paths: tuple[str, ...],
        arms: tuple[str, ...],
        not_arms: tuple[str, ...],
        *,
        user_id: str | None,
        **kwargs: object,
    ) -> tuple[
        list[Coroutine[Any, Any, Result]],
        list[tuple[Path, Coroutine[Any, Any, Result]]],
        list[ResultError],
    ]:
        """Build glob's dispatches: scoping crosses the seam as pattern text.

        The caller's pattern arrives brace-expanded as *arms* and the
        exclusions as *not_arms*; every step below is per-arm with
        any-arm admission and any-exclusion rejection. Each scope root
        composes each arm into one spatial pattern (name arm goes
        ``root/**/pattern``, path arm anchors under the root), but only
        into its owning entry and the entries beneath the root — never
        an ancestor's shadowed region. Residuation then derives every
        entry's members in entry-local coordinates, and each entry
        receives its whole deduped set as one batched call — exclusions
        compose per root identically, so one can never reach another
        root's subtree. Root assertions ride a separate concurrent
        probe grouped by owning entry (:meth:`_root_probe`),
        structurally immune to any dispatch optimization; its ``keep``
        honors every channel, so a root row is never served past a
        filter the caller stated. A dead residual set is routing, not a
        capability gap: the entry is not dispatched and no skip is
        minted; capability skips survive only where some arm can reach
        the entry's rows.
        """
        roots = tuple(dict.fromkeys(root for raw in paths if (root := resolve_path(raw).path) is not None))
        capable = {**plan.unscoped, **{key: binding for key, (binding, _rels) in plan.scoped.items()}}
        members = {key: self._composed_members(key, roots, arms) for key in capable}
        ext = cast("tuple[str, ...]", kwargs.get("ext", ()))
        ext_not = cast("tuple[str, ...]", kwargs.get("ext_not", ()))
        kind = cast("str | None", kwargs.get("kind"))
        columns = cast("frozenset[str] | None", kwargs.get("columns"))
        not_gates = [compile_filter(glob, ()) for glob in not_arms]
        unwanted = normalize_ext_channel(ext_not)

        def keep(row: Observation) -> bool:
            # Re-spells passes_filters, its authority: each arm composes
            # per row here, so the gates cannot be compiled once upfront.
            if not any(compile_filter(effective_pattern(row.path, arm), ext).matches(row.path) for arm in arms):
                return False
            if any(gate.matches(row.path) for gate in not_gates):
                return False
            if unwanted and (extract_extension(row.path) or "") in unwanted:
                return False
            return kind is None or row.kind == kind

        probes, unverifiable = self._root_probes(roots, keep, columns, user_id=user_id)
        branches: list[tuple[Path, Coroutine[Any, Any, Result]]] = [
            (
                key,
                self._dispatch_entry(
                    capable[key],
                    "glob",
                    patterns=tuple(sorted(live)),
                    globs_not=tuple(sorted(self._composed_members(key, roots, not_arms))),
                    user_id=user_id,
                    **kwargs,
                ),
            )
            for key, live in members.items()
            if live
        ]
        reach = roots or (ROOT,)
        skips = [
            skip
            for skip in plan.skips
            if skip.path is None or any(self._glob_reaches(skip.path, reach, arm) for arm in arms)
        ]
        return probes, branches, [*skips, *unverifiable]

    def _grep_dispatches(
        self,
        plan: _FanoutPlan,
        paths: tuple[str, ...],
        globs: tuple[str, ...],
        globs_not: tuple[str, ...],
        *,
        user_id: str | None,
        **kwargs: object,
    ) -> tuple[
        list[Coroutine[Any, Any, Result]],
        list[tuple[Path, Coroutine[Any, Any, Result]]],
        list[ResultError],
    ]:
        """Build grep's dispatches: scoping crosses the seam as glob text.

        Glob's dispatch shape on grep's channels: each scope root
        composes into the ``globs`` batch (no caller globs → the root
        composes to ``root/**``), exclusions compose per root so one can
        never reach another root's subtree, and a root whose path passes
        the caller's globs rides the batch as its own literal path — the
        content test can only happen at storage, so for grep the root
        row joins the scan, not the probe. Residuation, the owner gate,
        dead-entry skips, and the root probe are the glob machinery; the
        probe serves no rows, only classifications.
        """
        roots = tuple(dict.fromkeys(root for raw in paths if (root := resolve_path(raw).path) is not None))
        capable = {**plan.unscoped, **{key: binding for key, (binding, _rels) in plan.scoped.items()}}
        branches: list[tuple[Path, Coroutine[Any, Any, Result]]] = []
        for key, binding in capable.items():
            admissions = self._grep_admissions(key, roots, globs)
            if admissions is not None and not admissions:
                continue
            branches.append(
                (
                    key,
                    self._dispatch_entry(
                        binding,
                        "grep",
                        globs=tuple(sorted(admissions)) if admissions else (),
                        globs_not=tuple(sorted(self._composed_members(key, roots, globs_not))),
                        user_id=user_id,
                        **kwargs,
                    ),
                )
            )
        probes, unverifiable = self._root_probes(roots, lambda _row: False, None, user_id=user_id)
        reach = roots or (ROOT,)
        skips = [
            skip
            for skip in plan.skips
            if skip.path is None or any(self._glob_reaches(skip.path, reach, glob) for glob in globs or ("**",))
        ]
        return probes, branches, [*skips, *unverifiable]

    def _grep_admissions(self, key: Path, roots: tuple[Path, ...], globs: tuple[str, ...]) -> set[str] | None:
        """One entry's admission globs in its own coordinates; ``None`` is unrestricted.

        Unscoped with no globs restricts nothing; otherwise the composed
        members decide, plus find's operand law — a scope root whose own
        path passes the caller's globs (name-arm by name, path-arm by
        namespace path; no globs is an automatic hit) joins its owning
        entry's batch as a literal member. An empty set is a dead entry.
        """
        if not roots and not globs:
            return None
        members = self._composed_members(key, roots, (globs or ("**",)) if roots else globs)
        for root in roots:
            if root == ROOT or self._resolve_terminal(root).binding.path != key:
                continue
            if not globs or any(compile_filter(glob, ()).matches(root) for glob in globs):
                members.update(self._residual_renders(escape_glob(str(root)), key))
        return members

    def _composed_members(self, key: Path, roots: tuple[Path, ...], patterns: tuple[str, ...]) -> set[str]:
        """Entry-local renders of *patterns* under the call's scope shape.

        Unscoped: name-arm patterns broadcast verbatim (coordinate-free),
        path-arm patterns residuate against the bind path. Scoped: each
        pattern composes under each root reaching this entry, then
        residuates; a dead residual set simply contributes nothing.
        """
        members: set[str] = set()
        if not roots:
            for pattern in patterns:
                if "/" not in pattern:
                    members.add(pattern)
                else:
                    members.update(self._residual_renders(pattern, key))
            return members
        for root in roots:
            owner = self._resolve_terminal(root).binding.path
            if key != owner and not _path_covers(root, key):
                continue
            for pattern in patterns:
                members.update(self._residual_renders(composed_pattern(root, pattern), key))
        return members

    def _root_probes(
        self,
        roots: tuple[Path, ...],
        keep: Callable[[Observation], bool],
        columns: frozenset[str] | None,
        *,
        user_id: str | None,
    ) -> tuple[list[Coroutine[Any, Any, Result]], list[ResultError]]:
        """One point-read probe per owning entry, asserting its named roots.

        The namespace root is exempt — it is the namespace itself, never
        a row. An entry that cannot answer ``stat`` leaves its roots
        honestly undeterminable: a warning on record, never coerced to
        absent, never a silent pass.
        """
        grouped: dict[Path, tuple[Binding, list[Path]]] = {}
        unverifiable: list[ResultError] = []
        for root in roots:
            if root == ROOT:
                continue
            terminal = self._resolve_terminal(root)
            if "stat" not in terminal.binding.meta.caps:
                unverifiable.append(
                    ResultError(
                        kind=VFSErrorKind.unsupported,
                        message=f"Root {root} is unverifiable: {terminal.binding.path} does not support stat",
                        severity=Severity.warning,
                        path=root,
                        source=terminal.binding.path,
                    )
                )
                continue
            _b, rels = grouped.setdefault(terminal.binding.path, (terminal.binding, []))
            rels.append(terminal.rel)
        coros: list[Coroutine[Any, Any, Result]] = [
            self._root_probe(binding, rels, keep, columns, user_id=user_id) for binding, rels in grouped.values()
        ]
        return coros, unverifiable

    async def _root_probe(
        self,
        binding: Binding,
        rels: list[Path],
        keep: Callable[[Observation], bool],
        columns: frozenset[str] | None,
        *,
        user_id: str | None,
    ) -> Result:
        """Assert scope roots with one batched point-read against their entry.

        A missing root classifies loud through the entry's own descent
        ladder; *keep* decides whether a present root's row joins the
        result — glob serves it on a pattern match (find semantics:
        operands are tested, never exempt), grep serves none (a root's
        content test can only happen at storage).
        """
        probe = [Observation(path=rel) for rel in dict.fromkeys(rels)]
        result = await self._dispatch_entry(binding, "stat", observations=probe, columns=columns, user_id=user_id)
        kept = [row for row in result.observations if keep(row)]
        if len(kept) == len(result.observations):
            return result
        return result.model_copy(update={"observations": kept})

    @staticmethod
    def _residual_renders(pattern: str, bind_path: Path) -> list[str]:
        """Sorted entry-local renders of the pattern's live residuals.

        Empty-tuple residuals are dropped: the bind-point row is the
        parent's stored directory, never a child dispatch.
        """
        return sorted(render_residual(components) for components in residuals(pattern, bind_path) if components)

    @staticmethod
    def _glob_reaches(bind_path: Path, roots: tuple[Path, ...], pattern: str) -> bool:
        """Whether any scope root lets the pattern reach rows of this entry."""
        if any(_path_covers(bind_path, root) for root in roots):
            return True  # a root inside the entry names rows the entry holds
        return any(components for root in roots for components in residuals(composed_pattern(root, pattern), bind_path))

    @staticmethod
    def _merge_fanout(
        named: list[Result],
        branch_results: list[tuple[Path, Result]],
        scoped_keys: frozenset[Path],
        op: Op,
    ) -> Result:
        """Merge fan-out answers under the pinning rule — a pure function.

        Branches whose bind path the caller also *named* (subsumed
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
        user_id: str | None = None,
        **kwargs: object,
    ) -> Result:
        """Route src/dest pair mutations, gating every pair before any dispatch.

        Pairs arrive as caller-facing :class:`TwoPathOperation` and dispatch
        as gated, entry-relative :class:`ResolvedPair` groups.  Both
        endpoints of a pair must resolve to the same **entry** — a pair
        spanning entries is ``cross_mount`` (the EXDEV rule; no silent
        copy-and-delete), and a pair that would move a bind site is
        ``busy``.  ``move`` mutates both endpoints, so both are write-gated;
        ``copy`` only writes ``dest``.

        All pairs are *validated* up front: a single bad pair rejects the
        whole batch with nothing dispatched.  Atomicity stops at validation
        — once per-entry dispatch begins, entries run concurrently and a
        runtime failure in one does not roll back another.
        """
        if not self._bindings:
            return self._closed_error(op)
        if not operations:
            return Result(ops=(op,))

        groups: dict[Path, tuple[Binding, list[ResolvedPair]]] = {}
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
            if src_terminal.binding.path != dest_terminal.binding.path:
                return self._error(
                    f"Cross-mount {op} is not supported: {src_full} and {dest_full} resolve to different mounts",
                    kind=VFSErrorKind.cross_mount,
                    op=op,
                )
            write_rels = (src_terminal.rel, dest_terminal.rel) if op == "move" else (dest_terminal.rel,)
            err = self._gate_entry(src_terminal.binding, op, write_rels=write_rels)
            if err is not None:
                return err

            _b, pairs = groups.setdefault(src_terminal.binding.path, (src_terminal.binding, []))
            pairs.append(ResolvedPair(src=src_terminal.rel, dest=dest_terminal.rel))

        results = await self._gather_settled(
            self._dispatch_entry(binding, op, operations=group, user_id=user_id, **kwargs)
            for binding, group in groups.values()
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
        overwrite: bool,
        user_id: str | None,
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
                return self._error(
                    f"{op} batch must be an iterable of (src, dest) pairs, got {type(batch).__name__}",
                    kind=VFSErrorKind.invalid,
                    op=op,
                )
        else:
            assert src is not None and dest is not None
            pairs = [TwoPathOperation(src=src, dest=dest)]
        operations: list[TwoPathOperation] = []
        for item in pairs:
            pair = self._coerce_two_path(item)
            if pair is None:
                return self._error(
                    f"{op} pair must be (src, dest) of two strings: {item!r}",
                    kind=VFSErrorKind.invalid,
                    op=op,
                )
            operations.append(pair)
        return await self._route_two_path(op, operations, overwrite=overwrite, user_id=user_id)

    async def _route_entry_batch(
        self,
        entries: Sequence[Entry],
        *,
        overwrite: bool = True,
        parents: bool = False,
        user_id: str | None = None,
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
        if not self._bindings:
            return self._closed_error("write")
        rows = self._as_list(entries)
        if rows is None:
            return self._error(
                f"write entries must be an iterable of Entry, got {type(entries).__name__}",
                kind=VFSErrorKind.invalid,
                op="write",
            )
        if not rows:
            return Result(ops=("write",))

        groups: dict[Path, tuple[Binding, list[Entry]]] = {}
        for entry in rows:
            if not isinstance(entry, Entry):
                return self._error(
                    f"write entries must be Entry instances, got {type(entry).__name__}",
                    kind=VFSErrorKind.invalid,
                    op="write",
                )
            resolved = resolve_path(entry.path, mutation=True)
            if resolved.path is None:
                return self._invalid_path(resolved, entry.path, "write")
            terminal = self._resolve_terminal(resolved.path)
            err = self._gate_entry(terminal.binding, "write", write_rels=(terminal.rel,))
            if err is not None:
                return err
            _b, entry_group = groups.setdefault(terminal.binding.path, (terminal.binding, []))
            entry_group.append(entry.without_mount(terminal.binding.path))

        results = await self._gather_settled(
            self._dispatch_entry(
                binding,
                "write",
                entries=sorted(group, key=lambda e: e.path.depth),
                overwrite=overwrite,
                parents=parents,
                user_id=user_id,
            )
            for binding, group in groups.values()
        )
        return Result.merge(results, op="write")

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
                f"Hop budget exhausted while routing {op!r} — a mount loop, or a composition deeper than the budget",
                kind=VFSErrorKind.budget_exhausted,
                op=op,
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

    def _match_mount(self, path: Path) -> Binding | None:
        """Longest-prefix binding for *path* — ``None`` only when closed."""
        for mount_path in self._sorted_mount_paths:
            if mount_path == ROOT or path == mount_path or path.startswith(mount_path + "/"):
                return self._bindings[mount_path]
        return None

    def _resolve_terminal(self, path: Path) -> ResolvedTerminal:
        """Resolve a gated :class:`Path` to its owning entry plus residual.

        A single longest-prefix match — nested mounts are ordinary deeper
        rows in the same table, so there is nothing to recurse into.  The
        root identity entry backstops every path; callers guard the
        closed-table case before resolving.
        """
        binding = self._match_mount(path)
        assert binding is not None, "resolve on a closed filesystem"
        return ResolvedTerminal(binding=binding, rel=path.without_mount(binding.path))

    def _bindings_beneath(self, path: Path) -> list[Binding]:
        """The bindings strictly beneath *path* (router coordinates).

        Routing state, not visibility: region expansion, tree descents, the
        busy guard, and shadow filtering all read it.
        """
        if path == ROOT:
            return [b for p, b in self._bindings.items() if p != ROOT]
        return [b for p, b in self._bindings.items() if p.startswith(path + "/")]

    # -------------------------------------------------------------------
    # gates — capability snapshot, then composed permissions
    # -------------------------------------------------------------------

    def _gate_params(self, op: Op, /, **params: object) -> Result | None:
        """Refuse type, domain, and input-shape garbage before anything else.

        The rules live in the per-op table (``vfs.params``); a violation
        classifies ``invalid`` naming the parameter.  Caller-input facts
        outrank every router-state fact, so this gate runs first at every
        public verb — a bad parameter reports ``invalid`` even on a closed
        table or a busy path.
        """
        problem = param_violation(op, params)
        if problem is None:
            return None
        return self._error(problem, kind=VFSErrorKind.invalid, op=op)

    def _gate_entry(
        self,
        binding: Binding,
        op: Op,
        *,
        write_rels: Sequence[Path] = (),
    ) -> Result | None:
        """Capability → permission, in the pinned order.

        Every dispatch chokepoint runs this gate on its resolved entry
        before touching it.  The order is a contract: an incapable entry
        reads as ``unsupported``, never as a policy denial.  Existence and
        kind are storage truth, classified by the backend at dispatch — the
        gate holds only what the router itself knows.

        A capability failure is an entry-level fact and reports the entry's
        bind path.  *write_rels* are the entry-relative paths the permission
        layers check (empty when the write target is derived later, as in
        mkedge's pre-derivation gate); each denial reports its own
        router-side path.
        """
        if op not in binding.meta.caps:
            return self._error(
                f"Operation {op!r} is not supported for storage mounted at {binding.path}",
                kind=VFSErrorKind.unsupported,
                op=op,
                path=binding.path,
            )
        for rel in write_rels:
            full = rel.with_mount(binding.path)
            err = check_writable_composed(self._permission_layers(full), op)
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
            permission_map = self._bindings[mount_path].meta.permission_map
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

    def _busy_guard(self, op: Op, full: Path, *, subtree: bool) -> Result | None:
        """Refuse a data-plane mutation that targets a live bind site.

        The EBUSY rule: a bound path (or, with *subtree*, a region holding
        bound paths) may not be deleted or moved out from under its binding
        — a dangling binding whose stored site is gone would be worse than
        the refusal.  Unmount first.
        """
        at_bind = full != ROOT and full in self._bindings
        beneath = self._bindings_beneath(full) if subtree else []
        if not at_bind and not beneath:
            return None
        return self._error(
            f"{full} is a mount point or contains one — unmount first",
            kind=VFSErrorKind.busy,
            op=op,
            path=full,
        )

    # -------------------------------------------------------------------
    # the funnel — one seam from op to storage, one seam back out
    # -------------------------------------------------------------------

    async def _dispatch_entry(self, binding: Binding, op: Op, *, user_id: str | None = None, **kwargs: Any) -> Result:
        """Dispatch *op* to an entry and bring the result back to router coordinates.

        The single outbound/inbound seam: call the entry's storage, rebase
        under the entry path, then drop rows shadowed by deeper bindings.
        Every routed dispatch — single, grouped, paired, fan-out, tree —
        funnels through here.
        """
        result = await self._call_storage(binding, op, user_id=user_id, **kwargs)
        result = result.with_mount(binding.path)
        return self._shadow_filter(result, binding)

    async def _call_storage(
        self,
        binding: Binding,
        op: Op,
        *,
        user_id: str | None = None,
        **kwargs: Any,
    ) -> Result:
        """The exhaustive op → typed-method match beneath the funnel.

        The chokepoints upstream carry *op* as a variable, so this match is
        where the op meets a typed method: sixteen boring arms ending in
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
        the bind path on the way out (identity for the root entry).

        Transactions live behind these methods: a backend opens and commits
        its own session inside each op — the router never sees one.
        """
        storage = binding.storage
        try:
            match op:
                case "read":
                    return await storage.read(user_id=user_id, **kwargs)
                case "stat":
                    return await storage.stat(user_id=user_id, **kwargs)
                case "ls":
                    return await storage.ls(user_id=user_id, **kwargs)
                case "tree":
                    return await storage.tree(user_id=user_id, **kwargs)
                case "glob":
                    if not isinstance(storage, SupportsPatternSearch):
                        return self._backend_unsupported(op)
                    return await storage.glob(user_id=user_id, **kwargs)
                case "grep":
                    if not isinstance(storage, SupportsPatternSearch):
                        return self._backend_unsupported(op)
                    return await storage.grep(user_id=user_id, **kwargs)
                case "glean":
                    if not isinstance(storage, SupportsGlean):
                        return self._backend_unsupported(op)
                    return await storage.glean(user_id=user_id, **kwargs)
                case "write":
                    if not isinstance(storage, SupportsMutation):
                        return self._backend_unsupported(op)
                    return await storage.write(user_id=user_id, **kwargs)
                case "edit":
                    if not isinstance(storage, SupportsMutation):
                        return self._backend_unsupported(op)
                    return await storage.edit(user_id=user_id, **kwargs)
                case "delete":
                    if not isinstance(storage, SupportsMutation):
                        return self._backend_unsupported(op)
                    return await storage.delete(user_id=user_id, **kwargs)
                case "restore":
                    if not isinstance(storage, SupportsMutation):
                        return self._backend_unsupported(op)
                    return await storage.restore(user_id=user_id, **kwargs)
                case "sweep":
                    if not isinstance(storage, SupportsMutation):
                        return self._backend_unsupported(op)
                    return await storage.sweep(user_id=user_id, **kwargs)
                case "mkdir":
                    if not isinstance(storage, SupportsMutation):
                        return self._backend_unsupported(op)
                    return await storage.mkdir(user_id=user_id, **kwargs)
                case "move":
                    if not isinstance(storage, SupportsMutation):
                        return self._backend_unsupported(op)
                    return await storage.move(user_id=user_id, **kwargs)
                case "copy":
                    if not isinstance(storage, SupportsMutation):
                        return self._backend_unsupported(op)
                    return await storage.copy(user_id=user_id, **kwargs)
                case "graph":
                    if not isinstance(storage, SupportsGraph):
                        return self._backend_unsupported(op)
                    return await storage.graph(user_id=user_id, **kwargs)
                case "mkedge":
                    if not isinstance(storage, SupportsMutation):
                        return self._backend_unsupported(op)
                    return await storage.mkedge(user_id=user_id, **kwargs)
                case "run":
                    if not isinstance(storage, SupportsRun):
                        return self._backend_unsupported(op)
                    return await storage.run(user_id=user_id, **kwargs)
                case _:
                    assert_never(op)
        except TransportError as exc:
            return self._error(
                f"Backend for {binding.path} is unavailable: {exc}",
                kind=VFSErrorKind.backend_unavailable,
                op=op,
                path=ROOT,
            )

    def _backend_unsupported(self, op: Op) -> Result:
        """The funnel's narrowing miss: the backend lacks *op*'s family.

        Entry-anchored under the funnel's seam invariant (see
        :meth:`_call_storage`): ``path=ROOT`` rebases to the bind path.
        """
        return self._error(
            f"Storage backend does not support operation: {op}",
            kind=VFSErrorKind.unsupported,
            op=op,
            path=ROOT,
        )

    def _shadow_filter(self, result: Result, binding: Binding) -> Result:
        """Drop rows a deeper binding shadows — the full-shadow mount rule.

        A row strictly under a deeper bind path belongs to that binding's
        storage, whatever the shallower storage happens to hold there
        (crash orphans, rows written by another client of shared storage).
        The row *at* the bind path survives: it is the stored mount-point
        directory, visible in listings like any other.
        """
        deeper = [b.path for b in self._bindings_beneath(binding.path)]
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

    def _skip_entry(self, op: Op, binding: Binding) -> ResultError:
        """Info-severity coverage record for an entry an unscoped fan-out
        or tree descent skipped as incapable — recorded, never a failure.

        Minted in router coordinates above the rebase seam, so the bind
        path is stamped as both anchor (``path``) and provenance
        (``source``) here.
        """
        return ResultError(
            kind=VFSErrorKind.unsupported,
            message=f"Skipped {binding.path}: operation {op!r} is not supported for its storage",
            severity=Severity.info,
            path=binding.path,
            source=binding.path,
        )

    @staticmethod
    def _with_skips(result: Result, skips: list[ResultError]) -> Result:
        """Append capability-skip records after the merge — coverage facts
        must never feed the zero-progress rule's branch arithmetic."""
        if not skips:
            return result
        return result.model_copy(update={"errors": [*result.errors, *skips]})

    @staticmethod
    def _cap_rows(result: Result, op: Op, row_cap: int | None) -> Result:
        """Re-apply the caller's result bound after a merge.

        ``glean`` trims by score — the only ranked verb; cross-entry
        scores are only loosely comparable.  Everything else keeps merge
        order (named scopes first, then mount-table order), untouched by
        stray scores.  Errors and warnings are never trimmed.
        """
        if row_cap is None or len(result.observations) <= row_cap:
            return result
        if op == "glean":
            return result.top(row_cap)
        return result.model_copy(update={"observations": list(result.observations[:row_cap])})

    # -------------------------------------------------------------------
    # errors
    # -------------------------------------------------------------------

    def _error(
        self,
        message: str,
        *,
        kind: VFSErrorKind,
        op: str,
        severity: Severity = Severity.error,
        path: Path | None = None,
        data: dict[str, Any] | None = None,
    ) -> Result:
        """Compose a failed ``Result``.  The router never raises — values in,
        ``Result`` out; raising is the call boundary's job (``raise_if_failed``).

        Pass the prose *message*, the structured *kind*, and the producing
        *op* — all required; the router always knows its verb and a failure
        always reports it.  The verdict is derived from the entries, never
        stored.  Callers that already hold a shaped ``Result`` should
        return it directly.
        """
        return Result(
            ops=(op,),
            errors=[ResultError(kind=kind, message=message, severity=severity, path=path, data=data)],
        )

    def _invalid_path(self, resolved: ResolvedPath, raw: str, op: Op) -> Result:
        """Classify a failed path resolution — the one invalid-path mint.

        Total: called only in the ``resolved.path is None`` branch, so the
        resolve idiom keeps its narrowing; prefers the gate's own prose.
        """
        return self._error(resolved.error or f"Invalid path: {raw!r}", kind=VFSErrorKind.invalid, op=op)

    def _closed_error(self, op: Op) -> Result:
        """Classified answer for a dispatch attempted after ``close()``."""
        return self._error(
            "Filesystem is closed",
            kind=VFSErrorKind.backend_unavailable,
            op=op,
        )
