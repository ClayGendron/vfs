"""In process, the gate is a convention: the storage object is reachable directly."""
import asyncio, tempfile
from vfs.base import VirtualFileSystem
from vfs.authority import Authority, Principal
from vfs.models import Entry
from vfs.paths import Path
from vfs.storage.backends.database import DatabaseStorage

async def main() -> None:
    d = tempfile.mkdtemp()
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{d}/vfs.sqlite")
    fs = VirtualFileSystem(storage=storage, permissions="read")
    alice = Authority.of(Principal("alice"))
    r = await fs.write(path="/a.txt", content="via the gate", authority=alice)
    print("through the router (read_only map):", r.success, [e.kind for e in r.errors])
    r = await storage.write(entries=[Entry(path=Path("/a.txt"), content="around the gate")], authority=Authority.system())
    print("straight to storage as Authority.system():", r.success)
    r = await fs.read("/a.txt", authority=alice)
    print("read back through the router:", r.success, [o.content for o in r.observations])
    await fs.close()

asyncio.run(main())
