"""v24-p3: does grep's truncation/row output change with rows alice cannot read?"""
import asyncio, sys
from vfs.authority import Authority, Principal
from vfs.models import Entry
from vfs.paths import Path
from vfs.storage.backends.memory import InMemoryStorage
from vfs.storage.backends.database import grep as grep_mod

SYSTEM = Authority.system()
ALICE = Authority.of(Principal("alice"))
B = int(sys.argv[1])
MODE = sys.argv[2]  # "index" or "scan"
grep_mod.CANDIDATE_BUDGET = B  # module global read by grep_rows and _index_doc_ids

def kinds(r):
    return [(e.kind.value if hasattr(e.kind, "value") else str(e.kind), (getattr(e, "message", None) or str(e))[:80]) for e in r.errors]

async def world(hidden_body):
    s = InMemoryStorage()
    assert (await s.first_touch()).success
    assert (await s.posture(path=Path("/"), posture="none", authority=SYSTEM)).success
    assert (await s.grant(path=Path("/pub"), principal="alice", level="read", authority=SYSTEM)).success
    if hidden_body is not None:
        w = await s.write(entries=[Entry(path="/aaa-sec/h.txt", content=hidden_body)], parents=True, authority=SYSTEM)
        assert w.success, w.errors
    vis = [Entry(path=f"/pub/v{i:06d}.txt", content="needle visible\n") for i in range(B)]
    w = await s.write(entries=vis, parents=True, authority=SYSTEM); assert w.success, w.errors
    if MODE == "index":
        r = await s.reindex(); assert r.success, r.errors
    return s

async def run(label, hidden_body):
    s = await world(hidden_body)
    direct = await s.read(path=Path("/aaa-sec/h.txt"), authority=ALICE)
    g = await s.grep(pattern="needle", output_mode="files", allow_scan=True, authority=ALICE)
    print(f"[{MODE} B={B}] {label}: direct_read={[str(e.kind) for e in direct.errors]} "
          f"grep_rows={len(g.observations)} grep_errors={kinds(g)}")
    await s.close()

async def main():
    cases = {"none": ("no hidden row", None), "without": ("hidden row WITHOUT needle", "other text\n"),
             "with": ("hidden row WITH needle", "needle secret\n")}
    for key in (sys.argv[3].split(",") if len(sys.argv) > 3 else ["none", "without", "with"]):
        await run(*cases[key])

asyncio.run(main())
