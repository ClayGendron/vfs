"""Statement predicates the suite shares: which recorded SQL belongs to the planner-statistics step.

A test that bounds a verb's own statements leaves the statistics step
out, because the step is pinned by its own counts and a verb's bound
should hold for the verb alone. The step's statements are SQLite's:
the growth listing, the ``index_list`` reads, every ``ANALYZE`` (the
tables and the ``sqlite_schema`` reload), the fingerprint read over
``sqlite_stat1``, and everything carrying the ``vfs_statistics`` name,
which the savepoint statements and the analysis pass's tagged ``BEGIN
IMMEDIATE`` do.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import event

if TYPE_CHECKING:
    from vfs.storage.backends.database import DatabaseStorage

STATISTICS_NAME = "vfs_statistics"
"""The savepoint name, the analysis pass's begin tag and the connection-record key, all one word."""


def is_statistics_statement(sql: str) -> bool:
    """Whether *sql* is one of the planner-statistics step's statements and not a verb's own."""
    text = sql.lstrip()
    upper = text.upper()
    if upper.startswith("ANALYZE "):
        return True
    if upper.startswith("PRAGMA") and ("OPTIMIZE" in upper or "INDEX_LIST" in upper):
        return True
    return "sqlite_stat1" in text or STATISTICS_NAME in text


class Recorded(list[str]):
    """The statements a storage sends, a verb's own only, from the moment :func:`recorded` is called."""

    def verbs(self) -> list[str]:
        """The first word of each statement that is no transaction control: what the call ran, in order."""
        control = ("BEGIN", "COMMIT", "PRAGMA", "SAVEPOINT", "RELEASE", "ROLLBACK")
        return [sql.split()[0] for sql in self if not sql.startswith(control)]

    def mutations(self) -> list[str]:
        """Each recorded ``INSERT``, ``UPDATE`` or ``DELETE``."""
        return [sql for sql in self if sql.startswith(("INSERT", "UPDATE", "DELETE"))]


def recorded(storage: DatabaseStorage) -> Recorded:
    """A list that fills with every statement *storage* sends from now on, the statistics step's left out."""
    statements = Recorded()

    @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
    def record(conn, cursor, statement, parameters, context, executemany) -> None:
        if not is_statistics_statement(statement):
            statements.append(statement)

    return statements
