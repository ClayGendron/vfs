"""The tables the kernel keeps its own records in, beside a mount's tables and never among them.

A record is a row the kernel keeps about calls: a session, a turn, a job,
what a session saw. It has no path and no verb reaches it. The kernel's
store makes these tables in the place its root storage names, which is
the root's own database: on SQLite the mount's file, on Postgres the
mount's schema. So every name here begins with one of
:data:`KERNEL_TABLE_PREFIXES`, which no table of a mount uses.

:func:`build_kernel_tables` builds the family on one ``MetaData``, as
``build_vfs_tables`` does for a mount, so one ``create_all`` makes them
all. A landing that adds or changes a table here adds one to
:data:`KERNEL_FORMAT_VERSION`: the store writes it when it makes the
tables and refuses a store of any other format.

    tables = build_kernel_tables(schema="tenant_a")
    tables.metadata.create_all(connection)
"""

from __future__ import annotations

import functools
from typing import Final, NamedTuple

from sqlalchemy import CheckConstraint, Column, DateTime, Integer, MetaData, Table

KERNEL_FORMAT_VERSION: Final = 1
"""The shape of the kernel's tables that this build keeps; a store made by another is refused."""

KERNEL_TABLE_PREFIXES: Final = ("vfs_kernel_", "vfs_session", "vfs_job")
"""How every kernel table's name begins; no table of a mount's begins so."""

# Families cached by schema: a host with many tenants in their own schemas rebuilds the cold ones.
_FAMILY_CACHE: Final = 64


class KernelTables(NamedTuple):
    """The kernel's schema objects, all bound to the same ``metadata``."""

    metadata: MetaData
    meta: Table

    def names_to_drop(self) -> tuple[str, ...]:
        """Every table's name, in the order they are to be dropped: dependents first."""
        return tuple(table.name for table in reversed(self.metadata.sorted_tables))


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


@functools.lru_cache(maxsize=_FAMILY_CACHE)
def build_kernel_tables(schema: str | None = None) -> KernelTables:
    """Build the kernel's table family in memory, in *schema*; no DDL is issued.

    The family is immutable after construction and carries no engine
    binding, so every store in one schema shares it.
    """
    metadata = MetaData()
    meta = Table(
        "vfs_kernel_meta",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=False),
        Column("format_version", Integer, nullable=False),
        Column("created_at", DateTime(timezone=True)),
        CheckConstraint("id = 1", name="ck_vfs_kernel_meta_single_row"),
        schema=schema,
    )
    return KernelTables(metadata=metadata, meta=meta)
