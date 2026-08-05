"""``DatabaseStorage`` — the portable SQL backend (reads, glob, mutation core).

Runs on any SQLAlchemy-compatible database: known dialects carry tuned
policy, everything else serves on the generic floor (``dialects.py``).
The read family and glob are live — point reads with projection
push-down, ``parent_id`` listings, glob's batched pattern fan, and
the descent-ladder classification chokepoint (``descent.py`` /
``reads.py``) — as are the mutation core (write/edit/mkdir batches
planned and executed as one transaction each, ``writes.py``) and the
serialized topology verbs delete/restore/move/copy (``topology.py``).
``mkedge`` and grep are stubbed to a classified refusal and
``capabilities()`` is hand-declared per pass — capabilities stay honest
mid-story, and the router never routes to an undeclared family.

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

from typing import TYPE_CHECKING, Final, Literal

from sqlalchemy.exc import SQLAlchemyError

from vfs.results import Result, ResultError, VFSErrorKind
from vfs.storage.backends.database.descent import ROOT
from vfs.storage.backends.database.dialects import (
    PROFILES,
    StaleSnapshot,
    op_execution_options,
    topology_execution_options,
)
from vfs.storage.backends.database.engine import EngineHost
from vfs.storage.backends.database.reads import glob_rows, ls_rows, read_rows, stat_rows, tree_rows
from vfs.storage.backends.database.topology import delete_rows, restore_rows, sweep_rows, transfer_rows
from vfs.storage.backends.database.writes import edit_rows, mkdir_rows, write_rows
from vfs.storage.protocol import targets_of

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping

    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.models import Entry, Observation
    from vfs.ops import CaseMode, GrepOutputMode, Op
    from vfs.paths import Path
    from vfs.storage import ResolvedPair
    from vfs.storage.replace import EditOperation

# Hand-declared per pass: family derivation would over-declare while
# grep and mkedge are still classified stubs.
_LANDED_OPS: Final[frozenset[Op]] = frozenset(
    {"read", "stat", "ls", "tree", "glob", "write", "edit", "mkdir", "delete", "restore", "sweep", "move", "copy"}
)


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
        trash_days: int = 90,
    ) -> None:
        if trash_days < 0:
            msg = f"trash_days must be non-negative, got {trash_days}"
            raise ValueError(msg)
        self._host = EngineHost(url=url, session_factory=session_factory, table_name=table_name, schema=schema)
        self._trash_days = trash_days
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
            "version_encoding": "per_entry64",
            "arbitration": self._host.profile.arbitration,
        }
        # Tuned engines are the measured ones; only they may claim full
        # durability — unknown dialects resolve to GENERIC-renamed names.
        if self._host.profile.name in PROFILES:
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
        return await self._execute(
            "read",
            lambda session: read_rows(session, self._host.tables, self._host.membership_budget, targets, columns),
        )

    async def stat(
        self,
        *,
        path: Path | None = None,
        observations: list[Observation] | None = None,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result:
        targets = targets_of(path, observations)
        return await self._execute(
            "stat",
            lambda session: stat_rows(session, self._host.tables, self._host.membership_budget, targets, columns),
        )

    async def ls(
        self,
        *,
        path: Path | None = None,
        observations: list[Observation] | None = None,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result:
        targets = targets_of(path, observations, default=ROOT)
        return await self._execute(
            "ls", lambda session: ls_rows(session, self._host.tables, self._host.membership_budget, targets, columns)
        )

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
            "tree",
            lambda session: tree_rows(
                session, self._host.tables, self._host.membership_budget, path, max_depth, columns
            ),
        )

    # -------------------------------------------------------------------
    # Pattern search — glob live, grep stubbed until its pass lands
    # -------------------------------------------------------------------

    async def glob(
        self,
        *,
        patterns: tuple[str, ...],
        observations: list[Observation] | None = None,
        ext: tuple[str, ...] = (),
        max_count: int | None = None,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result:
        roots = tuple(observation.path for observation in observations or [])
        return await self._execute(
            "glob",
            lambda session: glob_rows(
                session,
                self._host.tables,
                self._host.profile,
                self._host.parameter_budget,
                self._host.membership_budget,
                patterns=patterns,
                roots=roots,
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
    # Mutation core — write / edit / mkdir and the topology verbs
    # -------------------------------------------------------------------

    async def write(
        self,
        *,
        entries: list[Entry],
        overwrite: bool = True,
        parents: bool = False,
        user_id: str | None = None,
    ) -> Result:
        return await self._execute_write(
            "write",
            lambda session: write_rows(
                session,
                self._host.tables,
                self._host.profile,
                self._host.parameter_budget,
                self._host.membership_budget,
                entries=entries,
                overwrite=overwrite,
                parents=parents,
                user_id=user_id,
            ),
        )

    async def edit(
        self,
        *,
        edits: list[EditOperation],
        path: Path | None = None,
        observations: list[Observation] | None = None,
        user_id: str | None = None,
    ) -> Result:
        targets = targets_of(path, observations)
        return await self._execute_write(
            "edit",
            lambda session: edit_rows(
                session,
                self._host.tables,
                self._host.profile,
                self._host.parameter_budget,
                self._host.membership_budget,
                edits=edits,
                targets=targets,
                user_id=user_id,
            ),
        )

    async def delete(
        self,
        *,
        path: Path | None = None,
        observations: list[Observation] | None = None,
        cascade: bool = True,
        user_id: str | None = None,
    ) -> Result:
        targets = targets_of(path, observations)
        return await self._execute_topology(
            "delete",
            lambda session: delete_rows(
                session,
                self._host.tables,
                self._host.profile,
                self._host.membership_budget,
                targets=targets,
                cascade=cascade,
                user_id=user_id,
                lock_key=self._host.topology_key,
            ),
        )

    async def restore(
        self,
        *,
        path: Path | None = None,
        observations: list[Observation] | None = None,
        overwrite: bool = False,
        user_id: str | None = None,
    ) -> Result:
        targets = targets_of(path, observations)
        return await self._execute_topology(
            "restore",
            lambda session: restore_rows(
                session,
                self._host.tables,
                self._host.profile,
                self._host.membership_budget,
                targets=targets,
                overwrite=overwrite,
                user_id=user_id,
                lock_key=self._host.topology_key,
            ),
        )

    async def sweep(
        self,
        *,
        path: Path,
        user_id: str | None = None,
    ) -> Result:
        return await self._execute_topology(
            "sweep",
            lambda session: sweep_rows(
                session,
                self._host.tables,
                self._host.profile,
                self._host.membership_budget,
                path=path,
                trash_days=self._trash_days,
                user_id=user_id,
                lock_key=self._host.topology_key,
            ),
        )

    async def mkdir(
        self,
        *,
        path: Path,
        parents: bool = False,
        exist_ok: bool = False,
        user_id: str | None = None,
    ) -> Result:
        return await self._execute_write(
            "mkdir",
            lambda session: mkdir_rows(
                session,
                self._host.tables,
                self._host.profile,
                self._host.parameter_budget,
                self._host.membership_budget,
                path=path,
                parents=parents,
                exist_ok=exist_ok,
                user_id=user_id,
            ),
        )

    async def move(
        self,
        *,
        operations: list[ResolvedPair],
        overwrite: bool = True,
        user_id: str | None = None,
    ) -> Result:
        return await self._execute_transfer("move", operations, overwrite=overwrite, user_id=user_id)

    async def copy(
        self,
        *,
        operations: list[ResolvedPair],
        overwrite: bool = True,
        user_id: str | None = None,
    ) -> Result:
        return await self._execute_transfer("copy", operations, overwrite=overwrite, user_id=user_id)

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
        """One op = one session under retry; failures come back classified.

        A declared op-isolation pin is stamped on the connection up front
        so every chunked statement observes one committed snapshot.
        """
        refusal = await self._host.ensure_ready()
        if refusal is not None:
            return Result(ops=(op,), errors=[refusal])

        async def attempt() -> Result:
            async with self._host.session_factory() as session:
                if options := op_execution_options(self._host.profile, writer=False):
                    await session.connection(execution_options=options)
                return await fn(session)

        try:
            return await self._host.with_retry(attempt)
        except StaleSnapshot as exc:
            message = f"{op} kept losing to concurrent changes: {exc.context}"
            return Result(ops=(op,), errors=[ResultError(kind=VFSErrorKind.conflict, message=message, retryable=True)])
        except (SQLAlchemyError, OSError) as exc:
            # SQLAlchemyError, not just DBAPIError: pool exhaustion
            # (TimeoutError) is an operating condition, never a raise.
            return Result(ops=(op,), errors=[self._host.classify_failure(exc, context=op)])

    async def _execute_write(self, op: str, fn: Callable[[AsyncSession], Awaitable[Result]]) -> Result:
        """One batch = one writer transaction, committed iff the plan succeeded.

        The connection carries ``vfs_writer`` so SQLite opens the
        transaction ``BEGIN IMMEDIATE`` — the write lock is held from the
        plan's first read.
        """
        return await self._mutate(op, fn, op_execution_options(self._host.profile, writer=True))

    async def _execute_transfer(
        self, op: Literal["move", "copy"], operations: list[ResolvedPair], *, overwrite: bool, user_id: str | None
    ) -> Result:
        return await self._execute_topology(
            op,
            lambda session: transfer_rows(
                session,
                self._host.tables,
                self._host.profile,
                self._host.parameter_budget,
                self._host.membership_budget,
                op=op,
                operations=operations,
                overwrite=overwrite,
                user_id=user_id,
                lock_key=self._host.topology_key,
            ),
        )

    async def _execute_topology(self, op: str, fn: Callable[[AsyncSession], Awaitable[Result]]) -> Result:
        """One batch = one serialized transaction; the point is its first statement.

        Topology options trade the op snapshot for the serialization
        point: the writer marker plus the declared topology-isolation
        pin, never ``op_isolation``.
        """
        return await self._mutate(op, fn, topology_execution_options(self._host.profile))

    async def _mutate(
        self, op: str, fn: Callable[[AsyncSession], Awaitable[Result]], options: dict[str, str | bool]
    ) -> Result:
        """The shared mutation runner: commit iff the batch succeeded.

        A retryable outcome discards the session and restarts the whole
        method from its first read; a failed batch returns classified
        errors and the session rolls back on exit.
        """
        refusal = await self._host.ensure_ready()
        if refusal is not None:
            return Result(ops=(op,), errors=[refusal])

        async def attempt() -> Result:
            async with self._host.session_factory() as session:
                await session.connection(execution_options=options)
                result = await fn(session)
                if result.success:
                    await session.commit()
                return result

        try:
            return await self._host.with_retry(attempt)
        except StaleSnapshot as exc:
            # Guards kept proving the snapshot stale through every redrive:
            # an honest transient outcome, never a torn commit.
            message = f"{op} kept losing to concurrent changes: {exc.context}"
            return Result(ops=(op,), errors=[ResultError(kind=VFSErrorKind.conflict, message=message, retryable=True)])
        except (SQLAlchemyError, OSError) as exc:
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
