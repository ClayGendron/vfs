"""VirtualFileSystem — concrete async base class with mount routing.

The base class owns mount routing, session management, and path rebasing.
The filesystem object itself owns ``/`` — mounting at ``"/"`` is illegal.

Public methods are routers.  They resolve the terminal filesystem via
longest-prefix mount matching, delegate to ``_*_impl`` methods for actual
storage work, then rebase paths before returning.

Subclasses override ``_*_impl`` for their storage backend:
- ``DatabaseFileSystem`` — SQL via ``VFSEntry``
- ``LocalFileSystem`` — disk bytes + SQL metadata
- ``VFSClientAsync`` — no storage, mount-only async router (``storage=False``)
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import TYPE_CHECKING, cast

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from vfs.exceptions import _classify_error
from vfs.paths import edge_out_path, extract_extension, normalize_path
from vfs.patterns import compile_glob
from vfs.permissions import (
    Permission,
    PermissionMap,
    check_writable,
    coerce_permissions,
)
from vfs.results import EditOperation, Entry, TwoPathOperation, VFSResult
from vfs.routing import (
    GlobMountPlan,
    GrepMountPlan,
    rewrite_glob_for_mount,
    rewrite_path_for_mount,
)

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]

if TYPE_CHECKING:
    import re
    from collections.abc import AsyncIterator, Sequence

    from vfs.models import VFSEntry
    from vfs.query import QueryPlan
    from vfs.query.ast import CaseMode, GrepOutputMode


class VirtualFileSystem:
    """Async base class for all VFS filesystems."""

    def __init__(
        self,
        *,
        engine: AsyncEngine | None = None,
        session_factory: SessionFactory | None = None,
        storage: bool = True,
        raise_on_error: bool = False,
        permissions: Permission | PermissionMap = "read_write",
        schema: str | None = None,
    ) -> None:
        self._storage = storage
        self._raise_on_error = raise_on_error
        self._permission_map: PermissionMap = coerce_permissions(permissions)
        self._engine = engine
        self._schema = schema
        if session_factory is not None:
            self._session_factory: SessionFactory | None = session_factory
        elif engine is not None:
            self._session_factory = async_sessionmaker(engine, expire_on_commit=False)
        elif storage:
            msg = "VirtualFileSystem requires either engine or session_factory when storage=True"
            raise ValueError(msg)
        else:
            self._session_factory = None
        self._mounts: dict[str, VirtualFileSystem] = {}
        self._sorted_mount_paths: list[str] = []
        self._name = self.__class__.__name__

    # -------------------------------------------------------------------
    # mounts and routing
    # -------------------------------------------------------------------

    @staticmethod
    def _normalize_mount_path(path: str) -> str:
        """Normalize a mount path.

        Accepts ``"data"`` or ``"/data"``.  Rejects empty, root, and
        nested paths like ``"/data/archive"``.
        """
        stripped = path.strip("/")
        if not stripped:
            msg = "Mount path must not be empty or root"
            raise ValueError(msg)
        if "/" in stripped:
            msg = f"Mount path must be a single segment, not a nested path: {path!r}"
            raise ValueError(msg)
        return f"/{stripped}"

    async def add_mount(self, path: str, filesystem: VirtualFileSystem) -> None:
        """Mount a child filesystem at *path*.

        Accepts ``"data"`` or ``"/data"``.  Rejects nested paths.
        """
        path = self._normalize_mount_path(path)
        if path in self._mounts:
            msg = f"Mount already exists at: {path}"
            raise ValueError(msg)
        filesystem._raise_on_error = self._raise_on_error
        self._mounts[path] = filesystem
        self._rebuild_sorted_mounts()

    async def remove_mount(self, path: str) -> None:
        """Unmount the filesystem at *path* and dispose its engine."""
        path = self._normalize_mount_path(path)
        if path not in self._mounts:
            msg = f"No mount at: {path!r}"
            raise ValueError(msg)
        fs = self._mounts.pop(path)
        self._rebuild_sorted_mounts()
        if fs._engine is not None:
            await fs._engine.dispose()

    async def close(self) -> None:
        """Dispose all engines and clear mounts."""
        for fs in self._mounts.values():
            if fs._engine is not None:
                await fs._engine.dispose()
        self._mounts.clear()
        self._sorted_mount_paths.clear()

    def _rebuild_sorted_mounts(self) -> None:
        """Rebuild the pre-sorted mount path list (longest first)."""
        self._sorted_mount_paths = cast(
            "list[str]",
            sorted(self._mounts.keys(), key=len, reverse=True),
        )

    def _match_mount(self, path: str) -> tuple[str, VirtualFileSystem] | None:
        """Longest-prefix mount match for *path*."""
        for mount_path in self._sorted_mount_paths:
            if path == mount_path or path.startswith(mount_path + "/"):
                return mount_path, self._mounts[mount_path]
        return None

    def _resolve_terminal(self, path: str) -> tuple[VirtualFileSystem, str, str]:
        """Walk mount chain to find the terminal filesystem.

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

    def _group_candidates_by_terminal(
        self,
        candidates: VFSResult,
    ) -> list[tuple[VirtualFileSystem, str, VFSResult]]:
        """Group candidates by terminal filesystem, rebasing paths.

        Returns ``[(filesystem, prefix, rebased_candidates)]`` where each
        ``VFSResult`` contains candidates with paths relative to that
        terminal filesystem.
        """
        groups: dict[tuple[int, str], tuple[VirtualFileSystem, list[Entry]]] = {}
        for c in candidates.entries:
            fs, rel, prefix = self._resolve_terminal(c.path)
            key = (id(fs), prefix)
            if key not in groups:
                groups[key] = (fs, [])
            groups[key][1].append(c.model_copy(update={"path": rel}))
        return [
            (fs, pfx, VFSResult(function=candidates.function, entries=cands))
            for ((_id, pfx), (fs, cands)) in groups.items()
        ]

    def _group_entries_by_terminal(
        self,
        entries: Sequence[VFSEntry],
    ) -> list[tuple[VirtualFileSystem, str, list[VFSEntry]]]:
        """Group entries by terminal filesystem, rebasing paths."""
        groups: dict[tuple[int, str], tuple[VirtualFileSystem, str, list[VFSEntry]]] = {}
        for entry in entries:
            fs, _rel, prefix = self._resolve_terminal(entry.path)
            key = (id(fs), prefix)
            if key not in groups:
                groups[key] = (fs, prefix, [])
            rebased = entry.clone()
            rebased.strip_prefix(prefix)
            groups[key][2].append(rebased)
        return list(groups.values())

    @staticmethod
    def _require_same_mount(
        resolved: Sequence[tuple[VirtualFileSystem, str, str]],
        label: str,
    ) -> tuple[VirtualFileSystem, str] | str:
        """Validate all resolved paths share the same filesystem and prefix.

        Returns ``(filesystem, prefix)`` on success, or an error message string.
        """
        fs, _, prefix = resolved[0]
        for r_fs, _, r_prefix in resolved[1:]:
            if r_fs is not fs or r_prefix != prefix:
                return f"All {label} must resolve to the same mount"
        return fs, prefix

    @staticmethod
    def _matches_path_filters(path: str, filters: tuple[str, ...]) -> bool:
        """Return True if *path* passes the literal-prefix path filters."""
        if not filters:
            return True
        for raw in filters:
            prefix = normalize_path(raw).rstrip("/") or "/"
            if prefix == "/" or path == prefix or path.startswith(prefix + "/"):
                return True
        return False

    @staticmethod
    def _matches_ext_filters(
        path: str,
        *,
        ext: tuple[str, ...] = (),
        ext_not: tuple[str, ...] = (),
    ) -> bool:
        """Return True if *path* passes ext / ext_not filters."""
        path_ext = extract_extension(path)
        if ext and path_ext not in ext:
            return False
        return not ext_not or path_ext not in ext_not

    @staticmethod
    def _compile_path_globs(globs: tuple[str, ...]) -> tuple[re.Pattern[str], ...]:
        """Compile valid path globs, skipping malformed ones like the backend does."""
        return tuple(regex for glob in globs if (regex := compile_glob(glob)) is not None)

    async def _dispatch_grouped_candidates(
        self,
        op: str,
        candidates: VFSResult,
        *,
        user_id: str | None = None,
        **kwargs: object,
    ) -> VFSResult:
        """Route pre-grouped candidate operations to terminal filesystems."""
        groups = self._group_candidates_by_terminal(candidates)
        if not groups:
            return VFSResult(
                function=op,
                success=candidates.success,
                errors=list(candidates.errors),
                entries=[],
            )

        for fs, prefix, gc in groups:
            for cand in gc.entries:
                err = check_writable(fs, op, cand.path, mount_prefix=prefix)
                if err is not None:
                    return err

        async def _run_group(
            fs: VirtualFileSystem,
            prefix: str,
            group_cands: VFSResult,
        ) -> VFSResult:
            async with fs._use_session() as s:
                impl = getattr(fs, f"_{op}_impl")
                r = await impl(candidates=group_cands, user_id=user_id, session=s, **kwargs)
            return r.add_prefix(prefix)

        results = await asyncio.gather(
            *(_run_group(fs, pfx, gc) for fs, pfx, gc in groups),
        )
        return self._merge_results(list(results))

    async def _dispatch_glob_candidates(
        self,
        candidates: VFSResult,
        *,
        pattern: str,
        paths: tuple[str, ...],
        ext: tuple[str, ...],
        max_count: int | None,
        user_id: str | None,
    ) -> VFSResult:
        """Filter absolute-path glob candidates before grouping by terminal."""
        regex = compile_glob(pattern)
        if regex is None:
            return self._error(f"Invalid glob pattern: {pattern}")

        filtered = candidates._with_entries(
            [
                c
                for c in candidates.entries
                if regex.match(c.path) is not None
                and self._matches_path_filters(c.path, paths)
                and self._matches_ext_filters(c.path, ext=ext)
            ]
        )
        result = await self._dispatch_grouped_candidates(
            "glob",
            filtered,
            user_id=user_id,
            pattern="**",
            paths=(),
            ext=(),
            max_count=None,
        )
        if max_count is not None:
            result = result._with_entries(result.entries[:max_count])
        return result

    async def _dispatch_grep_candidates(
        self,
        candidates: VFSResult,
        *,
        pattern: str,
        paths: tuple[str, ...],
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
        user_id: str | None,
    ) -> VFSResult:
        """Filter absolute-path grep candidates before grouping by terminal."""
        include_regexes = self._compile_path_globs(globs)
        exclude_regexes = self._compile_path_globs(globs_not)
        filtered = candidates._with_entries(
            [
                c
                for c in candidates.entries
                if self._matches_path_filters(c.path, paths)
                and self._matches_ext_filters(c.path, ext=ext, ext_not=ext_not)
                and (not include_regexes or any(regex.match(c.path) is not None for regex in include_regexes))
                and not any(regex.match(c.path) is not None for regex in exclude_regexes)
            ]
        )
        return await self._dispatch_grouped_candidates(
            "grep",
            filtered,
            user_id=user_id,
            pattern=pattern,
            paths=(),
            ext=(),
            ext_not=(),
            globs=(),
            globs_not=(),
            case_mode=case_mode,
            fixed_strings=fixed_strings,
            word_regexp=word_regexp,
            invert_match=invert_match,
            before_context=before_context,
            after_context=after_context,
            output_mode=output_mode,
            max_count=max_count,
        )

    async def _dispatch_candidates(
        self,
        op: str,
        candidates: VFSResult,
        *,
        user_id: str | None = None,
        **kwargs: object,
    ) -> VFSResult:
        """Route a candidate-based operation to terminal filesystems in parallel.

        Groups candidates by terminal filesystem, calls ``_{op}_impl``
        with rebased candidates on each concurrently, then rebases and
        merges results.
        """
        if op == "glob":
            pattern = cast("str", kwargs["pattern"])
            paths = cast("tuple[str, ...]", kwargs.get("paths", ()))
            ext = cast("tuple[str, ...]", kwargs.get("ext", ()))
            max_count = cast("int | None", kwargs.get("max_count"))
            return await self._dispatch_glob_candidates(
                candidates,
                pattern=pattern,
                paths=paths,
                ext=ext,
                max_count=max_count,
                user_id=user_id,
            )
        if op == "grep":
            pattern = cast("str", kwargs["pattern"])
            paths = cast("tuple[str, ...]", kwargs.get("paths", ()))
            ext = cast("tuple[str, ...]", kwargs.get("ext", ()))
            ext_not = cast("tuple[str, ...]", kwargs.get("ext_not", ()))
            globs = cast("tuple[str, ...]", kwargs.get("globs", ()))
            globs_not = cast("tuple[str, ...]", kwargs.get("globs_not", ()))
            case_mode = cast("CaseMode", kwargs.get("case_mode", "sensitive"))
            fixed_strings = cast("bool", kwargs.get("fixed_strings", False))
            word_regexp = cast("bool", kwargs.get("word_regexp", False))
            invert_match = cast("bool", kwargs.get("invert_match", False))
            before_context = cast("int", kwargs.get("before_context", 0))
            after_context = cast("int", kwargs.get("after_context", 0))
            output_mode = cast("GrepOutputMode", kwargs.get("output_mode", "lines"))
            max_count = cast("int | None", kwargs.get("max_count"))
            return await self._dispatch_grep_candidates(
                candidates,
                pattern=pattern,
                paths=paths,
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
                user_id=user_id,
            )
        return await self._dispatch_grouped_candidates(op, candidates, user_id=user_id, **kwargs)

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
        With path: resolve one terminal, call impl once.
        """
        if path is not None and candidates is not None:
            msg = "Exactly one of path or candidates must be provided"
            raise ValueError(msg)
        if path is None and candidates is None:
            msg = "Exactly one of path or candidates must be provided"
            raise ValueError(msg)

        if candidates is not None:
            return await self._dispatch_candidates(op, candidates, user_id=user_id, **kwargs)

        assert path is not None
        fs, rel, prefix = self._resolve_terminal(path)

        if fs is self and not self._storage:
            return self._error(f"No mount found for path: {path}")

        err = check_writable(fs, op, rel, mount_prefix=prefix)
        if err is not None:
            return err

        async with fs._use_session() as s:
            result = await getattr(fs, f"_{op}_impl")(rel, user_id=user_id, session=s, **kwargs)

        return result.add_prefix(prefix)

    async def _route_two_path(
        self,
        op: str,
        ops: Sequence[TwoPathOperation],
        *,
        overwrite: bool = True,
        user_id: str | None = None,
    ) -> VFSResult:
        """Route a batch of two-path operations (move/copy).

        All sources must resolve to the same mount, and all destinations
        must resolve to the same mount.

        Same-mount: call impl with the full batch.
        Cross-mount: batch-read from source, batch-write to dest.
        For move, also soft-deletes the sources on success.

        Note: cross-mount operations are not atomic — writes commit before
        deletes. A crash between phases may leave data on both filesystems.
        """
        if not ops:
            return VFSResult(function=op, success=True, entries=[])

        src_resolved = [self._resolve_terminal(o.src) for o in ops]
        dst_resolved = [self._resolve_terminal(o.dest) for o in ops]

        src_check = self._require_same_mount(src_resolved, f"{op} sources")
        if isinstance(src_check, str):
            return self._error(src_check)
        src_fs, _ = src_check

        dst_check = self._require_same_mount(dst_resolved, f"{op} destinations")
        if isinstance(dst_check, str):
            return self._error(dst_check)
        dst_fs, dst_prefix = dst_check
        _, src_prefix = src_check

        src_rels = [r[1] for r in src_resolved]
        dst_rels = [r[1] for r in dst_resolved]

        # Destination always mutates.  For ``move``, the source also
        # mutates (the original is deleted after the destination is
        # written), so check it too.  ``copy`` only reads the source,
        # so a read-only source is allowed.  Per-path checks fail fast
        # on the first rejected op so no partial writes happen.
        for dst_rel in dst_rels:
            dst_err = check_writable(dst_fs, op, dst_rel, mount_prefix=dst_prefix)
            if dst_err is not None:
                return dst_err
        if op == "move":
            for src_rel in src_rels:
                src_err = check_writable(src_fs, "delete", src_rel, mount_prefix=src_prefix)
                if src_err is not None:
                    return src_err

        if src_fs is dst_fs:
            batch = [TwoPathOperation(src=s, dest=d) for s, d in zip(src_rels, dst_rels, strict=True)]
            async with src_fs._use_session() as s:
                result = await getattr(src_fs, f"_{op}_impl")(
                    ops=batch,
                    overwrite=overwrite,
                    user_id=user_id,
                    session=s,
                )
            return result.add_prefix(dst_prefix)

        return await self._cross_mount_transfer(
            op,
            src_fs,
            dst_fs,
            src_rels,
            dst_rels,
            src_prefix,
            dst_prefix,
            overwrite=overwrite,
            user_id=user_id,
        )

    async def _cross_mount_transfer(
        self,
        op: str,
        src_fs: VirtualFileSystem,
        dst_fs: VirtualFileSystem,
        src_rels: list[str],
        dst_rels: list[str],
        src_prefix: str,
        dst_prefix: str,
        *,
        overwrite: bool,
        user_id: str | None = None,
    ) -> VFSResult:
        """Execute a cross-mount move/copy via read → write → delete."""
        # Read all sources
        async with src_fs._use_session() as s:
            read_results = self._merge_results(
                [await src_fs._read_impl(p, user_id=user_id, session=s) for p in src_rels],
            )
        if not read_results.success:
            return read_results.add_prefix(src_prefix)

        # Write all to destination
        async with dst_fs._use_session() as s:
            write_results = self._merge_results(
                [
                    await dst_fs._write_impl(
                        dst_rel,
                        content=candidate.content or "",
                        overwrite=overwrite,
                        user_id=user_id,
                        session=s,
                    )
                    for dst_rel, candidate in zip(dst_rels, read_results.entries, strict=True)
                ]
            )
        if not write_results.success:
            return write_results.add_prefix(dst_prefix)

        # Soft-delete sources for move
        if op == "move":
            async with src_fs._use_session() as s:
                delete_results = self._merge_results(
                    [await src_fs._delete_impl(p, permanent=False, user_id=user_id, session=s) for p in src_rels],
                )
            if not delete_results.success:
                # Writes succeeded but deletes failed — caller needs to know
                return delete_results.add_prefix(src_prefix)

        return write_results.add_prefix(dst_prefix)

    async def _route_glob_fanout(
        self,
        *,
        pattern: str,
        paths: tuple[str, ...],
        ext: tuple[str, ...],
        max_count: int | None,
        columns: frozenset[str] | None = None,
        candidates: VFSResult | None,
        user_id: str | None,
    ) -> VFSResult:
        """Glob fanout with mount-prefix-aware rewriting.

        Absolute patterns that can be rewritten exactly are dispatched
        mount-locally. Patterns that need a safe superset query
        (currently ``**``-leading) are post-filtered at the router after
        results are rebased, so correctness does not depend on the
        rewrite. When router-side post-filtering is active, ``max_count``
        is applied only after merge to avoid truncating candidates
        before the authoritative filter runs.
        """
        if candidates is not None:
            return await self._dispatch_candidates(
                "glob",
                candidates,
                user_id=user_id,
                pattern=pattern,
                paths=paths,
                ext=ext,
                max_count=max_count,
                columns=columns,
            )

        pattern_regex = compile_glob(pattern)
        if pattern_regex is None:
            return self._error(f"Invalid glob pattern: {pattern}")

        mount_plans: list[GlobMountPlan] = []
        any_router_post_filter = False
        for mount_path, fs in self._mounts.items():
            rewritten_pattern, needs_post_filter = rewrite_glob_for_mount(pattern, mount_path)
            if rewritten_pattern is None:
                continue

            if paths:
                rewritten_paths = tuple(
                    rp for rp in (rewrite_path_for_mount(path, mount_path) for path in paths) if rp is not None
                )
                if not rewritten_paths:
                    continue
                if "/" in rewritten_paths:
                    rewritten_paths = ()
            else:
                rewritten_paths = ()

            mount_plans.append(
                GlobMountPlan(
                    mount_path=mount_path,
                    filesystem=fs,
                    rewritten_pattern=rewritten_pattern,
                    rewritten_paths=rewritten_paths,
                    needs_post_filter=needs_post_filter,
                )
            )
            any_router_post_filter = any_router_post_filter or needs_post_filter

        self_max_count = None if any_router_post_filter else max_count

        async def _query_self() -> VFSResult:
            if not self._storage:
                return VFSResult(function="glob", success=True, entries=[])
            async with self._use_session() as s:
                return await self._glob_impl(
                    pattern=pattern,
                    paths=paths,
                    ext=ext,
                    max_count=self_max_count,
                    columns=columns,
                    user_id=user_id,
                    session=s,
                )

        async def _query_mount(
            fs: VirtualFileSystem,
            *,
            rewritten_pattern: str,
            rewritten_paths: tuple[str, ...],
            needs_post_filter: bool,
        ) -> VFSResult:
            return await fs.glob(
                pattern=rewritten_pattern,
                paths=rewritten_paths,
                ext=ext,
                max_count=None if needs_post_filter else max_count,
                columns=columns,
                user_id=user_id,
            )

        self_result, *mount_results = await asyncio.gather(
            _query_self(),
            *(
                _query_mount(
                    plan.filesystem,
                    rewritten_pattern=plan.rewritten_pattern,
                    rewritten_paths=plan.rewritten_paths,
                    needs_post_filter=plan.needs_post_filter,
                )
                for plan in mount_plans
            ),
        )

        results = [self._exclude_mounted_paths(self_result)]
        for plan, result in zip(
            mount_plans,
            mount_results,
            strict=True,
        ):
            rebased = result.add_prefix(plan.mount_path)
            if plan.needs_post_filter:
                rebased = rebased._with_entries(
                    [c for c in rebased.entries if pattern_regex.match(c.path) is not None],
                )
            results.append(rebased)

        merged = self._merge_results(results)
        if any_router_post_filter and max_count is not None:
            merged = merged._with_entries(merged.entries[:max_count])
        return merged

    async def _route_grep_fanout(
        self,
        *,
        pattern: str,
        paths: tuple[str, ...],
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
        columns: frozenset[str] | None = None,
        candidates: VFSResult | None,
        user_id: str | None,
    ) -> VFSResult:
        """Grep fanout with mount-prefix-aware structural filter rewriting.

        ``pattern`` is the content regex and is forwarded unchanged.
        Literal ``paths`` are rewritten exactly per mount. Positive and
        negative glob filters are pushed down when exact rewrite is
        possible; otherwise the router queries a safe superset and
        re-applies the original absolute glob filters after rebasing.
        """
        if candidates is not None:
            return await self._dispatch_candidates(
                "grep",
                candidates,
                user_id=user_id,
                pattern=pattern,
                paths=paths,
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
            )

        mount_plans: list[GrepMountPlan] = []
        any_router_post_filter = False

        for mount_path, fs in self._mounts.items():
            if paths:
                rewritten_paths = tuple(
                    rp for rp in (rewrite_path_for_mount(path, mount_path) for path in paths) if rp is not None
                )
                if not rewritten_paths:
                    continue
                if "/" in rewritten_paths:
                    rewritten_paths = ()
            else:
                rewritten_paths = ()

            positive_intersections: list[str] = []
            positive_pushdowns: list[str] = []
            positive_needs_router_filter = False
            for glob in globs:
                rewritten_glob, needs_post_filter = rewrite_glob_for_mount(glob, mount_path)
                if rewritten_glob is None:
                    continue
                positive_intersections.append(glob)
                if needs_post_filter:
                    positive_needs_router_filter = True
                else:
                    positive_pushdowns.append(rewritten_glob)
            if globs and not positive_intersections:
                continue

            post_include_regexes: list[re.Pattern[str]] = []
            if positive_needs_router_filter:
                for glob in positive_intersections:
                    regex = compile_glob(glob)
                    if regex is None:
                        return self._error(f"Invalid glob pattern: {glob}")
                    post_include_regexes.append(regex)
                mount_globs = ()
            else:
                mount_globs = tuple(positive_pushdowns)

            mount_globs_not_list: list[str] = []
            post_exclude_regexes: list[re.Pattern[str]] = []
            for glob in globs_not:
                rewritten_glob, needs_post_filter = rewrite_glob_for_mount(glob, mount_path)
                if rewritten_glob is None:
                    continue
                if needs_post_filter:
                    regex = compile_glob(glob)
                    if regex is None:
                        return self._error(f"Invalid glob pattern: {glob}")
                    post_exclude_regexes.append(regex)
                else:
                    mount_globs_not_list.append(rewritten_glob)

            needs_router_filter = bool(post_include_regexes or post_exclude_regexes)
            any_router_post_filter = any_router_post_filter or needs_router_filter
            mount_plans.append(
                GrepMountPlan(
                    mount_path=mount_path,
                    filesystem=fs,
                    rewritten_paths=rewritten_paths,
                    mount_globs=mount_globs,
                    mount_globs_not=tuple(mount_globs_not_list),
                    post_include_regexes=tuple(post_include_regexes),
                    post_exclude_regexes=tuple(post_exclude_regexes),
                    needs_router_filter=needs_router_filter,
                )
            )

        self_max_count = None if any_router_post_filter else max_count

        async def _query_self() -> VFSResult:
            if not self._storage:
                return VFSResult(function="grep", success=True, entries=[])
            async with self._use_session() as s:
                return await self._grep_impl(
                    pattern=pattern,
                    paths=paths,
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
                    max_count=self_max_count,
                    columns=columns,
                    user_id=user_id,
                    session=s,
                )

        async def _query_mount(
            fs: VirtualFileSystem,
            *,
            rewritten_paths: tuple[str, ...],
            mount_globs: tuple[str, ...],
            mount_globs_not: tuple[str, ...],
            needs_router_filter: bool,
        ) -> VFSResult:
            return await fs.grep(
                pattern=pattern,
                paths=rewritten_paths,
                ext=ext,
                ext_not=ext_not,
                globs=mount_globs,
                globs_not=mount_globs_not,
                case_mode=case_mode,
                fixed_strings=fixed_strings,
                word_regexp=word_regexp,
                invert_match=invert_match,
                before_context=before_context,
                after_context=after_context,
                output_mode=output_mode,
                max_count=None if needs_router_filter else max_count,
                columns=columns,
                user_id=user_id,
            )

        self_result, *mount_results = await asyncio.gather(
            _query_self(),
            *(
                _query_mount(
                    plan.filesystem,
                    rewritten_paths=plan.rewritten_paths,
                    mount_globs=plan.mount_globs,
                    mount_globs_not=plan.mount_globs_not,
                    needs_router_filter=plan.needs_router_filter,
                )
                for plan in mount_plans
            ),
        )

        results = [self._exclude_mounted_paths(self_result)]
        for plan, result in zip(
            mount_plans,
            mount_results,
            strict=True,
        ):
            rebased = result.add_prefix(plan.mount_path)
            if plan.needs_router_filter:
                rebased = rebased._with_entries(
                    [
                        c
                        for c in rebased.entries
                        if (
                            (
                                not plan.post_include_regexes
                                or any(rx.match(c.path) is not None for rx in plan.post_include_regexes)
                            )
                            and not any(rx.match(c.path) is not None for rx in plan.post_exclude_regexes)
                        )
                    ],
                )
            results.append(rebased)

        merged = self._merge_results(results)
        if any_router_post_filter and max_count is not None:
            merged = merged._with_entries(merged.entries[:max_count])
        return merged

    async def _route_fanout(
        self,
        op: str,
        candidates: VFSResult | None,
        *,
        user_id: str | None = None,
        **kwargs: object,
    ) -> VFSResult:
        """Route a namespace operation — dispatch candidates or fan-out.

        With candidates: group by filesystem, dispatch in parallel.
        Without: query self + every mount in parallel, merge results.
        When ``storage=False``, skips the self-query and fans out to mounts only.
        """
        if candidates is not None:
            return await self._dispatch_candidates(op, candidates, user_id=user_id, **kwargs)

        if not self._storage:
            if not self._mounts:
                return VFSResult(function=op, success=True, entries=[])
            mount_results = await asyncio.gather(
                *(getattr(fs, op)(user_id=user_id, **kwargs) for fs in self._mounts.values()),
            )
            rebased = [r.add_prefix(mp) for mp, r in zip(self._mounts, mount_results, strict=True)]
            return self._merge_results(rebased)

        async def _query_self() -> VFSResult:
            async with self._use_session() as s:
                return await getattr(self, f"_{op}_impl")(user_id=user_id, session=s, **kwargs)

        all_results = await asyncio.gather(
            _query_self(),
            *(getattr(fs, op)(user_id=user_id, **kwargs) for fs in self._mounts.values()),
        )

        self_result = self._exclude_mounted_paths(all_results[0])
        results = [self_result]
        for mount_path, r in zip(self._mounts, all_results[1:], strict=True):
            results.append(r.add_prefix(mount_path))

        return self._merge_results(results)

    async def _route_write_batch(
        self,
        entries: Sequence[VFSEntry],
        overwrite: bool = True,
        *,
        user_id: str | None = None,
    ) -> VFSResult:
        """Route a batch of entry writes to terminal filesystems in parallel."""
        if not entries:
            return VFSResult(function="write", success=True, entries=[])

        groups = self._group_entries_by_terminal(entries)

        for fs, prefix, group_entries in groups:
            for entry in group_entries:
                err = check_writable(fs, "write", entry.path, mount_prefix=prefix)
                if err is not None:
                    return err

        async def _write_group(fs: VirtualFileSystem, prefix: str, group_entries: list[VFSEntry]) -> VFSResult:
            async with fs._use_session() as s:
                result = await fs._write_impl(entries=group_entries, overwrite=overwrite, user_id=user_id, session=s)
            return result.add_prefix(prefix)

        results = await asyncio.gather(
            *(_write_group(fs, pfx, group_entries) for fs, pfx, group_entries in groups),
        )
        return self._merge_results(list(results))

    def _exclude_mounted_paths(self, result: VFSResult) -> VFSResult:
        """Remove self-storage candidates that fall under a mount prefix.

        Prevents shadow results when self has storage AND child mounts —
        the mount owns those paths, not self.
        """
        prefixes = list(self._mounts.keys())
        if not prefixes:
            return result
        filtered = [c for c in result.entries if not any(c.path == p or c.path.startswith(p + "/") for p in prefixes)]
        return result._with_entries(filtered)

    @staticmethod
    def _merge_results(results: list[VFSResult]) -> VFSResult:
        """Merge multiple results — any failure = overall failure.

        ``|`` already propagates ``success=False`` and concatenates
        ``errors``, so the merged result naturally reflects  all failures
        while preserving all successful candidates.
        """
        if not results:
            return VFSResult(success=True, entries=[])
        merged = results[0]
        for r in results[1:]:
            merged = merged | r
        return merged

    # -------------------------------------------------------------------
    # sessions
    # -------------------------------------------------------------------

    @asynccontextmanager
    async def _use_session(self) -> AsyncIterator[AsyncSession]:
        """Create a session from this filesystem's factory.

        Commits on success, rolls back on error.  If ``self._schema``
        is set, applies ``schema_translate_map={None: self._schema}``
        to the session's connection so ORM queries resolve unqualified
        table references to that schema.  Backends emitting raw
        ``text()`` SQL must also read ``self._schema`` themselves —
        ``schema_translate_map`` only rewrites compiled ``Table``
        references, not opaque string SQL.
        """
        if self._session_factory is None:
            msg = f"{self._name} has no session factory (storage=False)"
            raise RuntimeError(msg)
        async with self._session_factory() as session:
            try:
                if self._schema is not None:
                    await session.connection(
                        execution_options={"schema_translate_map": {None: self._schema}},
                    )
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    # -------------------------------------------------------------------
    # errors
    # -------------------------------------------------------------------

    def _error(self, errors: str | list[str] | VFSResult) -> VFSResult:
        """Create or check a failed result, raising if ``raise_on_error`` is set.

        Accepts either:
        - A string or list of strings → creates ``VFSResult(success=False)``
        - An existing ``VFSResult`` → returns it as-is if successful,
          raises if ``raise_on_error`` is set and ``success`` is ``False``
        """
        if isinstance(errors, VFSResult):
            if errors.success or not self._raise_on_error:
                return errors
            result = errors
        else:
            error_list = [errors] if isinstance(errors, str) else errors
            result = VFSResult(success=False, errors=error_list)
            if not self._raise_on_error:
                return result

        raise _classify_error(result.error_message, result.errors, result)

    def parse_query(self, query: str) -> QueryPlan:
        """Parse a CLI-style query string into an execution plan."""
        from vfs.query import parse_query

        return parse_query(query)

    async def run_query(
        self,
        query: str,
        *,
        user_id: str | None = None,
        initial: VFSResult | None = None,
    ) -> VFSResult:
        """Execute a parsed CLI-style query against this filesystem."""
        from vfs.query import execute_query

        plan = self.parse_query(query)
        return await execute_query(self, plan, initial=initial, user_id=user_id)

    async def cli(
        self,
        query: str,
        *,
        user_id: str | None = None,
        initial: VFSResult | None = None,
    ) -> str:
        """Execute *query* and render a human-readable text response."""
        from vfs.query import execute_query, render_query_result

        plan = self.parse_query(query)
        result = await execute_query(self, plan, initial=initial, user_id=user_id)
        return render_query_result(result, plan)

    # -------------------------------------------------------------------
    # public methods
    # -------------------------------------------------------------------

    # crud

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

    async def edit(
        self,
        path: str | None = None,
        old: str | None = None,
        new: str | None = None,
        edits: list[EditOperation] | None = None,
        candidates: VFSResult | None = None,
        replace_all: bool = False,
        *,
        user_id: str | None = None,
    ) -> VFSResult:
        if edits is None:
            if old is None or new is None:
                return self._error("edit requires old and new strings, or edits list")
            edits = [EditOperation(old=old, new=new, replace_all=replace_all)]
        return await self._route_single("edit", path, candidates, edits=edits, user_id=user_id)

    async def ls(
        self,
        path: str | None = None,
        candidates: VFSResult | None = None,
        *,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> VFSResult:
        return await self._route_single("ls", path, candidates, columns=columns, user_id=user_id)

    async def delete(
        self,
        path: str | None = None,
        candidates: VFSResult | None = None,
        permanent: bool = False,
        cascade: bool = True,
        *,
        user_id: str | None = None,
    ) -> VFSResult:
        return await self._route_single(
            "delete",
            path,
            candidates,
            permanent=permanent,
            cascade=cascade,
            user_id=user_id,
        )

    async def write(
        self,
        path: str | None = None,
        content: str | None = None,
        entries: Sequence[VFSEntry] | None = None,
        overwrite: bool = True,
        *,
        user_id: str | None = None,
    ) -> VFSResult:
        if entries is not None:
            return await self._route_write_batch(entries, overwrite=overwrite, user_id=user_id)
        return await self._route_single(
            "write",
            path,
            None,
            content=content,
            overwrite=overwrite,
            user_id=user_id,
        )

    async def mkdir(self, path: str, *, user_id: str | None = None) -> VFSResult:
        return await self._route_single("mkdir", path, None, user_id=user_id)

    async def tree(
        self,
        path: str,
        max_depth: int | None = None,
        *,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> VFSResult:
        return await self._route_single(
            "tree",
            path,
            None,
            max_depth=max_depth,
            columns=columns,
            user_id=user_id,
        )

    async def move(
        self,
        src: str | None = None,
        dest: str | None = None,
        moves: list[TwoPathOperation] | None = None,
        overwrite: bool = True,
        *,
        user_id: str | None = None,
    ) -> VFSResult:
        if moves is None:
            if not src or not dest:
                return self._error("move requires src and dest, or moves")
            moves = [TwoPathOperation(src=src, dest=dest)]
        return await self._route_two_path("move", moves, overwrite=overwrite, user_id=user_id)

    async def copy(
        self,
        src: str | None = None,
        dest: str | None = None,
        copies: list[TwoPathOperation] | None = None,
        overwrite: bool = True,
        *,
        user_id: str | None = None,
    ) -> VFSResult:
        if copies is None:
            if not src or not dest:
                return self._error("copy requires src and dest, or copies")
            copies = [TwoPathOperation(src=src, dest=dest)]
        return await self._route_two_path("copy", copies, overwrite=overwrite, user_id=user_id)

    async def mkedge(
        self,
        source: str,
        target: str,
        edge_type: str,
        *,
        user_id: str | None = None,
    ) -> VFSResult:
        src_fs, src_rel, src_pfx = self._resolve_terminal(source)
        tgt_fs, tgt_rel, _ = self._resolve_terminal(target)
        if src_fs is not tgt_fs:
            return self._error(
                f"Cross-mount edges not supported: {source} and {target} resolve to different filesystems",
            )
        edge_write_path = edge_out_path(src_rel, tgt_rel, edge_type)
        err = check_writable(src_fs, "mkedge", edge_write_path, mount_prefix=src_pfx)
        if err is not None:
            return err
        async with src_fs._use_session() as s:
            result = await src_fs._mkedge_impl(
                src_rel,
                tgt_rel,
                edge_type,
                user_id=user_id,
                session=s,
            )
        return result.add_prefix(src_pfx)

    # search

    async def glob(
        self,
        pattern: str,
        *,
        paths: tuple[str, ...] = (),
        ext: tuple[str, ...] = (),
        max_count: int | None = None,
        columns: frozenset[str] | None = None,
        candidates: VFSResult | None = None,
        user_id: str | None = None,
    ) -> VFSResult:
        return await self._route_glob_fanout(
            pattern=pattern,
            paths=paths,
            ext=ext,
            max_count=max_count,
            columns=columns,
            candidates=candidates,
            user_id=user_id,
        )

    async def grep(
        self,
        pattern: str,
        *,
        paths: tuple[str, ...] = (),
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
        candidates: VFSResult | None = None,
        user_id: str | None = None,
    ) -> VFSResult:
        return await self._route_grep_fanout(
            pattern=pattern,
            paths=paths,
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
            candidates=candidates,
            user_id=user_id,
        )

    async def semantic_search(
        self,
        query: str,
        k: int = 15,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
    ) -> VFSResult:
        return await self._route_fanout(
            "semantic_search",
            candidates,
            query=query,
            k=k,
            user_id=user_id,
        )

    async def vector_search(
        self,
        vector: list[float],
        k: int = 15,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
    ) -> VFSResult:
        return await self._route_fanout(
            "vector_search",
            candidates,
            vector=vector,
            k=k,
            user_id=user_id,
        )

    async def lexical_search(
        self,
        query: str,
        k: int = 15,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
    ) -> VFSResult:
        return await self._route_fanout(
            "lexical_search",
            candidates,
            query=query,
            k=k,
            user_id=user_id,
        )

    # graph

    async def predecessors(
        self,
        path: str | None = None,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
    ) -> VFSResult:
        return await self._route_single("predecessors", path, candidates, user_id=user_id)

    async def successors(
        self,
        path: str | None = None,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
    ) -> VFSResult:
        return await self._route_single("successors", path, candidates, user_id=user_id)

    async def ancestors(
        self,
        path: str | None = None,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
    ) -> VFSResult:
        return await self._route_single("ancestors", path, candidates, user_id=user_id)

    async def descendants(
        self,
        path: str | None = None,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
    ) -> VFSResult:
        return await self._route_single("descendants", path, candidates, user_id=user_id)

    async def neighborhood(
        self,
        path: str | None = None,
        candidates: VFSResult | None = None,
        *,
        depth: int = 2,
        user_id: str | None = None,
    ) -> VFSResult:
        return await self._route_single("neighborhood", path, candidates, depth=depth, user_id=user_id)

    async def meeting_subgraph(
        self,
        candidates: VFSResult,
        *,
        user_id: str | None = None,
    ) -> VFSResult:
        return await self._dispatch_candidates("meeting_subgraph", candidates, user_id=user_id)

    async def min_meeting_subgraph(
        self,
        candidates: VFSResult,
        *,
        user_id: str | None = None,
    ) -> VFSResult:
        return await self._dispatch_candidates("min_meeting_subgraph", candidates, user_id=user_id)

    async def pagerank(
        self,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
    ) -> VFSResult:
        return await self._route_fanout("pagerank", candidates, user_id=user_id)

    async def betweenness_centrality(
        self,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
    ) -> VFSResult:
        return await self._route_fanout("betweenness_centrality", candidates, user_id=user_id)

    async def closeness_centrality(
        self,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
    ) -> VFSResult:
        return await self._route_fanout("closeness_centrality", candidates, user_id=user_id)

    async def degree_centrality(
        self,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
    ) -> VFSResult:
        return await self._route_fanout("degree_centrality", candidates, user_id=user_id)

    async def in_degree_centrality(
        self,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
    ) -> VFSResult:
        return await self._route_fanout("in_degree_centrality", candidates, user_id=user_id)

    async def out_degree_centrality(
        self,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
    ) -> VFSResult:
        return await self._route_fanout("out_degree_centrality", candidates, user_id=user_id)

    async def hits(
        self,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
    ) -> VFSResult:
        return await self._route_fanout("hits", candidates, user_id=user_id)

    # -------------------------------------------------------------------
    # impl stubs
    # -------------------------------------------------------------------

    async def _read_impl(
        self,
        path: str | None = None,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        raise NotImplementedError

    async def _stat_impl(
        self,
        path: str | None = None,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        raise NotImplementedError

    async def _edit_impl(
        self,
        path: str | None = None,
        candidates: VFSResult | None = None,
        edits: list[EditOperation] | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        raise NotImplementedError

    async def _ls_impl(
        self,
        path: str | None = None,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        raise NotImplementedError

    async def _delete_impl(
        self,
        path: str | None = None,
        candidates: VFSResult | None = None,
        permanent: bool = False,
        cascade: bool = True,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        raise NotImplementedError

    async def _write_impl(
        self,
        path: str | None = None,
        content: str | None = None,
        entries: Sequence[VFSEntry] | None = None,
        overwrite: bool = True,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        raise NotImplementedError

    async def _mkdir_impl(
        self,
        path: str,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        raise NotImplementedError

    async def _move_impl(
        self,
        ops: Sequence[TwoPathOperation] | None = None,
        overwrite: bool = True,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        raise NotImplementedError

    async def _copy_impl(
        self,
        ops: Sequence[TwoPathOperation] | None = None,
        overwrite: bool = True,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        raise NotImplementedError

    async def _mkedge_impl(
        self,
        source: str | None = None,
        target: str | None = None,
        edge_type: str | None = None,
        entries: Sequence[VFSEntry] | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        raise NotImplementedError

    async def _tree_impl(
        self,
        path: str,
        max_depth: int | None = None,
        *,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        raise NotImplementedError

    async def _glob_impl(
        self,
        pattern: str,
        *,
        paths: tuple[str, ...] = (),
        ext: tuple[str, ...] = (),
        max_count: int | None = None,
        columns: frozenset[str] | None = None,
        candidates: VFSResult | None = None,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        raise NotImplementedError

    async def _grep_impl(
        self,
        pattern: str,
        *,
        paths: tuple[str, ...] = (),
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
        candidates: VFSResult | None = None,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        raise NotImplementedError

    async def _semantic_search_impl(
        self,
        query: str,
        k: int = 15,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        raise NotImplementedError

    async def _vector_search_impl(
        self,
        vector: list[float] | None = None,
        k: int = 15,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        raise NotImplementedError

    async def _lexical_search_impl(
        self,
        query: str,
        k: int = 15,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        raise NotImplementedError

    async def _predecessors_impl(
        self,
        path: str | None = None,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        raise NotImplementedError

    async def _successors_impl(
        self,
        path: str | None = None,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        raise NotImplementedError

    async def _ancestors_impl(
        self,
        path: str | None = None,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        raise NotImplementedError

    async def _descendants_impl(
        self,
        path: str | None = None,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        raise NotImplementedError

    async def _neighborhood_impl(
        self,
        path: str | None = None,
        candidates: VFSResult | None = None,
        *,
        depth: int = 2,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        raise NotImplementedError

    async def _meeting_subgraph_impl(
        self,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        raise NotImplementedError

    async def _min_meeting_subgraph_impl(
        self,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        raise NotImplementedError

    async def _pagerank_impl(
        self,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        raise NotImplementedError

    async def _betweenness_centrality_impl(
        self,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        raise NotImplementedError

    async def _closeness_centrality_impl(
        self,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        raise NotImplementedError

    async def _degree_centrality_impl(
        self,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        raise NotImplementedError

    async def _in_degree_centrality_impl(
        self,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        raise NotImplementedError

    async def _out_degree_centrality_impl(
        self,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        raise NotImplementedError

    async def _hits_impl(
        self,
        candidates: VFSResult | None = None,
        *,
        user_id: str | None = None,
        session: AsyncSession,
    ) -> VFSResult:
        raise NotImplementedError
