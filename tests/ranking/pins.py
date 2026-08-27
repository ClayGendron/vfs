"""The determinism pin: the ordered top-10 per golden query, identical on every engine.

``top10.json`` is recorded on sqlite (``VFS_RANKING_REPIN=1``) from the
driver and asserted by every leg — memory, sqlite and the four servers
— twice over: once through the driver, once through the ``glean`` verb,
which must reproduce the driver's order exactly. A backend whose float
sums drift past the rounding, or whose fetch order changes the engine's
accumulation, fails here; so does a verb that departs from the referee.
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Final

from tests.ranking.corpora import VFS_NATIVE, vfs_native
from tests.ranking.driver import Loaded, entry_ranking, glean_ranking, load_corpus

if TYPE_CHECKING:
    from vfs.storage.backends.database import DatabaseStorage

TOP10: Final = VFS_NATIVE / "top10.json"
REPIN_VAR: Final = "VFS_RANKING_REPIN"


async def ordered_top10(loaded: Loaded) -> dict[str, list[str]]:
    """Every golden query ranked to ten paths through the driver."""
    return {
        qid: [path for path, _ in await entry_ranking(loaded, query, 10)]
        for qid, query in loaded.corpus.queries.items()
    }


async def ordered_top10_via_glean(loaded: Loaded) -> dict[str, list[str]]:
    """Every golden query ranked to ten paths through the ``glean`` verb."""
    return {
        qid: [path for path, _ in await glean_ranking(loaded, query, 10)]
        for qid, query in loaded.corpus.queries.items()
    }


async def assert_top10_pin(storage: DatabaseStorage) -> None:
    """The ordered top-10 of every golden query equals the recorded pin, through
    the driver and through the verb."""
    loaded = await load_corpus(storage, vfs_native())
    actual = await ordered_top10(loaded)
    if os.environ.get(REPIN_VAR):
        TOP10.write_text(json.dumps(actual, indent=1) + "\n", encoding="utf-8")
    expected = json.loads(TOP10.read_text(encoding="utf-8"))
    assert actual == expected
    assert await ordered_top10_via_glean(loaded) == expected
