"""Hydration routes through ``fs.read`` — the single shared surface.

Phase 8.4 acceptance: when the user asks for a column via ``--output``
that the producing stage did not populate, the executor backfills via
exactly one ``fs.read(paths=..., columns=...)`` call.  Never a private
backend shortcut; never ``select(self._model)``; never N calls.

``to_str`` stays pure — rendering never triggers I/O.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from vfs.base import VirtualFileSystem
from vfs.query.ast import GlobCommand, QueryPlan
from vfs.query.executor import execute_query
from vfs.results import Candidate, VFSResult


def _fs() -> MagicMock:
    """Build a minimal spy over ``VirtualFileSystem``.

    Every method used by ``execute_query`` is an ``AsyncMock``.  Stages
    the test is not exercising still need to be callable — they return
    an empty ``VFSResult`` by default to keep the pipeline alive.
    """
    fs = MagicMock(spec=VirtualFileSystem)
    fs.read = AsyncMock(return_value=VFSResult(function="read", candidates=[]))
    fs.glob = AsyncMock(return_value=VFSResult(function="glob", candidates=[]))
    fs.stat = AsyncMock(return_value=VFSResult(function="stat", candidates=[]))
    fs._merge_results = lambda results: results[0] if results else VFSResult()
    return fs


def _plan(node, projection: tuple[str, ...] | None) -> QueryPlan:
    return QueryPlan(ast=node, methods=(), projection=projection)


# ===========================================================================
# Single-call hydration when a projected field is null for all entries
# ===========================================================================


class TestHydrationRoutesThroughRead:
    async def test_single_call_with_correct_columns(self):
        fs = _fs()
        # glob returns entries missing updated_at across the board
        fs.glob.return_value = VFSResult(
            function="glob",
            candidates=[
                Candidate(path="/a.md", kind="file"),
                Candidate(path="/b.md", kind="file"),
                Candidate(path="/c.md", kind="file"),
            ],
        )
        # read (the hydration target) fills in updated_at
        fs.read.return_value = VFSResult(
            function="read",
            candidates=[
                Candidate(path="/a.md", updated_at=datetime(2026, 1, 1, tzinfo=UTC)),
                Candidate(path="/b.md", updated_at=datetime(2026, 1, 2, tzinfo=UTC)),
                Candidate(path="/c.md", updated_at=datetime(2026, 1, 3, tzinfo=UTC)),
            ],
        )

        result = await execute_query(
            fs,
            _plan(GlobCommand(pattern="**/*.md"), projection=("path", "updated_at")),
        )

        fs.read.assert_called_once()
        kwargs = fs.read.call_args.kwargs
        assert "columns" in kwargs
        assert "updated_at" in kwargs["columns"]
        # Hydration should NOT pull the heavy columns unasked-for.
        assert "embedding" not in kwargs["columns"]
        assert "content" not in kwargs["columns"]
        # And it merged by path — every original entry should now carry updated_at.
        updated = {e.path: e.updated_at for e in result.candidates}
        assert updated == {
            "/a.md": datetime(2026, 1, 1, tzinfo=UTC),
            "/b.md": datetime(2026, 1, 2, tzinfo=UTC),
            "/c.md": datetime(2026, 1, 3, tzinfo=UTC),
        }

    async def test_one_call_for_many_paths(self):
        """500 paths in → exactly one hydration call, not 500."""
        fs = _fs()
        paths = [f"/docs/file_{i}.md" for i in range(500)]
        fs.glob.return_value = VFSResult(
            function="glob",
            candidates=[Candidate(path=p, kind="file") for p in paths],
        )
        fs.read.return_value = VFSResult(
            function="read",
            candidates=[Candidate(path=p, updated_at=datetime(2026, 1, 1, tzinfo=UTC)) for p in paths],
        )

        await execute_query(
            fs,
            _plan(GlobCommand(pattern="**/*.md"), projection=("path", "updated_at")),
        )
        assert fs.read.call_count == 1


# ===========================================================================
# Skip hydration when it's unnecessary
# ===========================================================================


class TestHydrationIsNoopWhenNotNeeded:
    async def test_noop_when_projection_is_none(self):
        fs = _fs()
        fs.glob.return_value = VFSResult(
            function="glob",
            candidates=[Candidate(path="/a.md", kind="file")],
        )
        await execute_query(fs, _plan(GlobCommand(pattern="**/*.md"), projection=None))
        fs.read.assert_not_called()

    async def test_noop_when_field_already_populated(self):
        fs = _fs()
        fs.glob.return_value = VFSResult(
            function="glob",
            candidates=[Candidate(path="/a.md", kind="file", updated_at=datetime(2026, 1, 1, tzinfo=UTC))],
        )
        await execute_query(
            fs,
            _plan(GlobCommand(pattern="**/*.md"), projection=("path", "updated_at")),
        )
        fs.read.assert_not_called()

    async def test_noop_when_result_is_empty(self):
        fs = _fs()
        fs.glob.return_value = VFSResult(function="glob", candidates=[])
        await execute_query(
            fs,
            _plan(GlobCommand(pattern="**/*.md"), projection=("path", "out_degree")),
        )
        fs.read.assert_not_called()

    async def test_noop_when_only_computed_fields_requested(self):
        """``score`` / ``lines`` aren't backed by model columns — no SQL can fill them."""
        fs = _fs()
        fs.glob.return_value = VFSResult(
            function="glob",
            candidates=[Candidate(path="/a.md", kind="file")],
        )
        await execute_query(
            fs,
            _plan(GlobCommand(pattern="**/*.md"), projection=("path", "score")),
        )
        fs.read.assert_not_called()


# ===========================================================================
# to_str stays pure — no I/O from rendering
# ===========================================================================


class TestToStrIsPure:
    def test_to_str_does_not_hydrate(self):
        """``VFSResult.to_str`` must never issue SQL or call ``fs.read``.

        We simulate a caller that missed a column: the render should
        stay pure and append a note rather than attempt a backfill.
        Hydration is the executor's job, not the result's.
        """
        result = VFSResult(
            function="glob",
            candidates=[Candidate(path="/a.md")],
        )
        # No fs available at render time — if to_str tried to hydrate, it
        # would need one.  Asking for a column the entry lacks must just
        # render an empty cell in the markdown table and append a note,
        # not trigger a backfill.
        rendered = result.to_str(projection=("path", "out_degree"))
        assert "/a.md" in rendered
        # Null out_degree appears as an empty-padded cell between the pipes.
        data_row = next(line for line in rendered.splitlines() if "/a.md" in line)
        cells = [c.strip() for c in data_row.strip("|").split("|")]
        assert cells == ["/a.md", ""]
        assert rendered.endswith("NOTE: out_degree not populated for any candidates.")


# ===========================================================================
# Hydration inherits read's narrowing discipline
# ===========================================================================


class TestHydrationNarrows:
    async def test_hydration_columns_are_minimal(self):
        fs = _fs()
        fs.glob.return_value = VFSResult(
            function="glob",
            candidates=[Candidate(path="/a.md", kind="file")],
        )
        fs.read.return_value = VFSResult(
            function="read",
            candidates=[Candidate(path="/a.md", updated_at=datetime(2026, 1, 1, tzinfo=UTC))],
        )
        await execute_query(
            fs,
            _plan(GlobCommand(pattern="**/*.md"), projection=("path", "updated_at")),
        )
        kwargs = fs.read.call_args.kwargs
        cols = kwargs["columns"]
        # Only the missing-for-all column's backing model column should be passed.
        # `path` is already populated → not in the missing set.
        assert "updated_at" in cols
        assert "embedding" not in cols


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
