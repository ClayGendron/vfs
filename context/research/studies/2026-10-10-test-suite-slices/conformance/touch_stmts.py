import asyncio, collections, re
from sqlalchemy import event
from sqlalchemy.engine import Engine
from vfs.storage.backends.memory import InMemoryStorage
kinds = collections.Counter()
@event.listens_for(Engine, "before_cursor_execute")
def _c(conn, cursor, statement, parameters, context, executemany):
    head = " ".join(statement.split()[:2]).upper()
    head = re.sub(r"\"?MAIN\"?\.", "", head)
    kinds[head] += 1
async def main():
    s = InMemoryStorage()
    await s._host.ensure_ready()
    await s.close()
asyncio.run(main())
print(sum(kinds.values()), dict(kinds.most_common()))
