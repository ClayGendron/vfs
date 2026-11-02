"""Shared pieces for the delta-segment prototype.

Synthetic corpus (deterministic per doc id and version), a sqlite posting
table keyed (segment, gram_key), delta/base segment builders on top of the
real vfs engine, a Python varint decoder, and grep-like gram selection.
"""

from __future__ import annotations

import random
import re
import sqlite3
import time
from dataclasses import dataclass, field

from vfs.models.code_grams import GramAnd, GramAny, GramOr, build_code_gram_query, folded_bytes
from vfs.models.postings import encode_postings, postings_builder
from vfs.native import extension

SEED = 20261031
POSTING_BATCH_BYTES = 1 << 20  # same drain cap as indexing.py
INTERSECT_GRAMS = 4  # grep's _INTERSECT_GRAMS
CANDIDATE_BUDGET = 25_000
VERIFY_SAMPLE = 3000

# ---------------------------------------------------------------------------
# Corpus
# ---------------------------------------------------------------------------

_rng = random.Random(SEED)
_LETTERS = "abcdefghijklmnopqrstuvwxyz"


def _word(rng: random.Random, lo: int = 3, hi: int = 9) -> str:
    return "".join(rng.choice(_LETTERS) for _ in range(rng.randint(lo, hi)))


# Prose vocabulary (Zipf-ish), identifiers, and a big pool of rare identifiers.
PROSE_VOCAB = [_word(_rng) for _ in range(6000)]
PROSE_WEIGHTS = [1.0 / (i + 1) ** 0.9 for i in range(len(PROSE_VOCAB))]
IDENTS = [f"{_word(_rng, 3, 7)}_{_word(_rng, 3, 7)}" for _ in range(3000)]
IDENT_WEIGHTS = [1.0 / (i + 1) ** 0.8 for i in range(len(IDENTS))]
RARE_POOL = [f"fn_{_rng.randrange(16**6):06x}" for _ in range(60_000)]
KEYWORDS = ["def", "return", "self", "import", "class", "if", "for", "while", "yield", "async", "await", "raise"]
_CUM_PROSE = list(_accum for _accum in __import__("itertools").accumulate(PROSE_WEIGHTS))
_CUM_IDENT = list(__import__("itertools").accumulate(IDENT_WEIGHTS))


