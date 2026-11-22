"""Run a line under asyncio.wait_for beside a heartbeat task; report whether the loop kept turning."""
import asyncio, sys, time
from vfs import AsyncVirtualFileSystem
from vfs.authority import Authority, Principal

async def main(line: str, budget: float) -> None:
    fs = AsyncVirtualFileSystem()
    beats = 0
    async def heartbeat() -> None:
        nonlocal beats
        while True:
            await asyncio.sleep(0.05)
            beats += 1
    hb = asyncio.create_task(heartbeat())
    await asyncio.sleep(0.2)
    before, t = beats, time.monotonic()
    try:
        r = await asyncio.wait_for(fs.cli(line, authority=Authority.of(Principal("a"))), timeout=budget)
        outcome = f"exit={r.exit_status} stdout_len={len(r.stdout)} errors={[e.kind.value for e in r.errors]}"
    except TimeoutError:
        outcome = "wait_for timed out"
    dt = time.monotonic() - t
    print(f"{outcome} secs={dt:.2f} heartbeats_during_call={beats - before} (expected about {dt / 0.05:.0f} if the loop turned)", flush=True)
    hb.cancel()

asyncio.run(main(sys.argv[1], float(sys.argv[2])))
