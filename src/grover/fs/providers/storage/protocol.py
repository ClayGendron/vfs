"""Storage provider protocols."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from grover.types.operations import FileInfoResult, ReconcileResult
    from grover.types.search import GlobResult, GrepResult, ListDirResult, TreeResult


@runtime_checkable
class StorageProvider(Protocol):
    """Core storage operations — NO session parameters.

    Handles content I/O, file operations, and metadata for an external
    storage backend (e.g. local disk). When ``storage_provider`` is ``None``
    on ``DatabaseFileSystem``, all content lives in the DB content column.
    """

    async def read_content(self, path: str) -> str | None: ...

    async def write_content(self, path: str, content: str) -> None: ...

    async def delete_content(self, path: str) -> None: ...

    async def move_content(self, src: str, dest: str) -> None: ...

    async def copy_content(self, src: str, dest: str) -> None: ...

    async def exists(self, path: str) -> bool: ...

    async def mkdir(self, path: str, parents: bool = True) -> None: ...

    async def get_info(self, path: str) -> FileInfoResult: ...


@runtime_checkable
class SupportsStorageQueries(Protocol):
    """Disk-level glob/grep/tree/list_dir."""

    async def storage_glob(self, pattern: str, path: str = "/") -> GlobResult: ...

    async def storage_grep(self, pattern: str, path: str = "/", **kwargs: Any) -> GrepResult: ...

    async def storage_tree(self, path: str = "/", max_depth: int | None = None) -> TreeResult: ...

    async def storage_list_dir(self, path: str) -> ListDirResult: ...


@runtime_checkable
class SupportsStorageReconcile(Protocol):
    """Sync external storage with DB."""

    async def reconcile(self, **kwargs: Any) -> ReconcileResult: ...
