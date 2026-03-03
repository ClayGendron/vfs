"""MetadataService — file lookup and info conversion."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlmodel import select

from grover.types.operations import ExistsResult, FileInfoResult

from .utils import normalize_path, validate_path

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from grover.models.files import FileBase


class MetadataService:
    """Stateless helpers for file record lookup and conversion.

    Receives the concrete file model at construction so callers can
    use custom SQLModel subclasses.
    """

    def __init__(self, file_model: type[FileBase]) -> None:
        self._file_model = file_model

    async def get_file(
        self,
        session: AsyncSession,
        path: str,
        include_deleted: bool = False,
    ) -> FileBase | None:
        """Get a file record by path."""
        path = normalize_path(path)
        model = self._file_model
        query = select(model).where(
            model.path == path,
        )
        if not include_deleted:
            query = query.where(model.deleted_at.is_(None))  # type: ignore[unresolved-attribute]

        result = await session.execute(query)
        return result.scalar_one_or_none()

    async def exists(self, session: AsyncSession, path: str) -> ExistsResult:
        """Check if a file or directory exists."""
        valid, _ = validate_path(path)
        if not valid:
            return ExistsResult(exists=False, path=path)

        path = normalize_path(path)
        if path == "/":
            return ExistsResult(exists=True, path=path)

        file = await self.get_file(session, path)
        return ExistsResult(exists=file is not None, path=path)

    async def get_info(self, session: AsyncSession, path: str) -> FileInfoResult:
        """Get metadata for a file or directory."""
        valid, msg = validate_path(path)
        if not valid:
            return FileInfoResult(success=False, message=msg or "Invalid path", path=path)

        path = normalize_path(path)

        file = await self.get_file(session, path)
        if not file:
            return FileInfoResult(success=False, message=f"File not found: {path}", path=path)
        return self.file_to_info(file)

    @staticmethod
    def file_to_info(f: FileBase) -> FileInfoResult:
        """Convert a file record to FileInfoResult."""
        return FileInfoResult(
            path=f.path,
            is_directory=f.is_directory,
            size_bytes=f.size_bytes or 0,
            mime_type=f.mime_type or "text/plain",
            version=f.current_version,
            created_at=f.created_at,
            updated_at=f.updated_at,
        )
