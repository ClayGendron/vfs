"""Deterministic synthetic corpus: prose-like docs from a fixed 5,000-word vocabulary plus code identifiers.

Each doc is 200-2,000 words (roughly 2-8 KB) in a tree /dAA/dBB/fNNNNN.md. Seeded, so every run
produces the same corpus for the same size.
"""

from __future__ import annotations

import random

SEED = 20261031
VOCAB_SIZE = 5000
SYLLABLES = [
    "ba", "be", "bi", "bo", "bu", "ca", "ce", "co", "cu", "da", "de", "di", "do", "du", "fa", "fe", "fi",
    "fo", "ga", "ge", "gi", "go", "ha", "he", "hi", "ho", "ka", "ke", "ki", "ko", "la", "le", "li", "lo",
    "lu", "ma", "me", "mi", "mo", "mu", "na", "ne", "ni", "no", "nu", "pa", "pe", "pi", "po", "ra", "re",
    "ri", "ro", "ru", "sa", "se", "si", "so", "su", "ta", "te", "ti", "to", "tu", "va", "ve", "vi", "vo",
    "wa", "we", "wi", "za", "ze", "zo", "tion", "ment", "ness", "ing", "er", "al", "ous", "ive", "ly", "an",
    "ar", "en", "es", "is", "on", "or", "st", "th", "ch", "sh",
]
COMMON = [
    "the", "of", "and", "to", "in", "is", "for", "that", "with", "as", "on", "by", "are", "this", "from",
    "or", "an", "be", "was", "it", "at", "which", "not", "but", "can", "has", "its", "when", "each", "into",
]


def build_vocab() -> list[str]:
    rng = random.Random(SEED)
    words: set[str] = set()
    while len(words) < VOCAB_SIZE:
        n = rng.choice((2, 2, 3, 3, 4))
        w = "".join(rng.choice(SYLLABLES) for _ in range(n))
        if 4 <= len(w) <= 14:
            words.add(w)
    return sorted(words)


def build_identifiers() -> list[str]:
    rng = random.Random(SEED + 1)
    heads = ["get", "set", "load", "parse", "build", "fetch", "write", "read", "index", "chunk", "merge", "score"]
    tails = ["Config", "Buffer", "Entry", "Epoch", "Posting", "Row", "Table", "Query", "Handle", "Stream", "Batch"]
    ids = set()
    while len(ids) < 600:
        style = rng.random()
        a, b = rng.choice(heads), rng.choice(tails)
        if style < 0.4:
            ids.add(f"{a}{b}{rng.randint(0, 99)}")
        elif style < 0.8:
            ids.add(f"{a}_{b.lower()}_{rng.randint(0, 999):03d}")
        else:
            ids.add(f"{b}::{a}_{rng.randint(0, 9999):04x}")
    return sorted(ids)


VOCAB = build_vocab()
IDENTS = build_identifiers()
# Zipf-like weights over a seeded permutation of the vocabulary: a few hundred frequent words, a long rare tail.
_perm = list(range(VOCAB_SIZE))
random.Random(SEED + 2).shuffle(_perm)
WEIGHTS = [0.0] * VOCAB_SIZE
for rank, idx in enumerate(_perm):
    WEIGHTS[idx] = 1.0 / (rank + 20) ** 0.95


def doc_text(rng: random.Random, n_words: int) -> str:
    # Zipf-ish: pick from a skewed index so some words are rare, some common.
    out: list[str] = []
    line: list[str] = []
    picks = iter(rng.choices(VOCAB, WEIGHTS, k=n_words))
    while len(out) + len(line) < n_words:
        r = rng.random()
        if r < 0.30:
            w = rng.choice(COMMON)
        elif r < 0.95:
            w = next(picks)
        else:
            w = rng.choice(IDENTS)
        line.append(w)
        if len(line) >= rng.randint(8, 16):
            if rng.random() < 0.3 and len(line) > 2:
                line[-1] += "."
            out.extend(line)
            out.append("\n")
            line = []
            if rng.random() < 0.15:
                out.append("\n")
    out.extend(line)
    return " ".join(out).replace(" \n ", "\n").replace(" \n", "\n").replace("\n ", "\n")


def path_for(i: int) -> str:
    return f"/d{(i // 2500) % 40:02d}/d{(i // 50) % 50:02d}/f{i:06d}.md"


def generate(n: int, *, salt: int = 0):
    """Yield (path, content) for docs 0..n-1. `salt` changes the content (a rewrite) but not the path."""
    for i in range(n):
        rng = random.Random((SEED, i, salt).__hash__())
        words = rng.randint(200, 2000)
        yield path_for(i), f"# Document {i} rev {salt}\n\n" + doc_text(rng, words)


if __name__ == "__main__":
    import statistics

    sizes = [len(c.encode()) for _, c in generate(500)]
    print("docs", len(sizes), "mean bytes", statistics.mean(sizes), "min", min(sizes), "max", max(sizes))
    p, c = next(generate(1))
    print(p)
    print(c[:600])
