"""Chunk provider protocol."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from grover.models.database.chunk import FileChunkModelBase
    from grover.models.internal.results import FileOperationResult


@runtime_checkable
class ChunkProvider(Protocol):
    """Chunk storage — file chunk CRUD."""

    async def replace_file_chunks(
        self, session: Any, file_path: str, chunks: list[dict]
    ) -> FileOperationResult: ...

    async def delete_file_chunks(self, session: Any, file_path: str) -> FileOperationResult: ...

    async def list_file_chunks(self, session: Any, file_path: str) -> FileOperationResult: ...

    async def write_chunk(
        self,
        session: Any,
        chunk: FileChunkModelBase,
    ) -> FileOperationResult: ...

    async def write_chunks(
        self,
        session: Any,
        chunks: list[FileChunkModelBase],
    ) -> FileOperationResult: ...
