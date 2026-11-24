"""What the store's first touch and its writes raise on a Postgres that will not take them, and how today's classifier reads each.

The spec's decision 5 says that where the serving role may not create tables, "the first record call of
a role that may makes them", and its "Not checked" reads a read-only Postgres to be decision 4's
unavailable store. Decision 15 sorts a flush's failure into one a retry can clear, whose rows are kept,
and one no retry can clear, whose rows are dropped. Neither case was run. Each case here runs the
stand-in store's first touch, and one write after the tables exist, and hands the error to the
functions ``EngineHost.classify_failure`` is made of.

- ``no-create``: a role with USAGE on the schema and no CREATE, before the tables exist.
- ``no-create-after``: the same role once a role that may has made the tables, with no rights on them.
- ``read-only``: a session whose transactions are read-only, as on a standby.

    VFS_TEST_POSTGRES_URL=postgresql+asyncpg://vfs:vfs@localhost:54320/vfs \
        uv run python agents/2026-11-22-the-kernel-keeps-records-of-its-own/probes/probe_postgres_refusals.py
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from typing import Any

from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import create_async_engine
from standin import StandinStore, StoreUnavailable, open_store

from vfs import PostgresStorage
from vfs.storage.backends.database.dialects import is_permanent_defect, is_retryable, profile_for


def read(exc: BaseException | None, storage: PostgresStorage) -> dict[str, Any]:
    if exc is None:
        return {"error": None}
    origin = getattr(exc, "orig", None)
    classified = storage._host.classify_failure(exc, context="kernel store")
    return {
        "error": f"{type(exc).__name__}: {str(exc).splitlines()[0][:170]}",
        "sqlstate": getattr(origin, "sqlstate", None),
        "retried_by_the_core": is_retryable(profile_for("postgresql"), exc),
        "permanent_defect": is_permanent_defect(exc),
        "classified_kind": str(classified.kind),
        "classified_retryable": classified.retryable,
        "decision_15_would": "drop the batch" if is_permanent_defect(exc) else "keep the rows",
    }


async def attempt(store: StandinStore, storage: PostgresStorage) -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        await store.first_touch()
        out["first_touch"] = {"error": None}
    except StoreUnavailable as exc:
        out["first_touch"] = read(exc.__cause__, storage) | {"tries": store.commits[-1].attempts}

    async def write(conn: Any) -> None:
        await conn.execute(store.stamps.insert().values(session="s", path=f"/{uuid.uuid4().hex}", vid="v", turn=1))

    try:
        await store.commit(write, what="record")
        out["write"] = {"error": None}
    except StoreUnavailable as exc:
        out["write"] = read(exc.__cause__, storage) | {"tries": store.commits[-1].attempts}
    await store.close()
    return out


async def main() -> None:
    url = make_url(os.environ["VFS_TEST_POSTGRES_URL"])
    schema = f"probe_{uuid.uuid4().hex[:12]}"
    role = f"probe_role_{uuid.uuid4().hex[:8]}"
    admin = create_async_engine(url)
    async with admin.begin() as conn:
        await conn.execute(text(f"CREATE SCHEMA {schema}"))
        await conn.execute(text(f"CREATE ROLE {role} LOGIN PASSWORD 'probe'"))
        await conn.execute(text(f"GRANT USAGE ON SCHEMA {schema} TO {role}"))
    storage = PostgresStorage(url=url, schema=schema)
    limited = url.set(username=role, password="probe")
    out: dict[str, Any] = {"script": "probe_postgres_refusals.py"}
    try:
        out["no-create"] = await attempt(open_store("postgresql", limited, schema=schema), storage)
        owner = open_store("postgresql", url, schema=schema)
        await owner.first_touch()
        await owner.close()
        out["no-create-after"] = await attempt(open_store("postgresql", limited, schema=schema), storage)
        settings = {"connect_args": {"server_settings": {"default_transaction_read_only": "on"}}}
        out["read-only"] = await attempt(open_store("postgresql", url, schema=schema, engine_arguments=settings), storage)
    finally:
        await storage.close()
        async with admin.begin() as conn:
            await conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
            await conn.execute(text(f"DROP ROLE {role}"))
        await admin.dispose()
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    asyncio.run(asyncio.wait_for(main(), timeout=90))
