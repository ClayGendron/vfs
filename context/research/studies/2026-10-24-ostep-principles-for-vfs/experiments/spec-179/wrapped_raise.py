import asyncio, sqlite3, tempfile
from sqlalchemy import event
from sqlalchemy.exc import OperationalError
from vfs.models import Entry
from vfs.paths import Path
from vfs.storage.backends.database import DatabaseStorage

def fault(code):
    orig = sqlite3.OperationalError("injected")
    orig.sqlite_errorcode = code
    return orig

async def attempt(code, tmp):
    s = DatabaseStorage(url=f"sqlite+aiosqlite:///{tmp}/{code}.sqlite")
    await s.first_touch()
    fired = {"n": 0}
    def hook(conn, cursor, statement, params, context, many):
        if statement.startswith("INSERT INTO vfs_content") and fired["n"] == 0:
            fired["n"] += 1
            raise OperationalError(statement, params, fault(code))
    event.listen(s._host.engine.sync_engine, "before_cursor_execute", hook)
    r = await s.write(entries=[Entry(path=Path("/a.txt"), content="a")])
    print(f"code={code}: success={r.success}", [(str(e.kind), e.message, e.retryable, e.data) for e in r.errors])
    st = await s.stat(path=Path("/a.txt"))
    print("   landed:", st.success)
    await s.close()

async def main():
    tmp = tempfile.mkdtemp()
    await attempt(10, tmp)  # SQLITE_IOERR
    await attempt(5, tmp)   # SQLITE_BUSY, retryable
asyncio.run(main())
