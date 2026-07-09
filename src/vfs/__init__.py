__version__ = "0.0.22"

from vfs import permissions
from vfs.base import VirtualFileSystem
from vfs.exceptions import (
    MountError,
    NotFoundError,
    ValidationError,
    VFSError,
    WriteConflictError,
)
from vfs.paths import Path
from vfs.permissions import PermissionMap
from vfs.results import Result, ResultError

__all__ = [
    "MountError",
    "NotFoundError",
    "Path",
    "PermissionMap",
    "Result",
    "ResultError",
    "VFSError",
    "ValidationError",
    "VirtualFileSystem",
    "WriteConflictError",
    "permissions",
]
