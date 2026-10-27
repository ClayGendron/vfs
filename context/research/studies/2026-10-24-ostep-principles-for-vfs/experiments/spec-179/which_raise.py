import asyncio, tempfile, traceback
from sqlalchemy import event
from vfs.models import Entry
from vfs.paths import Path
from vfs.storage.backends.database import DatabaseStorage

async def main():
    tmp = tempfile.mkdtemp()
    s = DatabaseStorage(url=f"sqlite+aiosqlite:///{tmp}/a.sqlite")
    await s.first_touch()
    dbapi = s._host.engine.sync_engine.dialect.loaded_dbapi
    print("loaded_dbapi", dbapi, dbapi.Error, dbapi.OperationalError, issubclass(dbapi.OperationalError, dbapi.Error))
    def hook(conn, cursor, statement, params, context, many):
        if statement.startswith("INSERT"):
            raise dbapi.OperationalError("injected")
    event.listen(s._host.engine.sync_engine, "before_cursor_execute", hook)
    try:
        r = await s.write(entries=[Entry(path=Path("/a.txt"), content="a")])
        print("RESULT", r.success, [(e.kind, e.message, e.data) for e in r.errors])
    except Exception as e:
        print("RAISED", type(e), type(e).__mro__[:4])
        traceback.print_exc(limit=-6)
asyncio.run(main())
