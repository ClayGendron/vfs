"""Fetch the harness's BEIR pair — SciFact and NFCorpus — into the cache.

The ranking harness (``tests/ranking``) reads the two corpora from a
directory *outside* the repo and skips when it is absent; this script
fills it. Each dataset is the canonical BEIR zip (``corpus.jsonl``,
``queries.jsonl``, ``qrels/test.tsv``), unpacked as-is::

    uv run python scripts/fetch_beir.py            # both datasets
    uv run python scripts/fetch_beir.py scifact    # one of them

The cache root is ``$VFS_RANKING_CACHE`` when set, else
``~/.cache/vfs/ranking``; datasets land under ``beir/<name>/``.
"""

from __future__ import annotations

import io
import os
import sys
import urllib.request
import zipfile
from pathlib import Path

DATASETS = ("scifact", "nfcorpus")
BASE_URL = "https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets"


def cache_root() -> Path:
    override = os.environ.get("VFS_RANKING_CACHE")
    return Path(override) if override else Path.home() / ".cache" / "vfs" / "ranking"


def fetch(name: str, root: Path) -> Path:
    target = root / "beir" / name
    if (target / "corpus.jsonl").exists():
        print(f"{name}: present at {target}")  # noqa: T201
        return target
    url = f"{BASE_URL}/{name}.zip"
    print(f"{name}: downloading {url}")  # noqa: T201
    with urllib.request.urlopen(url, timeout=120) as response:
        payload = response.read()
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        archive.extractall(root / "beir")
    print(f"{name}: unpacked {len(payload) // 1024} KB into {target}")  # noqa: T201
    return target


def main(argv: list[str]) -> int:
    names = argv or list(DATASETS)
    unknown = [n for n in names if n not in DATASETS]
    if unknown:
        print(f"unknown dataset(s): {', '.join(unknown)}; choose from {', '.join(DATASETS)}")  # noqa: T201
        return 2
    root = cache_root()
    for name in names:
        fetch(name, root)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
