from importlib.metadata import version

from vfs import permissions
from vfs.authority import Authority, Principal
from vfs.base import AsyncVirtualFileSystem, MountInfo
from vfs.exceptions import (
    MountError,
    NotFoundError,
    UnauthenticatedError,
    ValidationError,
    VFSError,
    WriteConflictError,
)
from vfs.models import Entry
from vfs.paths import Path
from vfs.permissions import PermissionMap, PermissionsPayload
from vfs.results import Result, ResultError
from vfs.session import AsyncSession
from vfs.storage.backends.database.backend import DatabaseStorage
from vfs.storage.backends.memory import InMemoryStorage
from vfs.sync import Session, VirtualFileSystem

# The one copy of the number is pyproject.toml; the installed metadata carries it here.
__version__ = version("vfs-py")

__all__ = [
    "AsyncSession",
    "AsyncVirtualFileSystem",
    "Authority",
    "DatabaseStorage",
    "Entry",
    "InMemoryStorage",
    "MountError",
    "MountInfo",
    "NotFoundError",
    "Path",
    "PermissionMap",
    "PermissionsPayload",
    "Principal",
    "Result",
    "ResultError",
    "Session",
    "UnauthenticatedError",
    "VFSError",
    "ValidationError",
    "VirtualFileSystem",
    "WriteConflictError",
    "permissions",
]
