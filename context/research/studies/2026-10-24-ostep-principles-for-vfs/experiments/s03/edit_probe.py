"""Print the SQL text of each statement an edit issues (study 03). Counts only."""
import asyncio
from sqlalchemy import event
from vfs.authority import Authority
from vfs.base import VirtualFileSystem
from vfs.storage.backends.memory import InMemoryStorage

async def main():
    s = InMemoryStorage(); fs = VirtualFileSystem(storage=s); sy = Authority.system()
    await s.first_touch()
    await fs.write(path="/docs/b.md", content="y\n", parents=True, authority=sy)
    log = []
    event.listen(s._host.engine.sync_engine, "before_cursor_execute", lambda c, cu, st, p, ctx, em: log.append((st, p)))
    await fs.edit("/docs/b.md", "y", "z", authority=sy)
    for st, p in log[:4]:
        print(" ".join(st.split())[:300], p, "\n")
    await fs.close()
asyncio.run(main())
