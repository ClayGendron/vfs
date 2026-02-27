"""VersionTrashMixin — version, trash, and reconciliation operations for GroverAsync."""

from __future__ import annotations

from typing import TYPE_CHECKING

from grover.events import EventType, FileEvent
from grover.fs.exceptions import CapabilityNotSupportedError
from grover.fs.permissions import Permission
from grover.fs.protocol import SupportsReconcile, SupportsTrash, SupportsVersions
from grover.fs.utils import normalize_path
from grover.types import (
    DeleteResult,
    GetVersionContentResult,
    RestoreResult,
    TrashResult,
    VerifyVersionResult,
    VersionResult,
)

if TYPE_CHECKING:
    from grover.facade.context import GroverContext


class VersionTrashMixin:
    """Version, trash, and reconciliation operations extracted from GroverAsync."""

    _ctx: GroverContext

    # ------------------------------------------------------------------
    # Version operations (absorbed from VFS, capability-gated)
    # ------------------------------------------------------------------

    async def list_versions(self, path: str, *, user_id: str | None = None) -> VersionResult:
        path = normalize_path(path)
        try:
            mount, rel_path = self._ctx.registry.resolve(path)
            cap = self._ctx.get_capability(mount.filesystem, SupportsVersions)
            if cap is None:
                raise CapabilityNotSupportedError(
                    f"Mount at {mount.path} does not support versioning"
                )
            async with self._ctx.session_for(mount) as sess:
                return await cap.list_versions(rel_path, session=sess, user_id=user_id)
        except CapabilityNotSupportedError as e:
            return VersionResult(success=False, message=str(e))

    async def get_version_content(
        self, path: str, version: int, *, user_id: str | None = None
    ) -> GetVersionContentResult:
        path = normalize_path(path)
        try:
            mount, rel_path = self._ctx.registry.resolve(path)
            cap = self._ctx.get_capability(mount.filesystem, SupportsVersions)
            if cap is None:
                raise CapabilityNotSupportedError(
                    f"Mount at {mount.path} does not support versioning"
                )
            async with self._ctx.session_for(mount) as sess:
                return await cap.get_version_content(
                    rel_path, version, session=sess, user_id=user_id
                )
        except CapabilityNotSupportedError as e:
            return GetVersionContentResult(success=False, message=str(e))

    async def restore_version(
        self, path: str, version: int, *, user_id: str | None = None
    ) -> RestoreResult:
        path = normalize_path(path)
        if err := self._ctx.check_writable(path):
            return RestoreResult(success=False, message=err)

        try:
            mount, rel_path = self._ctx.registry.resolve(path)
            cap = self._ctx.get_capability(mount.filesystem, SupportsVersions)
            if cap is None:
                raise CapabilityNotSupportedError(
                    f"Mount at {mount.path} does not support versioning"
                )
            async with self._ctx.session_for(mount) as sess:
                result = await cap.restore_version(rel_path, version, session=sess, user_id=user_id)
            result.path = self._ctx.prefix_path(result.path, mount.path) or result.path
            if result.success:
                await self._ctx.emit(
                    FileEvent(event_type=EventType.FILE_RESTORED, path=path, user_id=user_id)
                )
            return result
        except CapabilityNotSupportedError as e:
            return RestoreResult(success=False, message=str(e))

    async def verify_versions(
        self, path: str, *, user_id: str | None = None
    ) -> VerifyVersionResult:
        path = normalize_path(path)
        try:
            mount, rel_path = self._ctx.registry.resolve(path)
            cap = self._ctx.get_capability(mount.filesystem, SupportsVersions)
            if cap is None:
                raise CapabilityNotSupportedError(
                    f"Mount at {mount.path} does not support versioning"
                )
            async with self._ctx.session_for(mount) as sess:
                result = await cap.verify_versions(rel_path, session=sess, user_id=user_id)
            result.path = self._ctx.prefix_path(result.path, mount.path) or result.path
            return result
        except CapabilityNotSupportedError as e:
            return VerifyVersionResult(success=False, message=str(e), path=path)

    async def verify_all_versions(self, mount_path: str | None = None) -> list[VerifyVersionResult]:
        all_results: list[VerifyVersionResult] = []
        mounts = self._ctx.registry.list_mounts()
        if mount_path is not None:
            mount_path = normalize_path(mount_path).rstrip("/")
            mounts = [m for m in mounts if m.path == mount_path]

        for mount in mounts:
            cap = self._ctx.get_capability(mount.filesystem, SupportsVersions)
            if cap is None:
                continue
            async with self._ctx.session_for(mount) as sess:
                results = await cap.verify_all_versions(session=sess)
            for r in results:
                r.path = self._ctx.prefix_path(r.path, mount.path) or r.path
            all_results.extend(results)
        return all_results

    # ------------------------------------------------------------------
    # Trash operations (absorbed from VFS, capability-gated)
    # ------------------------------------------------------------------

    async def list_trash(self, *, user_id: str | None = None) -> TrashResult:
        """List all items in trash across all mounts."""
        combined = TrashResult(success=True, message="")
        for mount in self._ctx.registry.list_mounts():
            cap = self._ctx.get_capability(mount.filesystem, SupportsTrash)
            if cap is None:
                continue
            async with self._ctx.session_for(mount) as sess:
                result = await cap.list_trash(session=sess, user_id=user_id)
            if result.success:
                rebased = result.rebase(mount.path)
                combined = combined | rebased
        combined.message = f"Found {len(combined)} item(s) in trash"
        return combined

    async def restore_from_trash(self, path: str, *, user_id: str | None = None) -> RestoreResult:
        path = normalize_path(path)
        if err := self._ctx.check_writable(path):
            return RestoreResult(success=False, message=err)

        try:
            mount, rel_path = self._ctx.registry.resolve(path)
            cap = self._ctx.get_capability(mount.filesystem, SupportsTrash)
            if cap is None:
                raise CapabilityNotSupportedError(f"Mount at {mount.path} does not support trash")
            async with self._ctx.session_for(mount) as sess:
                result = await cap.restore_from_trash(rel_path, session=sess, user_id=user_id)
            result.path = self._ctx.prefix_path(result.path, mount.path) or result.path
            if result.success:
                await self._ctx.emit(
                    FileEvent(event_type=EventType.FILE_RESTORED, path=path, user_id=user_id)
                )
            return result
        except CapabilityNotSupportedError as e:
            return RestoreResult(success=False, message=str(e))

    async def empty_trash(self, *, user_id: str | None = None) -> DeleteResult:
        """Empty trash across all mounts.  Skips read-only mounts."""
        total_deleted = 0
        mounts_processed = 0
        for mount in self._ctx.registry.list_mounts():
            # Skip read-only mounts — empty_trash is a mutation
            if mount.permission == Permission.READ_ONLY:
                continue
            cap = self._ctx.get_capability(mount.filesystem, SupportsTrash)
            if cap is None:
                continue
            async with self._ctx.session_for(mount) as sess:
                result = await cap.empty_trash(session=sess, user_id=user_id)
            if not result.success:
                return result
            total_deleted += result.total_deleted or 0
            mounts_processed += 1
        return DeleteResult(
            success=True,
            message=f"Permanently deleted {total_deleted} file(s) from {mounts_processed} mount(s)",
            total_deleted=total_deleted,
            permanent=True,
        )

    # ------------------------------------------------------------------
    # Reconciliation
    # ------------------------------------------------------------------

    async def reconcile(self, mount_path: str | None = None) -> dict[str, int]:
        """Reconcile disk ↔ DB for capable mounts."""
        total: dict[str, int] = {"created": 0, "updated": 0, "deleted": 0, "chain_errors": 0}
        mounts = self._ctx.registry.list_mounts()
        if mount_path is not None:
            mount_path = normalize_path(mount_path).rstrip("/")
            mounts = [m for m in mounts if m.path == mount_path]

        for mount in mounts:
            # Skip read-only mounts — reconcile is a mutation
            if mount.permission == Permission.READ_ONLY:
                continue
            cap = self._ctx.get_capability(mount.filesystem, SupportsReconcile)
            if cap is None:
                continue
            async with self._ctx.session_for(mount) as sess:
                stats = await cap.reconcile(session=sess)
            for k, v in stats.items():
                total[k] = total.get(k, 0) + v

        return total
