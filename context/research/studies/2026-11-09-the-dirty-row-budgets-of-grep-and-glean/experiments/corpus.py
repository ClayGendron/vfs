"""Deterministic synthetic corpus for the dirty-set cost curve.

Bodies are prose-like runs of words drawn Zipf-style from a 30,000-word
seeded vocabulary (so query terms have a real idf spread), with a share of
English function words and code identifiers. Body sizes are log-normal
around a 4 KB median (sigma 1.0) and clamped to [300 B, 200 KB], so the tail
reaches about 200 KB. Files live in a tree of 3,600 directories
(/dAA/dBB/dCC/fNNNNNN.md). Everything is seeded: the same ``i`` always has
the same size class, and ``salt`` changes the words (a rewrite) but not the
size class or the path.
"""

from __future__ import annotations

import math
import random

SEED = 20261109
VOCAB_SIZE = 30_000
ZIPF_EXPONENT = 1.0
ZIPF_OFFSET = 10
MEDIAN_BYTES = 4096
SIGMA = 1.0
MIN_BYTES = 300
MAX_BYTES = 200_000
DIRS = (20, 15, 12)  # 3,600 directories

SYLLABLES = [
    "ba", "be", "bi", "bo", "bu", "ca", "ce", "co", "cu", "da", "de", "di", "do", "du", "fa", "fe", "fi",
    "fo", "ga", "ge", "gi", "go", "ha", "he", "hi", "ho", "ka", "ke", "ki", "ko", "la", "le", "li", "lo",
    "lu", "ma", "me", "mi", "mo", "mu", "na", "ne", "ni", "no", "nu", "pa", "pe", "pi", "po", "ra", "re",
    "ri", "ro", "ru", "sa", "se", "si", "so", "su", "ta", "te", "ti", "to", "tu", "va", "ve", "vi", "vo",
    "wa", "we", "wi", "za", "ze", "zo", "tion", "ment", "ness", "ing", "er", "al", "ous", "ive", "ly", "an",
    "ar", "en", "es", "is", "on", "or", "st", "th", "ch", "sh", "pro", "con", "dis", "tra", "ver", "gra",
]
COMMON = [
    "the", "of", "and", "to", "in", "is", "for", "that", "with", "as", "on", "by", "are", "this", "from",
    "or", "an", "be", "was", "it", "at", "which", "not", "but", "can", "has", "its", "when", "each", "into",
    "we", "they", "also", "than", "then", "there", "these", "those", "will", "would",
]


def build_vocab() -> list[str]:
    rng = random.Random(SEED)
    words: set[str] = set(COMMON)
    while len(words) < VOCAB_SIZE + len(COMMON):
        n = rng.choice((2, 2, 3, 3, 3, 4, 4))
        w = "".join(rng.choice(SYLLABLES) for _ in range(n))
        if 4 <= len(w) <= 16:
            words.add(w)
    return sorted(words - set(COMMON))


def build_identifiers() -> list[str]:
    rng = random.Random(SEED + 1)
    heads = ["get", "set", "load", "parse", "build", "fetch", "write", "read", "index", "chunk", "merge", "score"]
    tails = ["Config", "Buffer", "Entry", "Epoch", "Posting", "Row", "Table", "Query", "Handle", "Stream", "Batch"]
    ids: set[str] = set()
    while len(ids) < 800:
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
# Zipf weights over a seeded permutation: rank 0 is the most frequent word.
PERM = list(range(VOCAB_SIZE))
random.Random(SEED + 2).shuffle(PERM)
WEIGHTS = [0.0] * VOCAB_SIZE
for rank, idx in enumerate(PERM):
    WEIGHTS[idx] = 1.0 / (rank + ZIPF_OFFSET) ** ZIPF_EXPONENT
CUM_WEIGHTS: list[float] = []
_acc = 0.0
for _w in WEIGHTS:
    _acc += _w
    CUM_WEIGHTS.append(_acc)
RANK_TO_WORD = [VOCAB[PERM[r]] for r in range(VOCAB_SIZE)]


def word_at_rank(rank: int) -> str:
    """The vocabulary word of Zipf rank *rank* (0 = most frequent)."""
    return RANK_TO_WORD[rank]


