from importlib.metadata import version

from vfs import embedding, permissions, rendering, rerank
from vfs.authority import Authority, Narrowing, Principal, PrincipalKind, Provenance
from vfs.base import AsyncVirtualFileSystem
from vfs.exceptions import (
    MountError,
    NotFoundError,
    UnauthenticatedError,
    ValidationError,
    VFSError,
    WriteConflictError,
)
from vfs.models import ContentHash, Edge, Entry, Match, Observation, RenderStatus, Source
from vfs.mounts import EdgeLocation, Location, Mount, MountPayload
from vfs.ops import CaseMode, GrepOutputMode, Op, Rung, TwoPathOperation
from vfs.paths import ObjectKind, Path
from vfs.pattern_matching import ScopeChannel
from vfs.permissions import PermissionMap, PermissionsPayload
from vfs.results import ErrorKind, Result, ResultError, RetryClass, Severity
from vfs.session import AsyncSession
from vfs.shell import LineResult
from vfs.storage import ResolvedPair, StorageBackend, ranking
from vfs.storage.backends.database.backend import DatabaseStorage
from vfs.storage.backends.memory import InMemoryStorage
from vfs.storage.backends.postgres import PostgresStorage
from vfs.storage.backends.sqlite import SQLiteStorage
from vfs.storage.grants import GrantLevel, Posture
from vfs.storage.replace import EditOperation
from vfs.sync import Session, VirtualFileSystem
from vfs.vid import ABSENT, Vid, VidMint

# The one copy of the number is pyproject.toml; the installed metadata carries it here.
__version__ = version("vfs-py")

__all__ = [
    "ABSENT",
    "AsyncSession",
    "AsyncVirtualFileSystem",
    "Authority",
    "CaseMode",
    "ContentHash",
    "DatabaseStorage",
    "Edge",
    "EdgeLocation",
    "EditOperation",
    "Entry",
    "ErrorKind",
    "GrantLevel",
    "GrepOutputMode",
    "InMemoryStorage",
    "LineResult",
    "Location",
    "Match",
    "Mount",
    "MountError",
    "MountPayload",
    "Narrowing",
    "NotFoundError",
    "ObjectKind",
    "Observation",
    "Op",
    "Path",
    "PermissionMap",
    "PermissionsPayload",
    "PostgresStorage",
    "Posture",
    "Principal",
    "PrincipalKind",
    "Provenance",
    "RenderStatus",
    "ResolvedPair",
    "Result",
    "ResultError",
    "RetryClass",
    "Rung",
    "SQLiteStorage",
    "ScopeChannel",
    "Session",
    "Severity",
    "Source",
    "StorageBackend",
    "TwoPathOperation",
    "UnauthenticatedError",
    "VFSError",
    "ValidationError",
    "Vid",
    "VidMint",
    "VirtualFileSystem",
    "WriteConflictError",
    "embedding",
    "permissions",
    "ranking",
    "rendering",
    "rerank",
]
