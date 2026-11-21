"""The listing cursor at the storage: native keyset pages of ``ls``, ``tree`` and ``glob``, on every engine leg.

``CursorContract`` mixes into each database conformance class. Every case drains a listing a page at a
time, straight on the storage, and checks it against the same listing asked whole: the same rows, in
path order, none repeated and none lost. The work a page costs is pinned by counts: statements issued,
rows fetched, and the index the engine's plan reads, with the rows it visited where the engine reports
them. Nothing is timed.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, NamedTuple

import pytest
from sqlalchemy import event

from tests.support.statements import is_statistics_statement
from vfs.authority import Authority, Principal
from vfs.models import Entry, Observation
from vfs.models.rows import SCHEMA_FORMAT_VERSION
from vfs.paths import Path
from vfs.pattern_matching import ScopeChannel
from vfs.results import ErrorKind, Result
from vfs.storage.backends.database import reads as reads_module

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterator

    from vfs.storage.backends.database import DatabaseStorage

SYSTEM = Authority.system()
ADA = Authority.of(Principal("ada"))

# The partial indexes that hold a live page's read work to the rows it returns.
LIVE_CHILDREN = "ix_vfs_entries_live_children"
LIVE_PATHS = "ix_vfs_entries_live_path"


class Page(NamedTuple):
    """One page and the statements it issued, statistics left out."""

    result: Result
    statements: list[tuple[str, Any]]


def files(root: str, count: int) -> list[Entry]:
    return [Entry(path=Path(f"{root}/f{index:05d}.txt"), content="x") for index in range(count)]


def ok(result: Result) -> Result:
    assert result.success is True, result.error_message
    return result


@contextmanager
def recorded(storage: DatabaseStorage) -> Iterator[list[tuple[str, Any]]]:
    """Every statement the storage sends while the block runs, with its parameters."""
    seen: list[tuple[str, Any]] = []

    def record(conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool) -> None:
        if not is_statistics_statement(statement):
            seen.append((statement, parameters))

    engine = storage._host.engine.sync_engine
    event.listen(engine, "before_cursor_execute", record)
    try:
        yield seen
    finally:
        event.remove(engine, "before_cursor_execute", record)


async def drain(
    storage: DatabaseStorage, call: Callable[..., Awaitable[Result]], limit: int, **kwargs: Any
) -> tuple[list[str], list[Page]]:
    """Every row of a storage listing read ``limit`` at a time, and every page with its statements."""
    pages: list[Page] = []
    after: Path | None = None
    while True:
        with recorded(storage) as seen:
            result = ok(await call(after=after, limit=limit, **kwargs))
        pages.append(Page(result, seen))
        assert len(result) <= limit
        if result.next_after is None:
            return [str(path) for page in pages for path in page.result.paths], pages
        assert after is None or result.next_after > after
        after = result.next_after
        assert len(pages) < 2_000


def paged_selects(page: Page) -> list[tuple[str, Any]]:
    """The statements of a page that read a page of entries: the selects that carry a ``LIMIT``."""
    return [(sql, parameters) for sql, parameters in page.statements if "LIMIT" in sql.upper()]


async def plan_of(storage: DatabaseStorage, sql: str, parameters: Any) -> tuple[set[str], int | None]:
    """The indexes the engine's plan reads for one captured statement, and the rows it visited where it says.

    SQLite reports no per-statement count in the bundled build, so its answer is the plan alone. Postgres
    gathers the table's statistics, as autovacuum keeps them on a live server, runs the statement under
    ``EXPLAIN (ANALYZE, FORMAT JSON)``, and adds each scan's rows and the rows its filter removed.
    """
    engine = storage._host.engine
    async with engine.connect() as conn:
        if engine.dialect.name == "sqlite":
            rows = (await conn.exec_driver_sql("EXPLAIN QUERY PLAN " + sql, parameters)).all()
            return {word for row in rows for word in str(row[-1]).split() if word.startswith("ix_")}, None
        # A live server carries autovacuum's statistics; a table just written does not yet.
        await conn.exec_driver_sql(f"ANALYZE {storage._host.tables.entry.fullname}")
        raw = (await conn.exec_driver_sql("EXPLAIN (ANALYZE, FORMAT JSON) " + sql, parameters)).scalar_one()
    plan = (raw if isinstance(raw, list) else json.loads(raw))[0]["Plan"]
    nodes = _scans(plan)
    visited = sum(node["Actual Rows"] + node.get("Rows Removed by Filter", 0) for node in nodes)
    return {node["Index Name"] for node in nodes if "Index Name" in node}, visited


def _scans(node: dict[str, Any]) -> list[dict[str, Any]]:
    found = [node] if "Scan" in node["Node Type"] else []
    for child in node.get("Plans", []):
        found += _scans(child)
    return found


class CursorContract:
    """Native keyset pages, on the storage fixture of the conformance class it mixes into."""

    # ------------------------------------------------------------------
    # What the storage declares
    # ------------------------------------------------------------------

    def test_the_storage_declares_that_it_pages_by_key(self, storage: DatabaseStorage) -> None:
        assert storage.traits()["listing_cursor"] == "keyset"

    async def test_the_schema_holds_the_live_listing_indexes(self, storage: DatabaseStorage) -> None:
        ok(await storage.first_touch())
        names = {index.name for index in storage._host.tables.entry.indexes}
        assert {LIVE_CHILDREN, LIVE_PATHS} <= names
        assert SCHEMA_FORMAT_VERSION == 28

    # ------------------------------------------------------------------
    # ls
    # ------------------------------------------------------------------

    async def test_ls_drains_in_path_order_with_one_children_select_a_page(self, storage: DatabaseStorage) -> None:
        ok(await storage.write(entries=files("/d", 47), parents=True, authority=SYSTEM))
        whole = list(ok(await storage.ls(path=Path("/d"), authority=SYSTEM)).paths)
        rows, pages = await drain(storage, storage.ls, 10, path=Path("/d"), authority=SYSTEM)
        assert rows == whole == sorted(whole)
        assert len(pages) == 5
        assert [page.result.next_after is not None for page in pages] == [True] * 4 + [False]
        assert all(len(paged_selects(page)) == 1 for page in pages)
        counts = {len(page.statements) for page in pages}
        assert len(counts) == 1, counts

    async def test_a_page_costs_the_statements_of_a_whole_call(self, storage: DatabaseStorage) -> None:
        ok(await storage.write(entries=files("/d", 60), parents=True, authority=SYSTEM))
        ok(await storage.set_posture(path=Path("/"), posture="none", authority=SYSTEM))
        ok(await storage.grant(path=Path("/d"), principal="ada", level="read", authority=SYSTEM))
        sqlite = storage._host.engine.dialect.name == "sqlite"
        expected = {("system", "ls"): 3, ("system", "tree"): 3, ("system", "glob"): 2, ("ada", "ls"): 5}
        for name, who in (("system", SYSTEM), ("ada", ADA)):
            for op, kwargs in (("ls", {"path": Path("/d")}), ("tree", {"path": Path("/d")})):
                await self._counted(storage, op, who, kwargs)
            for op, kwargs in (
                ("ls", {"path": Path("/d")}),
                ("tree", {"path": Path("/d")}),
                ("glob", {"patterns": ("/d/*.txt",)}),
            ):
                whole = await self._counted(storage, op, who, kwargs)
                page = await self._counted(storage, op, who, {**kwargs, "after": Path("/d/f00009.txt"), "limit": 10})
                # A named caller's tree page asks once whether a directory hides at the key's own prefix.
                extra = 1 if (name, op) == ("ada", "tree") else 0
                assert page == whole + extra, (name, op, whole, page)
                if sqlite and (name, op) in expected:
                    assert page == expected[name, op], (name, op, page)

    @staticmethod
    async def _counted(storage: DatabaseStorage, op: str, who: Authority, kwargs: dict[str, Any]) -> int:
        """The statements one call issues, statistics left out."""
        with recorded(storage) as seen:
            ok(await getattr(storage, op)(authority=who, **kwargs))
        return len(seen)

    async def test_a_listing_of_exactly_n_pages_ends_on_its_last_page(self, storage: DatabaseStorage) -> None:
        ok(await storage.write(entries=files("/d", 30), parents=True, authority=SYSTEM))
        _rows, pages = await drain(storage, storage.ls, 10, path=Path("/d"), authority=SYSTEM)
        assert len(pages) == 3

    @pytest.mark.parametrize("deleted", ["the first nine tenths", "nine of every ten"])
    async def test_an_ls_page_reads_around_its_tombstones(self, storage: DatabaseStorage, deleted: str) -> None:
        ok(await storage.write(entries=files("/d", 1_000), parents=True, authority=SYSTEM))
        gone = range(900) if deleted == "the first nine tenths" else [i for i in range(1_000) if i % 10]
        ok(await storage.delete(observations=[Observation(path=Path(f"/d/f{i:05d}.txt")) for i in gone]))
        rows, pages = await drain(storage, storage.ls, 10, path=Path("/d"), authority=SYSTEM)
        assert len(rows) == len(set(rows)) == 100
        assert len(pages) == 10
        for page in pages:
            [(sql, parameters)] = paged_selects(page)
            indexes, visited = await plan_of(storage, sql, parameters)
            assert LIVE_CHILDREN in indexes, indexes
            assert visited is None or visited <= 11

    async def test_a_live_page_keeps_its_index_on_statistics_that_predate_a_mass_delete(
        self, storage: DatabaseStorage
    ) -> None:
        ok(await storage.write(entries=files("/d", 1_000), parents=True, authority=SYSTEM))
        await storage._host.settle_statistics()
        ok(await storage.delete(observations=[Observation(path=Path(f"/d/f{i:05d}.txt")) for i in range(900)]))
        await storage._host.settle_statistics()
        for call, index in ((storage.ls, LIVE_CHILDREN), (storage.tree, LIVE_PATHS)):
            _rows, pages = await drain(storage, call, 10, path=Path("/d"), authority=SYSTEM)
            assert len(pages) == 10
            [(sql, parameters)] = paged_selects(pages[0])
            indexes, visited = await plan_of(storage, sql, parameters)
            assert index in indexes, indexes
            assert visited is None or visited <= 11

    async def test_the_trash_head_and_the_meta_root_page_too(self, storage: DatabaseStorage) -> None:
        ok(await storage.write(entries=files("/t", 9), parents=True, authority=SYSTEM))
        ok(await storage.write(entries=files("/.vfs/notes", 3), parents=True, authority=SYSTEM))
        ok(await storage.delete(observations=[Observation(path=Path(f"/t/f{i:05d}.txt")) for i in range(0, 9, 2)]))
        for target in ("/.vfs/trash", "/.vfs"):
            whole = list(ok(await storage.ls(path=Path(target), authority=SYSTEM)).paths)
            for limit in (1, 2, 50):
                rows, _pages = await drain(storage, storage.ls, limit, path=Path(target), authority=SYSTEM)
                assert rows == sorted(whole), (target, limit)

    async def test_a_named_caller_pages_only_what_it_may_name(self, storage: DatabaseStorage) -> None:
        ok(await storage.write(entries=files("/d", 600), parents=True, authority=SYSTEM))
        ok(await storage.write(entries=files("/d/sub", 3), parents=True, authority=SYSTEM))
        ok(await storage.set_posture(path=Path("/"), posture="none", authority=SYSTEM))
        for index in range(0, 600, 60):
            ok(await storage.grant(path=Path(f"/d/f{index:05d}.txt"), principal="ada", level="read", authority=SYSTEM))
        ok(await storage.grant(path=Path("/d/sub/f00001.txt"), principal="ada", level="read", authority=SYSTEM))
        whole = list(ok(await storage.ls(path=Path("/d"), authority=ADA)).paths)
        assert len(whole) == 11 and "/d/sub" in whole
        rows, pages = await drain(storage, storage.ls, 2, path=Path("/d"), authority=ADA)
        assert rows == sorted(whole)
        assert all(page.result.next_after is None or page.result.next_after in page.result.paths for page in pages)
        assert all(len(paged_selects(page)) <= 7 for page in pages)

    async def test_rivals_between_pages(self, storage: DatabaseStorage) -> None:
        ok(await storage.write(entries=files("/d", 20), parents=True, authority=SYSTEM))
        first = ok(await storage.ls(path=Path("/d"), limit=10, authority=SYSTEM))
        assert first.next_after == "/d/f00009.txt"
        rivals = [Entry(path=Path("/d/f00004a.txt"), content="x"), Entry(path=Path("/d/f00014a.txt"), content="x")]
        ok(await storage.write(entries=rivals, authority=SYSTEM))
        ok(await storage.delete(path=Path("/d/f00003.txt"), authority=SYSTEM))
        rest = ok(await storage.ls(path=Path("/d"), after=first.next_after, authority=SYSTEM))
        assert "/d/f00004a.txt" not in rest.paths
        assert "/d/f00014a.txt" in rest.paths
        seen = [*first.paths, *rest.paths]
        assert len(seen) == len(set(seen)) == 21

    # ------------------------------------------------------------------
    # tree
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("limit", [1, 7, 100])
    async def test_tree_drains_whole(self, storage: DatabaseStorage, limit: int) -> None:
        ok(await storage.write(entries=[*files("/r/a", 9), *files("/r/a/b", 5), *files("/r", 4)], parents=True))
        whole = list(ok(await storage.tree(path=Path("/r"), authority=SYSTEM)).paths)
        rows, pages = await drain(storage, storage.tree, limit, path=Path("/r"), authority=SYSTEM)
        assert rows == whole == sorted(whole)
        assert all(len(paged_selects(page)) == 1 for page in pages)

    async def test_a_tree_page_reads_around_its_tombstones(self, storage: DatabaseStorage) -> None:
        ok(await storage.write(entries=files("/s", 500), parents=True, authority=SYSTEM))
        gone = [Observation(path=Path(f"/s/f{i:05d}.txt")) for i in range(500) if i % 10]
        ok(await storage.delete(observations=gone))
        rows, pages = await drain(storage, storage.tree, 10, path=Path("/s"), authority=SYSTEM)
        assert len(rows) == 50
        for page in pages:
            [(sql, parameters)] = paged_selects(page)
            indexes, visited = await plan_of(storage, sql, parameters)
            assert LIVE_PATHS in indexes, indexes
            assert visited is None or visited <= 11

    async def test_tree_pages_under_max_depth_and_in_the_trash_view(self, storage: DatabaseStorage) -> None:
        ok(await storage.write(entries=[*files("/r/a", 6), *files("/r/a/b", 5), *files("/r", 4)], parents=True))
        ok(await storage.delete(path=Path("/r/a/b"), authority=SYSTEM))
        cases: list[dict[str, Any]] = [{"path": Path("/r"), "max_depth": 2}, {"path": Path("/.vfs/trash")}]
        for kwargs in cases:
            whole = list(ok(await storage.tree(authority=SYSTEM, **kwargs)).paths)
            assert whole
            rows, _pages = await drain(storage, storage.tree, 3, authority=SYSTEM, **kwargs)
            assert rows == sorted(whole), kwargs

    async def test_a_named_caller_pages_a_tree_with_its_road(self, storage: DatabaseStorage) -> None:
        tree = ["/w/a/x.txt", "/w/a.txt", "/w/a-b/y.txt", "/w/b/c/d/z.txt", "/w/b/q.txt", "/w/e.txt", "/w/f/g.txt"]
        ok(await storage.write(entries=[Entry(path=Path(p), content="x") for p in tree], parents=True))
        ok(await storage.set_posture(path=Path("/"), posture="none", authority=SYSTEM))
        for path in ("/w/a/x.txt", "/w/a.txt", "/w/b/c/d/z.txt", "/w/f/g.txt"):
            ok(await storage.grant(path=Path(path), principal="ada", level="read", authority=SYSTEM))
        whole = list(ok(await storage.tree(path=Path("/w"), authority=ADA)).paths)
        assert "/w/b/c" in whole and "/w/a" in whole
        for limit in (1, 2, 3, 10):
            rows, pages = await drain(storage, storage.tree, limit, path=Path("/w"), authority=ADA)
            assert rows == sorted(whole), limit
            assert all(p.result.next_after is None or p.result.next_after in p.result.paths for p in pages)

    @pytest.mark.parametrize("limit", [1, 2, 3])
    async def test_a_road_whose_first_child_sorts_after_the_key_shows_on_its_own_page(
        self, storage: DatabaseStorage, limit: int
    ) -> None:
        names = ["/w/a.1", "/w/a.2", "/w/a.3", "/w/a.4", "/w/a/x.txt", "/w/b.txt"]
        ok(await storage.write(entries=[Entry(path=Path(p), content="x") for p in names], parents=True))
        ok(await storage.set_posture(path=Path("/"), posture="none", authority=SYSTEM))
        for path in names:
            ok(await storage.grant(path=Path(path), principal="ada", level="read", authority=SYSTEM))
        whole = list(ok(await storage.tree(path=Path("/w"), authority=ADA)).paths)
        assert whole[:2] == ["/w/a", "/w/a.1"]
        rows, _pages = await drain(storage, storage.tree, limit, path=Path("/w"), authority=ADA)
        assert rows == whole

    @pytest.mark.parametrize("limit", [1, 2])
    async def test_a_paged_tree_shows_no_road_the_whole_tree_does_not(
        self, storage: DatabaseStorage, limit: int
    ) -> None:
        # A grant on a file since deleted puts its directory on the view's road; no row the tree returns lies beneath.
        names = ["/r/a/x.txt", "/r/a-b/y.txt"]
        ok(await storage.write(entries=[Entry(path=Path(p), content="x") for p in names], parents=True))
        ok(await storage.set_posture(path=Path("/"), posture="none", authority=SYSTEM))
        for path in names:
            ok(await storage.grant(path=Path(path), principal="ada", level="read", authority=SYSTEM))
        ok(await storage.delete(path=Path("/r/a/x.txt"), authority=SYSTEM))
        whole = list(ok(await storage.tree(path=Path("/r"), authority=ADA)).paths)
        assert whole == ["/r/a-b", "/r/a-b/y.txt"]
        rows, _pages = await drain(storage, storage.tree, limit, path=Path("/r"), authority=ADA)
        assert rows == whole

    # ------------------------------------------------------------------
    # glob
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("patterns", [("/g/*.txt",), ("**/*.txt",), ("f0001*",), ("/g/**", "/h/*.md"), ("{a,b}*",)])
    async def test_glob_drains_whole(self, storage: DatabaseStorage, patterns: tuple[str, ...]) -> None:
        ok(await storage.write(entries=[*files("/g", 25), *files("/g/sub", 6), *files("/h", 3)], parents=True))
        ok(await storage.write(entries=[Entry(path=Path(f"/h/{n}.md"), content="x") for n in "abc"]))
        whole = list(ok(await storage.glob(patterns=patterns, authority=SYSTEM)).paths)
        assert whole
        rows, pages = await drain(storage, storage.glob, 4, patterns=patterns, authority=SYSTEM)
        assert rows == sorted(whole), patterns
        assert all(page.result.next_after is None or page.result.next_after in page.result.paths for page in pages)

    async def test_a_glob_page_is_a_bounded_statement_per_chunk(self, storage: DatabaseStorage) -> None:
        ok(await storage.write(entries=files("/g", 60), parents=True, authority=SYSTEM))
        _rows, pages = await drain(storage, storage.glob, 20, patterns=("/g/*.txt",), authority=SYSTEM)
        assert len(pages) == 3
        assert all(len(paged_selects(page)) == 1 for page in pages)
        for page in pages:
            [(_sql, parameters)] = paged_selects(page)
            assert 21 in (parameters.values() if isinstance(parameters, dict) else parameters)

    async def test_a_glob_under_a_scope_and_a_view_pages_whole(self, storage: DatabaseStorage) -> None:
        ok(await storage.write(entries=[*files("/g", 30), *files("/g/sub", 6)], parents=True, authority=SYSTEM))
        ok(await storage.set_posture(path=Path("/"), posture="none", authority=SYSTEM))
        for index in range(0, 30, 4):
            ok(await storage.grant(path=Path(f"/g/f{index:05d}.txt"), principal="ada", level="read", authority=SYSTEM))
        ok(await storage.grant(path=Path("/g/sub/f00002.txt"), principal="ada", level="list", authority=SYSTEM))
        for who in (SYSTEM, ADA):
            whole = list(ok(await storage.glob(patterns=("**",), authority=who)).paths)
            rows, _pages = await drain(storage, storage.glob, 3, patterns=("**",), authority=who)
            assert rows == sorted(whole)

    async def test_a_glob_page_that_reaches_its_wall_stops_and_keeps_its_key(
        self, storage: DatabaseStorage, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ok(await storage.write(entries=files("/g", 60), parents=True, authority=SYSTEM))
        real = reads_module.judge_rows

        async def short(*args: Any, **kwargs: Any) -> Any:
            verdicts, _completed = await real(*args, **kwargs)
            return verdicts, False

        monkeypatch.setattr(reads_module, "judge_rows", short)
        with recorded(storage) as seen:
            page = ok(await storage.glob(patterns=("/g/*.txt",), limit=10, authority=SYSTEM))
        assert page.paths == tuple(f"/g/f{index:05d}.txt" for index in range(10))
        assert page.next_after == "/g/f00009.txt"
        assert [error.kind for error in page.warnings] == [ErrorKind.truncated]
        assert len([sql for sql, _parameters in seen if "LIMIT" in sql.upper()]) == 1

    async def test_a_wall_in_one_fan_statement_loses_no_row_of_another(
        self, storage: DatabaseStorage, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        names = [f"/z/f{i:03d}.txt" for i in range(200)] + [f"/a/f{i:03d}.txt" for i in range(100)]
        ok(await storage.write(entries=[Entry(path=Path(p), content="x") for p in names], parents=True))
        # Two fan statements: the /z arms first, the /a arms second.
        monkeypatch.setattr(reads_module, "arm_budget", lambda *args, **kwargs: 200)
        whole = list(ok(await storage.glob(patterns=tuple(names), authority=SYSTEM)).paths)
        real = reads_module.judge_rows
        calls = [0]

        async def first_incomplete(*args: Any, **kwargs: Any) -> Any:
            verdicts, completed = await real(*args, **kwargs)
            calls[0] += 1
            return verdicts, completed and calls[0] != 1

        monkeypatch.setattr(reads_module, "judge_rows", first_incomplete)
        rows, pages = await drain(storage, storage.glob, 10, patterns=tuple(names), authority=SYSTEM)
        assert rows == sorted(whole)
        assert sum(len(page.result.warnings) for page in pages) == 1

    async def test_a_page_whose_wall_judges_nothing_ends_the_listing_loudly(
        self, storage: DatabaseStorage, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ok(await storage.write(entries=files("/g", 30), parents=True, authority=SYSTEM))
        first = ok(await storage.glob(patterns=("/g/*.txt",), limit=10, authority=SYSTEM))

        async def nothing(_executor: Any, _gates: Any, rows: Any, **_kwargs: Any) -> Any:
            return [None] * len(rows), False

        monkeypatch.setattr(reads_module, "judge_rows", nothing)
        for after in (None, first.next_after):
            page = ok(await storage.glob(patterns=("/g/*.txt",), after=after, limit=10, authority=SYSTEM))
            assert (page.paths, page.next_after) == ((), None)
            assert [error.kind for error in page.warnings] == [ErrorKind.truncated]

    async def test_glob_refuses_a_page_beside_max_count(self, storage: DatabaseStorage) -> None:
        refused = await storage.glob(patterns=("*",), max_count=3, limit=3, authority=SYSTEM)
        assert [error.kind for error in refused.errors] == [ErrorKind.invalid]

    async def test_a_glob_page_over_scope_root_clauses_drains_whole(
        self, storage: DatabaseStorage, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ok(await storage.write(entries=[*files("/g", 20), *files("/h", 5)], parents=True, authority=SYSTEM))
        monkeypatch.setattr(reads_module, "COMPOSED_PREFILTER_LIMIT", 0)
        scope = ScopeChannel(roots=(Path("/g"), Path("/h")), arms=("*.txt",))
        whole = list(ok(await storage.glob(patterns=(), scope=scope, authority=SYSTEM)).paths)
        assert len(whole) == 25
        rows, pages = await drain(storage, storage.glob, 4, patterns=(), scope=scope, authority=SYSTEM)
        assert rows == sorted(whole)
        assert all(len(paged_selects(page)) == 1 for page in pages)

    @pytest.mark.slow
    async def test_a_page_of_ten_thousand_patterns_builds_each_chunk_once_a_fetch(
        self, storage: DatabaseStorage, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ok(await storage.write(entries=files("/g", 300), parents=True, authority=SYSTEM))
        patterns = tuple(f"/g/f{index:05d}.txt" for index in range(10_000))
        real = reads_module.pattern_arm
        built: list[object] = []

        def counted(*args: Any, **kwargs: Any) -> Any:
            built.append(kwargs.get("after"))
            return real(*args, **kwargs)

        monkeypatch.setattr(reads_module, "pattern_arm", counted)
        first = ok(await storage.glob(patterns=patterns, limit=100, authority=SYSTEM))
        assert len(first) == 100 and first.next_after is not None
        built.clear()
        with recorded(storage) as seen:
            second = ok(await storage.glob(patterns=patterns, after=first.next_after, limit=100, authority=SYSTEM))
        assert second.paths == tuple(f"/g/f{index:05d}.txt" for index in range(100, 200))
        selects = [parameters for sql, parameters in seen if "LIMIT" in sql.upper()]
        budget = storage._host.parameter_budget
        assert all(len(parameters) <= budget for parameters in selects)
        # One build of every arm with no key, and one of each fetched statement's own arms from the key.
        assert built.count(None) == len(patterns)
        assert len(built) - len(patterns) <= len(patterns)

    # ------------------------------------------------------------------
    # A page the storage refuses before it reads a row
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        ("op", "kwargs"),
        [
            ("ls", {"path": Path("/d"), "limit": 0}),
            ("ls", {"observations": [Observation(path=Path("/d")), Observation(path=Path("/e"))], "limit": 2}),
            ("ls", {"path": Path("/d"), "after": Path("/e/x")}),
            ("ls", {"path": Path("/d"), "after": Path("/d/sub/x")}),
            ("ls", {"path": Path("/d"), "after": Path("/d")}),
            ("tree", {"path": Path("/d"), "after": Path("/d")}),
            ("tree", {"path": Path("/d"), "after": Path("/dx/y")}),
            ("tree", {"path": Path("/d"), "max_depth": 0, "limit": 2}),
            ("glob", {"patterns": ("*",), "limit": 0}),
        ],
    )
    async def test_a_bad_page_is_refused_before_any_read(
        self, storage: DatabaseStorage, op: str, kwargs: dict[str, Any]
    ) -> None:
        ok(await storage.write(entries=files("/d", 3), parents=True, authority=SYSTEM))
        with recorded(storage) as seen:
            refused = await getattr(storage, op)(authority=SYSTEM, **kwargs)
        assert [error.kind for error in refused.errors] == [ErrorKind.invalid], refused.errors
        assert seen == []

    async def test_the_trash_head_takes_any_key(self, storage: DatabaseStorage) -> None:
        ok(await storage.write(entries=files("/t", 4), parents=True, authority=SYSTEM))
        ok(await storage.delete(path=Path("/t/f00001.txt"), authority=SYSTEM))
        ok(await storage.delete(path=Path("/t/f00003.txt"), authority=SYSTEM))
        page = ok(await storage.ls(path=Path("/.vfs/trash"), after=Path("/t/f00002.txt"), authority=SYSTEM))
        assert page.paths == ("/t/f00003.txt",)

    async def test_an_ls_page_of_a_file_is_the_file_and_of_a_missing_path_is_not_found(
        self, storage: DatabaseStorage
    ) -> None:
        ok(await storage.write(entries=files("/d", 2), parents=True, authority=SYSTEM))
        file = ok(await storage.ls(path=Path("/d/f00000.txt"), limit=5, authority=SYSTEM))
        assert file.paths == ("/d/f00000.txt",)
        assert file.next_after is None
        missing = await storage.ls(path=Path("/nowhere"), limit=5, authority=SYSTEM)
        assert [error.kind for error in missing.errors] == [ErrorKind.not_found]

    # ------------------------------------------------------------------
    # Ten thousand children
    # ------------------------------------------------------------------

    @pytest.mark.slow
    async def test_ten_thousand_children_drain_in_ten_pages_on_every_verb(self, storage: DatabaseStorage) -> None:
        ok(await storage.write(entries=files("/big", 10_000), parents=True, authority=SYSTEM))
        expected = [f"/big/f{index:05d}.txt" for index in range(10_000)]
        for call, kwargs in (
            (storage.ls, {"path": Path("/big")}),
            (storage.tree, {"path": Path("/big")}),
            (storage.glob, {"patterns": ("/big/*.txt",)}),
        ):
            rows, pages = await drain(storage, call, 1_000, authority=SYSTEM, **kwargs)
            assert rows == expected
            assert len(pages) == 10
            assert all(len(paged_selects(page)) == 1 for page in pages)
            assert len({len(page.statements) for page in pages}) == 1
