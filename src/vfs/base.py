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
from collections.abc import Iterable
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, NamedTuple, assert_never

from vfs.exceptions import MountError
from vfs.models import Entry, Observation
from vfs.ops import MUTATING_OPS, CaseMode, GrepOutputMode, TwoPathOperation
from vfs.params import param_violation
from vfs.paths import METADATA_ROOT, Path, edge_in_path, edge_out_path, resolve_path, validate_edge_endpoint
from vfs.permissions import (
    Permission,
    PermissionLayer,
    PermissionMap,
    check_writable_composed,
    coerce_permissions,
)
from vfs.results import Result, ResultError, VFSErrorKind
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
    from collections.abc import Coroutine, Sequence

    from vfs.ops import Op
    from vfs.paths import ResolvedPath

ROOT = Path("/")

# Router-traversal depth budget for the current request: decremented once
# per router entered (adapters and wire hops re-enter), never per mount.
_hop_budget: ContextVar[int | None] = ContextVar("vfs_hop_budget", default=None)


@dataclass(slots=True)
class MountMeta:
    """Per-entry policy and lifecycle facts — the ``mnt_flags`` of a binding.

    Policy lives on the entry, state lives on the storage: *permission_map*
    holds mount-relative rules (``None`` — no local rules), *no_overlay*
    refuses further binds beneath this entry, *owned* says ``close()``
    disposes the storage, and *caps* is the capability snapshot taken from
    ``storage.capabilities()`` at bind.
    """

    permission_map: PermissionMap | None = None
    no_overlay: bool = False
    owned: bool = True
    caps: frozenset[str] = frozenset()


