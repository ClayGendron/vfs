"""model2vec static embeddings — the offline provider with real semantics.

A model2vec ``StaticModel`` is a token → row lookup mean-pooled over a
text: no transformer forward pass, no torch, ~30 MB of wheels beyond
vfs, thousands of chunks a second on one core. It is the "works on a
laptop, offline" tier behind the ``embed-local`` extra; the first use
of a named model downloads it from the Hub, so the test suite passes a
pre-built model object and never touches the network.

    provider = Model2VecEmbeddingProvider()                    # potion-base-8M, from the Hub cache
    provider = Model2VecEmbeddingProvider(model, model_name="…")   # a loaded StaticModel
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any, Final

from vfs.embedding.provider import LocalEmbeddingProvider, qualified_model_id

if TYPE_CHECKING:
    from collections.abc import Sequence
    from concurrent.futures import Executor

DEFAULT_MODEL: Final = "minishlab/potion-base-8M"
"""MIT, 256-d, 7.6M parameters — 92 % of MiniLM's MTEB at ~5,000 chunks/s."""

_PACKAGE: Final = "model2vec"


def static_model_loader() -> Any:
    """model2vec's ``StaticModel``, resolved on demand so importing vfs never loads the extra."""
    try:
        return importlib.import_module(_PACKAGE).StaticModel
    except ImportError as exc:
        msg = "Model2VecEmbeddingProvider needs the 'model2vec' package: install vfs-py[embed-local]"
        raise ImportError(msg) from exc


class Model2VecEmbeddingProvider(LocalEmbeddingProvider):
    """A ``StaticModel`` behind the seam; potion models take no query prefix.

    *model* is any object with model2vec's ``dim`` and ``encode``
    surface; ``None`` loads *model_name* through ``StaticModel``, which
    requires the ``embed-local`` extra and, on first use, the Hub.
    """

    def __init__(
        self, model: Any | None = None, *, model_name: str = DEFAULT_MODEL, executor: Executor | None = None
    ) -> None:
        super().__init__(executor=executor)
        if model is None:
            model = static_model_loader().from_pretrained(model_name)
        self._model = model
        self.dimension = int(model.dim)
        self.model_id = qualified_model_id("model2vec", model_name, self.dimension)

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        return [[float(value) for value in row] for row in self._model.encode(list(texts))]
