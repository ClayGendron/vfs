import asyncio, subprocess, sqlite3, time
import harness
from vfs.storage.backends.database import DatabaseStorage

MIRROR = "../linux-bench/mirror"

def rg_pairs(args):
    out = subprocess.run(["rg", "-uu", "--line-number", "--no-heading", *args],
                         capture_output=True, text=False, cwd=MIRROR).stdout
    pairs = set()
    for line in out.splitlines():
        p, n, _rest = line.split(b":", 2)
        pairs.add(("/" + p.decode(), int(n)))
    return pairs

async def main():
    t0=time.perf_counter()
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{harness.STORE}")
    assert await storage._host.ensure_ready() is None
    host = storage._host
    print("storage ready", time.perf_counter()-t0, flush=True)
    _t, _m, cp = await harness.staged_run(host, harness.ChunkMode(host), "copyright", {"case_mode": "insensitive"}, None, overlay=False)
    await storage.close()
    print("chunk pairs", len(cp), time.perf_counter()-t0, flush=True)
    rp = rg_pairs(["-i", "-e", "copyright"])
    print("rg pairs", len(rp), time.perf_counter()-t0, flush=True)

    db = sqlite3.connect(harness.STORE)
    cuts = set()
    for path, line in db.execute("""select a.path, a.line_end from proto_chunk_map a
            join proto_chunk_map b on b.doc_id=a.doc_id+1 and b.entry_sid=a.entry_sid
            where b.line_start=a.line_end"""):
        cuts.add((path, line))
    print("cuts", len(cuts), time.perf_counter()-t0, flush=True)
    missing, extra = rp - cp, cp - rp
    enc = {p for (p,) in db.execute("select path from vfs where encoded=1")}
    m_unenc = [x for x in missing if x[0] not in enc]
    m_enc = [x for x in missing if x[0] in enc]
    print(f"copyright -i: rg {len(rp)}, chunk {len(cp)}, missing {len(missing)} (non-encoded {len(m_unenc)}, encoded {len(m_enc)}), extra {len(extra)}")
    at_cut = [x for x in m_enc if x in cuts]
    print(f"  encoded-missing at a mid-line chunk cut: {len(at_cut)}")
    for x in sorted(m_enc)[:12]:
        print("   ", x, "cut" if x in cuts else "NOT-at-cut")
    if extra:
        print("  extra:", sorted(extra)[:10])
    import json
    json.dump({"rg": len(rp), "chunk": len(cp), "missing_unencoded": len(m_unenc),
               "missing_encoded": sorted(m_enc), "missing_encoded_at_cut": len(at_cut),
               "extra": sorted(extra)[:50], "n_extra": len(extra)}, open("copyright_gap.json","w"), indent=2)

    for pattern, rgargs in [("mutex_lock@drm", ["-e", "mutex_lock", "drivers/gpu/drm"]),
                            ("kzalloc@net", ["-e", "kzalloc", "drivers/net"]),
                            ("EXPORT_SYMBOL_GPL@drivers", ["-e", "EXPORT_SYMBOL_GPL", "drivers"]),
                            ("kfree -w", ["-w", "-e", "kfree"])]:
        pairs = rg_pairs(rgargs)
        split = sum(1 for x in pairs if x in cuts)
        print(f"{pattern:26s} lines {len(pairs):6d}, on a split line: {split}", flush=True)

asyncio.run(main())
