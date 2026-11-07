from importlib.metadata import version

from vfs import permissions
from vfs.authority import Authority, Principal
from vfs.base import MountInfo, VirtualFileSystem
from vfs.exceptions import (
    MountError,
    NotFoundError,
    UnauthenticatedError,
    ValidationError,
    VFSError,
    WriteConflictError,
)
from vfs.paths import Path
from vfs.permissions import PermissionMap, PermissionsPayload
from vfs.results import Result, ResultError
from vfs.session import Session

# The one copy of the number is pyproject.toml; the installed metadata carries it here.
__version__ = version("vfs-py")

__all__ = [
    "Authority",
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
