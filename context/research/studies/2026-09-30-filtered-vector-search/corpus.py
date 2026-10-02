"""Shared corpus, callers and scoring for the filtered-vector-search study.

The corpus mirrors the partial-glean bench's tree: ``TOPS`` top folders,
each holding ``FOLDERS`` folders of ``FILES`` files, one chunk per file.
Vectors are clustered by folder: every folder is given one of
``TOPICS`` topic centroids, and each file's vector is its topic centroid
plus noise, normalised. A query is noise around a random topic centroid,
so a query's true neighbours sit in a few folders, as real text would.
That correlation is the hard case for post-filtering: the nearest rows
may all be in folders the caller cannot see.

Study code only: nothing here is imported by vfs.
"""

from __future__ import annotations

import math
import random
import struct
from dataclasses import dataclass

TOPS, FOLDERS, FILES = 10, 100, 50
TOPICS = 200
NOISE = 1.0
K = 10


@dataclass(frozen=True)
class Caller:
    label: str
    prefixes: list[str]


def paths() -> list[str]:
    return [f"/t{t:02d}/f{f:03d}/doc{n:03d}.md" for t in range(TOPS) for f in range(FOLDERS) for n in range(FILES)]


def unit(v: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


def vectors(dim: int, seed: int = 30) -> list[list[float]]:
    rng = random.Random(seed)
    centroids = [unit([rng.gauss(0, 1) for _ in range(dim)]) for _ in range(TOPICS)]
    topic_of_folder = [rng.randrange(TOPICS) for _ in range(TOPS * FOLDERS)]
    out = []
    for folder in range(TOPS * FOLDERS):
        c = centroids[topic_of_folder[folder]]
        for _ in range(FILES):
            out.append(unit([x + rng.gauss(0, NOISE / math.sqrt(dim)) for x in c]))
    return out


def queries(dim: int, n: int, seed: int = 99) -> list[list[float]]:
    rng = random.Random(seed)
    centroids_rng = random.Random(30)
    centroids = [unit([centroids_rng.gauss(0, 1) for _ in range(dim)]) for _ in range(TOPICS)]
    return [unit([x + rng.gauss(0, NOISE / math.sqrt(dim)) for x in rng.choice(centroids)]) for _ in range(n)]


def pack(v: list[float]) -> bytes:
    return struct.pack(f"{len(v)}f", *v)


def callers() -> list[Caller]:
    folders = [f"/t{t:02d}/f{f:03d}" for t in range(TOPS) for f in range(FOLDERS)]
    files = paths()
    return [
        Caller("0.1% · 1 folder grant", [folders[0]]),
        Caller("1% · 10 folder grants", folders[::100]),
        Caller("1% · 500 file grants", files[::100]),
        Caller("10% · 1 top grant", ["/t00"]),
        Caller("10% · 100 folder grants", folders[::10]),
        Caller("50% · 5 top grants", [f"/t{t:02d}" for t in range(0, TOPS, 2)]),
        Caller("50% · 500 folder grants", folders[::2]),
    ]


def admits(prefixes: set[str], path: str) -> bool:
    """The app-side permission check: the path or one of its ancestors is granted."""
    if path in prefixes:
        return True
    cut = path.rfind("/")
    while cut > 0:
        path = path[:cut]
        if path in prefixes:
            return True
        cut = path.rfind("/")
    return False


def recall(found: list[int], truth: list[int]) -> float:
    return len(set(found) & set(truth)) / max(1, len(truth))
