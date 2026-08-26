"""Portable lexical index experiment: build a (term, chunk, tf, weight) table
in sqlite from a real corpus, time the BM25 statement shapes, and export
tokens + rankings for the bm25s agreement check.

Run from the repo root with the project interpreter:

    uv run python context/research/studies/2026-08-26-glean/lexical-leg/build_and_time.py \
        --corpus ~/Git/Repos/linux/drivers/gpu --max-chunks 50000 \
        --out context/research/studies/2026-08-26-glean/lexical-leg/results

Chunks are minted by vfs's own production splitter (``Chunk.split_batch``), so
the units scored here are the rows the ``chunks`` table would hold. Plain
``sqlite3`` is used for the timing harness: the statements are portable
arithmetic + IN-list + GROUP BY, the same shape SQLAlchemy would emit.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import sqlite3
import statistics
import sys
import time
from collections import Counter
from pathlib import Path as FsPath

from vfs.models.chunk import Chunk
from vfs.paths import Path

K1 = 1.2
B = 0.75
EPOCH = 1
MEMBERSHIP_BUDGET = 1000  # Oracle's IN-list cap: the floor every allow-list chunk obeys.

_WORD = re.compile(r"[A-Za-z0-9_]+")
_CAMEL = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|[0-9]+")
_TEXT_EXTS = {
    "c", "h", "py", "md", "rs", "go", "js", "ts", "toml", "txt", "yaml", "yml", "json", "sh", "cfg", "ini",
    "html", "css", "sql", "rst", "cpp", "hpp", "cc", "java", "kt", "swift", "rb", "lua", "mk", "dts", "dtsi",
}


def tokenize(text: str) -> list[str]:
    """Code-aware bag of words: fold case, split snake_case/camelCase, keep the whole identifier too."""
    out: list[str] = []
    for match in _WORD.finditer(text):
        word = match.group()
        lowered = word.lower()
        if word[0].isdigit():
            out.append(lowered)
            continue
        parts = [p for p in word.split("_") if p]
        subs: list[str] = []
        for part in parts:
            subs.extend(_CAMEL.findall(part))
        if len(subs) > 1:
            out.append(lowered)
            out.extend(s.lower() for s in subs if len(s) > 1)
        else:
            out.append(lowered)
    return out


def load_corpus(root: FsPath, max_chunks: int, max_files: int | None) -> tuple[list[tuple[int, str, list[Chunk]]], dict]:
    """Walk *root*, split every text file with the production splitter, stop at *max_chunks*."""
    files: list[tuple[Path, str, str | None]] = []
    stats = {"files": 0, "bytes": 0}
    roots = [FsPath(r).expanduser() for r in str(root).split(",")]
    for sub in roots:
        for path in sorted(sub.rglob("*")):
            if not path.is_file() or any(part.startswith(".") for part in path.parts):
                continue
            ext = path.suffix.lstrip(".").lower() or None
            if ext not in _TEXT_EXTS:
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if not content.strip() or "\x00" in content or len(content) > 2 * 1024 * 1024:
                continue
            rel = "/" + sub.name + "/" + str(path.relative_to(sub)).replace(os.sep, "/")
            files.append((Path(rel), content, ext))
            if max_files and len(files) >= max_files:
                break
    split_t0 = time.perf_counter()
    entries: list[tuple[int, str, list[Chunk]]] = []
    total_chunks = 0
    batch = 256
    for start in range(0, len(files), batch):
        window = files[start : start + batch]
        for (vpath, content, _ext), pieces in zip(window, Chunk.split_batch(window), strict=True):
            entries.append((len(entries) + 1, str(vpath), pieces))
            total_chunks += len(pieces)
            stats["bytes"] += len(content)
        if total_chunks >= max_chunks:
            break
    stats["files"] = len(entries)
    stats["split_seconds"] = time.perf_counter() - split_t0
    stats["chunks"] = total_chunks
    return entries, stats


def build_index(entries: list[tuple[int, str, list[Chunk]]]) -> tuple[sqlite3.Connection, dict, list[list[str]], list[int], list[int]]:
    """Tokenize, compute df/idf/weights, and load the four portable tables."""
    con = sqlite3.connect(":memory:")
    con.executescript(
        """
        CREATE TABLE lex_docs(epoch INTEGER NOT NULL, chunk_id INTEGER NOT NULL, entry_id INTEGER NOT NULL,
                              dl INTEGER NOT NULL, PRIMARY KEY(epoch, chunk_id)) WITHOUT ROWID;
        CREATE INDEX ix_lex_docs_entry ON lex_docs(epoch, entry_id);
        CREATE TABLE lex_terms(epoch INTEGER NOT NULL, term TEXT NOT NULL, chunk_id INTEGER NOT NULL,
                               tf INTEGER NOT NULL, weight REAL NOT NULL,
                               PRIMARY KEY(epoch, term, chunk_id)) WITHOUT ROWID;
        CREATE TABLE lex_df(epoch INTEGER NOT NULL, term TEXT NOT NULL, df INTEGER NOT NULL, idf REAL NOT NULL,
                            PRIMARY KEY(epoch, term)) WITHOUT ROWID;
        CREATE TABLE lex_stats(epoch INTEGER PRIMARY KEY, n_docs INTEGER NOT NULL, avg_dl REAL NOT NULL);
        CREATE TABLE segments(segment TEXT NOT NULL, entry_id INTEGER NOT NULL, PRIMARY KEY(segment, entry_id)) WITHOUT ROWID;
        """
    )
    t0 = time.perf_counter()
    doc_tokens: list[list[str]] = []
    doc_rows: list[tuple[int, int, int, int]] = []
    tf_rows: list[tuple[str, int, int]] = []
    df: Counter[str] = Counter()
    chunk_entry: list[int] = []
    chunk_ids: list[int] = []
    seg_rows: set[tuple[str, int]] = set()
    chunk_id = 0
    for entry_id, vpath, pieces in entries:
        for seg in vpath.strip("/").split("/")[:-1]:
            seg_rows.add((seg, entry_id))
        for piece in pieces:
            chunk_id += 1
            toks = tokenize(piece.content)
            doc_tokens.append(toks)
            chunk_entry.append(entry_id)
            chunk_ids.append(chunk_id)
            counts = Counter(toks)
            doc_rows.append((EPOCH, chunk_id, entry_id, len(toks)))
            for term, tf in counts.items():
                tf_rows.append((term, chunk_id, tf))
                df[term] += 1
    tokenize_seconds = time.perf_counter() - t0
    n_docs = len(doc_rows)
    avg_dl = sum(r[3] for r in doc_rows) / max(1, n_docs)
    dl_by_chunk = {r[1]: r[3] for r in doc_rows}
    idf = {t: math.log(1 + (n_docs - d + 0.5) / (d + 0.5)) for t, d in df.items()}
    t1 = time.perf_counter()
    term_rows = []
    for term, cid, tf in tf_rows:
        dl = dl_by_chunk[cid]
        weight = idf[term] * (tf * (K1 + 1)) / (tf + K1 * (1 - B + B * dl / avg_dl))
        term_rows.append((EPOCH, term, cid, tf, weight))
    con.executemany("INSERT INTO lex_docs VALUES (?,?,?,?)", doc_rows)
    con.executemany("INSERT INTO lex_terms VALUES (?,?,?,?,?)", term_rows)
    con.executemany("INSERT INTO lex_df VALUES (?,?,?,?)", [(EPOCH, t, d, idf[t]) for t, d in df.items()])
    con.execute("INSERT INTO lex_stats VALUES (?,?,?)", (EPOCH, n_docs, avg_dl))
    con.executemany("INSERT INTO segments VALUES (?,?)", sorted(seg_rows))
    con.commit()
    insert_seconds = time.perf_counter() - t1
    pages, page_size = con.execute("PRAGMA page_count").fetchone()[0], con.execute("PRAGMA page_size").fetchone()[0]
    table_bytes = {name: size for name, size in con.execute("SELECT name, SUM(pgsize) FROM dbstat GROUP BY name")}
    # the normalized sibling: integer term ids instead of the term text on every row
    con.executescript(
        """
        CREATE TABLE lex_terms_norm(epoch INTEGER NOT NULL, term_id INTEGER NOT NULL, chunk_id INTEGER NOT NULL,
                                    tf INTEGER NOT NULL, weight REAL NOT NULL,
                                    PRIMARY KEY(epoch, term_id, chunk_id)) WITHOUT ROWID;
        CREATE TEMP TABLE termmap(term_id INTEGER PRIMARY KEY, term TEXT UNIQUE NOT NULL);
        INSERT INTO termmap(term) SELECT term FROM lex_df ORDER BY term;
        INSERT INTO lex_terms_norm SELECT t.epoch, m.term_id, t.chunk_id, t.tf, t.weight
            FROM lex_terms t JOIN termmap m ON m.term = t.term;
        DROP TABLE termmap;
        """
    )
    table_bytes["lex_terms_norm"] = con.execute("SELECT SUM(pgsize) FROM dbstat WHERE name = 'lex_terms_norm'").fetchone()[0]
    con.execute("DROP TABLE lex_terms_norm")
    stats = {
        "table_bytes": table_bytes,
        "n_chunks": n_docs,
        "n_terms_rows": len(term_rows),
        "n_vocab": len(df),
        "avg_dl": avg_dl,
        "tokenize_seconds": tokenize_seconds,
        "insert_seconds": insert_seconds,
        "db_bytes": pages * page_size,
        "tokens_total": sum(r[3] for r in doc_rows),
    }
    return con, stats, doc_tokens, chunk_ids, chunk_entry


# --- statement shapes ---------------------------------------------------------


def q_precomputed(n: int, scope: str = "") -> str:
    marks = ",".join("?" * n)
    return (
        f"SELECT t.chunk_id, SUM(t.weight) AS score FROM lex_terms t {scope} "
        f"WHERE t.epoch = ? AND t.term IN ({marks}) GROUP BY t.chunk_id ORDER BY score DESC, t.chunk_id LIMIT ?"
    )


def q_runtime(n: int, scope: str = "") -> str:
    marks = ",".join("?" * n)
    return (
        "SELECT t.chunk_id, SUM(f.idf * (t.tf * (1 + ?)) / (t.tf + ? * (1 - ? + ? * d.dl / s.avg_dl))) AS score "
        "FROM lex_terms t JOIN lex_docs d ON d.epoch = t.epoch AND d.chunk_id = t.chunk_id "
        "JOIN lex_df f ON f.epoch = t.epoch AND f.term = t.term JOIN lex_stats s ON s.epoch = t.epoch "
        f"{scope} WHERE t.epoch = ? AND t.term IN ({marks}) GROUP BY t.chunk_id ORDER BY score DESC, t.chunk_id LIMIT ?"
    )


def q_entry_maxp(n: int, scope: str = "") -> str:
    marks = ",".join("?" * n)
    return (
        "SELECT d.entry_id, MAX(c.score) AS score FROM ("
        f"SELECT t.chunk_id, SUM(t.weight) AS score FROM lex_terms t {scope} WHERE t.epoch = ? AND t.term IN ({marks}) "
        "GROUP BY t.chunk_id) c JOIN lex_docs d ON d.epoch = ? AND d.chunk_id = c.chunk_id "
        "GROUP BY d.entry_id ORDER BY score DESC, d.entry_id LIMIT ?"
    )


SCOPE_IDS = "JOIN lex_docs sd ON sd.epoch = t.epoch AND sd.chunk_id = t.chunk_id AND sd.entry_id IN ({marks})"
SCOPE_SEGMENT = (
    "JOIN lex_docs sd ON sd.epoch = t.epoch AND sd.chunk_id = t.chunk_id "
    "JOIN segments sg ON sg.entry_id = sd.entry_id AND sg.segment = ?"
)


def timed(con: sqlite3.Connection, sql: str, params: tuple, reps: int = 5) -> tuple[float, list]:
    best: list[float] = []
    rows: list = []
    for _ in range(reps):
        t0 = time.perf_counter()
        rows = con.execute(sql, params).fetchall()
        best.append(time.perf_counter() - t0)
    return statistics.median(best) * 1000, rows


def pick_queries(con: sqlite3.Connection, n_docs: int, rng: random.Random, per_arity: int) -> dict[int, list[list[str]]]:
    mid = [r[0] for r in con.execute("SELECT term FROM lex_df WHERE df BETWEEN ? AND ? AND length(term) >= 3",
                                     (max(2, n_docs * 0.002), n_docs * 0.05))]
    common = [r[0] for r in con.execute("SELECT term FROM lex_df WHERE df > ? AND length(term) >= 3", (n_docs * 0.2,))]
    rare = [r[0] for r in con.execute("SELECT term FROM lex_df WHERE df BETWEEN 1 AND ? AND length(term) >= 4",
                                      (max(1, n_docs * 0.002),))]
    queries: dict[int, list[list[str]]] = {}
    for arity in (1, 3, 6):
        qs = []
        for _ in range(per_arity):
            terms = rng.sample(mid, min(len(mid), arity))
            if arity >= 3 and common:
                terms[-1] = rng.choice(common)
            if arity == 6 and rare:
                terms[0] = rng.choice(rare)
            qs.append(terms)
        queries[arity] = qs
    return queries


def run_timings(con: sqlite3.Connection, queries: dict[int, list[list[str]]], entries: list, rng: random.Random) -> dict:
    n_entries = len(entries)
    out: dict[str, dict] = {}
    # allow-lists: 5% and 50% of entries, as id lists, chunked by the membership budget
    allow_small = sorted(rng.sample(range(1, n_entries + 1), max(1, n_entries // 20)))
    allow_half = sorted(rng.sample(range(1, n_entries + 1), max(1, n_entries // 2)))
    # one segment that covers a slice of the corpus
    seg = con.execute(
        "SELECT segment, COUNT(*) c FROM segments GROUP BY segment ORDER BY c DESC LIMIT 1 OFFSET 2"
    ).fetchone()
    segment, seg_entries = (seg[0], seg[1]) if seg else ("", 0)
    out["_allow_sizes"] = {"small": len(allow_small), "half": len(allow_half), "segment": segment, "segment_entries": seg_entries}
    out["_allow"] = {"small": allow_small, "half": allow_half, "segment": segment}
    for arity, qs in queries.items():
        shape_ms: dict[str, list[float]] = {k: [] for k in
                                           ("precomputed", "runtime", "entry_maxp", "scope_ids_small", "scope_ids_half", "scope_segment")}
        for terms in qs:
            n = len(terms)
            ms, _ = timed(con, q_precomputed(n), (EPOCH, *terms, 10))
            shape_ms["precomputed"].append(ms)
            ms, _ = timed(con, q_runtime(n), (K1, K1, B, B, EPOCH, *terms, 10))
            shape_ms["runtime"].append(ms)
            ms, _ = timed(con, q_entry_maxp(n), (EPOCH, *terms, EPOCH, 10))
            shape_ms["entry_maxp"].append(ms)
            for label, allow in (("scope_ids_small", allow_small), ("scope_ids_half", allow_half)):
                # the allow-list rides as IN-list chunks under the membership budget; results merge client-side
                total = 0.0
                for start in range(0, len(allow), MEMBERSHIP_BUDGET):
                    ids = allow[start : start + MEMBERSHIP_BUDGET]
                    sql = q_precomputed(n, SCOPE_IDS.format(marks=",".join("?" * len(ids))))
                    ms, _ = timed(con, sql, (*ids, EPOCH, *terms, 10))
                    total += ms
                shape_ms[label].append(total)
            ms, _ = timed(con, q_precomputed(n, SCOPE_SEGMENT), (segment, EPOCH, *terms, 10))
            shape_ms["scope_segment"].append(ms)
        out[str(arity)] = {k: {"median_ms": round(statistics.median(v), 3), "max_ms": round(max(v), 3)} for k, v in shape_ms.items()}
    return out


def export_rankings(con: sqlite3.Connection, queries: dict[int, list[list[str]]], k: int = 50) -> dict:
    """Top-k chunk rankings per query from the precomputed statement, for the bm25s comparison."""
    ranked = {}
    for arity, qs in queries.items():
        for i, terms in enumerate(qs):
            rows = con.execute(q_precomputed(len(terms)), (EPOCH, *terms, k)).fetchall()
            ranked[f"{arity}:{i}"] = {"terms": terms, "top": [[cid, score] for cid, score in rows]}
    return ranked


def overlay_cost(entries: list, con: sqlite3.Connection, rng: random.Random, n_dirty: int) -> dict:
    """Price the live-text fallback: tokenize + score *n_dirty* freshly written entries client-side."""
    sample = rng.sample(entries, min(n_dirty, len(entries)))
    n_docs, avg_dl = con.execute("SELECT n_docs, avg_dl FROM lex_stats WHERE epoch = ?", (EPOCH,)).fetchone()
    query = ["drm", "device", "init"]
    idf = {t: r[0] for t in query for r in con.execute("SELECT idf FROM lex_df WHERE epoch = ? AND term = ?", (EPOCH, t))}
    t0 = time.perf_counter()
    scored = 0
    for _eid, _vpath, pieces in sample:
        for piece in pieces:
            counts = Counter(tokenize(piece.content))
            dl = sum(counts.values())
            score = sum(idf.get(t, 0.0) * (counts[t] * (K1 + 1)) / (counts[t] + K1 * (1 - B + B * dl / avg_dl)) for t in query if t in counts)
            scored += score > 0
    return {"dirty_entries": len(sample), "chunks": sum(len(p) for _, _, p in sample), "seconds": round(time.perf_counter() - t0, 4), "hits": scored}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--max-chunks", type=int, default=50000)
    ap.add_argument("--max-files", type=int, default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--label", default=None)
    ap.add_argument("--export-tokens", action="store_true")
    args = ap.parse_args()
    rng = random.Random(7)
    out_dir = FsPath(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    label = args.label or f"{args.max_chunks}"

    entries, corpus_stats = load_corpus(FsPath(args.corpus).expanduser(), args.max_chunks, args.max_files)
    con, index_stats, doc_tokens, chunk_ids, chunk_entry = build_index(entries)
    n_docs = index_stats["n_chunks"]
    queries = pick_queries(con, n_docs, rng, per_arity=15)
    timings = run_timings(con, queries, entries, rng)
    incremental = {}
    # incremental alternative: delete + reinsert one entry's rows, 1,000 entries, timed.
    # Needs a chunk-keyed secondary index the epoch rebuild never needs; its cost is priced too.
    victims = rng.sample(entries, min(1000, len(entries)))
    t0 = time.perf_counter()
    con.execute("CREATE INDEX ix_lex_terms_chunk ON lex_terms(epoch, chunk_id)")
    incremental["secondary_index_seconds"] = round(time.perf_counter() - t0, 4)
    pages, page_size = con.execute("PRAGMA page_count").fetchone()[0], con.execute("PRAGMA page_size").fetchone()[0]
    incremental["db_bytes_with_index"] = pages * page_size
    # scope-driven shape: walk the allow-list's chunks via the chunk-keyed index, probe terms per chunk
    allow = timings.pop("_allow")
    driven: dict[str, dict[str, list[float]]] = {}
    for arity, qs in queries.items():
        shape_ms = {"scope_driven_small": [], "scope_driven_half": []}
        for terms in qs:
            n = len(terms)
            for shape, ids_all in (("scope_driven_small", allow["small"]), ("scope_driven_half", allow["half"])):
                total = 0.0
                for start in range(0, len(ids_all), MEMBERSHIP_BUDGET):
                    ids = ids_all[start : start + MEMBERSHIP_BUDGET]
                    sql = (
                        "SELECT t.chunk_id, SUM(t.weight) AS score FROM lex_docs sd "
                        "JOIN lex_terms t ON t.epoch = sd.epoch AND t.chunk_id = sd.chunk_id "
                        f"WHERE sd.epoch = ? AND sd.entry_id IN ({','.join('?' * len(ids))}) AND t.term IN ({','.join('?' * n)}) "
                        "GROUP BY t.chunk_id ORDER BY score DESC, t.chunk_id LIMIT ?"
                    )
                    ms, _ = timed(con, sql, (EPOCH, *ids, *terms, 10))
                    total += ms
                shape_ms[shape].append(total)
        driven[str(arity)] = {k: {"median_ms": round(statistics.median(v), 3), "max_ms": round(max(v), 3)} for k, v in shape_ms.items()}
    incremental["scope_driven_timings_ms"] = driven
    t0 = time.perf_counter()
    for eid, _vpath, pieces in victims:
        cids = [r[0] for r in con.execute("SELECT chunk_id FROM lex_docs WHERE epoch = ? AND entry_id = ?", (EPOCH, eid))]
        rows = con.execute(f"SELECT term, chunk_id, tf, weight FROM lex_terms WHERE epoch = ? AND chunk_id IN ({','.join('?' * len(cids))})", (EPOCH, *cids)).fetchall()
        con.execute(f"DELETE FROM lex_terms WHERE epoch = ? AND chunk_id IN ({','.join('?' * len(cids))})", (EPOCH, *cids))
        con.executemany("INSERT INTO lex_terms VALUES (?,?,?,?,?)", [(EPOCH, *r) for r in rows])
    con.commit()
    incremental["reinsert_1000_entries_seconds"] = round(time.perf_counter() - t0, 4)
    overlay = {n: overlay_cost(entries, con, rng, n) for n in (100, 1000)}

    report = {
        "label": label,
        "corpus": corpus_stats,
        "index": index_stats,
        "queries": {str(a): qs for a, qs in queries.items()},
        "timings_ms": timings,
        "incremental": incremental,
        "overlay_scan": overlay,
        "sqlite_version": sqlite3.sqlite_version,
    }
    (out_dir / f"report-{label}.json").write_text(json.dumps(report, indent=1))
    if args.export_tokens:
        (out_dir / f"tokens-{label}.json").write_text(json.dumps({"chunk_ids": chunk_ids, "chunk_entry": chunk_entry, "tokens": doc_tokens}))
        (out_dir / f"rankings-{label}.json").write_text(json.dumps(export_rankings(con, queries)))
    print(json.dumps({k: v for k, v in report.items() if k not in ("queries",)}, indent=1))


if __name__ == "__main__":
    sys.exit(main())
