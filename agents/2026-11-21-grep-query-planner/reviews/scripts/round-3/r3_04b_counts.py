"""Row counts per scope and caller on r3_04's store, today's code, to show the cells r3_04 compared are not empty."""
import asyncio, sys
from vfs import AsyncVirtualFileSystem, Authority, DatabaseStorage, Principal
DB = sys.argv[1]
C = {"system": Authority.system(), "alice": Authority.of(Principal("alice")), "bob": Authority.of(Principal("bob")), "anon": Authority.anonymous()}
async def main():
    fs = AsyncVirtualFileSystem(storage=DatabaseStorage(url=f"sqlite+aiosqlite:///{DB}"))
    for scope in [("/pub",), ("/team",), ("/alice",), ("/secret",), ("/secret/security/selinux",), ("/pub/late",), ("/secret/late",), ("/.vfs/ipc",), ("/.vfs/trash/pub",), ("/.vfs/trash/team", "/.vfs/trash/secret"), ("/.vfs/trash/alice/mm",)]:
        row = []
        for n, a in C.items():
            r = await fs.grep("static", paths=scope, authority=a, output_mode="files")
            row.append(f"{n}={len(r.observations)}{'!' if r.errors else ''}")
        print(scope, " ".join(row))
    await fs.close()
asyncio.run(main())
