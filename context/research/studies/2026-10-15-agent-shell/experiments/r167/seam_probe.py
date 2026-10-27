"""Review probe for spec 167: the rows-to-bytes law as executed by the s3 reference.

Run from the vfs repo root:

    uv run python context/research/studies/2026-10-15-agent-shell/experiments/r167/seam_probe.py

Loads the s3 reference (abi_demo.py) by path and drives its law and runner
over cases the reference never compared with bash.
"""

from __future__ import annotations

import asyncio
import importlib.util
import pathlib
import sys

from vfs import Authority, Principal, VirtualFileSystem
from vfs.models import Entry
from vfs.results import Result
from vfs.storage.backends.memory import InMemoryStorage

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("abi_demo", HERE.parent / "s3" / "abi_demo.py")
assert spec is not None and spec.loader is not None
demo = importlib.util.module_from_spec(spec)
sys.modules["abi_demo"] = demo
spec.loader.exec_module(demo)


async def main() -> None:
    vfs = VirtualFileSystem(storage=InMemoryStorage())
    alice = Authority.of(Principal("alice"))
    body = "line one\nline two\n"
    big = "".join(f"row {i:06d} of the big log\n" for i in range(3000))
    seed = [
        Entry(path="/t/two.txt", content=body),
        Entry(path="/t/nonl.txt", content="no newline"),
        Entry(path="/t/big.log", content=big),
        Entry(path="/t/empty.txt", content=""),
    ]
    assert (await vfs.write(seed, parents=True, authority=alice)).success
    fs = demo.BoundFs(vfs, alice)

    print("=== A. one text read row across a byte seam (pin 4: render + trailing newline) ===")
    for path, bash_bytes in (("/t/two.txt", len(body)), ("/t/nonl.txt", len("no newline")), ("/t/empty.txt", 0)):
        crossed = demo.rows_to_bytes(demo.Rows(await fs.read(path))).data
        print(f"   {path}: crossed {len(crossed)} bytes, bash `cat` gives {bash_bytes}; repr={crossed[:40]!r}")

    print("=== B. cat f | wc (the s3 runner) against the bash numbers ===")
    out = await demo.run_pipeline([(demo.Cat(), ("/t/two.txt",)), (demo.Wc(), ())], fs=fs, env={}, cwd=demo.Path("/"))
    print(f"   s3 runner: {out.rows.one().content!r}   bash: '2 4 18\\n'")

    print("=== C. a cap of 32,768 characters applied inside render_result would land in the pipe ===")
    rendered = Result(ops=("read",), observations=(await fs.read("/t/big.log")).observations).to_str()
    print(f"   big.log renders to {len(rendered)} characters; bash `cat big.log | tail -1` -> {big.splitlines()[-1]!r}")
    print("   if render_result capped at 32,768, tail -1 would print the truncation marker instead")

    print("=== D. empty listing across a seam: the empty marker would count as a line ===")
    await vfs.mkdir("/void", authority=alice)
    empty = demo.rows_to_bytes(demo.Rows(await fs.ls("/void"))).data
    print(f"   ls /void crosses {empty!r} today (wc -l = 0); with '(empty directory)' in render_result it would cross 1 line")


asyncio.run(main())
