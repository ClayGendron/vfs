"""v24-p3 glean variant: overlay-budget truncation vs rows alice cannot read (real OVERLAY_BUDGET=500)."""
import asyncio
from vfs.authority import Authority, Principal
from vfs.models import Entry
from vfs.paths import Path
from vfs.storage.backends.memory import InMemoryStorage
from vfs.storage.backends.database.glean import OVERLAY_BUDGET

SYSTEM = Authority.system()
ALICE = Authority.of(Principal("alice"))

async def run(label, hidden):
    s = InMemoryStorage()
    assert (await s.first_touch()).success
    assert (await s.posture(path=Path("/"), posture="none", authority=SYSTEM)).success
    assert (await s.grant(path=Path("/pub"), principal="alice", level="read", authority=SYSTEM)).success
    if hidden:
        assert (await s.write(entries=[Entry(path="/aaa-sec/h.txt", content="unrelated words\n")], parents=True, authority=SYSTEM)).success
    vis = [Entry(path=f"/pub/v{i:06d}.txt", content=f"lantern note {i}\n") for i in range(OVERLAY_BUDGET)]
    assert (await s.write(entries=vis, parents=True, authority=SYSTEM)).success
    direct = await s.read(path=Path("/aaa-sec/h.txt"), authority=ALICE)
    g = await s.glean(query="lantern", limit=1000, authority=ALICE)
    errs = [(str(e.kind), (getattr(e, "message", None) or str(e))[:90]) for e in g.errors]
    print(f"[glean OVERLAY_BUDGET={OVERLAY_BUDGET}] {label}: direct_read={[str(e.kind) for e in direct.errors]} rows={len(g.observations)} errors={errs}")
    await s.close()

async def main():
    await run("no hidden row", False)
    await run("one hidden unindexed row", True)

asyncio.run(main())
