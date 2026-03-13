"""New internal result types — FileSearchSet, FileSearchResult, FileOperationResult.

``FileSearchSet`` carries candidates (files + connections) with set algebra,
iteration, and path transformations — but no success/message semantics.

``FileSearchResult`` inherits from ``FileSearchSet`` and adds ``success``,
``message``, and factory methods, collapsing the 30+ old result subclasses
into a single type.  Operations differentiate via Evidence types on Files,
not separate result classes.
"""

import copy
from collections.abc import Callable, Iterator
from typing import Self

from pydantic import BaseModel

from grover.models.internal.evidence import Evidence
from grover.models.internal.ref import File, FileConnection, Ref


class FileOperationResult(BaseModel):
    """Result of a single-file operation (read, write, delete, etc.)."""

    file: File = File(path="")
    message: str = ""
    success: bool = True


class FileSearchSet(BaseModel):
    """An unordered set of file candidates and connections.

    Supports set algebra (``&``, ``|``, ``-``, ``>>``), iteration over
    file paths, and path transformations (``rebase``, ``remap_paths``).

    Unlike ``FileSearchResult`` this type carries **no** ``success`` /
    ``message`` fields — it is a pure candidate container suitable for
    passing into search methods as input.
    """

    files: list[File] = []
    connections: list[FileConnection] = []

    # -----------------------------------------------------------------
    # Properties and iteration
    # -----------------------------------------------------------------

    @property
    def paths(self) -> tuple[str, ...]:
        """All file paths in this set."""
        return tuple(f.path for f in self.files)

    @property
    def connection_paths(self) -> tuple[str, ...]:
        """All connection ref-format paths (``source[type]target``)."""
        return tuple(f"{c.source.path}[{c.type}]{c.target.path}" for c in self.connections)

    def __len__(self) -> int:
        return len(self.files)

    def __bool__(self) -> bool:
        return len(self.files) > 0

    def __iter__(self) -> Iterator[str]:  # type: ignore[override]
        return iter(f.path for f in self.files)

    def __contains__(self, path: object) -> bool:
        return any(f.path == path for f in self.files)

    # -----------------------------------------------------------------
    # Query helpers
    # -----------------------------------------------------------------

    def explain(self, path: str) -> list[Evidence]:
        """Return the evidence chain for *path*, or ``[]`` if absent."""
        for f in self.files:
            if f.path == path:
                return list(f.evidence)
        return []

    def to_refs(self) -> list[Ref]:
        """Convert file paths to a list of ``Ref`` objects."""
        return [Ref(path=f.path) for f in self.files]

    # -----------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------

    def _as_dict(self) -> dict[str, File]:
        """Convert files to dict keyed by path."""
        return {f.path: f for f in self.files}

    @staticmethod
    def _merge_files(f1: File, f2: File) -> File:
        """Merge two files with the same path, combining evidence."""
        return File(
            path=f1.path,
            is_directory=f1.is_directory or f2.is_directory,
            content=f1.content if f1.content is not None else f2.content,
            embedding=f1.embedding if f1.embedding is not None else f2.embedding,
            tokens=max(f1.tokens, f2.tokens),
            lines=max(f1.lines, f2.lines),
            size_bytes=max(f1.size_bytes, f2.size_bytes),
            mime_type=f1.mime_type or f2.mime_type,
            current_version=max(f1.current_version, f2.current_version),
            chunks=f1.chunks or f2.chunks,
            versions=f1.versions or f2.versions,
            evidence=list(f1.evidence) + list(f2.evidence),
            created_at=f1.created_at or f2.created_at,
            updated_at=f1.updated_at or f2.updated_at,
        )

    def _connections_as_dict(self) -> dict[str, FileConnection]:
        """Convert connections to dict keyed by source[type]target."""
        result: dict[str, FileConnection] = {}
        for c in self.connections:
            key = f"{c.source.path}[{c.type}]{c.target.path}"
            result[key] = c
        return result

    @staticmethod
    def _merge_connections(c1: FileConnection, c2: FileConnection) -> FileConnection:
        """Merge two connections, combining evidence."""
        return FileConnection(
            source=c1.source,
            target=c1.target,
            type=c1.type,
            weight=c1.weight,
            distance=c1.distance,
            evidence=list(c1.evidence) + list(c2.evidence),
            created_at=c1.created_at or c2.created_at,
            updated_at=c1.updated_at or c2.updated_at,
        )

    # -----------------------------------------------------------------
    # Path transformations
    # -----------------------------------------------------------------

    def rebase(self, prefix: str) -> Self:
        """Return a new set with all paths prefixed by *prefix*."""
        result = copy.copy(self)
        result.files = [
            File(
                path=(prefix + f.path if f.path != "/" else prefix),
                is_directory=f.is_directory,
                content=f.content,
                embedding=f.embedding,
                tokens=f.tokens,
                lines=f.lines,
                size_bytes=f.size_bytes,
                mime_type=f.mime_type,
                current_version=f.current_version,
                chunks=f.chunks,
                versions=f.versions,
                evidence=list(f.evidence),
                created_at=f.created_at,
                updated_at=f.updated_at,
            )
            for f in self.files
        ]
        result.connections = [
            FileConnection(
                source=Ref(path=(prefix + c.source.path if c.source.path != "/" else prefix)),
                target=Ref(path=(prefix + c.target.path if c.target.path != "/" else prefix)),
                type=c.type,
                weight=c.weight,
                distance=c.distance,
                evidence=list(c.evidence),
                created_at=c.created_at,
                updated_at=c.updated_at,
            )
            for c in self.connections
        ]
        return result

    def remap_paths(self, fn: Callable[[str], str]) -> Self:
        """Return a new set with all paths transformed by *fn*.

        If two files map to the same new path, their evidence is merged.
        """
        result = copy.copy(self)
        merged: dict[str, File] = {}
        for f in self.files:
            new_path = fn(f.path)
            new_file = File(
                path=new_path,
                is_directory=f.is_directory,
                content=f.content,
                embedding=f.embedding,
                tokens=f.tokens,
                lines=f.lines,
                size_bytes=f.size_bytes,
                mime_type=f.mime_type,
                current_version=f.current_version,
                chunks=f.chunks,
                versions=f.versions,
                evidence=list(f.evidence),
                created_at=f.created_at,
                updated_at=f.updated_at,
            )
            if new_path in merged:
                merged[new_path] = self._merge_files(merged[new_path], new_file)
            else:
                merged[new_path] = new_file
        result.files = list(merged.values())
        result.connections = [
            FileConnection(
                source=Ref(path=fn(c.source.path)),
                target=Ref(path=fn(c.target.path)),
                type=c.type,
                weight=c.weight,
                distance=c.distance,
                evidence=list(c.evidence),
                created_at=c.created_at,
                updated_at=c.updated_at,
            )
            for c in self.connections
        ]
        return result

    # -----------------------------------------------------------------
    # Set algebra
    # -----------------------------------------------------------------

    def __and__(self, other: object) -> Self:
        """Intersection — paths in both, evidence merged."""
        if not isinstance(other, FileSearchSet):
            return NotImplemented
        d1 = self._as_dict()
        d2 = other._as_dict()
        common = set(d1) & set(d2)
        files = [self._merge_files(d1[p], d2[p]) for p in common]
        # Connection algebra
        cd1 = self._connections_as_dict()
        cd2 = other._connections_as_dict()
        conn_common = set(cd1) & set(cd2)
        conns = [self._merge_connections(cd1[p], cd2[p]) for p in conn_common]
        return type(self)(
            files=files,
            connections=conns,
        )

    def __or__(self, other: object) -> Self:
        """Union — paths from either, evidence merged."""
        if not isinstance(other, FileSearchSet):
            return NotImplemented
        d1 = self._as_dict()
        d2 = other._as_dict()
        all_paths = set(d1) | set(d2)
        files: list[File] = []
        for p in all_paths:
            if p in d1 and p in d2:
                files.append(self._merge_files(d1[p], d2[p]))
            elif p in d1:
                files.append(d1[p])
            else:
                files.append(d2[p])
        # Connection algebra
        cd1 = self._connections_as_dict()
        cd2 = other._connections_as_dict()
        conn_all = set(cd1) | set(cd2)
        conns: list[FileConnection] = []
        for cp in conn_all:
            if cp in cd1 and cp in cd2:
                conns.append(self._merge_connections(cd1[cp], cd2[cp]))
            elif cp in cd1:
                conns.append(cd1[cp])
            else:
                conns.append(cd2[cp])
        return type(self)(
            files=files,
            connections=conns,
        )

    def __sub__(self, other: object) -> Self:
        """Difference — paths in LHS not in RHS."""
        if not isinstance(other, FileSearchSet):
            return NotImplemented
        d1 = self._as_dict()
        d2 = other._as_dict()
        diff = set(d1) - set(d2)
        files = [d1[p] for p in diff]
        # Connection algebra
        cd1 = self._connections_as_dict()
        cd2 = other._connections_as_dict()
        conn_diff = set(cd1) - set(cd2)
        conns = [cd1[p] for p in conn_diff]
        return type(self)(
            files=files,
            connections=conns,
        )

    def __rshift__(self, other: object) -> Self:
        """Pipeline — passes LHS paths as candidates to RHS."""
        if not isinstance(other, FileSearchSet):
            return NotImplemented
        d1 = self._as_dict()
        d2 = other._as_dict()
        common = set(d1) & set(d2)
        files = [self._merge_files(d1[p], d2[p]) for p in common]
        # Connection algebra
        cd1 = self._connections_as_dict()
        cd2 = other._connections_as_dict()
        conn_common = set(cd1) & set(cd2)
        conns = [self._merge_connections(cd1[p], cd2[p]) for p in conn_common]
        return type(self)(
            files=files,
            connections=conns,
        )


