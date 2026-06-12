"""VirtualFileSystem — async router whose mount boundary is the public API.

The base class owns mount routing and path rebasing.  The filesystem object
itself owns ``/`` — mounting at ``"/"`` is illegal.

Public methods are routers.  They resolve the terminal filesystem via
longest-prefix mount matching, then dispatch across the mount boundary:

- When the terminal is ``self``, the router drops to local storage through
  ``_call_local_impl`` — the one seam down to an ``_*_impl`` method.
- When the terminal is a child mount, the router calls the child's **public**
  method only — never the child's session, engine, or ``_*_impl``.  Values go
  in, ``VFSResult`` comes out.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from vfs.exceptions import _classify_error
from vfs.paths import METADATA_ROOT, normalize_path, resolve_path
from vfs.permissions import (
    Permission,
    PermissionMap,
    check_writable,
    coerce_permissions,
)
from vfs.results import Candidate, VFSResult

if TYPE_CHECKING:
    from collections.abc import Sequence

    from vfs.models import VFSEntry


# Ops that author or rewrite entries; their paths get the namespace-write
# authorization check at the gate. Read-family ops (read/stat/ls/grep) skip it.
_MUTATION_OPS = frozenset({"write", "edit", "move", "copy", "mkedge", "rm", "delete"})


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
        self._mounts: dict[str, VirtualFileSystem] = {}
        self._sorted_mount_paths: list[str] = []
        self._class_name = self.__class__.__name__

    # -------------------------------------------------------------------
    # mounts and routing
    # -------------------------------------------------------------------

    async def add_mount(self, path: str, filesystem: VirtualFileSystem) -> None:
        """Mount a child filesystem at *path*, which may be nested.

        *path* is interpreted relative to this filesystem: the namespace
        root is the global origin, and calling on a sub-node treats *path*
        as local to that node (so ``data.add_mount("/tmp")`` lands at the
        data-local ``/tmp``).

        Routing:

        - If *path* falls under an existing mount, the request is delegated
          to that mount — with ``/data`` mounted, ``add_mount("/data/tmp")``
          becomes ``data_fs.add_mount("/tmp")``.  This recurses to any depth.
        - Otherwise *self* owns the mount.  It is rejected when a deeper
          mount already sits beneath *path* (the reverse order: ``/data/tmp``
          first, then ``/data``), when it duplicates an instance or would
          form a cycle, or — if *self* has storage — when stored contents
          conflict with the mount point (see ``_is_path_mountable``).

        Aliasing is done with a distinct ``BindFS`` wrapper, not by reusing
        an instance, so the duplicate-instance guard does not block binds.

        A filesystem created with ``allow_child_mounts=False`` (e.g. a mount
        that proxies a remote/external namespace) rejects any mount whose
        owner it would be — including a delegated one — so a parent cannot
        mutate the remote's local mount table without an explicit opt-in.
        """
        mount_path = self._normalize_mount_path(path)

        if not self._allow_child_mounts:
            msg = f"{self._class_name} does not allow child mounts"
            raise ValueError(msg)

        # A filesystem is mounted in at most one place, so a non-None parent
        # means it already lives in some tree (here or under another root) —
        # reject rather than re-parent it and double-close on teardown.  The
        # cycle check runs against the true root (via parent links) so it
        # holds no matter which node add_mount is called on.
        if filesystem is self:
            msg = "Cannot mount a filesystem into itself"
            raise ValueError(msg)
        if filesystem._parent is not None:
            msg = f"Cannot mount at {mount_path}: that filesystem is already mounted elsewhere"
            raise ValueError(msg)
        if id(self._root()) in filesystem._reachable_ids():
            msg = f"Mounting at {mount_path} would create a cycle: that filesystem already contains this namespace's root"
            raise ValueError(msg)

        matched = self._match_mount(mount_path)
        if matched is not None:
            mount_at, mount_fs = matched
            if mount_at == mount_path:
                msg = f"Mount already exists at: {mount_path}"
                raise ValueError(msg)
            await mount_fs.add_mount(mount_path[len(mount_at) :], filesystem)
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
            except Exception as exc:  # noqa: BLE001 - surface after closing all
                errors.append(exc)
            fs._parent = None
        self._mounts.clear()
        self._sorted_mount_paths.clear()
        if len(errors) == 1:
            raise errors[0]
        if errors:
            raise ExceptionGroup("errors while closing mounts", errors)

    @staticmethod
    def _normalize_mount_path(path: str) -> str:
        """Normalize and validate a mount path.

        A mount path is a canonical path with extra constraints.  It shares the
        validate+normalize gate with operations via :func:`resolve_path`, then
        adds the mount-specific rules: rejects empty/root, non-canonical input
        (relative ``"."`` / ``".."`` segments or stray whitespace, which mounts
        reject rather than silently collapse), whitespace-only segments, and the
        reserved metadata segment (``".vfs"``).  Interior spaces within a
        segment (``"/My Documents"``) are permitted.
        """
        stripped = path.strip("/")
        if not stripped:
            msg = "Mount path must not be empty or root"
            raise ValueError(msg)
        mount_path = f"/{stripped}"
        resolved = resolve_path(mount_path)
        if resolved.path is None:
            msg = f"Invalid mount path {path!r}: {resolved.error}"
            raise ValueError(msg)
        if resolved.path != mount_path:
            msg = f"Mount path must be a normalized path (no '.', '..', or stray whitespace): {path!r}"
            raise ValueError(msg)
        segments = mount_path.split("/")[1:]
        for segment in segments:
            if not segment.strip() or segment != segment.strip():
                msg = f"Mount path segment {segment!r} is whitespace-only or has stray whitespace: {path!r}"
                raise ValueError(msg)
        meta_segment = METADATA_ROOT.strip("/")
        if meta_segment in segments:
            msg = f"Mount path may not use the reserved metadata segment {meta_segment!r}: {path!r}"
            raise ValueError(msg)
        return mount_path

    def _rebuild_sorted_mounts(self) -> None:
        """Rebuild the pre-sorted mount path list (longest first)."""
        self._sorted_mount_paths = sorted(self._mounts.keys(), key=len, reverse=True)

    def _match_mount(self, path: str) -> tuple[str, VirtualFileSystem] | None:
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
    # candidate grouping
    # -------------------------------------------------------------------

    def _group_candidates_by_terminal(
        self,
        candidates: VFSResult,
    ) -> list[tuple[VirtualFileSystem, str, VFSResult]]:
        """Group candidates by terminal filesystem, rebasing paths.

        Returns ``[(filesystem, prefix, rebased_candidates)]`` where each
        ``VFSResult`` carries candidates with paths relative to that terminal
        filesystem.
        """
        groups: dict[tuple[int, str], tuple[VirtualFileSystem, list[Candidate]]] = {}
        for c in candidates.candidates:
            fs, rel, prefix = self._resolve_terminal(c.path)
            key = (id(fs), prefix)
            if key not in groups:
                groups[key] = (fs, [])
            groups[key][1].append(c.model_copy(update={"path": rel}))
        return [
            (fs, pfx, VFSResult(function=candidates.function, candidates=cands))
            for ((_id, pfx), (fs, cands)) in groups.items()
        ]

    # -------------------------------------------------------------------
    # dispatch across the mount boundary
    # -------------------------------------------------------------------

    async def _call_local_impl(
        self,
        op: str,
        *,
        user_id: str | None = None,
        **kwargs: object,
    ) -> VFSResult:
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
            return self._error(f"No storage backend for operation: {op}")
        impl = getattr(self, f"_{op}_impl")
        return await impl(user_id=user_id, **kwargs)

    async def _dispatch_grouped_candidates(
        self,
        op: str,
        candidates: VFSResult,
        *,
        user_id: str | None = None,
        **kwargs: object,
    ) -> VFSResult:
        """Route pre-grouped candidate operations to terminal filesystems.

        Each group runs against its terminal filesystem: ``self`` through the
        local seam, a child mount through its public method.  Results are
        rebased and merged.
        """
        for cand in candidates.candidates:
            resolved = resolve_path(cand.path, mutation=op in _MUTATION_OPS)
            if resolved.path is None:
                return self._error(resolved.error or f"Invalid path: {cand.path!r}")

        groups = self._group_candidates_by_terminal(candidates)
        if not groups:
            return VFSResult(
                function=op,
                success=candidates.success,
                errors=list(candidates.errors),
                candidates=[],
            )

        for fs, prefix, gc in groups:
            for cand in gc.candidates:
                err = check_writable(fs, op, cand.path, mount_prefix=prefix)
                if err is not None:
                    return err

        async def _run_group(
            fs: VirtualFileSystem,
            prefix: str,
            group_cands: VFSResult,
        ) -> VFSResult:
            if fs is self:
                r = await self._call_local_impl(op, candidates=group_cands, user_id=user_id, **kwargs)
            else:
                r = await getattr(fs, op)(candidates=group_cands, user_id=user_id, **kwargs)
            return r.add_prefix(prefix)

        results = await asyncio.gather(
            *(_run_group(fs, pfx, gc) for fs, pfx, gc in groups),
        )
        return self._merge_results(list(results))

    async def _route_single(
        self,
        op: str,
        path: str | None,
        candidates: VFSResult | None,
        *,
        user_id: str | None = None,
        **kwargs: object,
    ) -> VFSResult:
        """Route a single-path or candidate-based operation.

        With candidates: group by filesystem, dispatch in parallel.
        With path: resolve one terminal and dispatch once — to ``self``
        through the local seam, or to a child mount through its public method.
        """
        if (path is None) == (candidates is None):
            msg = "Exactly one of path or candidates must be provided"
            raise ValueError(msg)

        if candidates is not None:
            return await self._dispatch_grouped_candidates(op, candidates, user_id=user_id, **kwargs)

        assert path is not None
        resolved = resolve_path(path, mutation=op in _MUTATION_OPS)
        if resolved.path is None:
            return self._error(resolved.error or f"Invalid path: {path!r}")
        path = resolved.path

        fs, rel, prefix = self._resolve_terminal(path)

        if fs is self and not self._storage:
            return self._error(f"No mount found for path: {path}")

        err = check_writable(fs, op, rel, mount_prefix=prefix)
        if err is not None:
            return err

        if fs is self:
            result = await self._call_local_impl(op, path=rel, user_id=user_id, **kwargs)
        else:
            result = await getattr(fs, op)(path=rel, user_id=user_id, **kwargs)

        return result.add_prefix(prefix)

    @staticmethod
    def _merge_results(results: list[VFSResult]) -> VFSResult:
        """Merge multiple results — any failure makes the whole a failure.

        ``|`` propagates ``success=False`` and concatenates ``errors`` while
        preserving all successful candidates.
        """
        if not results:
            return VFSResult(success=True, candidates=[])
        merged = results[0]
        for r in results[1:]:
            merged = merged | r
        return merged

    # -------------------------------------------------------------------
    # errors
    # -------------------------------------------------------------------

    def _error(self, errors: str | list[str]) -> VFSResult:
        """Compose a failed ``VFSResult``, or raise if ``raise_on_error`` is set.

        Pass the raw error message(s); this composes the result and either
        returns it or raises a classified exception.  Callers that already
        hold a shaped ``VFSResult`` should return it directly.
        """
        error_list = [errors] if isinstance(errors, str) else errors
        result = VFSResult(success=False, errors=error_list)
        if not self._raise_on_error:
            return result
        raise _classify_error(result.error_message, result.errors, result)

    # -------------------------------------------------------------------
    # public methods
    # -------------------------------------------------------------------

    async def read(
        self,
        path: str | None = None,
        candidates: VFSResult | None = None,
        *,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> VFSResult:
        return await self._route_single("read", path, candidates, columns=columns, user_id=user_id)

    async def stat(
        self,
        path: str | None = None,
        candidates: VFSResult | None = None,
        *,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> VFSResult:
        return await self._route_single("stat", path, candidates, columns=columns, user_id=user_id)

    async def ls(
        self,
        path: str | None = None,
        candidates: VFSResult | None = None,
        *,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> VFSResult:
        return await self._route_single("ls", path, candidates, columns=columns, user_id=user_id)
