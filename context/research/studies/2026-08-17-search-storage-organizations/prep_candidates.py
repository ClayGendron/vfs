"""Nominate + fetch + verify the four bench rows; persist candidate sets.

Writes candidates.json: per row the fetched candidate list (doc id, entry_id
hex, path, size_bytes), matched line numbers per matched path, and sanity
counts (total matching lines must reproduce the earlier benchmark's counts).
"""

from __future__ import annotations

import json

from common import BENCH_ROWS, OUT, candidate_rows, connect, fetch_contents, match_lines, nominate

con = connect()
out = {}
for label, pattern, prefix, insensitive in BENCH_ROWS:
    doc_ids, stats = nominate(con, pattern)
    rows, truncated = candidate_rows(con, doc_ids, prefix)
    contents = fetch_contents(con, [r[1] for r in rows])
    matched = {}
    total_lines = 0
    total_fetch_bytes = 0
    mismatch = 0
    for _id, eid, path, size_bytes in rows:
        text = contents.get(eid)
        if text is None:
            continue
        blen = len(text.encode("utf-8"))
        if blen != size_bytes:
            mismatch += 1
        total_fetch_bytes += blen
        hits = match_lines(text, pattern, insensitive)
        if hits:
            matched[path] = hits
            total_lines += len(hits)
    out[label] = {
        "pattern": pattern,
        "prefix": prefix,
        "insensitive": insensitive,
        "nominate": stats,
        "truncated": truncated,
        "candidates": [
            {"id": r[0], "entry_id": r[1].hex(), "path": r[2], "size_bytes": r[3]} for r in rows
        ],
        "n_candidates": len(rows),
        "total_fetch_bytes": total_fetch_bytes,
        "size_bytes_mismatches": mismatch,
        "matched_files": len(matched),
        "matching_lines": total_lines,
        "matches": matched,
    }
    print(
        f"{label:28s} nominated={stats['nominated_docs']:6d} fetched={len(rows):6d} "
        f"bytes={total_fetch_bytes/1e6:8.1f}MB matched_files={len(matched):5d} lines={total_lines:6d} "
        f"trunc={truncated} size_mismatch={mismatch}"
    )

with open(f"{OUT}/candidates.json", "w") as f:
    json.dump(out, f)
print("wrote candidates.json")
