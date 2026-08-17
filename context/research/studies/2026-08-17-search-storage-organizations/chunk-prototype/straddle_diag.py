"""Diagnose the copyright -i gap (rg untruncated vs chunk-unbounded) and
quantify split-line straddle exposure on the heavy exact rows."""
import asyncio, subprocess, sqlite3

import harness
from vfs.storage.backends.database import DatabaseStorage

MIRROR = "../linux-bench/mirror"

async def chunk_pairs(pattern, kwargs):
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{harness.STORE}")
    assert await storage._host.ensure_ready() is None
    host = storage._host
    _t, _m, pairs = await harness.staged_run(host, harness.ChunkMode(host), pattern, kwargs, None, overlay=False)
    await storage.close()
    return pairs

def rg_pairs(args):
    out = subprocess.run(["rg", "-uu", "--line-number", "--no-heading", *args],
                         capture_output=True, text=False, cwd=MIRROR).stdout
    pairs = set()
    for line in out.splitlines():
        p, n, _rest = line.split(b":", 2)
        pairs.add(("/" + p.decode(), int(n)))
    return pairs

async def main():
    db = sqlite3.connect(harness.STORE)
    print("loading mid-line boundary set...", flush=True)
    cuts = set()
    for path, line in db.execute("""select a.path, a.line_end from proto_chunk_map a
            join proto_chunk_map b on b.doc_id=a.doc_id+1 and b.entry_sid=a.entry_sid
            where b.line_start=a.line_end"""):
        cuts.add((path, line))
    print(f"mid-line cuts: {len(cuts)}", flush=True)

    cp = await chunk_pairs("copyright", {"case_mode": "insensitive"})
    rp = rg_pairs(["-i", "-e", "copyright"])
    missing, extra = rp - cp, cp - rp
    print(f"copyright -i: rg {len(rp)}, chunk {len(cp)}, missing {len(missing)}, extra {len(extra)}")
    enc = {p for (p,) in db.execute("select path from vfs where encoded=1")}
    m_unenc = [x for x in missing if x[0] not in enc]
    m_enc = [x for x in missing if x[0] in enc]
    print(f"  missing in non-encoded (scan-side) files: {len(m_unenc)}")
    print(f"  missing in ENCODED files (true chunk losses): {len(m_enc)}")
    at_cut = [x for x in m_enc if x in cuts]
    print(f"    of those, at a mid-line chunk cut: {len(at_cut)}")
    for x in sorted(m_enc)[:10]:
        print("     ", x, "cut" if x in cuts else "NOT-at-cut")
    if extra:
        print("  extra (false positives):", sorted(extra)[:10])

    for pattern, rgargs in [("mutex_lock@drm", ["-e", "mutex_lock", "drivers/gpu/drm"]),
                            ("kzalloc@net", ["-e", "kzalloc", "drivers/net"]),
                            ("EXPORT_SYMBOL_GPL@drivers", ["-e", "EXPORT_SYMBOL_GPL", "drivers"]),
                            ("kfree -w", ["-w", "-e", "kfree"])]:
        pairs = rg_pairs(rgargs)
        split = sum(1 for x in pairs if x in cuts)
        print(f"{pattern:26s} matching lines {len(pairs):6d}, on a split line: {split} (recall exact anyway)")

asyncio.run(main())