def make_doc(doc_id: int, version: int = 0) -> str:
    """A deterministic ~2-8 KB prose+code document for (doc_id, version)."""
    rng = random.Random((doc_id * 1_000_003) ^ (version * 7_919) ^ SEED)
    target = rng.randint(2000, 8000)
    out: list[str] = []
    size = 0
    rare = rng.sample(RARE_POOL, 2)
    while size < target:
        if rng.random() < 0.55:
            words = rng.choices(PROSE_VOCAB, cum_weights=_CUM_PROSE, k=rng.randint(8, 18))
            if rng.random() < 0.08:
                words.append(rare[0])
            line = " ".join(words).capitalize() + "."
        else:
            idents = rng.choices(IDENTS, cum_weights=_CUM_IDENT, k=3)
            kind = rng.randrange(4)
            if kind == 0:
                line = f"def {idents[0]}(self, {idents[1]}):"
            elif kind == 1:
                line = f"    return self.{idents[0]}({idents[1]}, {idents[2]})"
            elif kind == 2:
                line = f"    {idents[0]} = {rare[1] if rng.random() < 0.1 else idents[1]}.{idents[2]}()"
            else:
                line = f"    if {idents[0]} is None: raise ValueError({idents[1]!r})"
        out.append(line)
        size += len(line) + 1
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# Posting store: sqlite, keyed (segment, gram_key)
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS posting_list (
    segment INTEGER NOT NULL,
    gram_key INTEGER NOT NULL,
    postings BLOB NOT NULL,
    doc_count INTEGER NOT NULL,
    byte_size INTEGER NOT NULL,
    PRIMARY KEY (segment, gram_key)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS manifest (
    segment INTEGER PRIMARY KEY,
    doc_count INTEGER NOT NULL,
    row_count INTEGER NOT NULL,
    byte_total INTEGER NOT NULL
);
"""


def open_store(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.executescript("PRAGMA journal_mode=WAL; PRAGMA synchronous=OFF;")
    conn.executescript(SCHEMA)
    return conn


@dataclass
class BuildTiming:
    docs: int = 0
    gen_s: float = 0.0  # corpus generation (NOT part of index cost)
    fold_s: float = 0.0
    feed_s: float = 0.0
    drain_s: float = 0.0
    insert_s: float = 0.0
    rows: int = 0
    bytes: int = 0
    doc_bytes: int = 0

    @property
    def index_s(self) -> float:
        return self.fold_s + self.feed_s + self.drain_s + self.insert_s


def build_segment(
    conn: sqlite3.Connection,
    segment: int,
    docs: list[tuple[int, int]],
    *,
    feed_chunk: int = 2000,
) -> BuildTiming:
    """Build one segment over `docs` = [(doc_id, version)] (sorted by id) into the store.

    Phases are timed separately: generation (excluded from the index
    cost), folding, builder feed, drain, sqlite insert.
    """
    t = BuildTiming(docs=len(docs))
    builder = postings_builder()
    docs = sorted(docs)
    for start in range(0, len(docs), feed_chunk):
        chunk = docs[start : start + feed_chunk]
        t0 = time.perf_counter()
        texts = [make_doc(d, v) for d, v in chunk]
        t1 = time.perf_counter()
        folded = [(d, folded_bytes(text)) for (d, _v), text in zip(chunk, texts)]
        t2 = time.perf_counter()
        builder.add_docs(folded)
        t3 = time.perf_counter()
        t.gen_s += t1 - t0
        t.fold_s += t2 - t1
        t.feed_s += t3 - t2
        t.doc_bytes += sum(len(b) for _, b in folded)
    cur = conn.cursor()
    cur.execute("BEGIN")
    while True:
        t0 = time.perf_counter()
        batch = builder.next_batch(POSTING_BATCH_BYTES)
        t1 = time.perf_counter()
        t.drain_s += t1 - t0
        if batch is None:
            break
        rows = [(segment, gram, blob, count, len(blob)) for gram, blob, count in batch]
        t2 = time.perf_counter()
        cur.executemany("INSERT INTO posting_list VALUES (?,?,?,?,?)", rows)
        t.insert_s += time.perf_counter() - t2
        t.rows += len(rows)
        t.bytes += sum(len(blob) for _, blob, _ in batch)
    cur.execute("INSERT OR REPLACE INTO manifest VALUES (?,?,?,?)", (segment, len(docs), t.rows, t.bytes))
    cur.execute("COMMIT")
    return t


def live_segments(conn: sqlite3.Connection) -> list[int]:
    return [r[0] for r in conn.execute("SELECT segment FROM manifest ORDER BY segment")]


# ---------------------------------------------------------------------------
# Codec helpers (Python side; the engine decodes in the kernel)
# ---------------------------------------------------------------------------


def decode_varints(blob: bytes) -> list[int]:
    out: list[int] = []
    value = 0
    shift = 0
    for byte in blob:
        value |= (byte & 0x7F) << shift
        if byte & 0x80:
            shift += 7
        else:
            out.append(value)
            value = 0
            shift = 0
    return out


def decode_postings(blob: bytes) -> list[int]:
    values = decode_varints(blob)
    count, deltas = values[0], values[1:]
    assert len(deltas) == count, (count, len(deltas))
    ids: list[int] = []
    prev = 0
    for d in deltas:
        prev += d
        ids.append(prev)
    return ids


def union_blobs(blobs: list[bytes], drop: set[int] | None = None) -> bytes:
    """Union several sorted-id blobs (disjoint or not) into one blob, optionally dropping ids."""
    ids: set[int] = set()
    for blob in blobs:
        ids.update(decode_postings(blob))
    if drop:
        ids -= drop
    return encode_postings(sorted(ids))


# ---------------------------------------------------------------------------
# Query planning, grep-style
# ---------------------------------------------------------------------------


def plan_groups(pattern: str, fixed: bool = False) -> list[tuple[int, ...]] | None:
    plan = build_code_gram_query(pattern, fixed_strings=fixed)
    if isinstance(plan, GramAny):
        return None

    def groups(p) -> list[tuple[int, ...]]:
        if isinstance(p, GramOr):
            out = []
            for b in p.branches:
                out.extend(groups(b))
            return out
        assert isinstance(p, GramAnd)
        return [tuple(sorted(p.grams))]

    return groups(plan)


def fetch_meta(conn: sqlite3.Connection, segments: list[int], grams: list[int]) -> dict[tuple[int, int], tuple[int, int]]:
    """(segment, gram) -> (doc_count, byte_size) for the grams present."""
    meta: dict[tuple[int, int], tuple[int, int]] = {}
    q = f"SELECT segment, gram_key, doc_count, byte_size FROM posting_list WHERE segment IN ({','.join('?' * len(segments))}) AND gram_key IN ({','.join('?' * len(grams))})"
    for seg, gram, dc, bs in conn.execute(q, [*segments, *grams]):
        meta[(seg, gram)] = (dc, bs)
    return meta


def choose_grams(groups: list[tuple[int, ...]], total_count: dict[int, int]) -> list[list[int] | None]:
    """grep's rarest-first choice, up to INTERSECT_GRAMS per group, by summed doc_count across segments."""
    out: list[list[int] | None] = []
    for group in groups:
        if any(total_count.get(g, 0) == 0 for g in group):
            out.append(None)
            continue
        ranked = sorted(group, key=lambda g: total_count[g])
        out.append(ranked[:INTERSECT_GRAMS])
    return out


@dataclass
class FetchResult:
    rows: int = 0
    bytes: int = 0
    fetch_s: float = 0.0
    blobs: dict[tuple[int, int], bytes] = field(default_factory=dict)


def fetch_blobs(conn: sqlite3.Connection, segments: list[int], grams: list[int]) -> FetchResult:
    """All (segment, gram) blobs for the wanted grams across the live segments, one statement."""
    res = FetchResult()
    t0 = time.perf_counter()
    q = f"SELECT segment, gram_key, postings FROM posting_list WHERE segment IN ({','.join('?' * len(segments))}) AND gram_key IN ({','.join('?' * len(grams))})"
    for seg, gram, blob in conn.execute(q, [*segments, *grams]):
        res.blobs[(seg, gram)] = blob
        res.rows += 1
        res.bytes += len(blob)
    res.fetch_s = time.perf_counter() - t0
    return res


def candidates_merge_python(chosen: list[list[int] | None], segments: list[int], blobs: dict) -> tuple[list[int], int, float, float]:
    """Strategy (a): per gram, decode every segment's blob in Python, union, re-encode; one blob per gram to the kernel."""
    t0 = time.perf_counter()
    merged: dict[int, bytes] = {}
    for group in chosen:
        if not group:
            continue
        for g in group:
            if g in merged:
                continue
            parts = [blobs[(s, g)] for s in segments if (s, g) in blobs]
            merged[g] = union_blobs(parts) if len(parts) != 1 else parts[0]
    fed = [[merged[g] for g in group] for group in chosen if group]
    t1 = time.perf_counter()
    ids, total = extension().candidate_ids(fed, None, CANDIDATE_BUDGET)
    t2 = time.perf_counter()
    return ids, total, t1 - t0, t2 - t1


def candidates_kernel_groups(chosen: list[list[int] | None], segments: list[int], blobs: dict) -> tuple[list[int], int, float]:
    """Strategy (b'): one kernel group per (AND-group, segment). Sound because a doc lives whole in one segment:
    AND within a segment's blobs, OR across segments. No Python merge."""
    t0 = time.perf_counter()
    fed: list[list[bytes]] = []
    for group in chosen:
        if not group:
            continue
        for s in segments:
            seg_blobs = [blobs.get((s, g)) for g in group]
            if any(b is None for b in seg_blobs):
                continue  # a required gram absent in this segment: no doc of it can match
            fed.append(seg_blobs)
    ids, total = extension().candidate_ids(fed, None, CANDIDATE_BUDGET)
    return ids, total, time.perf_counter() - t0


def verify(pattern: str, fixed: bool, doc_ids: list[int], current_version: dict[int, int | None]) -> tuple[int, int, int]:
    """(true matches, ghosts of rewritten/deleted docs, other false positives) under the current corpus state."""
    rx = re.compile(re.escape(pattern) if fixed else pattern, re.IGNORECASE)
    true = ghosts = fp = 0
    if len(doc_ids) > VERIFY_SAMPLE:  # sample: regenerating a body costs ~200 us; counts are scaled by the caller
        doc_ids = random.Random(1).sample(doc_ids, VERIFY_SAMPLE)
    for d in doc_ids:
        v = current_version.get(d, 0)
        if v is None:  # deleted
            ghosts += 1
            continue
        if rx.search(make_doc(d, v)):
            true += 1
        elif v > 0:
            ghosts += 1  # stale posting from the pre-rewrite body (or an honest fp on a rewritten doc)
        else:
            fp += 1
    return true, ghosts, fp