class FileSearchResult(FileSearchSet):
    """Result of a multi-file query (search, graph, glob, etc.).

    Inherits candidate storage and set algebra from ``FileSearchSet``
    and adds ``success`` / ``message`` fields plus factory methods.
    """

    message: str = ""
    success: bool = True

    def __bool__(self) -> bool:
        return self.success and len(self.files) > 0

    # -----------------------------------------------------------------
    # Set algebra overrides (propagate success/message)
    # -----------------------------------------------------------------

    def __and__(self, other: object) -> Self:
        """Intersection — paths in both, evidence merged."""
        if not isinstance(other, FileSearchSet):
            return NotImplemented
        base = super().__and__(other)
        other_success = other.success if isinstance(other, FileSearchResult) else True
        return type(self)(
            success=self.success and other_success,
            message=f"{len(base.files)} paths",
            files=base.files,
            connections=base.connections,
        )

    def __or__(self, other: object) -> Self:
        """Union — paths from either, evidence merged."""
        if not isinstance(other, FileSearchSet):
            return NotImplemented
        base = super().__or__(other)
        other_success = other.success if isinstance(other, FileSearchResult) else True
        return type(self)(
            success=self.success or other_success,
            message=f"{len(base.files)} paths",
            files=base.files,
            connections=base.connections,
        )

    def __sub__(self, other: object) -> Self:
        """Difference — paths in LHS not in RHS."""
        if not isinstance(other, FileSearchSet):
            return NotImplemented
        base = super().__sub__(other)
        return type(self)(
            success=self.success,
            message=f"{len(base.files)} paths",
            files=base.files,
            connections=base.connections,
        )

    def __rshift__(self, other: object) -> Self:
        """Pipeline — passes LHS paths as candidates to RHS."""
        if not isinstance(other, FileSearchSet):
            return NotImplemented
        base = super().__rshift__(other)
        other_success = other.success if isinstance(other, FileSearchResult) else True
        return type(self)(
            success=self.success and other_success,
            message=f"{len(base.files)} paths",
            files=base.files,
            connections=base.connections,
        )

    # -----------------------------------------------------------------
    # Factories
    # -----------------------------------------------------------------

    @classmethod
    def from_paths(cls, paths: list[str], *, operation: str = "unknown") -> Self:
        """Create a result from a list of paths with default evidence."""
        files = [
            File(
                path=p,
                evidence=[Evidence(operation=operation)],
            )
            for p in paths
        ]
        return cls(
            success=True,
            message=f"{len(paths)} paths",
            files=files,
        )

    @classmethod
    def from_refs(cls, refs: list[Ref], *, operation: str = "unknown") -> Self:
        """Create a result from a list of ``Ref`` objects."""
        files = [
            File(
                path=ref.path,
                evidence=[Evidence(operation=operation)],
            )
            for ref in refs
        ]
        return cls(
            success=True,
            message=f"{len(refs)} refs",
            files=files,
        )
