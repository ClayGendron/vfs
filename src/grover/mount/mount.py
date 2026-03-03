"""Mount — minimal routing dataclass for filesystem composition."""

from __future__ import annotations

from typing import TYPE_CHECKING

from grover.fs.permissions import Permission
from grover.fs.utils import normalize_path

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncSession

    from grover.fs.protocol import StorageBackend


class Mount:
    """A mount point binding a path to a filesystem.

    Each mount has:
    - ``filesystem`` — the storage backend (required)
    - ``session_factory`` — optional async session factory for DB-backed filesystems
    - ``permission`` — read-write or read-only

    Graph, search, and other providers live on the filesystem itself
    (via ``filesystem.graph_provider``, ``filesystem.search_provider``, etc.).
    """

    def __init__(
        self,
        path: str = "",
        filesystem: StorageBackend | None = None,
        *,
        session_factory: Callable[..., AsyncSession] | None = None,
        permission: Permission = Permission.READ_WRITE,
        label: str = "",
        mount_type: str = "vfs",
        hidden: bool = False,
        read_only_paths: set[str] | None = None,
    ) -> None:
        self.path: str = normalize_path(path).rstrip("/")
        self.filesystem: StorageBackend | None = filesystem
        self.session_factory: Callable[..., AsyncSession] | None = session_factory
        self.permission: Permission = permission
        self.label: str = label or self.path.lstrip("/") or "root"
        self.mount_type: str = mount_type
        self.hidden: bool = hidden
        self.read_only_paths: set[str] = read_only_paths if read_only_paths is not None else set()

    def __repr__(self) -> str:
        parts = [f"path={self.path!r}"]
        if self.filesystem is not None:
            parts.append(f"filesystem={type(self.filesystem).__name__}")
        return f"Mount({', '.join(parts)})"
