"""DefaultChunkProvider — stateless chunk CRUD for DB-backed chunk storage."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlmodel import select

from grover.models.internal.ref import File, FileChunk
from grover.models.internal.results import FileOperationResult
from grover.util.content import compute_content_hash


class _BatchChunkResult(FileOperationResult):
    """Internal batch chunk write result (includes per-chunk results list)."""

    results: list[FileOperationResult] = []  # noqa: RUF012
    succeeded: int = 0
    failed: int = 0


if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from grover.models.database.chunk import FileChunkModelBase


class DefaultChunkProvider:
    """Stateless helpers for file chunk record CRUD.

    Receives the concrete chunk model at construction so callers can
    use custom SQLModel subclasses.  Never creates, commits, or closes
    sessions — callers are responsible for session lifecycle.
    """

    def __init__(self, chunk_model: type[FileChunkModelBase]) -> None:
        self._chunk_model = chunk_model

    async def replace_file_chunks(
        self,
        session: AsyncSession,
        file_path: str,
        chunks: list[dict],
    ) -> FileOperationResult:
        """Delete all chunks for *file_path*, insert new ones. Returns count inserted."""
        await self.delete_file_chunks(session, file_path)

        model = self._chunk_model
        count = 0
        for chunk_data in chunks:
            record = model(
                file_path=file_path,
                path=chunk_data.get("path", ""),
                line_start=chunk_data.get("line_start", 0),
                line_end=chunk_data.get("line_end", 0),
                content=chunk_data.get("content", ""),
                content_hash=chunk_data.get("content_hash", ""),
            )
            session.add(record)
            count += 1

        await session.flush()
        return FileOperationResult(
            success=True,
            message=f"{count} chunks replaced",
            file=File(path=file_path),
        )

    async def delete_file_chunks(
        self,
        session: AsyncSession,
        file_path: str,
    ) -> FileOperationResult:
        """Delete all chunks for *file_path*. Returns count deleted."""
        model = self._chunk_model
        result = await session.execute(select(model).where(model.file_path == file_path))
        rows = list(result.scalars().all())
        count = len(rows)
        for row in rows:
            await session.delete(row)
        if count > 0:
            await session.flush()
        return FileOperationResult(
            success=True,
            message=f"{count} chunks deleted",
            file=File(path=file_path),
        )

    async def list_file_chunks(
        self,
        session: AsyncSession,
        file_path: str,
    ) -> FileOperationResult:
        """List all chunks for *file_path*, ordered by line_start."""
        model = self._chunk_model
        result = await session.execute(
            select(model).where(model.file_path == file_path).order_by(model.line_start)  # type: ignore[arg-type]
        )
        db_chunks = list(result.scalars().all())
        internal_chunks = [
            FileChunk(
                path=c.path,
                name=c.path.split("#")[-1] if "#" in c.path else c.path,
                content=c.content,
                tokens=0,
                line_start=c.line_start,
                line_end=c.line_end,
            )
            for c in db_chunks
        ]
        return FileOperationResult(
            success=True,
            message=f"{len(db_chunks)} chunks found",
            file=File(path=file_path, chunks=internal_chunks),
        )

    async def write_chunk(
        self,
        session: AsyncSession,
        chunk: FileChunkModelBase,
    ) -> FileOperationResult:
        """Upsert a single chunk. Delegates to write_chunks."""
        batch_result = await self.write_chunks(session, [chunk])
        if batch_result.success and batch_result.results:
            return batch_result.results[0]
        return FileOperationResult(
            success=False, message="Write failed", file=File(path=chunk.path)
        )

    async def write_chunks(
        self,
        session: AsyncSession,
        chunks: list[FileChunkModelBase],
    ) -> _BatchChunkResult:
        """Batch upsert chunks. System manages content_hash and timestamps."""
        model = self._chunk_model
        now = datetime.now(UTC)

        # Batch lookup: one query for all chunk paths
        chunk_paths = [c.path for c in chunks]
        existing_result = await session.execute(
            select(model).where(model.path.in_(chunk_paths))  # type: ignore[arg-type]
        )
        existing_map: dict[str, FileChunkModelBase] = {
            row.path: row for row in existing_result.scalars().all()
        }

        individual_results: list[FileOperationResult] = []
        for chunk in chunks:
            content_hash, _ = compute_content_hash(chunk.content)

            existing = existing_map.get(chunk.path)
            if existing is not None:
                # Update existing record
                existing.content = chunk.content
                existing.content_hash = content_hash
                existing.line_start = chunk.line_start
                existing.line_end = chunk.line_end
                existing.updated_at = now
                individual_results.append(
                    FileOperationResult(
                        success=True,
                        message=f"Updated chunk: {chunk.path}",
                        file=File(path=chunk.path),
                    )
                )
            else:
                # Insert new record using the configured model class
                record = model(
                    file_path=chunk.file_path,
                    path=chunk.path,
                    content=chunk.content,
                    content_hash=content_hash,
                    line_start=chunk.line_start,
                    line_end=chunk.line_end,
                    created_at=now,
                    updated_at=now,
                )
                session.add(record)
                individual_results.append(
                    FileOperationResult(
                        success=True,
                        message=f"Created chunk: {chunk.path}",
                        file=File(path=chunk.path),
                    )
                )

        await session.flush()

        succeeded = sum(1 for r in individual_results if r.success)
        failed = len(individual_results) - succeeded
        return _BatchChunkResult(
            success=failed == 0,
            message=f"{succeeded} succeeded, {failed} failed",
            results=individual_results,
            succeeded=succeeded,
            failed=failed,
        )
