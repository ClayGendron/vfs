"""Mount — first-class composition unit for filesystem, graph, and search."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from grover.fs.permissions import Permission
from grover.fs.utils import normalize_path

from .errors import ProtocolConflictError, ProtocolNotAvailableError
from .protocols import DISPATCH_PROTOCOLS

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncSession


class Mount:
    """A mount point composing filesystem, graph, and search components.

    Each mount has:
    - ``filesystem`` — the storage backend (required)
    - ``graph`` — an optional in-memory graph for this mount
    - ``search`` — an optional search engine for this mount

    Protocol dispatch checks all three components at construction time and
    builds a dispatch map.  If two components implement the same dispatch
    protocol, ``ProtocolConflictError`` is raised.

    Backward-compatible with the legacy ``MountConfig`` dataclass — the
    ``mount_path``, ``backend``, and ``has_session_factory`` properties
    are preserved.
    """

    def __init__(
        self,
        path: str = "",
        filesystem: Any | None = None,
        *,
        graph: Any | None = None,
        search: Any | None = None,
        session_factory: Callable[..., AsyncSession] | None = None,
        permission: Permission = Permission.READ_WRITE,
        label: str = "",
        mount_type: str = "vfs",
        hidden: bool = False,
        read_only_paths: set[str] | None = None,
        # Backward compat aliases (MountConfig parameter names)
        mount_path: str | None = None,
        backend: Any | None = None,
    ) -> None:
        # Resolve aliases — backward compat with MountConfig(mount_path=..., backend=...)
        actual_path = mount_path if mount_path is not None else path
        actual_fs = backend if backend is not None else filesystem

        self.path: str = normalize_path(actual_path).rstrip("/")
        self.filesystem: Any = actual_fs
        self.graph: Any | None = graph
        self.search: Any | None = search
        self.session_factory: Callable[..., AsyncSession] | None = session_factory
        self.permission: Permission = permission
        self.label: str = label or self.path.lstrip("/") or "root"
        self.mount_type: str = mount_type
        self.hidden: bool = hidden
        self.read_only_paths: set[str] = read_only_paths if read_only_paths is not None else set()
        self._dispatch_map: dict[type, tuple[str, Any]] = self._build_dispatch_map()

    # ------------------------------------------------------------------
    # Backward compat with MountConfig
    # ------------------------------------------------------------------

    @property
    def mount_path(self) -> str:
        """Alias for ``path`` (MountConfig compat)."""
        return self.path

    @mount_path.setter
    def mount_path(self, value: str) -> None:
        self.path = value

    @property
    def backend(self) -> Any:
        """Alias for ``filesystem`` (MountConfig compat)."""
        return self.filesystem

    @backend.setter
    def backend(self, value: Any) -> None:
        self.filesystem = value

    @property
    def has_session_factory(self) -> bool:
        """True when this mount has a session factory (MountConfig compat)."""
        return self.session_factory is not None

    # ------------------------------------------------------------------
    # Protocol dispatch
    # ------------------------------------------------------------------

    def dispatch(self, protocol: type) -> Any:
        """Return the component implementing *protocol*.

        Raises
        ------
        ProtocolNotAvailableError
            If no component implements the requested protocol.
        """
        entry = self._dispatch_map.get(protocol)
        if entry is None:
            raise ProtocolNotAvailableError(
                f"{protocol.__name__} not available. Check mount configuration at '{self.path}'."
            )
        return entry[1]

    def has_capability(self, protocol: type) -> bool:
        """Check if any component implements *protocol*."""
        return protocol in self._dispatch_map

    def supported_protocols(self) -> set[type]:
        """Return all dispatch protocols available on this mount."""
        return set(self._dispatch_map.keys())

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_dispatch_map(self) -> dict[type, tuple[str, Any]]:
        """Build the protocol → component dispatch map.

        Checks each component against dispatch protocols.  Components that
        expose a ``supported_protocols()`` method (like ``SearchEngine``)
        use that.  Others are checked via ``isinstance()``.
        """
        dmap: dict[type, tuple[str, Any]] = {}
        components: list[tuple[str, Any]] = [
            ("filesystem", self.filesystem),
            ("graph", self.graph),
            ("search", self.search),
        ]
        for name, comp in components:
            if comp is None:
                continue
            # Get protocols this component satisfies
            if hasattr(comp, "supported_protocols") and callable(comp.supported_protocols):
                protos = comp.supported_protocols()
            else:
                protos = [p for p in DISPATCH_PROTOCOLS if isinstance(comp, p)]
            for proto in protos:
                if proto in dmap:
                    existing_name = dmap[proto][0]
                    raise ProtocolConflictError(
                        f"{proto.__name__} implemented by both '{existing_name}' and '{name}'"
                    )
                dmap[proto] = (name, comp)
        return dmap

    def __repr__(self) -> str:
        parts = [f"path={self.path!r}"]
        if self.filesystem is not None:
            parts.append(f"filesystem={type(self.filesystem).__name__}")
        if self.graph is not None:
            parts.append(f"graph={type(self.graph).__name__}")
        if self.search is not None:
            parts.append(f"search={type(self.search).__name__}")
        return f"Mount({', '.join(parts)})"
