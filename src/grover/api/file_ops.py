"""FileOpsMixin — file CRUD, version, trash, and reconciliation operations for GroverAsync."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from grover.backends.protocol import SupportsReconcile
from grover.exceptions import MountNotFoundError
from grover.models.database.file import FileModel
from grover.models.internal.detail import WriteDetail
from grover.models.internal.ref import Directory, File
from grover.models.internal.results import (
    BatchResult,
    FileOperationResult,
    FileSearchResult,
    FileSearchSet,
    GroverResult,
)
from grover.permissions import Permission
from grover.ref import Ref
from grover.util.paths import normalize_path

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from grover.api.context import GroverContext
    from grover.models.database.chunk import FileChunkModelBase
    from grover.models.database.file import FileModelBase
    from grover.mount import Mount


class FileOpsMixin:
    """File CRUD, version, trash, and reconciliation operations extracted from GroverAsync."""

    _ctx: GroverContext

    # ------------------------------------------------------------------
    # FS Operations (absorbed from VFS)
    # ------------------------------------------------------------------

    async def read(
        self,
        path: str,
        offset: int = 0,
        limit: int = 2000,
        *,
        user_id: str | None = None,
    ) -> GroverResult:
        path = normalize_path(path)
        async with self._ctx.mount_session(path) as (mount, rel_path, session):
            result = await mount.filesystem.read(rel_path, offset, limit, session=session, user_id=user_id)
        return result.rebase(mount.path)

    async def write(
        self,
        path: str,
        content: str,
        overwrite: bool = True,
        *,
        user_id: str | None = None,
    ) -> GroverResult:
        f = FileModel(path=path, content=content)
        return await self.write_files([f], overwrite=overwrite, user_id=user_id)

    async def write_files(self,
        files: list[FileModelBase],
        overwrite: bool = True,
        *,
        user_id: str | None = None,
    ) -> GroverResult:
        """Batch write files from model instances."""
        if not files:
            return GroverResult(success=True, message="No files to write")

        groups, err = self._ctx.group_by_mount_writable(files, lambda f: f.path)
        if err:
            return GroverResult(success=False, message=err)

        async def _handler(mount: Mount, group: list[FileModelBase], session: AsyncSession) -> GroverResult:
            backend_files = [f.model_copy(update={"path": f.path.removeprefix(mount.path) or "/"}) for f in group]
            try:
                result = await mount.filesystem.write_files(
                    backend_files,
                    overwrite=overwrite,
                    session=session,
                )
                return result.rebase(mount.path)
            except Exception as e:
                return GroverResult(
                    success=False,
                    message=str(e),
                    files=[
                        File(
                            path=f.path,
                            evidence=[WriteDetail(operation="write", success=False, message=str(e))],
                        )
                        for f in group
                    ],
                )

        result = await self._ctx.dispatch_to_mounts(groups, _handler)
        result.message = f"Wrote {result.succeeded} file(s)" + (f", {result.failed} failed" if result.failed else "")
        return result

    async def edit(
        self,
        path: str,
        old: str,
        new: str,
        *,
        replace_all: bool = False,
        user_id: str | None = None,
    ) -> GroverResult:
        if error := self._ctx.check_writable(path):
            return error
        async with self._ctx.mount_session(path) as (mount, rel_path, session):
            result = await mount.filesystem.edit(
                rel_path,
                old,
                new,
                replace_all,
                "agent",
                session=session,
                user_id=user_id,
            )
        return result.rebase(mount.path)

    async def delete(self, path: str, permanent: bool = False, *, user_id: str | None = None) -> GroverResult:
        if error := self._ctx.check_writable(path):
            return error
        async with self._ctx.mount_session(path) as (mount, rel_path, session):
            result = await mount.filesystem.delete(rel_path, permanent, session=session, user_id=user_id)
        return result.rebase(mount.path)

    async def mkdir(
        self,
        path: str,
        parents: bool = True,
        *,
        user_id: str | None = None,
    ) -> GroverResult:
        if error := self._ctx.check_writable(path):
            return error
        async with self._ctx.mount_session(path) as (mount, rel_path, session):
            result = await mount.filesystem.mkdir(rel_path, parents, session=session, user_id=user_id)
        return result.rebase(mount.path)

    async def exists(self, path: str, *, user_id: str | None = None) -> GroverResult:
        path = normalize_path(path)

        if path == "/":
            return GroverResult(success=True, directories=[Directory(path=path)])

        if self._ctx.registry.has_mount(path):
            return GroverResult(success=True, directories=[Directory(path=path)])

        async with self._ctx.mount_session(path) as (mount, rel_path, session):
            return await mount.filesystem.exists(rel_path, session=session, user_id=user_id)

    def get_permission_info(self, path: str) -> tuple[str, bool]:
        path = normalize_path(path)
        permission = self._ctx.registry.get_permission(path)
        return permission.value, False

    async def move(
        self, src: str, dest: str, *, user_id: str | None = None,
    ) -> GroverResult:
        return await self.move_files([(src, dest)], user_id=user_id)

    async def move_files(
        self,
        pairs: list[tuple[str, str]],
        *,
        user_id: str | None = None,
    ) -> GroverResult:
        """Batch move files. All pairs must be within the same mount."""
        if not pairs:
            return GroverResult(success=True, message="No files to move")

        files: list[File] = []
        for src, dest in pairs:
            src = normalize_path(src)
            dest = normalize_path(dest)

            if error := self._ctx.check_writable(src):
                return error
            if error := self._ctx.check_writable(dest):
                return error

            src_mount, src_rel = self._ctx.registry.resolve(src)
            dest_mount, dest_rel = self._ctx.registry.resolve(dest)
            if src_mount is not dest_mount:
                return GroverResult(success=False, message=f"Cannot move across mounts: {src} -> {dest}")

            async with self._ctx.session_for(src_mount) as session:
                result = await src_mount.filesystem.move(
                    src_rel, dest_rel, session=session, user_id=user_id,
                )
            if not result.success:
                return GroverResult(
                    success=False,
                    message=f"Move failed: {src} -> {dest}: {result.message}",
                    files=files,
                )
            result.file.path = self._ctx.prefix_path(result.file.path, src_mount.path) or result.file.path
            files.append(result.file)

        return GroverResult(
            success=True,
            message=f"Moved {len(files)} file(s)",
            files=files,
        )

    async def copy(self, src: str, dest: str, *, user_id: str | None = None) -> GroverResult:
        return await self.copy_files([(src, dest)], user_id=user_id)

    async def copy_files(
        self,
        pairs: list[tuple[str, str]],
        *,
        user_id: str | None = None,
    ) -> GroverResult:
        """Batch copy files. Cross-mount copies use read + write."""
        if not pairs:
            return GroverResult(success=True, message="No files to copy")

        files: list[File] = []
        for src, dest in pairs:
            src = normalize_path(src)
            dest = normalize_path(dest)

            if error := self._ctx.check_writable(dest):
                return error

            src_mount, src_rel = self._ctx.registry.resolve(src)
            dest_mount, dest_rel = self._ctx.registry.resolve(dest)

            if src_mount is dest_mount:
                async with self._ctx.session_for(src_mount) as session:
                    result = await src_mount.filesystem.copy(
                        src_rel, dest_rel, session=session, user_id=user_id,
                    )
                result.file.path = self._ctx.prefix_path(result.file.path, dest_mount.path) or result.file.path
                if not result.success:
                    return GroverResult(
                        success=False,
                        message=f"Copy failed: {src} -> {dest}: {result.message}",
                        files=files,
                    )
                files.append(result.file)
            else:
                # Cross-mount: read from source, write to dest
                async with self._ctx.mount_session(src) as (_, src_rel_path, src_sess):
                    read_result = await src_mount.filesystem.read(src_rel_path, session=src_sess, user_id=user_id)
                if not read_result.success or read_result.content is None:
                    return GroverResult(
                        success=False,
                        message=f"Cannot read source for cross-mount copy: {src}",
                        files=files,
                    )
                async with self._ctx.session_for(dest_mount) as dest_sess:
                    write_result = await dest_mount.filesystem.write(
                        dest_rel, read_result.content, session=dest_sess, user_id=user_id,
                    )
                if not write_result.success:
                    return GroverResult(
                        success=False,
                        message=f"Cannot write dest for cross-mount copy: {dest}",
                        files=files,
                    )
                files.append(write_result.file)

        return GroverResult(
            success=True,
            message=f"Copied {len(files)} file(s)",
            files=files,
        )
    
    async def list_dir(
        self,
        path: str = "/",
        *,
        user_id: str | None = None,
    ) -> GroverResult:
        path = normalize_path(path)

        if path == "/":
            return self._list_root()

        async with self._ctx.mount_session(path) as (mount, rel_path, session):
            result = await mount.filesystem.list_dir(rel_path, session=session, user_id=user_id)
        return result.rebase(mount.path)

    def _list_root(self) -> GroverResult:
        dirs = [
            Directory(path=mount.path)
            for mount in self._ctx.registry.list_mounts()
        ]
        return GroverResult(
            success=True,
            message=f"Found {len(dirs)} mount(s)",
            directories=dirs,
        )

    async def tree(
        self,
        path: str = "/",
        *,
        max_depth: int | None = None,
        user_id: str | None = None,
    ) -> GroverResult:
        path = normalize_path(path)

        if path == "/":
            combined = GroverResult(
                success=True,
                directories=[Directory(path=mount.path) for mount in self._ctx.registry.list_mounts()],
            )
            if max_depth is None or max_depth > 0:
                for mount in self._ctx.registry.list_mounts():
                    async with self._ctx.session_for(mount) as session:
                        mount_depth = max_depth - 1 if max_depth is not None else None
                        result = await mount.filesystem.tree(
                            "/", max_depth=mount_depth, session=session, user_id=user_id,
                        )
                    if result.success:
                        combined = combined | result.rebase(mount.path)
            combined.message = f"{len(combined.directories)} directories, {len(combined.files)} files"
            return combined

        async with self._ctx.mount_session(path) as (mount, rel_path, session):
            result = await mount.filesystem.tree(
                rel_path, max_depth=max_depth, session=session, user_id=user_id,
            )
        return result.rebase(mount.path)

    async def list_versions(self, path: str, *, user_id: str | None = None) -> FileSearchResult:
        path = normalize_path(path)
        mount, rel_path = self._ctx.registry.resolve(path)
        assert mount.filesystem is not None
        async with self._ctx.session_for(mount) as sess:
            result = await mount.filesystem.list_versions(rel_path, session=sess, user_id=user_id)
        return result

    async def read_version(self, path: str, version: int, *, user_id: str | None = None) -> FileOperationResult:
        path = normalize_path(path)
        mount, rel_path = self._ctx.registry.resolve(path)
        assert mount.filesystem is not None
        async with self._ctx.session_for(mount) as sess:
            return await mount.filesystem.get_version_content(rel_path, version, session=sess, user_id=user_id)

    async def diff_versions(
        self, path: str, version_a: int, version_b: int, *, user_id: str | None = None
    ) -> FileOperationResult:
        from grover.providers.versioning.diff import compute_diff

        path = normalize_path(path)
        result_a = await self.read_version(path, version_a, user_id=user_id)
        if not result_a.success:
            return FileOperationResult(
                success=False,
                message=f"Cannot read version {version_a}: {result_a.message}",
                file=File(path=path),
            )
        result_b = await self.read_version(path, version_b, user_id=user_id)
        if not result_b.success:
            return FileOperationResult(
                success=False,
                message=f"Cannot read version {version_b}: {result_b.message}",
                file=File(path=path),
            )
        diff = compute_diff(result_a.file.content or "", result_b.file.content or "")
        return FileOperationResult(
            success=True,
            message=f"Diff between v{version_a} and v{version_b}",
            file=File(path=path, content=diff),
        )

    async def restore_version(self, path: str, version: int, *, user_id: str | None = None) -> FileOperationResult:
        path = normalize_path(path)
        if err := self._ctx.check_writable(path):
            return FileOperationResult(success=False, message=err)

        mount, rel_path = self._ctx.registry.resolve(path)
        assert mount.filesystem is not None
        async with self._ctx.session_for(mount) as sess:
            result = await mount.filesystem.restore_version(rel_path, version, session=sess, user_id=user_id)
        result.file.path = self._ctx.prefix_path(result.file.path, mount.path) or result.file.path
        if result.success:
            self._ctx.worker.schedule(
                path,
                lambda p=path, u=user_id: self._process_write(p, None, u),  # type: ignore[attr-defined]
            )
        return result

    # ------------------------------------------------------------------
    # Trash operations (absorbed from VersionTrashMixin)
    # ------------------------------------------------------------------

    async def list_trash(self, *, user_id: str | None = None) -> FileSearchResult:
        """List all items in trash across all mounts."""
        combined = FileSearchResult(success=True, message="")
        for mount in self._ctx.registry.list_mounts():
            assert mount.filesystem is not None
            async with self._ctx.session_for(mount) as sess:
                result = await mount.filesystem.list_trash(session=sess, user_id=user_id)
            if result.success:
                rebased = result.rebase(mount.path)
                combined = combined | rebased
        combined.message = f"Found {len(combined)} item(s) in trash"
        return combined

    async def restore_from_trash(self, path: str, *, user_id: str | None = None) -> FileOperationResult:
        path = normalize_path(path)
        if err := self._ctx.check_writable(path):
            return FileOperationResult(success=False, message=err)

        mount, rel_path = self._ctx.registry.resolve(path)
        assert mount.filesystem is not None
        async with self._ctx.session_for(mount) as sess:
            result = await mount.filesystem.restore_from_trash(rel_path, session=sess, user_id=user_id)
        result.file.path = self._ctx.prefix_path(result.file.path, mount.path) or result.file.path
        if result.success:
            self._ctx.worker.schedule(
                path,
                lambda p=path, u=user_id: self._process_write(p, None, u),  # type: ignore[attr-defined]
            )
        return result

    async def empty_trash(self, *, user_id: str | None = None) -> FileOperationResult:
        """Empty trash across all mounts.  Skips read-only mounts."""
        total_deleted = 0
        mounts_processed = 0
        for mount in self._ctx.registry.list_mounts():
            if mount.permission == Permission.READ_ONLY:
                continue
            assert mount.filesystem is not None
            async with self._ctx.session_for(mount) as sess:
                result = await mount.filesystem.empty_trash(session=sess, user_id=user_id)
            if not result.success:
                return result
            mounts_processed += 1
        return FileOperationResult(
            success=True,
            message=(f"Permanently deleted {total_deleted} file(s) from {mounts_processed} mount(s)"),
        )

    # ------------------------------------------------------------------
    # Reconciliation (absorbed from VersionTrashMixin)
    # ------------------------------------------------------------------

    async def reconcile(self, mount_path: str | None = None) -> FileOperationResult:
        """Reconcile disk <-> DB for capable mounts."""
        total = FileOperationResult()
        mounts = self._ctx.registry.list_mounts()
        if mount_path is not None:
            mount_path = normalize_path(mount_path).rstrip("/")
            mounts = [m for m in mounts if m.path == mount_path]

        for mount in mounts:
            if mount.permission == Permission.READ_ONLY:
                continue
            cap = self._ctx.get_capability(mount.filesystem, SupportsReconcile)
            if cap is None:
                continue
            async with self._ctx.session_for(mount) as sess:
                await cap.reconcile(session=sess)

        return total

    # ------------------------------------------------------------------
    # Chunk write operations
    # ------------------------------------------------------------------

    async def write_chunk(
        self,
        chunk: FileChunkModelBase,
        *,
        user_id: str | None = None,
    ) -> FileOperationResult:
        """Write (upsert) a single chunk. Parent file must exist."""
        result = await self.write_chunks([chunk], user_id=user_id)
        if result.results:
            return result.results[0]
        return FileOperationResult(success=result.success, message=result.message, file=File(path=chunk.path))

    async def write_chunks(
        self,
        chunks: list[FileChunkModelBase],
        *,
        user_id: str | None = None,
    ) -> BatchResult:
        """Batch write (upsert) chunks. Parent files must exist."""
        if not chunks:
            return BatchResult(success=True, message="No chunks to write")

        # Validate all chunk refs upfront
        for chunk in chunks:
            ref = Ref(chunk.path)
            if not ref.is_chunk:
                return BatchResult(
                    success=False,
                    message=f"Invalid chunk ref (must contain '#'): {chunk.path}",
                )
            if chunk.file_path != ref.base_path:
                return BatchResult(
                    success=False,
                    message=(f"file_path mismatch: {chunk.file_path} != {ref.base_path} for chunk {chunk.path}"),
                )

        # Track results by original index to preserve input order
        results_by_idx: dict[int, FileOperationResult] = {}

        # Group chunks by mount, keeping original indices

        mount_groups: dict[str, list[tuple[int, FileChunkModelBase]]] = defaultdict(list)
        for idx, chunk in enumerate(chunks):
            path = normalize_path(chunk.file_path)
            mount, _rel = self._ctx.registry.resolve(path)
            mount_groups[mount.path].append((idx, chunk))

        for mount_path, group in mount_groups.items():
            mount, _ = self._ctx.registry.resolve(mount_path + "/dummy")

            # Check writable
            if err := self._ctx.check_writable(mount_path + "/dummy"):
                for idx, c in group:
                    results_by_idx[idx] = FileOperationResult(success=False, message=err, file=File(path=c.path))
                continue

            assert mount.filesystem is not None
            async with self._ctx.session_for(mount) as sess:
                # Validate parent files exist (one exists() per unique parent)
                unique_parents = {normalize_path(c.file_path) for _, c in group}
                parent_exists: dict[str, bool] = {}
                for parent in unique_parents:
                    _, rel_parent = self._ctx.registry.resolve(parent)
                    ex = await mount.filesystem.exists(rel_parent, session=sess)
                    parent_exists[parent] = ex.message == "exists"

                valid_items: list[tuple[int, FileChunkModelBase]] = []
                for idx, c in group:
                    if not parent_exists.get(normalize_path(c.file_path), False):
                        results_by_idx[idx] = FileOperationResult(
                            success=False,
                            message=f"Parent file not found: {c.file_path}",
                            file=File(path=c.path),
                        )
                    else:
                        valid_items.append((idx, c))

                if valid_items:
                    # Strip mount prefix from paths for backend
                    backend_chunks = []
                    idx_order: list[int] = []
                    for idx, c in valid_items:
                        rel_file = normalize_path(c.file_path).removeprefix(mount.path) or "/"
                        rel_chunk_path = normalize_path(c.path).removeprefix(mount.path) or "/"
                        bc = type(c).model_validate(
                            {
                                "file_path": rel_file,
                                "path": rel_chunk_path,
                                "content": c.content,
                                "line_start": c.line_start,
                                "line_end": c.line_end,
                            }
                        )
                        backend_chunks.append(bc)
                        idx_order.append(idx)

                    batch_result = await mount.filesystem.write_chunks(backend_chunks, session=sess)
                    # Re-prefix paths and map back to original indices
                    batch_results: list[FileOperationResult] = getattr(batch_result, "results", [])
                    for i, r in enumerate(batch_results):
                        r.file.path = self._ctx.prefix_path(r.file.path, mount.path) or r.file.path
                        results_by_idx[idx_order[i]] = r

        # Build ordered results list
        all_results = [results_by_idx[i] for i in range(len(chunks))]

        # Schedule background processing for successful chunks
        for chunk, result in zip(chunks, all_results, strict=True):
            if result.success:
                self._ctx.worker.schedule_immediate(
                    self._process_chunk_write(chunk)  # type: ignore[attr-defined]
                )

        succeeded = sum(1 for r in all_results if r.success)
        failed = len(all_results) - succeeded
        return BatchResult(
            success=failed == 0,
            message=f"Wrote {succeeded} chunk(s)" + (f", {failed} failed" if failed else ""),
            results=all_results,
            succeeded=succeeded,
            failed=failed,
        )
