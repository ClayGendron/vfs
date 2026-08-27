"""The harness's corpora: the frozen vfs-native golden set and the BEIR pair.

A :class:`Corpus` is documents, queries and graded relevance judgments
with two id spaces: the corpus's own doc id (a repo-relative path for
vfs-native, BEIR's ``_id`` otherwise) and the vfs path each document is
written under. Runs and qrels speak doc ids; the driver speaks paths.
"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import NamedTuple

import pytest

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "ranking"
VFS_NATIVE = FIXTURES / "vfs_native"
BEIR_NAMES = ("scifact", "nfcorpus")


class Corpus(NamedTuple):
    """Documents, queries and qrels; ``paths`` maps a doc id to its vfs path."""

    name: str
    docs: dict[str, str]
    paths: dict[str, str]
    queries: dict[str, str]
    qrels: dict[str, dict[str, int]]

    @property
    def doc_of(self) -> dict[str, str]:
        """The inverse of ``paths``: vfs path → doc id."""
        return {path: doc for doc, path in self.paths.items()}


def cache_root() -> Path:
    """Where the BEIR pair lives: ``$VFS_RANKING_CACHE`` or ``~/.cache/vfs/ranking``."""
    override = os.environ.get("VFS_RANKING_CACHE")
    return Path(override) if override else Path.home() / ".cache" / "vfs" / "ranking"


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def vfs_native() -> Corpus:
    """The frozen snapshot of ``docs/`` + ``context/`` with its hand labels."""
    corpus_dir = VFS_NATIVE / "corpus"
    docs = {
        str(path.relative_to(corpus_dir)): path.read_text(encoding="utf-8") for path in sorted(corpus_dir.rglob("*.md"))
    }
    with (VFS_NATIVE / "queries.tsv").open(encoding="utf-8", newline="") as handle:
        queries = {row["qid"]: row["query"] for row in csv.DictReader(handle, delimiter="\t")}
    return Corpus(
        "vfs_native", docs, {doc: f"/{doc}" for doc in docs}, queries, read_trec_qrels(VFS_NATIVE / "qrels.txt")
    )


def beir(name: str) -> Corpus:
    """A BEIR dataset from the cache, or a pytest skip when it is not there."""
    root = cache_root() / "beir" / name
    if not (root / "corpus.jsonl").exists():
        pytest.skip(f"BEIR {name} is not cached at {root}; run scripts/fetch_beir.py")
    docs: dict[str, str] = {}
    with (root / "corpus.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            title = row.get("title") or ""
            docs[row["_id"]] = f"{title}\n\n{row['text']}" if title else row["text"]
    qrels: dict[str, dict[str, int]] = {}
    with (root / "qrels" / "test.tsv").open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            qrels.setdefault(row["query-id"], {})[row["corpus-id"]] = int(row["score"])
    queries: dict[str, str] = {}
    with (root / "queries.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if row["_id"] in qrels:
                queries[row["_id"]] = row["text"]
    return Corpus(name, docs, {doc: f"/{doc}.txt" for doc in docs}, queries, qrels)


def read_trec_qrels(path: Path) -> dict[str, dict[str, int]]:
    """``qid 0 docid grade`` lines → nested dict; zero grades are kept."""
    qrels: dict[str, dict[str, int]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        qid, _iteration, doc, grade = line.split()
        qrels.setdefault(qid, {})[doc] = int(grade)
    return qrels
