"""VirtualFileSystem — async router whose mount boundary is the public API.

The base class owns mount routing and path rebasing.  The filesystem object
itself owns ``/`` — mounting at ``"/"`` is illegal.

Public methods are routers.  They resolve the terminal filesystem via
longest-prefix mount matching, then dispatch across the mount boundary:

- When the terminal is ``self``, the router drops to local storage through
  ``_call_local_impl`` — the one seam down to an ``_*_impl`` method.
- When the terminal is a child mount, the router calls the child's **public**
  method only — never the child's session, engine, or ``_*_impl``.  Values go
  in, ``Result`` comes out.

Five dispatch shapes cover the whole verb surface: single-path (most verbs),
grouped observations (chained rows, and ``graph`` over row sets), two-path
pairs (``move``/``copy``), the endpoint pair (``mkedge``), and fan-out
(``glob``/``grep``/``glean`` with no scope reach every mount in parallel).
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Literal, NamedTuple

from vfs.exceptions import exception_for_kind
from vfs.ops import MUTATING_OPS
from vfs.paths import METADATA_ROOT, Path, edge_out_path, normalize_path, resolve_path
from vfs.permissions import (
    Permission,
    PermissionMap,
    check_writable,
    coerce_permissions,
)
from vfs.projection import TRAVERSAL_FUNCTIONS
from vfs.replace import EditOperation
from vfs.results2 import Result, ResultError, VFSErrorKind

if TYPE_CHECKING:
    from collections.abc import Sequence

    from vfs.models2 import Entry, Observation
    from vfs.ops import Op

# Grep option vocabularies — shared with the CLI grammar when it lands.
CaseMode = Literal["sensitive", "insensitive", "smart"]
GrepOutputMode = Literal["lines", "files", "count"]


class TwoPathOperation(NamedTuple):
    """A source/destination pair for move or copy — a router-owned shape."""

    src: str
    dest: str


class VirtualFileSystem:
    """Async router base class for all VFS filesystems."""

    def __init__(
        self,
        *,
        name: str | None = None,
        title: str | None = None,
        description: str | None = None,
        storage: bool = False,
        allow_child_mounts: bool = True,
        raise_on_error: bool = False,
        permissions: Permission | PermissionMap = "read_write",
    ) -> None:
        self.name = name
        self.title = title
        self.description = description
        self._storage = storage
        self._allow_child_mounts = allow_child_mounts
        self._raise_on_error = raise_on_error
        self._permission_map: PermissionMap = coerce_permissions(permissions)
        self._parent: VirtualFileSystem | None = None
        self._mounts: dict[Path, VirtualFileSystem] = {}
        self._sorted_mount_paths: list[Path] = []
        self._class_name = self.__class__.__name__

    # -------------------------------------------------------------------
    # mounts and routing
    # -------------------------------------------------------------------

    async def add_mount(self, filesystem: VirtualFileSystem, path: str | None = None) -> None:
        """Mount a child *filesystem* at *path*, which may be nested.

        *path* is optional: when omitted, the filesystem's ``name`` is used as
        the mount point, so a named filesystem can mount itself
        (``root.add_mount(VirtualFileSystem(name="data"))`` lands at ``/data``).
        An explicit *path* takes precedence; if neither *path* nor the
        filesystem's name is available, the call raises.

        *path* is interpreted relative to this filesystem: the namespace
        root is the global origin, and calling on a sub-node treats *path*
        as local to that node (so ``data.add_mount(fs, "/tmp")`` lands at the
        data-local ``/tmp``).

        Routing:

        - If *path* falls under an existing mount, the request is delegated
          to that mount — with ``/data`` mounted, ``add_mount(fs, "/data/tmp")``
          becomes ``data_fs.add_mount(fs, "/tmp")``.  This recurses to any depth.
        - Otherwise *self* owns the mount.  It is rejected when a deeper
          mount already sits beneath *path* (the reverse order: ``/data/tmp``
          first, then ``/data``), when it duplicates an instance or would
          form a cycle, or — if *self* has storage — when stored contents
          conflict with the mount point (see ``_is_path_mountable``).

        A filesystem created with ``allow_child_mounts=False`` (e.g. a mount
        that proxies a remote/external namespace) rejects any mount whose
        owner it would be — including a delegated one — so a parent cannot
        mutate the remote's local mount table without an explicit opt-in.
        """
        mount_name = path or filesystem.name
        if not mount_name:
            msg = "add_mount needs a path or a named filesystem"
            raise ValueError(msg)
        mount_path = self._normalize_mount_path(mount_name)

        if not self._allow_child_mounts:
            msg = f"{self._class_name} does not allow child mounts"
            raise ValueError(msg)

        # A filesystem lives in one place only: reject self-mounts, re-mounts, or cycles (checked at the true root).
        if filesystem is self:
            msg = "Cannot mount a filesystem into itself"
            raise ValueError(msg)
        if filesystem._parent is not None:
            msg = f"Cannot mount at {mount_path}: that filesystem is already mounted elsewhere"
            raise ValueError(msg)
        if id(self._root()) in filesystem._reachable_ids():
            msg = (
                f"Mounting at {mount_path} would create a cycle: "
                "that filesystem already contains this namespace's root"
            )
            raise ValueError(msg)

        matched = self._match_mount(mount_path)
        if matched is not None:
            mount_at, mount_fs = matched
            if mount_at == mount_path:
                msg = f"Mount already exists at: {mount_path}"
                raise ValueError(msg)
            await mount_fs.add_mount(filesystem, mount_path[len(mount_at) :])
            return

        # self owns mount_path
        for existing_path in self._mounts:
            if existing_path.startswith(mount_path + "/"):
                msg = f"Cannot mount at {mount_path}: it is owned by a deeper mount at {existing_path}"
                raise ValueError(msg)
        if self._storage and not await self._is_path_mountable(mount_path):
            msg = f"Cannot mount at {mount_path}: storage contents conflict with that mount point"
            raise ValueError(msg)

        filesystem._raise_on_error = self._raise_on_error
        filesystem._parent = self
        self._mounts[mount_path] = filesystem
        self._rebuild_sorted_mounts()

    async def remove_mount(self, path: str) -> None:
        """Unmount the filesystem at *path*, which may be nested.

        *path* is interpreted relative to this filesystem, as in
        ``add_mount``.  A nested path under an existing mount is delegated to
        that mount.  Only the mount table is updated; lifecycle
        (engine disposal) is the caller's concern — disposal happens in
        ``close()`` or via an explicit ``await fs.close()`` on a reference
        the caller retained.
        """
        mount_path = self._normalize_mount_path(path)
        matched = self._match_mount(mount_path)
        if matched is not None and matched[0] != mount_path:
            mount_at, mount_fs = matched
            await mount_fs.remove_mount(mount_path[len(mount_at) :])
            return
        if mount_path not in self._mounts:
            msg = f"No mount at: {mount_path!r}"
            raise ValueError(msg)
        detached = self._mounts.pop(mount_path)
        detached._parent = None
        self._rebuild_sorted_mounts()

    async def close(self) -> None:
        """Close every mounted filesystem, then clear the mount table.

        Closing is polymorphic: each mount closes itself (a
        ``DatabaseFileSystem`` disposes its own engine).  The router never
        touches a child's engine directly.

        Every mount is closed even if one fails; failures are collected and
        re-raised after the table is cleared, so a single bad disposal can
        neither strand a sibling's engine nor leave the table populated.
        """
        errors: list[Exception] = []
        for fs in list(self._mounts.values()):
            try:
                await fs.close()
            except Exception as exc:
                errors.append(exc)
            fs._parent = None
        self._mounts.clear()
        self._sorted_mount_paths.clear()
        if len(errors) == 1:
            raise errors[0]
        if errors:
            raise ExceptionGroup("errors while closing mounts", errors)

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
        if mount_path == "/":
            msg = "Mount path must not be empty or root"
            raise ValueError(msg)
        meta_segment = METADATA_ROOT.strip("/")
        if meta_segment in mount_path.split("/")[1:]:
            msg = f"Mount path may not use the reserved metadata segment {meta_segment!r}: {path!r}"
            raise ValueError(msg)
        return mount_path

    def _rebuild_sorted_mounts(self) -> None:
        """Rebuild the pre-sorted mount path list (longest first)."""
        self._sorted_mount_paths = sorted(self._mounts.keys(), key=len, reverse=True)

    def _match_mount(self, path: str) -> tuple[Path, VirtualFileSystem] | None:
        """Longest-prefix mount match for *path*."""
        for mount_path in self._sorted_mount_paths:
            if path == mount_path or path.startswith(mount_path + "/"):
                return mount_path, self._mounts[mount_path]
        return None

    def _resolve_terminal(self, path: str) -> tuple[VirtualFileSystem, str, str]:
        """Walk the mount chain to find the terminal filesystem.

        Returns ``(terminal_fs, relative_path, prefix)`` where:
        - *terminal_fs* is the filesystem that owns the path
        - *relative_path* is the path within that filesystem
        - *prefix* is the accumulated mount path for rebasing results
        """
        fs = self
        prefix = ""
        rel = normalize_path(path)
        while True:
            matched = fs._match_mount(rel)
            if matched is None:
                break
            mount_path, mount_fs = matched

            fs = mount_fs
            prefix = prefix + mount_path
            rel = rel[len(mount_path) :] or "/"
        return fs, rel, prefix

    def _root(self) -> VirtualFileSystem:
        """Walk parent links to the top of this mount tree.

        Visited-guarded so a malformed parent chain cannot hang the walk,
        matching ``_reachable_ids``; the single-parent invariant keeps the
        chain acyclic in practice.
        """
        node = self
        seen: set[int] = set()
        while node._parent is not None and id(node) not in seen:
            seen.add(id(node))
            node = node._parent
        return node

    def _reachable_ids(self) -> set[int]:
        """Return ``id()`` of this filesystem and every transitive mount.

        Used to keep the mount graph a tree: a new mount's reachable set
        must be disjoint from the destination tree's, which rejects cycles,
        duplicate instances, and shared sub-mounts in one check — including
        the case where the incoming filesystem already carries its own
        mounts.  The walk is visited-guarded so it terminates even on a
        malformed graph.
        """
        ids: set[int] = set()
        stack: list[VirtualFileSystem] = [self]
        while stack:
            fs = stack.pop()
            if id(fs) in ids:
                continue
            ids.add(id(fs))
            stack.extend(fs._mounts.values())
        return ids

    async def _is_path_mountable(self, path: str) -> bool:
        """Return whether a mount may be attached at *path* inside this filesystem.

        The pure router has no storage, so any path is mountable.  Storage
        backends (``DatabaseFileSystem``) override this as a *policy*
        predicate — not an exact-path check — and should reject when:

        - any ancestor of *path* exists as a non-directory,
        - *path* itself already exists, or
        - any descendant already exists and would be shadowed by the mount.
        """
        return True

    # -------------------------------------------------------------------
    # observation grouping
    # -------------------------------------------------------------------

    def _group_observations_by_terminal(
        self,
        observations: list[Observation],
    ) -> list[tuple[VirtualFileSystem, str, list[Observation]]]:
        """Group observations by terminal filesystem, rebasing paths.

        Returns ``[(filesystem, prefix, rebased_observations)]`` where each
        observation's path is relative to its terminal filesystem (the mount
        prefix stripped via :meth:`Observation.without_mount`).
        """
        groups: dict[tuple[int, str], tuple[VirtualFileSystem, list[Observation]]] = {}
        for obs in observations:
            fs, _rel, prefix = self._resolve_terminal(obs.path)
            key = (id(fs), prefix)
            if key not in groups:
                groups[key] = (fs, [])
            groups[key][1].append(obs.without_mount(prefix))
        return [(fs, pfx, obs_list) for ((_id, pfx), (fs, obs_list)) in groups.items()]

    # -------------------------------------------------------------------
    # dispatch across the mount boundary
    # -------------------------------------------------------------------

    def capabilities(self) -> frozenset[str] | None:
        """Operations this filesystem answers as a terminal, or ``None`` for no limit.

        The router consults the terminal's set before dispatch and returns
        ``unsupported`` without a wire call when an op is absent (the no-probe
        rule). The base router imposes no limit; capability-limited leaves (an
        MCP tool catalog) override with an explicit set.
        """
        return None

    def _capability_error(self, fs: VirtualFileSystem, op: Op, path: Path | None) -> Result | None:
        """Return an ``unsupported`` result if *fs* does not answer *op*, else ``None``."""
        caps = fs.capabilities()
        if caps is not None and op not in caps:
            return self._error(f"Operation {op!r} is not supported here", kind=VFSErrorKind.unsupported, path=path)
        return None

    async def _call_local_impl(
        self,
        op: Op,
        *,
        user_id: str | None = None,
        **kwargs: object,
    ) -> Result:
        """The one seam from the router down to *self*'s own storage.

        This is the *only* place a filesystem reaches its own ``_*_impl``.
        It is valid for ``self`` alone — a child mount is always reached
        through its public method, never through this helper.

        The pure router has no storage, so the base implementation errors.
        Storage backends override it to open their own transaction and pass
        the resulting handle (e.g. a SQL session) to ``_{op}_impl`` — the
        session contract is a backend internal the router never sees.
        """
        if not self._storage:
            return self._error(f"No storage backend for operation: {op}", kind=VFSErrorKind.unsupported)
        impl = getattr(self, f"_{op}_impl")
        return await impl(user_id=user_id, **kwargs)

    async def _dispatch_grouped_observations(
        self,
        op: Op,
        observations: list[Observation],
        *,
        user_id: str | None = None,
        **kwargs: object,
    ) -> Result:
        """Route pre-grouped observation operations to terminal filesystems.

        Each group runs against its terminal filesystem: ``self`` through the
        local seam, a child mount through its public method.  Results are
        rebased and merged.
        """
        for obs in observations:
            resolved = resolve_path(obs.path, mutation=op in MUTATING_OPS)
            if resolved.path is None:
                return self._error(resolved.error or f"Invalid path: {obs.path!r}", kind=VFSErrorKind.invalid)

        groups = self._group_observations_by_terminal(observations)
        if not groups:
            return Result(function=op, observations=[])

        for fs, prefix, group in groups:
            for obs in group:
                err = check_writable(fs, op, obs.path, mount_prefix=prefix)
                if err is not None:
                    return err

        async def _run_group(
            fs: VirtualFileSystem,
            prefix: str,
            group: list[Observation],
        ) -> Result:
            cap_err = self._capability_error(fs, op, None)
            if cap_err is not None:
                return cap_err.with_mount(prefix)
            if fs is self:
                r = await self._call_local_impl(op, observations=group, user_id=user_id, **kwargs)
            else:
                r = await getattr(fs, op)(observations=group, user_id=user_id, **kwargs)
            return r.with_mount(prefix)

        results = await asyncio.gather(
            *(_run_group(fs, pfx, group) for fs, pfx, group in groups),
        )
        return self._merge_results(list(results))

    async def _route_single(
        self,
        op: Op,
        path: str | None,
        observations: list[Observation] | None,
        *,
        user_id: str | None = None,
        **kwargs: object,
    ) -> Result:
        """Route a single-path or observation-based operation.

        With observations: group by filesystem, dispatch in parallel.
        With path: resolve one terminal and dispatch once — to ``self``
        through the local seam, or to a child mount through its public method.
        """
        if (path is None) == (observations is None):
            msg = "Exactly one of path or observations must be provided"
            raise ValueError(msg)

        if observations is not None:
            return await self._dispatch_grouped_observations(op, observations, user_id=user_id, **kwargs)

        assert path is not None
        resolved = resolve_path(path, mutation=op in MUTATING_OPS)
        if resolved.path is None:
            return self._error(resolved.error or f"Invalid path: {path!r}", kind=VFSErrorKind.invalid)
        path = resolved.path

        fs, rel, prefix = self._resolve_terminal(path)

        if fs is self and not self._storage:
            return self._error(f"No mount found for path: {path}", kind=VFSErrorKind.not_found)

        cap_err = self._capability_error(fs, op, path)
        if cap_err is not None:
            return cap_err

        err = check_writable(fs, op, rel, mount_prefix=prefix)
        if err is not None:
            return err

        if fs is self:
            result = await self._call_local_impl(op, path=rel, user_id=user_id, **kwargs)
        else:
            result = await getattr(fs, op)(path=rel, user_id=user_id, **kwargs)

        return result.with_mount(prefix)

    async def _route_two_path(
        self,
        op: Op,
        operations: list[TwoPathOperation],
        *,
        user_id: str | None = None,
        **kwargs: object,
    ) -> Result:
        """Route src/dest pair mutations, gating every pair before any dispatch.

        Both endpoints of a pair must resolve to the same terminal — a pair
        spanning mounts is ``cross_mount``, never a partial execution.
        ``move`` mutates both endpoints, so both are write-gated; ``copy``
        only writes ``dest``, so its source needs no mutation resolution or
        write permission.  All pairs are validated up front: a single bad
        pair rejects the whole batch with nothing dispatched.
        """
        if not operations:
            return Result(function=op, observations=[])

        groups: dict[int, tuple[VirtualFileSystem, str, list[TwoPathOperation]]] = {}
        for pair in operations:
            src = resolve_path(pair.src, mutation=op == "move")
            if src.path is None:
                return self._error(src.error or f"Invalid path: {pair.src!r}", kind=VFSErrorKind.invalid)
            dest = resolve_path(pair.dest, mutation=True)
            if dest.path is None:
                return self._error(dest.error or f"Invalid path: {pair.dest!r}", kind=VFSErrorKind.invalid)

            src_fs, src_rel, src_prefix = self._resolve_terminal(src.path)
            dest_fs, dest_rel, _ = self._resolve_terminal(dest.path)
            if src_fs is not dest_fs:
                return self._error(
                    f"Cross-mount {op} is not supported: {src.path} and {dest.path} "
                    "resolve to different filesystems",
                    kind=VFSErrorKind.cross_mount,
                )
            if src_fs is self and not self._storage:
                return self._error(f"No mount found for path: {src.path}", kind=VFSErrorKind.not_found)
            cap_err = self._capability_error(src_fs, op, src.path)
            if cap_err is not None:
                return cap_err

            if op == "move":
                err = check_writable(src_fs, op, src_rel, mount_prefix=src_prefix)
                if err is not None:
                    return err
            err = check_writable(dest_fs, op, dest_rel, mount_prefix=src_prefix)
            if err is not None:
                return err

            key = id(src_fs)
            if key not in groups:
                groups[key] = (src_fs, src_prefix, [])
            groups[key][2].append(TwoPathOperation(src=src_rel, dest=dest_rel))

        batch_kwarg = "moves" if op == "move" else "copies"

        async def _run_group(
            fs: VirtualFileSystem,
            prefix: str,
            group: list[TwoPathOperation],
        ) -> Result:
            if fs is self:
                r = await self._call_local_impl(op, operations=group, user_id=user_id, **kwargs)
            else:
                r = await getattr(fs, op)(**{batch_kwarg: group}, user_id=user_id, **kwargs)
            return r.with_mount(prefix)

        results = await asyncio.gather(
            *(_run_group(fs, pfx, group) for fs, pfx, group in groups.values()),
        )
        return self._merge_results(list(results))

    async def _route_fanout(
        self,
        op: Op,
        *,
        paths: tuple[str, ...] = (),
        observations: list[Observation] | None = None,
        user_id: str | None = None,
        **kwargs: object,
    ) -> Result:
        """Route a namespace-wide query: everywhere, a scope subset, or rows.

        With observations: reuse grouped dispatch.  With scope paths: group
        the scopes by terminal and dispatch each group — a scoped terminal
        that cannot answer errors ``unsupported``, like the single shape.
        With neither: fan out to self-storage and every mount in parallel
        (mount-table order), silently skipping terminals whose
        ``capabilities()`` lack *op* — the no-probe rule's purpose: one
        incapable catalog must not fail a namespace-wide query.
        """
        if observations is not None:
            return await self._dispatch_grouped_observations(op, observations, user_id=user_id, **kwargs)

        if paths:
            groups: dict[int, tuple[VirtualFileSystem, str, list[str]]] = {}
            for raw in paths:
                resolved = resolve_path(raw)
                if resolved.path is None:
                    return self._error(resolved.error or f"Invalid path: {raw!r}", kind=VFSErrorKind.invalid)
                fs, rel, prefix = self._resolve_terminal(resolved.path)
                if fs is self and not self._storage:
                    return self._error(f"No mount found for path: {resolved.path}", kind=VFSErrorKind.not_found)
                cap_err = self._capability_error(fs, op, resolved.path)
                if cap_err is not None:
                    return cap_err
                key = id(fs)
                if key not in groups:
                    groups[key] = (fs, prefix, [])
                groups[key][2].append(rel)

            async def _run_scoped(
                fs: VirtualFileSystem,
                prefix: str,
                rels: list[str],
            ) -> Result:
                if fs is self:
                    r = await self._call_local_impl(op, paths=tuple(rels), user_id=user_id, **kwargs)
                else:
                    r = await getattr(fs, op)(paths=tuple(rels), user_id=user_id, **kwargs)
                return r.with_mount(prefix)

            results = await asyncio.gather(
                *(_run_scoped(fs, pfx, rels) for fs, pfx, rels in groups.values()),
            )
            return self._merge_results(list(results))

        targets: list[tuple[VirtualFileSystem, str]] = []
        own_caps = self.capabilities()
        if self._storage and (own_caps is None or op in own_caps):
            targets.append((self, ""))
        for mount_path, fs in self._mounts.items():
            child_caps = fs.capabilities()
            if child_caps is not None and op not in child_caps:
                continue
            targets.append((fs, mount_path))
        if not targets:
            return Result(function=op, observations=[])

        async def _run_target(fs: VirtualFileSystem, prefix: str) -> Result:
            if fs is self:
                r = await self._call_local_impl(op, paths=(), user_id=user_id, **kwargs)
            else:
                r = await getattr(fs, op)(user_id=user_id, **kwargs)
            return r.with_mount(prefix)

        results = await asyncio.gather(*(_run_target(fs, pfx) for fs, pfx in targets))
        return self._merge_results(list(results))

    async def _route_entry_batch(
        self,
        entries: Sequence[Entry],
        *,
        overwrite: bool = True,
        user_id: str | None = None,
    ) -> Result:
        """Route a batch write, grouping entries by terminal via each entry's path.

        The entry-path analogue of grouped-observation dispatch: every
        entry's path is mutation-resolved and write-gated before anything
        dispatches, then each terminal receives its entries rebased into
        local coordinates via :meth:`Entry.without_mount`.
        """
        if not entries:
            return Result(function="write", observations=[])

        groups: dict[int, tuple[VirtualFileSystem, str, list[Entry]]] = {}
        for entry in entries:
            resolved = resolve_path(entry.path, mutation=True)
            if resolved.path is None:
                return self._error(resolved.error or f"Invalid path: {entry.path!r}", kind=VFSErrorKind.invalid)
            fs, rel, prefix = self._resolve_terminal(resolved.path)
            if fs is self and not self._storage:
                return self._error(f"No mount found for path: {resolved.path}", kind=VFSErrorKind.not_found)
            cap_err = self._capability_error(fs, "write", resolved.path)
            if cap_err is not None:
                return cap_err
            err = check_writable(fs, "write", rel, mount_prefix=prefix)
            if err is not None:
                return err
            key = id(fs)
            if key not in groups:
                groups[key] = (fs, prefix, [])
            groups[key][2].append(entry.without_mount(prefix))

        async def _run_group(
            fs: VirtualFileSystem,
            prefix: str,
            group: list[Entry],
        ) -> Result:
            if fs is self:
                r = await self._call_local_impl("write", entries=group, overwrite=overwrite, user_id=user_id)
            else:
                r = await fs.write(entries=group, overwrite=overwrite, user_id=user_id)
            return r.with_mount(prefix)

        results = await asyncio.gather(
            *(_run_group(fs, pfx, group) for fs, pfx, group in groups.values()),
        )
        return self._merge_results(list(results))

    @staticmethod
    def _merge_results(results: list[Result]) -> Result:
        """Merge multiple results — any failure makes the whole a failure.

        ``|`` propagates ``success=False`` and concatenates ``errors`` while
        preserving all successful observations.
        """
        if not results:
            return Result(observations=[])
        merged = results[0]
        for r in results[1:]:
            merged = merged | r
        return merged

    # -------------------------------------------------------------------
    # errors
    # -------------------------------------------------------------------

    def _error(
        self,
        message: str,
        *,
        kind: VFSErrorKind,
        path: Path | None = None,
        data: dict[str, Any] | None = None,
    ) -> Result:
        """Compose a failed ``Result``, or raise if ``raise_on_error`` is set.

        Pass the prose *message* and the structured *kind* (required), plus an
        optional *path* and machine-readable *data*; this wraps them in a
        :class:`ResultError` and either returns the failed result or raises the
        exception the kind maps to.  Callers that already hold a shaped
        ``Result`` should return it directly.
        """
        result = Result(success=False, errors=[ResultError(kind=kind, message=message, path=path, data=data)])
        if not self._raise_on_error:
            return result
        raise exception_for_kind(kind)(message, result)

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
        return await self._route_single("read", path, observations, columns=columns, user_id=user_id)

    async def stat(
        self,
        path: str | None = None,
        observations: list[Observation] | None = None,
        *,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result:
        return await self._route_single("stat", path, observations, columns=columns, user_id=user_id)

    async def ls(
        self,
        path: str | None = None,
        observations: list[Observation] | None = None,
        *,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result:
        return await self._route_single("ls", path, observations, columns=columns, user_id=user_id)

    async def tree(
        self,
        path: str,
        max_depth: int | None = None,
        *,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result:
        return await self._route_single("tree", path, None, max_depth=max_depth, columns=columns, user_id=user_id)

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
        """Match *pattern* against the namespace — unscoped calls reach every mount."""
        return await self._route_fanout(
            "glob",
            paths=paths,
            observations=observations,
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
        """Search content for *pattern* — unscoped calls reach every mount."""
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
        opaquely; results report ``function="glean"``.
        """
        return await self._route_fanout(
            "glean",
            paths=paths,
            observations=observations,
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
        """Run the graph traversal *method* — each terminal answers over its own subgraph.

        A path routes to one terminal; observations group by terminal and
        each mount runs the algorithm on its own graph, so a walk can never
        follow an edge out of its mount.  *method* is validated against the
        traversal vocabulary before any dispatch; results report the
        specific method name in ``function``.
        """
        if method not in TRAVERSAL_FUNCTIONS:
            return self._error(
                f"Unknown graph method {method!r}; expected one of {sorted(TRAVERSAL_FUNCTIONS)}",
                kind=VFSErrorKind.invalid,
            )
        return await self._route_single("graph", path, observations, method=method, depth=depth, user_id=user_id)

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
        user_id: str | None = None,
    ) -> Result:
        """Write one file (*path* + *content*) or a batch of *entries*.

        Batch entries route by their own paths — grouped per terminal,
        rebased, and gated per entry before anything dispatches.
        """
        if entries is not None:
            return await self._route_entry_batch(entries, overwrite=overwrite, user_id=user_id)
        return await self._route_single("write", path, None, content=content, overwrite=overwrite, user_id=user_id)

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
        The *old*/*new* pair is sugar wrapping a one-item list.
        """
        if edits is None:
            if old is None or new is None:
                return self._error(
                    "edit requires old and new strings, or an edits list",
                    kind=VFSErrorKind.invalid,
                )
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
        return await self._route_single(
            "delete",
            path,
            observations,
            permanent=permanent,
            cascade=cascade,
            user_id=user_id,
        )

    async def mkdir(self, path: str, *, user_id: str | None = None) -> Result:
        return await self._route_single("mkdir", path, None, user_id=user_id)

    async def mkedge(
        self,
        source: str,
        target: str,
        edge_type: str,
        *,
        user_id: str | None = None,
    ) -> Result:
        """Create a typed edge from *source* to *target*.

        Both endpoints must resolve to the same terminal (``cross_mount``
        otherwise — cross-server edges are a later story).  The terminal
        writes the canonical ``edges/out`` projection; the inverse ``in``
        path is derived, never a write target.
        """
        src = resolve_path(source)
        if src.path is None:
            return self._error(src.error or f"Invalid path: {source!r}", kind=VFSErrorKind.invalid)
        tgt = resolve_path(target)
        if tgt.path is None:
            return self._error(tgt.error or f"Invalid path: {target!r}", kind=VFSErrorKind.invalid)

        src_fs, src_rel, src_prefix = self._resolve_terminal(src.path)
        tgt_fs, tgt_rel, _ = self._resolve_terminal(tgt.path)
        if src_fs is not tgt_fs:
            return self._error(
                f"Cross-mount edges are not supported: {src.path} and {tgt.path} "
                "resolve to different filesystems",
                kind=VFSErrorKind.cross_mount,
            )
        if src_fs is self and not self._storage:
            return self._error(f"No mount found for path: {src.path}", kind=VFSErrorKind.not_found)
        cap_err = self._capability_error(src_fs, "mkedge", src.path)
        if cap_err is not None:
            return cap_err

        if src_fs is not self:
            # The child re-derives the edge path and gates it against its own
            # permission map — rules live in filesystem-relative coordinates.
            result = await src_fs.mkedge(src_rel, tgt_rel, edge_type, user_id=user_id)
            return result.with_mount(src_prefix)

        try:
            edge_path = edge_out_path(Path(src_rel), Path(tgt_rel), edge_type)
        except ValueError as exc:
            return self._error(str(exc), kind=VFSErrorKind.invalid)
        err = check_writable(self, "mkedge", edge_path, mount_prefix=src_prefix)
        if err is not None:
            return err
        result = await self._call_local_impl(
            "mkedge",
            source=src_rel,
            target=tgt_rel,
            edge_type=edge_type,
            user_id=user_id,
        )
        return result.with_mount(src_prefix)

    async def move(
        self,
        src: str | None = None,
        dest: str | None = None,
        moves: Sequence[TwoPathOperation | tuple[str, str]] | None = None,
        *,
        overwrite: bool = True,
        user_id: str | None = None,
    ) -> Result:
        if moves is None:
            if not src or not dest:
                return self._error("move requires src and dest, or a moves list", kind=VFSErrorKind.invalid)
            moves = [TwoPathOperation(src=src, dest=dest)]
        operations = [p if isinstance(p, TwoPathOperation) else TwoPathOperation(*p) for p in moves]
        return await self._route_two_path("move", operations, overwrite=overwrite, user_id=user_id)

    async def copy(
        self,
        src: str | None = None,
        dest: str | None = None,
        copies: Sequence[TwoPathOperation | tuple[str, str]] | None = None,
        *,
        overwrite: bool = True,
        user_id: str | None = None,
    ) -> Result:
        if copies is None:
            if not src or not dest:
                return self._error("copy requires src and dest, or a copies list", kind=VFSErrorKind.invalid)
            copies = [TwoPathOperation(src=src, dest=dest)]
        operations = [p if isinstance(p, TwoPathOperation) else TwoPathOperation(*p) for p in copies]
        return await self._route_two_path("copy", operations, overwrite=overwrite, user_id=user_id)

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
        return await self._route_single("run", path, None, arguments=arguments, user_id=user_id)
