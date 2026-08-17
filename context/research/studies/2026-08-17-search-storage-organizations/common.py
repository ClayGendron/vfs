"""Shared helpers: replicate the grep pipeline's nomination against the raw store.

Doc ids in vfs_grams_posting_list are vfs.id surrogate ids (entries table).
Nomination mirrors grep.py: folded gram plan -> posting meta -> rarest-first
<=4 grams per AND group under the 4MB byte budget -> decode + intersect ->
union across groups. Scope is applied as a path-prefix filter on the entry
rows (equivalent to the fetched candidate set: gates run before content
fetch). The candidate budget (25,000, by ascending doc id) replicates
truncation for unscoped-wide rows.
"""

from __future__ import annotations

import re
import sqlite3

import numpy as np

from vfs.models.code_grams import GramOr, build_code_gram_query
from vfs.models.postings import decode_postings

SP = "/private/tmp/claude-501/-Users-claygendron-Git-Repos-vfs/0e5b6050-047e-4aa4-9c2b-859dd3ac7aa4/scratchpad"
DB = f"{SP}/linux-bench/linux.sqlite"
OUT = f"{SP}/storage-org-arith"

POSTING_BYTE_BUDGET = 4 * 1024 * 1024
INTERSECT_GRAMS = 4
CANDIDATE_BUDGET = 25_000

BENCH_ROWS = [
    # (label, pattern, path_prefix or None, case-insensitive verify?)
    ("mutex_lock@drm", "mutex_lock", "/drivers/gpu/drm/", True),   # smart case -> insensitive
    ("kzalloc@drivers/net", "kzalloc", "/drivers/net/", True),
    ("EXPORT_SYMBOL_GPL@drivers", "EXPORT_SYMBOL_GPL", "/drivers/", False),  # has uppercase -> sensitive
    ("copyright -i unscoped", "copyright", None, True),
]


def connect(path: str = DB) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.execute("PRAGMA query_only=1")
    return con


def plan_groups(pattern: str) -> list[tuple[int, ...]]:
    plan = build_code_gram_query(pattern)
    if plan.is_any():
        return []
    if isinstance(plan, GramOr):
        return [tuple(sorted(b.required_grams())) for b in plan.branches]
    return [tuple(sorted(plan.required_grams()))]


def choose_grams(groups, meta):
    """Rarest-first <=4 grams per group under the shared byte budget (grep.py law)."""
    budget = POSTING_BYTE_BUDGET
    out = []
    for group in groups:
        if any(g not in meta for g in group):
            out.append(None)
            continue
        chosen = []
        for gram in sorted(group, key=lambda k: meta[k][0]):
            size = meta[gram][1]
            if chosen and (len(chosen) >= INTERSECT_GRAMS or size > budget):
                break
            chosen.append(gram)
            budget -= size
        out.append(chosen)
    return out


def nominate(con: sqlite3.Connection, pattern: str):
    """Return (sorted candidate doc ids ndarray, stats dict)."""
    groups = plan_groups(pattern)
    grams = sorted({g for grp in groups for g in grp})
    meta = {}
    for row in con.execute(
        f"SELECT gram_key, doc_count, byte_size FROM vfs_grams_posting_list "
        f"WHERE epoch=1 AND gram_key IN ({','.join(map(str, grams))})"
    ):
        meta[row[0]] = (row[1], row[2])
    chosen = choose_grams(groups, meta)
    wanted = sorted({g for grp in chosen if grp for g in grp})
    blobs = {}
    for row in con.execute(
        f"SELECT gram_key, postings FROM vfs_grams_posting_list "
        f"WHERE epoch=1 AND gram_key IN ({','.join(map(str, wanted))})"
    ):
        blobs[row[0]] = row[1]
    parts = [np.empty(0, dtype=np.int64)]
    posting_bytes = 0
    for grp in chosen:
        if not grp:
            continue
        ids = None
        for gram in grp:
            posting_bytes += len(blobs[gram])
            decoded = decode_postings(blobs[gram])
            ids = decoded if ids is None else np.intersect1d(ids, decoded, assume_unique=True)
            if ids.size == 0:
                break
        if ids is not None:
            parts.append(ids)
    doc_ids = np.unique(np.concatenate(parts))
    stats = {
        "plan_total_grams": len(grams),
        "chosen_grams": wanted,
        "chosen_gram_count": len(wanted),
        "posting_bytes_fetched": posting_bytes,
        "nominated_docs": int(doc_ids.size),
    }
    return doc_ids, stats


def candidate_rows(con, doc_ids, prefix, budget=CANDIDATE_BUDGET):
    """(id, entry_id, path, size_bytes) rows the pipeline would content-fetch."""
    ids = doc_ids.tolist()
    truncated = False
    if len(ids) > budget:
        ids = ids[:budget]
        truncated = True
    rows = []
    for i in range(0, len(ids), 500):
        chunk = ids[i : i + 500]
        q = (
            f"SELECT id, entry_id, path, size_bytes FROM vfs "
            f"WHERE id IN ({','.join(map(str, chunk))}) AND encoded=1 AND kind='file'"
        )
        rows.extend(con.execute(q).fetchall())
    if prefix is not None:
        rows = [r for r in rows if r[2].startswith(prefix)]
    rows.sort(key=lambda r: r[2])  # path order, the pipeline's verify order
    return rows, truncated


def fetch_contents(con, entry_ids):
    """entry_id -> content for a list of BLOB entry ids (chunks of 500)."""
    out = {}
    for i in range(0, len(entry_ids), 500):
        chunk = entry_ids[i : i + 500]
        q = f"SELECT entry_id, content FROM vfs_content WHERE entry_id IN ({','.join('?' * len(chunk))})"
        for eid, content in con.execute(q, chunk):
            out[eid] = content
    return out


def match_lines(text: str, pattern: str, insensitive: bool) -> list[int]:
    """1-based matching line numbers under the grep line law."""
    rx = re.compile(re.escape(pattern) if _is_literal(pattern) else pattern,
                    re.IGNORECASE if insensitive else 0)
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return [i for i, line in enumerate(lines, start=1) if rx.search(line)]


def _is_literal(pattern: str) -> bool:
    return not set(pattern) & set(r".*+?[](){}|^$\\")
