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
_ENGINES = {"postgresql", "sqlite"}

# The forced walks, one per hiding place the reader must see through, and the constructed shapes it cannot parse.
_WALKS = (
    "postgresql-walk-nonleading.txt",
    "postgresql-walk-pending-nonleading.txt",
    "postgresql-walk-unknown.txt",
    "sqlite-walk-scantable.txt",
)


def test_the_scan_reader_sees_the_walks_of_the_old_world() -> None:
    """Guards: the reader taking a full scan or an ordered index walk for a seek, so the scan-tier plan pin passes
    a statement that reads the whole table or a whole index; or taking a seek for a walk, so a correct plan fails.

    The old world's captured plans each hold an access the bound refuses,
    and every one is read as a scan. So is a walk a seek's operator can
    hide, forced on a small store: a Postgres index condition on a later
    column alone; and so is every constructed shape the reader does not
    parse, beside a seek it does: what it cannot read is a scan, never
    dropped. Every access of the corrected world's captured plans is one
    the bound admits.
    """
    refused = [*_plans("old"), *_plans("walk")]
    corrected = _plans("corrected")
    assert {engine for engine, _name, _plan in refused} == _ENGINES
    assert {engine for engine, _name, _plan in corrected} == _ENGINES
    assert {name for _engine, name, _plan in _plans("walk")} == set(_WALKS)
    for engine, name, plan in refused:
        accesses = entry_access(engine, plan)
        assert accesses, name
        assert [access for access in accesses if not bounded_access(access)], (name, accesses)
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
    [access] = entry_access("postgresql", (FIXTURES / "postgresql-corrected-pending.txt").read_text())
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
