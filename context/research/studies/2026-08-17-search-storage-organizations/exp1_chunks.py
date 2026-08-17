"""Experiment 1: chunk-granularity nomination bound + posting-side cost.

Per bench row: bytes fetched today (full candidate bodies) vs
(a) ideal bound - bytes of only the chunks containing >=1 matching line,
(b) realistic  - bytes of chunks whose folded content contains all chosen
    grams of at least one AND group (what chunk-granularity postings with
    the same rarest-4 ladder would actually nominate).
Posting-side: distinct (gram,file) vs (gram,chunk) pairs on a ~500-file
stratified sample (every Nth encoded file by id).
"""

from __future__ import annotations

import json

import numpy as np

from common import OUT, connect
from vfs.native import folded_bytes

con = connect()


def gram_array(data: bytes) -> np.ndarray:
    if len(data) < 3:
        return np.empty(0, dtype=np.int64)
    d = np.frombuffer(data, dtype=np.uint8).astype(np.int64)
    return (d[:-2] << 16) | (d[1:-1] << 8) | d[2:]


with open(f"{OUT}/candidates.json") as f:
    cand = json.load(f)

results = {}
for label, row in cand.items():
    matches = row["matches"]
    chosen = row["nominate"]["chosen_grams"]
    chosen_arr = np.array(chosen, dtype=np.int64)
    # --- ideal bound: chunks containing >=1 matching line, matched files only
    ideal_bytes = 0
    match_chunks = 0
    total_chunks_matched_files = 0
    paths = list(matches)
    path_to_eid = {c["path"]: c["entry_id"] for c in row["candidates"]}
    for i in range(0, len(paths), 400):
        batch = paths[i : i + 400]
        eids = [bytes.fromhex(path_to_eid[p]) for p in batch]
        eid_to_path = {e: p for e, p in zip(eids, batch)}
        q = (
            f"SELECT entry_id, line_start, line_end, content FROM vfs_chunks "
            f"WHERE entry_id IN ({','.join('?' * len(eids))})"
        )
        for eid, ls, le, content in con.execute(q, eids):
            total_chunks_matched_files += 1
            lines = matches[eid_to_path[bytes(eid)]]
            if any(ls <= ln <= le for ln in lines):
                ideal_bytes += len(content.encode("utf-8"))
                match_chunks += 1
    # --- realistic: chunks of ALL candidates passing the chosen-gram AND test
    real_bytes = 0
    real_chunks = 0
    total_chunks_all = 0
    all_eids = [bytes.fromhex(c["entry_id"]) for c in row["candidates"]]
    for i in range(0, len(all_eids), 400):
        batch = all_eids[i : i + 400]
        q = f"SELECT line_start, content FROM vfs_chunks WHERE entry_id IN ({','.join('?' * len(batch))})"
        for _ls, content in con.execute(q, batch):
            total_chunks_all += 1
            g = gram_array(folded_bytes(content))
            if np.isin(chosen_arr, g).all():
                real_bytes += len(content.encode("utf-8"))
                real_chunks += 1
    total = row["total_fetch_bytes"]
    results[label] = {
        "fetch_bytes_today": total,
        "ideal_match_chunk_bytes": ideal_bytes,
        "ideal_reduction_factor": total / ideal_bytes if ideal_bytes else None,
        "match_chunks": match_chunks,
        "chunks_in_matched_files": total_chunks_matched_files,
        "realistic_chunk_bytes": real_bytes,
        "realistic_reduction_factor": total / real_bytes if real_bytes else None,
        "realistic_chunks": real_chunks,
        "chunks_in_all_candidates": total_chunks_all,
    }
    print(
        f"{label:28s} today={total/1e6:7.1f}MB ideal={ideal_bytes/1e6:7.1f}MB ({total/max(ideal_bytes,1):5.1f}x) "
        f"realistic={real_bytes/1e6:7.1f}MB ({total/max(real_bytes,1):5.1f}x) "
        f"chunks {match_chunks}/{real_chunks}/{total_chunks_all}"
    )

# --- posting-side cost on a ~500-file sample
ids = [r[0] for r in con.execute("SELECT id FROM vfs WHERE kind='file' AND encoded=1 ORDER BY id")]
sample = ids[:: max(1, len(ids) // 500)][:500]
gram_file_pairs = 0
gram_chunk_pairs = 0
n_chunks = 0
sample_eids = []
for i in range(0, len(sample), 400):
    chunk = sample[i : i + 400]
    q = f"SELECT entry_id FROM vfs WHERE id IN ({','.join(map(str, chunk))})"
    sample_eids.extend(r[0] for r in con.execute(q))
for i in range(0, len(sample_eids), 200):
    batch = sample_eids[i : i + 200]
    q = f"SELECT entry_id, content FROM vfs_content WHERE entry_id IN ({','.join('?' * len(batch))})"
    for _eid, content in con.execute(q, batch):
        gram_file_pairs += np.unique(gram_array(folded_bytes(content))).size
    q = f"SELECT content FROM vfs_chunks WHERE entry_id IN ({','.join('?' * len(batch))})"
    for (content,) in con.execute(q, batch):
        n_chunks += 1
        gram_chunk_pairs += np.unique(gram_array(folded_bytes(content))).size

results["posting_sample"] = {
    "sample_files": len(sample_eids),
    "sample_chunks": n_chunks,
    "gram_file_pairs": int(gram_file_pairs),
    "gram_chunk_pairs": int(gram_chunk_pairs),
    "posting_multiplier": gram_chunk_pairs / gram_file_pairs,
}
print(
    f"sample: {len(sample_eids)} files, {n_chunks} chunks, (gram,file)={gram_file_pairs:,} "
    f"(gram,chunk)={gram_chunk_pairs:,} multiplier={gram_chunk_pairs / gram_file_pairs:.2f}x"
)

with open(f"{OUT}/exp1_chunks.json", "w") as f:
    json.dump(results, f, indent=1)
print("wrote exp1_chunks.json")
