"""How SQLAlchemy 2's async front sits on its sync core: shared names, the run_sync hatch, the greenlet refusal.

Run from /home/user/vfs: uv run python <this file>
"""

import asyncio
import inspect

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import Session

print("sqlalchemy", sa.__version__)
for sync_cls, async_cls in ((sa.engine.Engine, AsyncEngine), (sa.engine.Connection, AsyncConnection), (Session, AsyncSession)):
    s = {n for n in dir(sync_cls) if not n.startswith("_")}
    a = {n for n in dir(async_cls) if not n.startswith("_")}
    coros = sorted(n for n in s & a if inspect.iscoroutinefunction(getattr(async_cls, n, None)))
    print(f"{sync_cls.__name__}/{async_cls.__name__}: shared public names={len(s & a)}, async-only={len(a - s)}, of shared that are coroutines on the async side={len(coros)} e.g. {coros[:6]}")

aeng = create_async_engine("sqlite+aiosqlite://")
try:
    with aeng.sync_engine.connect() as conn:
        conn.execute(sa.text("select 1"))
except Exception as exc:
    print("sync_engine IO outside a greenlet ->", type(exc).__name__, str(exc).splitlines()[0][:110])


def sync_work(conn: sa.engine.Connection) -> int:
    return conn.execute(sa.text("select 41 + 1")).scalar_one()


async def main() -> None:
    async with aeng.connect() as conn:
        print("AsyncConnection.run_sync(plain sync function) ->", await conn.run_sync(sync_work))
    await aeng.dispose()


asyncio.run(main())
