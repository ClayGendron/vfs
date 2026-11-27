"""The kernel's tables: their names keep apart from a mount's, and the family is built with no engine."""

from __future__ import annotations

from vfs.models.kernel_rows import KERNEL_FORMAT_VERSION, KERNEL_TABLE_PREFIXES, build_kernel_tables
from vfs.models.rows import build_vfs_tables


def test_every_kernel_table_begins_with_a_kernel_prefix() -> None:
    """Guards a kernel table named as a mount's could be, which the remedy of a store of another format would drop."""
    names = [table.name for table in build_kernel_tables().metadata.sorted_tables]
    assert names
    assert [name for name in names if not name.startswith(KERNEL_TABLE_PREFIXES)] == []


def test_no_mount_table_begins_with_a_kernel_prefix() -> None:
    """Guards a mount table whose name a kernel table could take, in the one file or schema they share."""
    names = [table.name for table in build_vfs_tables().metadata.sorted_tables]
    assert [name for name in names if name.startswith(KERNEL_TABLE_PREFIXES)] == []


def test_the_family_takes_its_schema_and_names_its_tables_to_drop() -> None:
    """Guards a family that ignores its schema, or names its tables in an order a drop would refuse."""
    tables = build_kernel_tables(schema="tenant_a")
    assert (tables.meta.schema, tables.names_to_drop()) == ("tenant_a", ("vfs_kernel_meta",))
    assert build_kernel_tables(schema="tenant_a") is tables
    assert KERNEL_FORMAT_VERSION == 1
