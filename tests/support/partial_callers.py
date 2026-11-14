"""The scan tier's partial-caller test pieces: one small store, and a session that records what it executes.

``partial_store`` builds the world the scan-tier rows of the search and
grep test files share: posture ``none``, ``bob`` granted ``read`` on
``/pub``, one indexed file and two readable files written after the index
pass, and a given number of dirty files under ``/hr``, which bob cannot read
and which sort ahead of his. ``RecordingSession`` stands in for the session
a scan-tier call is handed and keeps each statement object it executes, so a
test or the plan store can read the statements as built.
"""

from __future__ import annotations

from typing import Any

from vfs.authority import Authority, Principal
from vfs.models import Entry
from vfs.paths import Path
from vfs.storage.backends.memory import InMemoryStorage

SYSTEM = Authority.system()
BOB = Authority.of(Principal("bob"))


async def partial_store(hidden: int) -> InMemoryStorage:
    """bob reads ``/pub`` under posture ``none``: an indexed file, two readable dirty ones, *hidden* dirty under /hr."""
    storage = InMemoryStorage()
    indexed = Entry(path=Path("/pub/indexed.md"), content="lantern indexed\n")
    assert (await storage.write(entries=[indexed], parents=True, authority=SYSTEM)).success is True
    assert (await storage.posture(path=Path("/"), posture="none", authority=SYSTEM)).success is True
    assert (await storage.grant(path=Path("/pub"), principal="bob", level="read", authority=SYSTEM)).success is True
    assert (await storage.reindex()).success is True
    dirty = [Entry(path=Path(f"/pub/fresh{n}.md"), content="lantern fresh\n") for n in range(2)]
    dirty += [Entry(path=Path(f"/hr/h{n}.md"), content="lantern hidden\n") for n in range(hidden)]
    assert (await storage.write(entries=dirty, parents=True, authority=SYSTEM)).success is True
    return storage


class RecordingSession:
    """The session the scan tier is handed, recording every statement it executes."""

    def __init__(self, inner: Any, recorded: list[Any]) -> None:
        self._inner = inner
        self._recorded = recorded

    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        self._recorded.append(statement)
        return await self._inner.execute(statement, *args, **kwargs)
