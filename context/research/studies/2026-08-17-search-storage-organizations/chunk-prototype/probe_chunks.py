"""Probe: chunk coverage vs entry content, overlap law, mid-line ends."""
import sqlite3, random

db = sqlite3.connect("linux-chunk.sqlite")
db.row_factory = sqlite3.Row

n_encoded = db.execute("select count(*) from vfs where encoded=1").fetchone()[0]
n_chunk_entries = db.execute("select count(distinct entry_id) from vfs_chunks").fetchone()[0]
print("encoded entries:", n_encoded, "| entries with chunks:", n_chunk_entries)

# entries encoded but without chunks?
q = db.execute("""
  select count(*) from vfs e where e.encoded=1 and not exists
    (select 1 from vfs_chunks c where c.entry_id = e.entry_id)
""").fetchone()[0]
print("encoded entries with zero chunks:", q)

random.seed(7)
sids = [r[0] for r in db.execute(
    "select id from vfs where encoded=1 order by id").fetchall()]
sample = random.sample(sids, 300)
exact_concat = 0; mismatch = 0; midline_ends = 0; total_chunks = 0
overlap_pairs = 0; gap_pairs = 0; adj_pairs = 0
for sid in sample:
    row = db.execute("select e.entry_id, c.content from vfs e join vfs_content c on c.entry_id=e.entry_id where e.id=?", (sid,)).fetchone()
    body = row["content"]
    chs = db.execute("select chunk_index, line_start, line_end, content from vfs_chunks where entry_id=? order by chunk_index", (row["entry_id"],)).fetchall()
    total_chunks += len(chs)
    cat = "".join(c["content"] for c in chs)
    if cat == body: exact_concat += 1
    else: mismatch += 1
    lines = body.split("\n")
    for c in chs:
        if not c["content"].endswith("\n"):
            midline_ends += 1
    for a, b in zip(chs, chs[1:]):
        if b["line_start"] == a["line_end"]: overlap_pairs += 1
        elif b["line_start"] == a["line_end"] + 1: adj_pairs += 1
        else: gap_pairs += 1
print(f"sample {len(sample)} entries, {total_chunks} chunks")
print(f"concat==body: {exact_concat}, mismatch: {mismatch}")
print(f"chunks not ending with newline: {midline_ends}")
print(f"adjacent line ranges: {adj_pairs}, overlapping: {overlap_pairs}, gaps: {gap_pairs}")

# Does a chunk's content start/end align to line boundaries of the body?
# Check: sum of chunk content lengths vs body length for mismatches.
bad = 0
for sid in random.sample(sids, 100):
    row = db.execute("select e.entry_id, e.lines, c.content from vfs e join vfs_content c on c.entry_id=e.entry_id where e.id=?", (sid,)).fetchone()
    chs = db.execute("select line_start, line_end, content from vfs_chunks where entry_id=? order by chunk_index", (row["entry_id"],)).fetchall()
    if chs:
        last = chs[-1]
        nlines = row["content"].count("\n") + (0 if row["content"].endswith("\n") else 1)
        if last["line_end"] not in (nlines, nlines - 1, nlines + 1):
            bad += 1
print("last-chunk line_end far from body line count:", bad)
