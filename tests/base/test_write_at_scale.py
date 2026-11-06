"""A 10,000-entry write through the kernel costs the statements a formula names.

The formula's only size-dependent terms are page counts under the host's
own budgets, so the test says, in a count, that the write path is bounded
by a budget and never by the batch.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import event

from vfs import AsyncVirtualFileSystem, DatabaseStorage, Entry
from vfs.paths import Path
from vfs.storage.backends.database.dialects import rows_per_statement

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path as FsPath

    from vfs.results import Result
    from vfs.storage.backends.database.engine import EngineHost

DIRECTORIES = 100
FILES = 10_000
# A budget under which every family pages more than once at a tenth of the batch.
SHRUNKEN_BUDGET = 480

# Every statement the warm write path issues, named by the words it opens with, in the path's own order.
FAMILIES: tuple[tuple[str, str], ...] = (
    ("begin", "BEGIN IMMEDIATE"),
    ("grants", "SELECT vfs_grants."),
    ("principal revision", "SELECT max(vfs_principal_revisions.revision)"),
    ("relabels", "SELECT vfs_relabels."),
    ("target probe", "SELECT vfs_entries.path, vfs_entries.kind, vfs_entries.deleted_at"),
    ("committed fetch", "SELECT vfs_entries.entry_id, vfs_entries.path"),
    ("savepoint", "SAVEPOINT "),
    ("entries", "INSERT INTO vfs_entries "),
    ("release", "RELEASE SAVEPOINT "),
    ("segments", "INSERT INTO vfs_segments "),
    ("edges", "INSERT INTO vfs_edges "),
    ("content", "INSERT INTO vfs_content "),
    ("parent bump", "UPDATE vfs_entries SET version="),
)
INSERT_COLUMNS = re.compile(r"INSERT INTO \w+ \(([^)]*)\)")


def _file_paths(directories: int, files: int) -> list[str]:
    return [f"/d{i % directories}/f{i}.txt" for i in range(files)]


def _entries(directories: int, files: int) -> Iterable[Entry]:
    return (Entry(path=Path(p), content=f"row {p}") for p in _file_paths(directories, files))


async def _count(
    storage: DatabaseStorage, entries: Iterable[Entry], *, budget: int | None = None
) -> tuple[Result, Counter[str], dict[str, tuple[str, ...]]]:
    """Write *entries* with parents through a warm kernel: the result, the per-family counts, the insert columns."""
    counts: Counter[str] = Counter()
    columns: dict[str, tuple[str, ...]] = {}
    armed = False

    @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
    def record(conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool) -> None:
        if not armed:
            return
        text = " ".join(statement.split())
        family = next((name for name, prefix in FAMILIES if text.startswith(prefix)), f"unnamed: {text[:60]}")
        counts[family] += 1
        if (listed := INSERT_COLUMNS.match(text)) is not None:
            columns[family] = tuple(name.strip() for name in listed.group(1).split(","))

    fs = AsyncVirtualFileSystem(storage=storage)
    try:
        assert (await fs.write(path="/warm.txt", content="warm")).success is True
        if budget is not None:
            # The host reads both of its budgets off this one dialect datum.
            storage._host.engine.sync_engine.dialect.insertmanyvalues_max_parameters = budget
        armed = True
        result = await fs.write(entries=entries, parents=True)
    finally:
        await fs.close()
    return result, counts, columns


def _expected(host: EngineHost, columns: dict[str, tuple[str, ...]], directories: int, files: int) -> Counter[str]:
    """The fixed reads, then pages under the parameter budget and chunks under the membership budget."""
    parameter_budget, membership_budget = host.parameter_budget, host.membership_budget

    def per(family: str) -> int:
        return rows_per_statement(parameter_budget, [dict.fromkeys(columns[family])])

    rows = directories + files
    paths = rows + 1  # the written paths with their ancestors: the root rides along
    pages = math.ceil(directories / per("entries")) + math.ceil(files / per("entries"))
    # Segment rows are each path's ancestor names: one per file, none for a directory under the root.
    segment_rows = files
    return Counter(
        {
            "begin": 1,
            "grants": 2 * math.ceil(paths / membership_budget),
            "principal revision": 1,
            "relabels": 1,
            "target probe": math.ceil(paths / membership_budget),
            "committed fetch": math.ceil(paths / membership_budget),
            "savepoint": pages,
            "entries": pages,
            "release": pages,
            "segments": math.ceil(segment_rows / per("segments")),
            "edges": math.ceil(rows / per("edges")),
            "content": math.ceil(files / per("content")),
            "parent bump": math.ceil(1 / membership_budget),
        }
    )


@pytest.mark.slow
async def test_a_ten_thousand_entry_write_issues_the_statements_the_formula_names(tmp_path: FsPath) -> None:
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{tmp_path}/batch.sqlite")
    result, counts, columns = await _count(storage, list(_entries(DIRECTORIES, FILES)))
    assert result.success is True
    assert counts == _expected(storage._host, columns, DIRECTORIES, FILES)
    assert counts["entries"] > 1  # the chunk arithmetic is exercised, not a trivial one page


@pytest.mark.slow
async def test_a_generator_of_ten_thousand_entries_costs_what_the_list_costs(tmp_path: FsPath) -> None:
    """The router walks the batch once, so a generator meets the same formula the list does."""
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{tmp_path}/generated.sqlite")
    result, counts, columns = await _count(storage, _entries(DIRECTORIES, FILES))
    assert result.success is True
    assert counts == _expected(storage._host, columns, DIRECTORIES, FILES)
    observed = {str(o.path) for o in result.observations}
    assert set(_file_paths(DIRECTORIES, FILES)) <= observed
    assert len(observed) == FILES  # the minted directories are staged by the parent walk, never observed


async def test_the_formula_holds_under_a_shrunken_budget(tmp_path: FsPath) -> None:
    """SQLite's budgets hide two terms at 10,000; a small budget makes every family page more than once."""
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{tmp_path}/shrunken.sqlite")
    directories, files = DIRECTORIES // 10, FILES // 10
    result, counts, columns = await _count(storage, list(_entries(directories, files)), budget=SHRUNKEN_BUDGET)
    assert result.success is True
    expected = _expected(storage._host, columns, directories, files)
    assert counts == expected
    assert (
        min(
            expected[name]
            for name, _ in FAMILIES
            if name not in ("begin", "principal revision", "relabels", "parent bump")
        )
        > 1
    )
