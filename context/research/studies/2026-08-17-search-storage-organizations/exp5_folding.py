"""Experiment 5: case-folded gram family — what 'copyright -i' pays today.

The stored index is ALREADY a single folded stream (code_grams module
docstring): the planner has no case input at all, so the -i and sensitive
forms compile to the identical gram query. This experiment (a) proves that
and measures the posting bytes each form reads, (b) prices the
counterfactual raw-stream index: the -i gram expansion it would need, and
the index-size delta folding costs/saves on a 500-file sample.
"""

from __future__ import annotations

import itertools
import json

import numpy as np

from common import OUT, connect, nominate, plan_groups
from vfs.models.code_grams import normalize_content, pack_gram, unpack_gram
from vfs.native import folded_bytes

con = connect()

# (a) today: identical plan either way; measure gram count + posting bytes.
doc_ids, stats = nominate(con, "copyright")
groups = plan_groups("copyright")
all_grams = sorted({g for grp in groups for g in grp})
meta = {
    r[0]: (r[1], r[2])
    for r in con.execute(
        f"SELECT gram_key, doc_count, byte_size FROM vfs_grams_posting_list "
        f"WHERE epoch=1 AND gram_key IN ({','.join(map(str, all_grams))})"
    )
}
print("plan grams (folded, case-independent):", [unpack_gram(g).decode() for g in all_grams])
print("chosen:", [unpack_gram(g).decode() for g in stats["chosen_grams"]],
      "posting bytes read:", stats["posting_bytes_fetched"])

# (b) counterfactual raw index: -i expansion of each required trigram into
# its case orbit (ASCII letters fork 2 ways per byte).
def case_variants(gram: int) -> set[int]:
    tri = unpack_gram(gram)
    choices = []
    for byte in tri:
        ch = chr(byte)
        choices.append({ord(ch.lower()), ord(ch.upper())} if ch.isalpha() else {byte})
    return {pack_gram(a, b, c) for a, b, c in itertools.product(*choices)}

expanded = sorted(set().union(*(case_variants(g) for g in all_grams)))
exp_meta = {
    r[0]: (r[1], r[2])
    for r in con.execute(
        f"SELECT gram_key, doc_count, byte_size FROM vfs_grams_posting_list "
        f"WHERE epoch=1 AND gram_key IN ({','.join(map(str, expanded))})"
    )
}
# NOTE: the store is folded, so these byte sizes overstate a raw store's
# per-variant lists (a raw store splits each folded list across variants);
# the honest counterfactual metric is lookup count, reported as such.
print(f"raw-index -i expansion: {len(all_grams)} grams -> {len(expanded)} case-variant grams "
      f"({len(expanded)/len(all_grams):.1f}x lookups); {len(exp_meta)} present in the folded store")

# (c) index-size delta of folding, 500-file sample: raw vs folded distinct
# grams and (gram, doc) pairs.
def gram_array(data: bytes) -> np.ndarray:
    if len(data) < 3:
        return np.empty(0, dtype=np.int64)
    d = np.frombuffer(data, dtype=np.uint8).astype(np.int64)
    return (d[:-2] << 16) | (d[1:-1] << 8) | d[2:]


ids = [r[0] for r in con.execute("SELECT id FROM vfs WHERE kind='file' AND encoded=1 ORDER BY id")]
sample = ids[:: max(1, len(ids) // 500)][:500]
eids = []
for i in range(0, len(sample), 400):
    chunk = sample[i : i + 400]
    eids.extend(r[0] for r in con.execute(f"SELECT entry_id FROM vfs WHERE id IN ({','.join(map(str, chunk))})"))

raw_pairs = folded_pairs = 0
raw_vocab: set[int] = set()
folded_vocab: set[int] = set()
for i in range(0, len(eids), 200):
    batch = eids[i : i + 200]
    q = f"SELECT content FROM vfs_content WHERE entry_id IN ({','.join('?' * len(batch))})"
    for (content,) in con.execute(q, batch):
        raw = np.unique(gram_array(normalize_content(content)))
        fold = np.unique(gram_array(folded_bytes(content)))
        raw_pairs += raw.size
        folded_pairs += fold.size
        raw_vocab.update(int(x) for x in raw)
        folded_vocab.update(int(x) for x in fold)

out = {
    "plan_gram_count": len(all_grams),
    "chosen_gram_count": stats["chosen_gram_count"],
    "posting_bytes_read_today": stats["posting_bytes_fetched"],
    "identical_plan_for_both_case_modes": True,
    "raw_index_i_lookup_expansion": len(expanded),
    "expansion_factor": len(expanded) / len(all_grams),
    "sample_files": len(eids),
    "raw_gram_doc_pairs": int(raw_pairs),
    "folded_gram_doc_pairs": int(folded_pairs),
    "folded_pair_ratio": folded_pairs / raw_pairs,
    "raw_vocab": len(raw_vocab),
    "folded_vocab": len(folded_vocab),
    "folded_vocab_ratio": len(folded_vocab) / len(raw_vocab),
}
for k, v in out.items():
    print(f"{k:36s}: {v}")
with open(f"{OUT}/exp5_folding.json", "w") as f:
    json.dump(out, f, indent=1)
