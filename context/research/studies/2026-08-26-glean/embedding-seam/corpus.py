"""Synthetic corpus: 10,000 chunks of ~500 tokens (~375 words) of code-ish English."""
import random

VOCAB = (
    "the of and to in for with as is on by that from this at be are it or an not "
    "def class return self import async await session table column select where "
    "insert update delete result entry chunk embedding vector index path mount "
    "storage backend dialect budget batch offload lease heartbeat epoch publish "
    "reclaim grep glob glean graph query limit score rank fusion lexical trigram "
    "posting content hash version deleted trash sweep restore write read stat "
    "list observation match preview line start end model dimension provider "
    "cache token request retry backoff concurrency deadline cancel error warn"
).split()


def make_chunks(n: int = 10_000, words: int = 375, seed: int = 7) -> list[str]:
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        ws = rng.choices(VOCAB, k=words)
        # sprinkle punctuation and line breaks so tokenizers see realistic shape
        text = " ".join(w + ("." if rng.random() < 0.08 else "") for w in ws)
        out.append(text.replace(". ", ".\n", 12))
    return out
