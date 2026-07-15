"""``DatabaseStorage`` — the portable SQL backend (read family + glob).

Runs on any SQLAlchemy-compatible database: known dialects carry tuned
policy, everything else serves on the generic floor (``dialects.py``).
The read family and glob are live — point reads with projection
push-down, ``parent_id`` listings, sargable prefix-LIKE subtrees, and
the descent-ladder classification chokepoint (``descent.py`` /
``reads.py``). The mutation family and grep are stubbed to a classified
refusal and ``capabilities()`` is hand-declared per pass — capabilities
stay honest mid-story, and the router never routes to an undeclared
family.

    storage = DatabaseStorage(url="sqlite+aiosqlite:///vfs.sqlite")     # built
    storage = DatabaseStorage(session_factory=app_sessionmaker)         # borrowed

Built or borrowed, never a bare engine: a backend builds its engine or
borrows sessions — it never holds an engine it didn't make. First touch
happens at the first routed op (or the ``first_touch`` admin verb) on
the caller's loop; ``close()`` disposes the engine iff built and never
touches a borrowed pool. Each protocol method runs in one session under
the retry discipline: a retryable outcome restarts the whole method
from its first read, and a driver failure that escapes retry returns a
classified ``Result`` — never a raw exception.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from sqlalchemy.exc import SQLAlchemyError

from vfs.results import Result, ResultError, VFSErrorKind
from vfs.storage.backends.database.descent import ROOT
from vfs.storage.backends.database.engine import EngineHost
from vfs.storage.backends.database.reads import glob_rows, ls_rows, read_rows, stat_rows, targets_of, tree_rows

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping

    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.models import Entry, Observation
    from vfs.ops import CaseMode, GrepOutputMode, Op
    from vfs.paths import Path
    from vfs.storage import ResolvedPair
    from vfs.storage.replace import EditOperation

# Hand-declared per pass: family derivation would over-declare while
# grep and the mutation verbs are still classified stubs.
_LANDED_OPS: Final[frozenset[Op]] = frozenset({"read", "stat", "ls", "tree", "glob"})


class DatabaseStorage:
    """One mount's portable database backend over SQLAlchemy Core."""

    def __init__(
        self,
        *,
        url: str | None = None,
        session_factory: Callable[[], AsyncSession] | None = None,
        table_name: str = "vfs",
        schema: str | None = None,
        name: str = "database",
        description: str | None = None,
    ) -> None:
        self._host = EngineHost(url=url, session_factory=session_factory, table_name=table_name, schema=schema)
        self.name = name
        # Construction stays dialect-free: a borrowed host knows its
        # dialect only at first use, so the default names the tables.
        self.description = description or f"Database storage ({table_name})"

    @property
    def mount_identity(self) -> str | None:
        """The durable mount identity, known after first touch."""
        return self._host.mount_identity

    def capabilities(self) -> frozenset[Op]:
        return _LANDED_OPS

    def traits(self) -> Mapping[str, str]:
        declared = {
            "revision_encoding": "counter64",
            "arbitration": self._host.profile.arbitration,
        }
        if self._host.profile.name in ("sqlite", "postgresql", "mssql"):
            declared["durability"] = "full"
        return declared

    # -------------------------------------------------------------------
    # Read family
    # -------------------------------------------------------------------

    async def read(
        self,
        *,
        path: Path | None = None,
        observations: list[Observation] | None = None,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result:
        targets = targets_of(path, observations)
        return await self._execute("read", lambda session: read_rows(session, self._host.tables, targets, columns))

    async def stat(
        self,
        *,
        path: Path | None = None,
        observations: list[Observation] | None = None,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result:
        targets = targets_of(path, observations)
        return await self._execute("stat", lambda session: stat_rows(session, self._host.tables, targets, columns))

    async def ls(
        self,
        *,
        path: Path | None = None,
        observations: list[Observation] | None = None,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result:
        targets = targets_of(path, observations, default=ROOT)
        return await self._execute("ls", lambda session: ls_rows(session, self._host.tables, targets, columns))

    async def tree(
        self,
        *,
        path: Path,
        max_depth: int | None = None,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result:
        if max_depth is not None and max_depth < 1:
            return Result(
                ops=("tree",),
                errors=[ResultError(kind=VFSErrorKind.invalid, message=f"max_depth must be >= 1, got {max_depth}")],
            )
        return await self._execute(
            "tree", lambda session: tree_rows(session, self._host.tables, path, max_depth, columns)
        )

    # -------------------------------------------------------------------
    # Pattern search — glob live, grep stubbed until its pass lands
    # -------------------------------------------------------------------

    async def glob(
        self,
        *,
        pattern: str,
        paths: tuple[Path, ...] = (),
        observations: list[Observation] | None = None,
        ext: tuple[str, ...] = (),
        max_count: int | None = None,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result:
        scope = paths or tuple(o.path for o in observations or [])
        return await self._execute(
            "glob",
            lambda session: glob_rows(
                session,
                self._host.tables,
                pattern=pattern,
                scope=scope,
                ext=ext,
                max_count=max_count,
                columns=columns,
            ),
        )

    async def grep(
        self,
        *,
        pattern: str,
        paths: tuple[Path, ...] = (),
        observations: list[Observation] | None = None,
        ext: tuple[str, ...] = (),
        ext_not: tuple[str, ...] = (),
        globs: tuple[str, ...] = (),
        globs_not: tuple[str, ...] = (),
        case_mode: CaseMode = "sensitive",
        fixed_strings: bool = False,
        word_regexp: bool = False,
        invert_match: bool = False,
        before_context: int = 0,
        after_context: int = 0,
        output_mode: GrepOutputMode = "lines",
        max_count: int | None = None,
        allow_scan: bool = False,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result:
        return await self._stub("grep")

    # -------------------------------------------------------------------
    # Mutation family — stubbed until its slices land
    # -------------------------------------------------------------------

    async def write(
        self,
        *,
        path: Path | None = None,
        content: str | None = None,
        entries: list[Entry] | None = None,
        overwrite: bool = True,
        parents: bool = False,
        user_id: str | None = None,
    ) -> Result:
        return await self._stub("write")

    async def edit(
        self,
        *,
        edits: list[EditOperation],
        path: Path | None = None,
        observations: list[Observation] | None = None,
        user_id: str | None = None,
    ) -> Result:
        return await self._stub("edit")

    async def delete(
        self,
        *,
        path: Path | None = None,
        observations: list[Observation] | None = None,
        permanent: bool = False,
        cascade: bool = True,
        user_id: str | None = None,
    ) -> Result:
        return await self._stub("delete")

    async def mkdir(
        self,
        *,
        path: Path,
        parents: bool = False,
        exist_ok: bool = False,
        user_id: str | None = None,
    ) -> Result:
        return await self._stub("mkdir")

    async def move(
        self,
        *,
        operations: list[ResolvedPair],
        overwrite: bool = True,
        user_id: str | None = None,
    ) -> Result:
        return await self._stub("move")

    async def copy(
        self,
        *,
        operations: list[ResolvedPair],
        overwrite: bool = True,
        user_id: str | None = None,
    ) -> Result:
        return await self._stub("copy")

    async def mkedge(
        self,
        *,
        source: Path,
        target: Path,
        edge_type: str,
        user_id: str | None = None,
    ) -> Result:
        return await self._stub("mkedge")

    # -------------------------------------------------------------------
    # Admin verbs — beside close(), outside the routed surface
    # -------------------------------------------------------------------

    async def first_touch(self) -> Result:
        """Provision-or-verify now instead of at the first routed op."""
        refusal = await self._host.ensure_ready()
        if refusal is not None:
            return Result(ops=("first_touch",), errors=[refusal])
        return Result(ops=("first_touch",))

    async def close(self) -> None:
        await self._host.close()

    # -------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------

    async def _execute(self, op: str, fn: Callable[[AsyncSession], Awaitable[Result]]) -> Result:
        """One op = one session under retry; failures come back classified."""
        refusal = await self._host.ensure_ready()
        if refusal is not None:
            return Result(ops=(op,), errors=[refusal])

        async def attempt() -> Result:
            async with self._host.session_factory() as session:
                return await fn(session)

        try:
            return await self._host.with_retry(attempt)
        except (SQLAlchemyError, OSError) as exc:
            # SQLAlchemyError, not just DBAPIError: pool exhaustion
            # (TimeoutError) is an operating condition, never a raise.
            return Result(ops=(op,), errors=[self._host.classify_failure(exc, context=op)])

    async def _stub(self, op: str) -> Result:
        refusal = await self._host.ensure_ready()
        if refusal is not None:
            return Result(ops=(op,), errors=[refusal])
        return Result(
            ops=(op,),
            errors=[
                ResultError(
                    kind=VFSErrorKind.unsupported,
                    message=f"{op} is not yet implemented on DatabaseStorage",
                )
            ],
        )