class Binding(NamedTuple):
    """One mount-table fact: *storage* bound at *path* under *meta* policy.

    The identity binding — the node's own storage at ``/`` — is an ordinary
    entry: every path resolves to exactly one binding, and the root entry
    is simply the longest-prefix fallback.
    """

    path: Path
    storage: StorageBackend
    meta: MountMeta


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
            caps=frozenset(storage.capabilities()),
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
        on the entry; *owned* says ``close()`` disposes this storage.

        The site probe is storage I/O and runs outside the mount lock; the
        table is re-checked and committed under it with no await between.
        """
        if not isinstance(storage, StorageBackend):
            msg = f"storage must implement the read family (see vfs.storage), got {type(storage).__name__}"
            raise TypeError(msg)
        mount_path = self._normalize_mount_path(path)

        probed = await self._probe_bind_site(mount_path)
        if probed is not None:
            msg = f"Cannot bind at {mount_path}: {probed}"
            raise ValueError(msg)

        meta = MountMeta(
            permission_map=None if permissions is None else coerce_permissions(permissions),
            no_overlay=no_overlay,
            owned=owned,
            caps=frozenset(storage.capabilities()),
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

        made = await self.mkdir(str(mount_path), parents=parents, exist_ok=True)
        if not made.success:
            detail = made.error_message or "storage refused the mount-point directory"
            msg = f"Cannot mount at {mount_path}: {detail}"
            raise MountError(msg, result=made)
        await self.bind(storage, str(mount_path), permissions=permissions, no_overlay=no_overlay, owned=owned)

    async def remove_mount(self, path: str) -> None:
        """Unmount *path* — unbind + strict rmdir, fused.

        The binding is dropped first (table surgery under the lock), then
        the mount-point directory is removed with a strict, non-recursive
        delete against whichever storage owns the parent path.  Never a
        cascade: on shared or persistent storage the directory may have
        gained rows this router never saw, and unmount must not destroy
        them.  A failed rmdir leaves the unbind standing and raises — the
        namespace keeps a plain directory, loud and recoverable.

        Storage lifecycle is untouched: unbinding never disposes an engine
        or session.  Dispose through ``close()`` or by closing a retained
        reference to the storage.
        """
        mount_path = self._normalize_mount_path(path)
        await self.unbind(str(mount_path))
        removed = await self.delete(path=str(mount_path), permanent=True, cascade=False)
        if not removed.success:
            detail = removed.error_message or "storage refused the delete"
            msg = f"Unmounted {mount_path}, but removing its directory failed: {detail}"
            raise MountError(msg, result=removed)

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
        if len(errors) == 1:
            raise errors[0]
        if errors:
            raise ExceptionGroup("errors while closing storages", errors)

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
    def _normalize_mount_path(path: str) -> Path:
        """Canonicalize and validate a mount path through the :class:`Path` gate.

        The gate does the normalization and structural validation (make
        absolute, drop ``.``/``..``, strip per-segment whitespace, reject
        control characters and over-long segments).  A mount path adds only
        two policy rules the generic gate cannot know: it is never the root,
        and it never uses the reserved metadata segment (``".vfs"``).  Stray
        whitespace is canonicalized like any other path, not rejected;
        interior spaces (``"/My Documents"``) are preserved.
        """
        mount_path = Path(path)
        if mount_path == ROOT:
            msg = "Mount path must not be empty or root"
            raise ValueError(msg)
        meta_segment = METADATA_ROOT.strip("/")
        if meta_segment in mount_path.split("/")[1:]:
            msg = f"Mount path may not use the reserved metadata segment {meta_segment!r}: {path!r}"
            raise ValueError(msg)
        return mount_path

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
        and *path*/*content* are mutually exclusive.

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
        return await self._route_single(
            "write",
            path,
            None,
            content=content,
            overwrite=overwrite,
            parents=parents,
            user_id=user_id,
        )

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
        permanent: bool = False,
        cascade: bool = True,
        user_id: str | None = None,
    ) -> Result:
        """Delete *path* (or each observation row).

        A live bind site is ``busy``: a bound path, or a region holding
        bound paths, must be unmounted before it can be deleted — the
        EBUSY rule.
        """
        refusal = self._gate_params(
            "delete", path=path, observations=observations, permanent=permanent, cascade=cascade, user_id=user_id
        )
        if refusal is not None:
            return refusal
        return await self._route_single(
            "delete",
            path,
            observations,
            permanent=permanent,
            cascade=cascade,
            user_id=user_id,
        )

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
        otherwise — cross-backend edges are a later story).  The entry
        writes the canonical ``edges/out`` projection; the inverse ``in``
        path is derived, never a write target, and is permission-gated in
        the owning entry's coordinates like any other write.
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
            validate_edge_endpoint(src_terminal.rel, "source")
            validate_edge_endpoint(tgt_terminal.rel, "target")
        except ValueError as exc:
            return self._error(str(exc), kind=VFSErrorKind.invalid, op="mkedge")
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

        try:
            full_edge = edge_out_path(src_terminal.rel, tgt_terminal.rel, edge_type).with_mount(binding.path)
            full_inverse = edge_in_path(src_terminal.rel, tgt_terminal.rel, edge_type).with_mount(binding.path)
        except ValueError as exc:
            return self._error(str(exc), kind=VFSErrorKind.invalid, op="mkedge")
        for full in (full_edge, full_inverse):
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
        max_count: int | None = None,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result:
        """Match *pattern* against the namespace — unscoped calls reach every entry.

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
            max_count=max_count,
            columns=columns,
            user_id=user_id,
        )
        if refusal is not None:
            return refusal
        return await self._route_fanout(
            "glob",
            paths=paths,
            observations=observations,
            row_cap=max_count,
            pattern=pattern,
            ext=ext,
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
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result:
        """Search content for *pattern* — unscoped calls reach every entry.

        *max_count* caps matches **per file** (ripgrep's ``-m``), not the
        row count — a fan-out returns one row per matching file regardless.
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
            columns=columns,
            user_id=user_id,
        )
        if refusal is not None:
            return refusal
        return await self._route_fanout(
            "grep",
            paths=paths,
            observations=observations,
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

        if op == "delete":
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
        rows = self._as_list(observations)
        if rows is None:
            return self._error(
                f"observations must be an iterable of Observation, got {type(observations).__name__}",
                kind=VFSErrorKind.invalid,
                op=op,
            )
        groups: dict[Path, tuple[Binding, list[Observation]]] = {}
        for obs in rows:
            if not isinstance(obs, Observation):
                return self._error(
                    f"observations must be Observation instances, got {type(obs).__name__}",
                    kind=VFSErrorKind.invalid,
                    op=op,
                )
            resolved = resolve_path(obs.path, mutation=op in MUTATING_OPS)
            if resolved.path is None:
                return self._invalid_path(resolved, obs.path, op)
            if op == "delete":
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
        plain.  *row_cap* re-applies the caller's result bound after the
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

            # An unscoped dispatch already covers its whole entry, so a
            # narrower scope into the same entry is subsumed.
            named_coros = [
                self._dispatch_entry(binding, op, paths=tuple(rels), user_id=user_id, **kwargs)
                for key, (binding, rels) in plan.scoped.items()
                if key not in plan.unscoped
            ]
            branch_bindings = list(plan.unscoped.values())
            branch_coros = [
                self._dispatch_entry(binding, op, paths=(), user_id=user_id, **kwargs) for binding in branch_bindings
            ]
            if not named_coros and not branch_coros:
                return self._with_skips(Result(ops=(op,)), plan.skips)
            results = await self._gather_settled([*named_coros, *branch_coros])
            named = results[: len(named_coros)]
            branch_results = list(zip((b.path for b in branch_bindings), results[len(named_coros) :], strict=True))
            merged = self._merge_fanout(named, branch_results, frozenset(plan.scoped), op)
            return self._with_skips(self._cap_rows(merged, op, row_cap), plan.skips)
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
                entries=group,
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
        if len(bugs) == 1:
            raise bugs[0]
        if bugs:
            raise ExceptionGroup("impl errors during dispatch", bugs)
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
