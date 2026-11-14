"""The covered chunk page: a keyset page over the chunk table, its entry filter spelled as each planner serves it.

SQLite takes the filter as a correlated probe on the entry table compared
to a constant, the one spelling its planner never rewrites into a join;
every other profile keeps the join. These pins hold the rendered SQL of
the embed step's page, the one page that reads the filter; the plans
themselves are pinned on a filled store by the statistics pins and the
conformance row.
"""

from __future__ import annotations

import ast
import pathlib
from typing import TYPE_CHECKING

from sqlalchemy.dialects import postgresql as postgresql_dialect
from sqlalchemy.dialects import sqlite as sqlite_dialect

from vfs.models.rows import build_vfs_tables
from vfs.storage.backends.database import pages
from vfs.storage.backends.database.dialects import POSTGRESQL, SQLITE
from vfs.storage.backends.database.embed import EMBED_PAGE_ROWS, unembedded_page

if TYPE_CHECKING:
    from sqlalchemy import Select
    from sqlalchemy.engine import Dialect

    from vfs.storage.backends.database.dialects import DialectProfile

# The modules above the page builder: each imports it, so it may import none of them.
_ABOVE = frozenset({"indexing", "lexical", "embed", "backend"})


def _embed_page(profile: DialectProfile) -> Select:
    """The embed step's page as the backend builds it, past chunk id 1,000."""
    return unembedded_page(build_vfs_tables(), 1_000, EMBED_PAGE_ROWS, ("pages", -1, -1), profile)


def _literal(statement: Select, dialect: Dialect) -> str:
    return str(statement.compile(dialect=dialect, compile_kwargs={"literal_binds": True}))


def test_the_page_probes_on_sqlite_and_joins_elsewhere() -> None:
    """Guards: the SQLite page spelled as the join (its planner rebuilds a
    Bloom filter on every page) or as a labelled bind, and the other
    engines losing the join their planners serve."""
    probe = _literal(_embed_page(SQLITE), sqlite_dialect.dialect())
    assert "(SELECT 1 " in probe and "FROM vfs_entries" in probe and ") = 1" in probe, probe
    assert "anon_1" not in probe and "JOIN" not in probe, probe
    join = _literal(_embed_page(POSTGRESQL), postgresql_dialect.dialect())
    assert "JOIN vfs_entries" in join and "SELECT 1" not in join, join


def test_the_module_imports_downward() -> None:
    """Guards: the page builder importing a module that imports it, the cycle its own module exists to avoid."""
    tree = ast.parse(pathlib.Path(pages.__file__).read_text(encoding="utf-8"))
    names = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module is not None}
    names |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    assert names, names
    assert not any(name.rsplit(".", 1)[-1] in _ABOVE for name in names), names