# Mean bytes per emitted token including its separator, measured once from the
# mix (70% vocab, 27% common, 3% identifier); used to turn a byte target into
# a word count.
def _mean_token_bytes() -> float:
    rng = random.Random(SEED + 3)
    total = 0
    k = 20_000
    picks = rng.choices(VOCAB, cum_weights=CUM_WEIGHTS, k=k)
    for i in range(k):
        r = rng.random()
        if r < 0.27:
            total += len(rng.choice(COMMON)) + 1
        elif r < 0.97:
            total += len(picks[i]) + 1
        else:
            total += len(rng.choice(IDENTS)) + 1
    return total / k


MEAN_TOKEN_BYTES = _mean_token_bytes()


def size_bytes_for(i: int) -> int:
    """The size class of document *i*: log-normal, median 4 KB, clamped to [300 B, 200 KB]."""
    rng = random.Random(SEED * 7919 + i)
    size = int(round(math.exp(rng.gauss(math.log(MEDIAN_BYTES), SIGMA))))
    return max(MIN_BYTES, min(MAX_BYTES, size))


def doc_text(rng: random.Random, target_bytes: int) -> str:
    n_words = max(20, int(target_bytes / MEAN_TOKEN_BYTES))
    picks = rng.choices(VOCAB, cum_weights=CUM_WEIGHTS, k=n_words)
    out: list[str] = []
    line: list[str] = []
    line_len = rng.randint(8, 16)
    for i in range(n_words):
        r = rng.random()
        if r < 0.27:
            w = rng.choice(COMMON)
        elif r < 0.97:
            w = picks[i]
        else:
            w = rng.choice(IDENTS)
        line.append(w)
        if len(line) >= line_len:
            if rng.random() < 0.3:
                line[-1] += "."
            out.append(" ".join(line))
            if rng.random() < 0.15:
                out.append("")
            line = []
            line_len = rng.randint(8, 16)
    if line:
        out.append(" ".join(line))
    return "\n".join(out) + "\n"


def path_for(i: int) -> str:
    a = i % DIRS[0]
    b = (i // DIRS[0]) % DIRS[1]
    c = (i // (DIRS[0] * DIRS[1])) % DIRS[2]
    return f"/d{a:02d}/d{b:02d}/d{c:02d}/f{i:06d}.md"


def document(i: int, salt: int = 0) -> tuple[str, str]:
    """``(path, content)`` of document *i* at revision *salt*; the size class is salt-independent."""
    rng = random.Random(SEED * 1_000_003 + i * 1_009 + salt)
    return path_for(i), f"# Document {i} rev {salt}\n\n" + doc_text(rng, size_bytes_for(i))


def generate(n: int, *, salt: int = 0):
    for i in range(n):
        yield document(i, salt)


SENTINEL_PATH = "/zzz/zzz/last.md"
SENTINEL_WORD = "qzxvunique"


def sentinel(salt: int) -> tuple[str, str]:
    body = (
        f"# sentinel rev {salt}\n\nthis body holds the {SENTINEL_WORD} word and little else of note\n"
        f"{word_at_rank(5)} {word_at_rank(300)} {SENTINEL_WORD}\n"
    )
    return SENTINEL_PATH, body


if __name__ == "__main__":
    import statistics
    import sys
    import time

    n = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    t0 = time.perf_counter()
    sizes = [len(c.encode()) for _, c in generate(n)]
    dt = time.perf_counter() - t0
    sizes.sort()
    print(f"docs {n} in {dt:.1f}s; mean token bytes {MEAN_TOKEN_BYTES:.2f}")
    print(
        "bytes: median", statistics.median(sizes), "mean", round(statistics.mean(sizes)),
        "p90", sizes[int(0.9 * n)], "p99", sizes[int(0.99 * n)], "max", max(sizes), "min", min(sizes),
        "total MB", round(sum(sizes) / 1e6, 1),
    )
    dirs = {path_for(i).rsplit("/", 1)[0] for i in range(n)}
    print("directories", len(dirs))
    for r in (5, 40, 300, 800, 2000, 5000, 9000, 12000, 20000):
        print("rank", r, word_at_rank(r))
    p, c = document(0)
    print(p)
    print(c[:400])
