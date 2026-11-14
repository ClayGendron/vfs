"""The plan store's reader, pinned on plans captured from live engines.

The scan-tier plan pin judges every access with
:func:`~tests.support.plan_store.entry_access` and
:func:`~tests.support.plan_store.bounded_access`. These rows feed the reader
the plans the engines printed (``tests/fixtures/plan_store``), so the pin's
own judge is proven to name a walk a walk and a seek a seek without a server.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Boolean, Column, Index, MetaData, String, Table

from tests.support.plan_store import DIRTY_INDEXES, bounded_access, dirty_indexes, entry_access

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "plan_store"

# Each fixture file's engine, as the plan store's readers key it, by its name's first part.
_ENGINES = {"postgresql", "mariadb", "mssql", "oracle", "sqlite"}

# The old world's Oracle half-caller plans: a range of the everyone index, and a full walk of the path index.
_ORACLE_HALF = ("oracle-old-half-everyone.txt", "oracle-old-half-fullscan.txt")

# The refused plans whose refused access is a range seek, not a scan: the bound refuses them for the range.
_RANGES = frozenset({"oracle-old-half-everyone.txt", "mariadb-old-partial.txt"})

# The forced walks, one per hiding place the reader must see through, and the constructed shapes it cannot parse.
_WALKS = (
    "mssql-walk-wholeindex.xml",
    "oracle-walk-skipscan.txt",
    "postgresql-walk-nonleading.txt",
    "postgresql-walk-pending-nonleading.txt",
    "mariadb-walk-unknown.txt",
    "mssql-walk-partitioned.xml",
    "oracle-walk-unnamed.txt",
    "postgresql-walk-unknown.txt",
    "sqlite-walk-scantable.txt",
)


def test_the_scan_reader_sees_the_walks_of_the_old_world() -> None:
    """Guards: the reader taking a full scan or an ordered index walk for a seek, so the scan-tier plan pin passes
    a statement that reads the whole table or a whole index; or taking a seek for a walk, so a correct plan fails.

    The old world's captured plans each hold an access the bound refuses
    (Oracle's half-caller plans among them, a range of the everyone index
    and a full walk of the path index), and every one but the two ranges
    (that one, and MariaDB's merge of ranges over the path and owner
    indexes) is read as a scan. So are three walks a seek's operator can hide, each
    forced on a small store: a Postgres index condition on a later column
    alone, a SQL Server seek whose ranges cover the whole index, and an
    Oracle index skip scan; and so is every constructed shape the reader
    does not parse, beside a seek it does: what it cannot read is a scan,
    never dropped. Every access of the corrected world's captured
    plans, SQL Server's equality seek of the owner index included, is one
    the bound admits.
    """
    refused = [*_plans("old"), *_plans("walk")]
    corrected = _plans("corrected")
    assert {engine for engine, _name, _plan in refused} == _ENGINES
    assert {engine for engine, _name, _plan in corrected} == _ENGINES
    assert {name for _engine, name, _plan in _plans("walk")} == set(_WALKS)
    assert set(_ORACLE_HALF) <= {name for _engine, name, _plan in refused}
    for engine, name, plan in refused:
        accesses = entry_access(engine, plan)
        assert accesses, name
        assert [access for access in accesses if not bounded_access(access)], (name, accesses)
        if name not in _RANGES:
            assert [access for access in accesses if not access.seeks], (name, accesses)
    for engine, name, plan in corrected:
        accesses = entry_access(engine, plan)
        assert accesses, name
        assert all(bounded_access(access) for access in accesses), (name, accesses)


def test_every_index_led_by_encoded_is_a_dirty_index_and_no_other() -> None:
    """Guards: the bound naming one dirty index by hand, so the refresh's pending index (or a third led by
    ``encoded``) is refused where its seek is the one the bound exists to allow; or admitting an index that
    holds ``encoded`` past its first column, whose seek reads whatever its leading column holds."""
    assert {"ix_vfs_entries_encoded_kind", "ix_vfs_entries_index_pending"} == DIRTY_INDEXES
    for name in ("postgresql-corrected-pending.txt", "mariadb-corrected-pending.txt"):
        [access] = entry_access(name.partition("-")[0], (FIXTURES / name).read_text())
        assert (access.index, access.seeks, bounded_access(access)) == ("ix_vfs_entries_index_pending", True, True)
    [walk] = entry_access("postgresql", (FIXTURES / "postgresql-walk-pending-nonleading.txt").read_text())
    assert (walk.index, walk.seeks, bounded_access(walk)) == ("ix_vfs_entries_index_pending", False, False)
    table = Table(
        "t",
        MetaData(),
        Column("encoded", Boolean),
        Column("kind", String(8)),
        Index("ix_led", "encoded", "kind"),
        Index("ix_later", "kind", "encoded"),
    )
    assert dirty_indexes(table) == {"ix_led"}


def _plans(world: str) -> list[tuple[str, str, str]]:
    """``(engine, file name, plan text)`` for every captured plan of *world*."""
    found = []
    for path in sorted(FIXTURES.iterdir()):
        engine, _sep, rest = path.stem.partition("-")
        if engine in _ENGINES and rest.startswith(world):
            found.append((engine, path.name, path.read_text()))
    return found
