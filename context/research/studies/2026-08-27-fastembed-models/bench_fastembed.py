"""Benchmark fastembed dense models beside the hash floor, potion, and the BM25 baseline.

For each corpus and model this driver measures the three costs the
choice of a default local model turns on: time to embed the corpus
(the reindex embed step), time to answer a query (the glean call,
model forward included), and ranking quality (nDCG@10 and friends via
ranx) for the vector leg alone and fused 50/50 with the lexical leg.

Run from the repo root:

    uv run --with fastembed python context/research/studies/2026-08-27-fastembed-models/bench_fastembed.py \
        --corpora vfs_native scifact --out results.json

The first run downloads each ONNX model from the HuggingFace Hub
(~70-210 MB each); model load time is reported separately so the
download does not pollute the embed numbers.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

from sqlalchemy import select  # noqa: E402

from tests.ranking.corpora import Corpus, beir, vfs_native  # noqa: E402
from tests.ranking.driver import WRITE_BATCH, Loaded, entry_ranking, glean_ranking  # noqa: E402
from tests.ranking.metrics import evaluate  # noqa: E402
from vfs.embedding import HashEmbeddingProvider, Model2VecEmbeddingProvider  # noqa: E402
from vfs.embedding.provider import LocalEmbeddingProvider, qualified_model_id  # noqa: E402
from vfs.models import Entry  # noqa: E402
from vfs.paths import Path as VPath  # noqa: E402
from vfs.storage.backends.database import DatabaseStorage  # noqa: E402
from vfs.storage.backends.database.dialects import chunked  # noqa: E402
from vfs.storage.ranking import Convex, Ranker  # noqa: E402

BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

# key -> (fastembed model name, query prefix); prefixes per each model's card.
# bge-small/bge-base are excluded from DEFAULT_MODELS: fastembed serves them only as
# int8-quantized ONNX (qdrant/*-onnx-q), which runs ~27x slower than fp32 on macOS ARM
# (4.3 docs/s vs MiniLM's 114.5 measured here) and times out the embed step.
FASTEMBED_MODELS: dict[str, tuple[str, str]] = {
    "minilm": ("sentence-transformers/all-MiniLM-L6-v2", ""),
    "bge-small": ("BAAI/bge-small-en-v1.5", BGE_QUERY_PREFIX),
    "arctic-xs": ("snowflake/snowflake-arctic-embed-xs", BGE_QUERY_PREFIX),
    "arctic-s": ("snowflake/snowflake-arctic-embed-s", BGE_QUERY_PREFIX),
    "jina-small": ("jinaai/jina-embeddings-v2-small-en", ""),
    "bge-base": ("BAAI/bge-base-en-v1.5", BGE_QUERY_PREFIX),
}

DEFAULT_MODELS = ["hash", "potion", "minilm", "arctic-xs", "arctic-s", "jina-small"]


class FastEmbedProvider(LocalEmbeddingProvider):
    """A fastembed ``TextEmbedding`` behind the seam; the wrapper owns the query prefix."""

    def __init__(self, model_name: str, query_prefix: str = "") -> None:
        super().__init__()
        from fastembed import TextEmbedding

        self._model = TextEmbedding(model_name)
        self._query_prefix = query_prefix
        # Small per-call batches: one 2,048-input call outlives the embed step's
        # 120 s per-call timeout on the slower fp32 models, and vectors never land.
        self.max_batch_inputs = 256
        self.dimension = len(next(iter(self._model.embed(["probe"]))))
        self.model_id = qualified_model_id("fastembed", model_name, self.dimension)

    def embed_batch(self, texts):
        return [[float(v) for v in row] for row in self._model.embed(list(texts), batch_size=64)]

    async def embed_query(self, text: str) -> list[float]:
        return self.embed_batch([self._query_prefix + text])[0]


async def load_timed(storage: DatabaseStorage, corpus: Corpus) -> tuple[Loaded, float, float]:
    """load_corpus with the write and reindex phases timed separately."""
    entries = [Entry(path=VPath(corpus.paths[doc]), content=text) for doc, text in corpus.docs.items()]
    t0 = time.perf_counter()
    for batch in chunked(entries, WRITE_BATCH):
        written = await storage.write(entries=list(batch), parents=True)
        assert written.success is True, written.errors
    t1 = time.perf_counter()
    indexed = await storage.reindex()
    assert indexed.success is True, indexed.errors
    t2 = time.perf_counter()
    tables = storage._host.tables
    entry, chunks, meta = tables.entry, tables.chunks, tables.meta
    async with storage._host.engine.connect() as conn:
        epoch = (await conn.execute(select(meta.c.current_gram_epoch))).scalar_one()
        located = select(chunks.c.id, entry.c.path).select_from(
            chunks.join(entry, entry.c.entry_id == chunks.c.entry_id)
        )
        path_of = {row.id: row.path for row in await conn.execute(located)}
    return Loaded(storage, corpus, epoch, path_of), t1 - t0, t2 - t1


async def timed_run(loaded: Loaded, ranking, k: int = 50):
    """A run keyed by doc id plus per-query wall-clock milliseconds."""
    doc_of = loaded.corpus.doc_of
    run, millis = {}, []
    for qid, query in loaded.corpus.queries.items():
        t0 = time.perf_counter()
        ranked = await ranking(loaded, query, k)
        millis.append((time.perf_counter() - t0) * 1000.0)
        run[qid] = {doc_of[path]: score for path, score in ranked}
    return run, millis


def latency(millis: list[float]) -> dict[str, float]:
    ordered = sorted(millis)
    return {
        "mean_ms": round(statistics.fmean(millis), 2),
        "p50_ms": round(ordered[len(ordered) // 2], 2),
        "max_ms": round(ordered[-1], 2),
    }


def arm_report(corpus: Corpus, run: dict, millis: list[float]) -> dict:
    """Metrics plus latency, or an ``empty`` marker when the arm returned nothing at all."""
    if not any(run.values()):
        return {"empty": True, **latency(millis)}
    return {**evaluate(corpus.qrels, run), **latency(millis)}


async def bench_corpus(corpus: Corpus, model_keys: list[str], workdir: Path) -> dict:
    results: dict = {"docs": len(corpus.docs), "queries": len(corpus.queries), "arms": {}}

    # The lexical baseline: its reindex time is the embed-free floor.
    lex_file = workdir / f"{corpus.name.replace('/', '_')}_lex.sqlite"
    lex_file.unlink(missing_ok=True)
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{lex_file}")
    loaded, write_s, lex_reindex_s = await load_timed(storage, corpus)
    run, millis = await timed_run(loaded, entry_ranking)
    results["chunks"] = len(loaded.path_of)
    results["write_s"] = round(write_s, 2)
    results["lexical_reindex_s"] = round(lex_reindex_s, 2)
    results["arms"]["bm25"] = {**evaluate(corpus.qrels, run), **latency(millis)}
    await storage.close()
    print(f"[{corpus.name}] bm25: {results['arms']['bm25']}", flush=True)

    for key in model_keys:
        t0 = time.perf_counter()
        if key == "hash":
            provider = HashEmbeddingProvider(256)
        elif key == "potion":
            provider = Model2VecEmbeddingProvider()
        elif key == "openai-large":
            from openai import AsyncOpenAI

            from vfs.embedding import OpenAIEmbeddingProvider

            provider = OpenAIEmbeddingProvider(AsyncOpenAI(), "text-embedding-3-large", dimensions=1024)
        else:
            name, prefix = FASTEMBED_MODELS[key]
            provider = FastEmbedProvider(name, prefix)
        load_s = time.perf_counter() - t0

        db_file = workdir / f"{corpus.name.replace('/', '_')}_{key}.sqlite"
        db_file.unlink(missing_ok=True)
        url = f"sqlite+aiosqlite:///{db_file}"
        arms: dict = {"model_id": provider.model_id, "dimension": provider.dimension, "load_s": round(load_s, 2)}
        fused = DatabaseStorage(url=url, embedder=provider, ranker=Ranker(fusion=Convex({"vector": 0.5, "lexical": 0.5})))
        loaded, _, reindex_s = await load_timed(fused, corpus)
        embed_s = max(0.0, reindex_s - lex_reindex_s)
        arms["reindex_s"] = round(reindex_s, 2)
        arms["embed_s"] = round(embed_s, 2)
        arms["chunks_per_s"] = round(len(loaded.path_of) / embed_s, 1) if embed_s > 0 else None
        run, millis = await timed_run(loaded, glean_ranking)
        arms["fused"] = arm_report(corpus, run, millis)
        await fused.close()

        # Same file, same vectors: only the ranker changes for the vector-only arm.
        vector = DatabaseStorage(url=url, embedder=provider, ranker=Ranker(fusion=Convex({"vector": 1.0})))
        run, millis = await timed_run(loaded._replace(storage=vector), glean_ranking)
        arms["vector"] = arm_report(corpus, run, millis)
        await vector.close()

        results["arms"][key] = arms
        print(f"[{corpus.name}] {key}: embed {arms['embed_s']}s, fused {arms['fused']}", flush=True)
    return results


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpora", nargs="+", default=["vfs_native", "scifact"])
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    parser.add_argument("--out", default=str(Path(__file__).parent / "results.json"))
    parser.add_argument("--workdir", default=None)
    args = parser.parse_args()

    workdir = Path(args.workdir) if args.workdir else Path(__file__).parent / "work"
    workdir.mkdir(parents=True, exist_ok=True)
    out = Path(args.out)
    results = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
    for name in args.corpora:
        corpus = vfs_native() if name == "vfs_native" else beir(name)
        fresh = await bench_corpus(corpus, list(args.models), workdir)
        if name in results:  # merge: this run's arms win, earlier arms survive
            fresh["arms"] = {**results[name]["arms"], **fresh["arms"]}
        results[name] = fresh
        out.write_text(json.dumps(results, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {args.out}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
