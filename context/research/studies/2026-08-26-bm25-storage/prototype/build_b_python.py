"""Option B build in Python: one streaming pass over the store's chunks.

Per chunk: tokenize, count tf, append (delta, tf, dl) to the term's open
block; a block that reaches the block size is written at once. Only the
open blocks and one ``df`` per term are held — memory scales with the
vocabulary, not the postings. ``df``/``idf`` and ``avg_dl`` are fixed at
the end (no second pass: the block bound is (max_tf, min_dl), applied
with idf at query time).

    uv run --no-sync python build_b_python.py <out.sqlite> <block_size>
"""

from __future__ import annotations

import resource
import sqlite3
import sys
import time

from common import EPOCH_B, SCAN, STORE, idf, put_varint
from vfs.models.lexical import tokenize

SCHEMA = """
PRAGMA journal_mode = OFF; PRAGMA synchronous = OFF;
CREATE TABLE lex_postings (epoch INTEGER NOT NULL, term VARCHAR(64) NOT NULL, block_no INTEGER NOT NULL,
    doc_count INTEGER NOT NULL, max_tf INTEGER NOT NULL, min_dl INTEGER NOT NULL,
    doc_ids BLOB NOT NULL, tfs BLOB NOT NULL, dls BLOB NOT NULL,
    PRIMARY KEY (epoch, term, block_no)) WITHOUT ROWID;
CREATE TABLE lex_docs (epoch INTEGER NOT NULL, chunk_id BIGINT NOT NULL, entry_id BINARY(16) NOT NULL,
    dl INTEGER NOT NULL, PRIMARY KEY (epoch, chunk_id)) WITHOUT ROWID;
CREATE TABLE lex_df (epoch INTEGER NOT NULL, term VARCHAR(64) NOT NULL, df INTEGER NOT NULL, idf DOUBLE NOT NULL,
    PRIMARY KEY (epoch, term)) WITHOUT ROWID;
CREATE TABLE lex_stats (epoch INTEGER NOT NULL, n_docs INTEGER NOT NULL, avg_dl DOUBLE NOT NULL,
    PRIMARY KEY (epoch)) WITHOUT ROWID;
"""
INSERT_BLOCK = "INSERT INTO lex_postings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
WRITE_BATCH = 10_000


class TermAcc:
    __slots__ = ("block_no", "count", "df", "dls", "ids", "last_id", "max_tf", "min_dl", "tfs")

    def __init__(self) -> None:
        self.df = 0
        self.block_no = 0
        self.count = 0
        self.last_id = 0
        self.max_tf = 0
        self.min_dl = 1 << 31
        self.ids = bytearray()
        self.tfs = bytearray()
        self.dls = bytearray()

    def row(self, term: str) -> tuple:
        return (EPOCH_B, term, self.block_no, self.count, self.max_tf, self.min_dl, bytes(self.ids), bytes(self.tfs), bytes(self.dls))

    def reset(self) -> None:
        self.block_no += 1
        self.count = 0
        self.last_id = 0
        self.max_tf = 0
        self.min_dl = 1 << 31
        self.ids = bytearray()
        self.tfs = bytearray()
        self.dls = bytearray()


def build(out_path: str, block_size: int) -> dict:
    t_wall = time.perf_counter()
    src = sqlite3.connect(STORE)
    dst = sqlite3.connect(out_path)
    dst.executescript(SCHEMA)
    accs: dict[str, TermAcc] = {}
    pending_blocks: list[tuple] = []
    pending_docs: list[tuple] = []
    n_docs = total_dl = rows_written = 0
    tokenize_s = 0.0
    for chunk_id, entry_id, content in src.execute(SCAN):
        t0 = time.perf_counter()
        tokens = tokenize(content)
        tokenize_s += time.perf_counter() - t0
        dl = len(tokens)
        counts: dict[str, int] = {}
        for term in tokens:
            counts[term] = counts.get(term, 0) + 1
        for term, tf in counts.items():
            acc = accs.get(term)
            if acc is None:
                acc = accs[term] = TermAcc()
            put_varint(acc.ids, chunk_id - acc.last_id)
            put_varint(acc.tfs, tf)
            put_varint(acc.dls, dl)
            acc.last_id = chunk_id
            acc.count += 1
            acc.df += 1
            if tf > acc.max_tf:
                acc.max_tf = tf
            if dl < acc.min_dl:
                acc.min_dl = dl
            if acc.count == block_size:
                pending_blocks.append(acc.row(term))
                acc.reset()
        pending_docs.append((EPOCH_B, chunk_id, entry_id, dl))
        n_docs += 1
        total_dl += dl
        if len(pending_blocks) >= WRITE_BATCH:
            dst.executemany(INSERT_BLOCK, pending_blocks)
            rows_written += len(pending_blocks)
            pending_blocks = []
        if len(pending_docs) >= WRITE_BATCH:
            dst.executemany("INSERT INTO lex_docs VALUES (?, ?, ?, ?)", pending_docs)
            pending_docs = []
    dst.executemany(INSERT_BLOCK, pending_blocks)
    rows_written += len(pending_blocks)
    dst.executemany("INSERT INTO lex_docs VALUES (?, ?, ?, ?)", pending_docs)
    # Trailing partial blocks and df/idf, in term order.
    tail = []
    dfs = []
    for term in sorted(accs):
        acc = accs[term]
        dfs.append((EPOCH_B, term, acc.df, idf(acc.df, n_docs)))
        if acc.count:
            tail.append(acc.row(term))
    dst.executemany(INSERT_BLOCK, tail)
    rows_written += len(tail)
    dst.executemany("INSERT INTO lex_df VALUES (?, ?, ?, ?)", dfs)
    dst.execute("INSERT INTO lex_stats VALUES (?, ?, ?)", (EPOCH_B, n_docs, total_dl / n_docs))
    dst.commit()
    wall = time.perf_counter() - t_wall
    blob_bytes = dst.execute("SELECT SUM(LENGTH(doc_ids) + LENGTH(tfs) + LENGTH(dls)) FROM lex_postings").fetchone()[0]
    dst.close()
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {
        "wall_s": round(wall, 3),
        "tokenize_s": round(tokenize_s, 3),
        "n_docs": n_docs,
        "total_tokens": total_dl,
        "terms": len(accs),
        "block_rows": rows_written,
        "blob_bytes": blob_bytes,
        "block_size": block_size,
        "peak_rss_mb": round(rss / 2**20, 1),
    }


if __name__ == "__main__":
    import json
    from pathlib import Path

    out = sys.argv[1]
    Path(out).unlink(missing_ok=True)
    print(json.dumps(build(out, int(sys.argv[2]))))
