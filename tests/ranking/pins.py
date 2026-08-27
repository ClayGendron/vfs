"""The determinism pin: the ordered top-10 per golden query, identical on every engine.

``top10.json`` is recorded on sqlite (``VFS_RANKING_REPIN=1``) and
asserted by every leg — memory, sqlite and the four servers. A backend
whose float sums drift past the rounding, or whose fetch order changes
the engine's accumulation, fails here.
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Final

from tests.ranking.corpora import VFS_NATIVE, vfs_native
from tests.ranking.driver import entry_ranking, load_corpus

if TYPE_CHECKING:
    from vfs.storage.backends.database import DatabaseStorage

TOP10: Final = VFS_NATIVE / "top10.json"
REPIN_VAR: Final = "VFS_RANKING_REPIN"


async def ordered_top10(storage: DatabaseStorage) -> dict[str, list[str]]:
    """Load the golden corpus into *storage* and rank every query to ten paths."""
    loaded = await load_corpus(storage, vfs_native())
    return {
        qid: [path for path, _ in await entry_ranking(loaded, query, 10)]
        for qid, query in loaded.corpus.queries.items()
    }


async def assert_top10_pin(storage: DatabaseStorage) -> None:
    """The ordered top-10 of every golden query equals the recorded pin."""
    actual = await ordered_top10(storage)
    if os.environ.get(REPIN_VAR):
        TOP10.write_text(json.dumps(actual, indent=1) + "\n", encoding="utf-8")
    expected = json.loads(TOP10.read_text(encoding="utf-8"))
    assert actual == expected
