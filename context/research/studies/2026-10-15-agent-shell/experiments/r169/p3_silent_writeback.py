"""Probe 3: does a refused write-back reach the guest, or is it lost at close? (spec 169 review)

Runs the E1 spike's own shim and host unchanged, with the E1 `upper` guest,
as a caller who may read /data but not write it.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
E1 = HERE.parent / "e1"
sys.path.insert(0, str(E1 / "shim"))

from host import Host  # noqa: E402

from vfs.authority import Authority, Principal  # noqa: E402
from vfs.base import VirtualFileSystem  # noqa: E402
from vfs.storage.backends.memory import InMemoryStorage  # noqa: E402

SYSTEM = Authority.system()
BOB = Authority.of(Principal("bob"))
UPPER = (E1 / "guest/target/wasm32-wasip1/release/upper.wasm").read_bytes()


async def main() -> None:
    fs = VirtualFileSystem(storage=InMemoryStorage(), default_authority=SYSTEM)
    await fs.write(path="/bin/upper.wasm", data=UPPER, parents=True)
    await fs.write(path="/data/in.txt", content="alpha\nbeta\n", parents=True)
    await fs.write(path="/data/out.txt", content="untouched\n")
    print("posture / read:", (await fs.posture("/", "read")).success)

    with tempfile.TemporaryDirectory() as cache:
        host = Host(Path(cache), tick_s=0.05)
        try:
            res = await host.run(fs, "upper", ["upper", "/data/in.txt", "/data/out.txt"], authority=BOB, timeout_s=5.0)
            print(f"bob runs upper: exit={res.exit_code} trap={res.trap_code} stdout={res.stdout!r} stderr={res.stderr!r}")
            print(f"  verbs={res.verbs} per_path={res.per_path}")
            print(f"  preview1 fd_close calls={res.preview1_calls.get('fd_close')}")
            body = await fs.read("/data/out.txt")
            print(f"  /data/out.txt after: {body.first().content!r} v={body.first().version}")
            direct = await fs.write(path="/data/out.txt", content="X", authority=BOB)
            print(f"  the same write called directly as bob: success={direct.success} kind={direct.errors[0].kind if direct.errors else None}")

            print("\ncache-hit run as a caller with no read on the program (zed, posture none on /bin):")
            await fs.posture("/bin", "list")
            zed = Authority.of(Principal("zed"))
            res2 = await host.run(fs, "upper", ["upper", "/data/in.txt", "/data/out2.txt"], authority=zed, timeout_s=5.0)
            print(f"  zed: exit={res2.exit_code} compile_mode={res2.compile} verbs={res2.verbs}")
        except Exception as exc:  # noqa: BLE001
            print(f"  zed: {type(exc).__name__}: {exc}")
        finally:
            host.close()
    await fs.close()


asyncio.run(main())
