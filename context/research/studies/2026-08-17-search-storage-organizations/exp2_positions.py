"""Experiment 2: positional-postings cost on a ~500-file sample.

Counts total trigram occurrences vs distinct (gram, doc) pairs, computes the
exact varint size of within-doc delta-encoded positions (plus a per-pair
count varint), measures the store's actual blob bytes for the sample's
grams, and projects the index-size multiplier at corpus scale.
"""

from __future__ import annotations

import json

import numpy as np

from common import OUT, connect
from vfs.native import folded_bytes


def gram_array(data: bytes) -> np.ndarray:
    if len(data) < 3:
        return np.empty(0, dtype=np.int64)
    d = np.frombuffer(data, dtype=np.uint8).astype(np.int64)
    return (d[:-2] << 16) | (d[1:-1] << 8) | d[2:]


def varint_bytes(vals: np.ndarray) -> int:
    """Total LEB128 bytes for an array of non-negative ints."""
    if vals.size == 0:
        return 0
    b = np.ones(vals.size, dtype=np.int64)
    for k in (7, 14, 21, 28, 35):
        b += vals >= (1 << k)
    return int(b.sum())


con = connect()
ids = [r[0] for r in con.execute("SELECT id FROM vfs WHERE kind='file' AND encoded=1 ORDER BY id")]
sample = ids[:: max(1, len(ids) // 500)][:500]
eids = []
for i in range(0, len(sample), 400):
    chunk = sample[i : i + 400]
    eids.extend(r[0] for r in con.execute(f"SELECT entry_id FROM vfs WHERE id IN ({','.join(map(str, chunk))})"))

occurrences = 0
pairs = 0
pos_delta_bytes = 0
count_bytes = 0
sample_grams: set[int] = set()
folded_total = 0
for i in range(0, len(eids), 200):
    batch = eids[i : i + 200]
    q = f"SELECT content FROM vfs_content WHERE entry_id IN ({','.join('?' * len(batch))})"
    for (content,) in con.execute(q, batch):
        data = folded_bytes(content)
        folded_total += len(data)
        g = gram_array(data)
        occurrences += g.size
        if g.size == 0:
            continue
        # Stable sort by gram groups positions in ascending order per gram.
        order = np.argsort(g, kind="stable")
        gs = g[order]
        pos = order.astype(np.int64)  # position = index in stream
        boundaries = np.flatnonzero(np.diff(gs)) + 1
        starts = np.concatenate(([0], boundaries))
        n_pairs = starts.size
        pairs += n_pairs
        counts = np.diff(np.concatenate((starts, [gs.size])))
        deltas = np.diff(pos)
        # First position of each run is absolute-in-doc; interior deltas stay.
        first_mask = np.zeros(pos.size, dtype=bool)
        first_mask[starts] = True
        d = pos.copy()
        d[1:] = deltas
        d[starts] = pos[starts]
        pos_delta_bytes += varint_bytes(d)
        count_bytes += varint_bytes(counts)
        uniq = np.unique(gs)
        sample_grams.update(int(x) for x in uniq)

# Store facts: actual blob bytes for the sample's grams, and corpus totals.
sg = sorted(sample_grams)
blob_bytes = 0
blob_pairs = 0
for i in range(0, len(sg), 900):
    chunk = sg[i : i + 900]
    r = con.execute(
        f"SELECT sum(byte_size), sum(doc_count) FROM vfs_grams_posting_list "
        f"WHERE epoch=1 AND gram_key IN ({','.join(map(str, chunk))})"
    ).fetchone()
    blob_bytes += r[0] or 0
    blob_pairs += r[1] or 0

corpus = con.execute(
    "SELECT sum(byte_size), sum(doc_count), count(*) FROM vfs_grams_posting_list WHERE epoch=1"
).fetchone()
corpus_content = con.execute("SELECT sum(size_bytes), count(*) FROM vfs WHERE kind='file' AND encoded=1").fetchone()

positions_per_pair = occurrences / pairs
pos_bytes_per_occurrence = pos_delta_bytes / occurrences
count_bytes_per_pair = count_bytes / pairs
docid_bytes_per_pair = corpus[0] / corpus[1]
# Corpus occurrences approximated from stored size_bytes (folded stream length
# tracked on the sample to calibrate the ratio).
fold_ratio = folded_total / sum(
    r[0] for r in [con.execute(
        f"SELECT sum(size_bytes) FROM vfs WHERE id IN ({','.join(map(str, sample))})"
    ).fetchone()]
)
corpus_occ = (corpus_content[0] * fold_ratio) - 2 * corpus_content[1]
projected_position_bytes = corpus_occ * pos_bytes_per_occurrence + corpus[1] * count_bytes_per_pair
multiplier = (corpus[0] + projected_position_bytes) / corpus[0]

out = {
    "sample_files": len(eids),
    "occurrences": int(occurrences),
    "gram_doc_pairs": int(pairs),
    "positions_per_pair": positions_per_pair,
    "position_delta_bytes": int(pos_delta_bytes),
    "count_header_bytes": int(count_bytes),
    "pos_bytes_per_occurrence": pos_bytes_per_occurrence,
    "sample_distinct_grams": len(sg),
    "store_blob_bytes_for_sample_grams": int(blob_bytes),
    "store_pairs_for_sample_grams": int(blob_pairs),
    "corpus_blob_bytes": corpus[0],
    "corpus_pairs": corpus[1],
    "corpus_grams": corpus[2],
    "docid_bytes_per_pair": docid_bytes_per_pair,
    "fold_len_ratio": fold_ratio,
    "corpus_occurrences_est": corpus_occ,
    "projected_position_bytes": projected_position_bytes,
    "projected_index_multiplier": multiplier,
}
for k, v in out.items():
    print(f"{k:36s}: {v:,}" if isinstance(v, int) else f"{k:36s}: {v}")
with open(f"{OUT}/exp2_positions.json", "w") as f:
    json.dump(out, f, indent=1)
