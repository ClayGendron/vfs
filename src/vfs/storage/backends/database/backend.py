"""``DatabaseStorage`` — the portable SQL backend (lifecycle skeleton).

Runs on any SQLAlchemy-compatible database: known dialects carry tuned
policy, everything else serves on the generic floor (``dialects.py``).
This slice ships construction, first touch, and close; the read surface
is stubbed to a classified refusal and ``capabilities()`` is
hand-declared empty until the read slice lands — capabilities stay
honest per pass, and the router never routes to an undeclared family.

    storage = DatabaseStorage(url="sqlite+aiosqlite:///vfs.sqlite")     # built
    storage = DatabaseStorage(session_factory=app_sessionmaker)         # borrowed

Built or borrowed, never a bare engine: a backend builds its engine or
borrows sessions — it never holds an engine it didn't make. First touch
happens at the first routed op (or the ``first_touch`` admin verb) on
the caller's loop; ``close()`` disposes the engine iff built and never
touches a borrowed pool.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vfs.results import Result, ResultError, VFSErrorKind
from vfs.storage.backends.database.engine import EngineHost

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from sqlalchemy.ext.asyncio import AsyncSession

    from vfs.models import Observation
    from vfs.ops import Op
    from vfs.paths import Path


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
        # Hand-declared per pass: nothing is landed yet, so nothing is
        # declared — family derivation would over-declare mid-story.
        return frozenset()

    def traits(self) -> Mapping[str, str]:
        declared = {
            "revision_encoding": "counter64",
            "arbitration": self._host.profile.arbitration,
        }
        if self._host.profile.name in ("sqlite", "postgresql", "mssql"):
            declared["durability"] = "full"
        return declared

    # -------------------------------------------------------------------
    # Read family — stubbed until the read slice lands
    # -------------------------------------------------------------------

    async def read(
        self,
        *,
        path: Path | None = None,
        observations: list[Observation] | None = None,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result:
        return await self._stub("read")

    async def stat(
        self,
        *,
        path: Path | None = None,
        observations: list[Observation] | None = None,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result:
        return await self._stub("stat")

    async def ls(
        self,
        *,
        path: Path | None = None,
        observations: list[Observation] | None = None,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result:
        return await self._stub("ls")

    async def tree(
        self,
        *,
        path: Path,
        max_depth: int | None = None,
        columns: frozenset[str] | None = None,
        user_id: str | None = None,
    ) -> Result:
        return await self._stub("tree")

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
