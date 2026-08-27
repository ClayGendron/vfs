"""The determinism pins: the ordered top-10 per golden query, identical on every engine.

``top10.json`` is recorded on sqlite (``VFS_RANKING_REPIN=1``) from the
lexical driver and asserted by every leg — memory, sqlite and the four
servers — through the driver, and through the ``glean`` verb on a mount
with no embedder, which must reproduce the driver's order exactly.
``top10_hybrid.json`` is the same pin for the verb on a mount carrying
the hashing embedder: the vector leg's in-engine cosine, fused with the
lexical leg, must order identically on every engine. A backend whose
float sums drift past the rounding, whose fetch order changes the
engine's accumulation, or whose cosine disagrees with the referee's
fails here.
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
TOP10_HYBRID: Final = VFS_NATIVE / "top10_hybrid.json"
REPIN_VAR: Final = "VFS_RANKING_REPIN"
HYBRID_PIN_MODEL: Final = "hash/blake2b-tokens-bigrams@64"


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
    the driver (lexical) and through the verb (lexical, or hybrid on a mount with
    the hashing embedder)."""
    loaded = await load_corpus(storage, vfs_native())
    actual = await ordered_top10(loaded)
    if os.environ.get(REPIN_VAR):
        TOP10.write_text(json.dumps(actual, indent=1) + "\n", encoding="utf-8")
    expected = json.loads(TOP10.read_text(encoding="utf-8"))
    assert actual == expected
    via_verb = await ordered_top10_via_glean(loaded)
    if storage.embedder is None:
        assert via_verb == expected
        return
    assert storage.embedder.model_id == HYBRID_PIN_MODEL, "the hybrid pin is recorded on the 64-d hashing embedder"
    if os.environ.get(REPIN_VAR):
        TOP10_HYBRID.write_text(json.dumps(via_verb, indent=1) + "\n", encoding="utf-8")
    assert via_verb == json.loads(TOP10_HYBRID.read_text(encoding="utf-8"))
