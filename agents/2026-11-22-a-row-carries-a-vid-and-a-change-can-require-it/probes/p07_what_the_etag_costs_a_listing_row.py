"""A size of cost, never a pass or a fail: what selecting the entry id and minting a digest adds to a 10,000-row listing.

The etag spec costs a read row at about 1.1 microseconds (0.2 to fetch
the id as bytes, 0.9 to mint), measured on in-memory SQLite, and its
"Not checked" asks for the same on a Postgres server. The etag is not
built, so the probe times the parts and the whole they would join:

1. today's ``glob`` and ``ls`` of 10,000 rows at the storage seam, end to
   end, as the baseline a row costs now;
2. one select of the listing's columns for the 10,000 rows, three ways:
   without the id, with the id through today's ``ULIDKey`` (text), and
   with the id through the sketch of ``ULIDBytes`` (the stored bytes);
3. 10,000 mints from bytes, and 10,000 from text through ``entry_key_of``;
4. building 10,000 ``Observation`` rows with and without one more
   20-character field, and the compact JSON bytes of each.

Each figure is the median of ``ROUNDS`` runs, in microseconds a row, on
this machine. The clock measures the machine and the driver; it sizes a
cost and pins nothing.

    VFS_TEST_POSTGRES_URL=postgresql+asyncpg://vfs:vfs@localhost:54320/vfs \
        uv run python agents/2026-11-22-a-row-carries-an-etag-and-a-change-can-require-it/probes/p07_what_the_etag_costs_a_listing_row.py
"""

from __future__ import annotations

import platform
import statistics
import time
from typing import TYPE_CHECKING

from sqlalchemy import select, type_coerce

from harness import engines, run, storage_on
from p05_the_entry_id_as_bytes_and_the_mint import EtagMint, ULIDBytes, entry_key_of
from vfs.models import Entry, Observation
from vfs.paths import Path

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from vfs.storage.backends.database import DatabaseStorage

ROWS = 10_000
ROUNDS = 7


async def per_row(call: Callable[[], Awaitable[object]]) -> float:
    """The median wall time of *call* over the rounds, in microseconds for each of the rows."""
    samples = []
    for _ in range(ROUNDS):
        start = time.perf_counter()
        await call()
        samples.append(time.perf_counter() - start)
    return statistics.median(samples) / ROWS * 1e6


def per_row_sync(call: Callable[[], object]) -> float:
    samples = []
    for _ in range(ROUNDS):
        start = time.perf_counter()
        call()
        samples.append(time.perf_counter() - start)
    return statistics.median(samples) / ROWS * 1e6


async def one_engine(storage: DatabaseStorage) -> None:
    entries = [Entry(path=Path(f"/big/f{i:05}.txt"), content=f"body {i}") for i in range(ROWS)]
    assert (await storage.write(entries=entries, parents=True)).success
    entry = storage._host.tables.entry

    async def glob() -> None:
        result = await storage.glob(patterns=("/big/*",), limit=ROWS)
        assert len(result.observations) == ROWS, len(result.observations)

    async def ls() -> None:
        result = await storage.ls(path=Path("/big"), limit=ROWS)
        assert len(result.observations) == ROWS, len(result.observations)

    listing = [entry.c.path, entry.c.kind, entry.c.version, entry.c.size_bytes, entry.c.updated_at]
    under = entry.c.path.like("/big/%")

    async def fetch(*more: object) -> list[object]:
        async with storage._host.session_factory() as session:
            return list((await session.execute(select(*listing, *more).where(under))).all())

    glob_cost = await per_row(glob)
    ls_cost = await per_row(ls)
    bare = await per_row(fetch)
    as_text = await per_row(lambda: fetch(entry.c.entry_id))
    as_bytes = await per_row(lambda: fetch(type_coerce(entry.c.entry_id, ULIDBytes()).label("entry_key")))
    rows = await fetch(entry.c.entry_id, type_coerce(entry.c.entry_id, ULIDBytes()).label("entry_key"))
    texts = [row[-2] for row in rows]
    keys = [row[-1] for row in rows]
    mint = EtagMint(storage._host.mount_identity or "")
    from_bytes = per_row_sync(lambda: [mint.mint(key, 1) for key in keys])
    from_text = per_row_sync(lambda: [mint.mint(entry_key_of(text), 1) for text in texts])
    print(f"   today's glob of {ROWS} rows, end to end          {glob_cost:6.2f} us a row")
    print(f"   today's ls of {ROWS} rows, end to end            {ls_cost:6.2f} us a row")
    print(f"   one select of the listing columns              {bare:6.2f} us a row")
    print(f"     and the id as text, through ULIDKey          {as_text:6.2f}   (+{as_text - bare:.2f})")
    print(f"     and the id as bytes, through ULIDBytes       {as_bytes:6.2f}   (+{as_bytes - bare:.2f})")
    print(f"   mint from bytes                                {from_bytes:6.2f} us a row")
    print(f"   mint from text, through entry_key_of           {from_text:6.2f} us a row")
    added = (as_bytes - bare) + from_bytes
    print(f"   id as bytes + mint                             {added:6.2f} us a row: "
          f"{added / glob_cost:.0%} of a glob row, {added / ls_cost:.0%} of an ls row; "
          f"{added * ROWS / 1000:.1f} ms for the listing")  # fmt: skip


def the_row() -> None:
    etag = "0123456789abcdef0123"
    plain = [Observation(path=Path(f"/big/f{i:05}.txt"), kind="file", version=1) for i in range(ROWS)]
    build = per_row_sync(lambda: [Observation(path=Path(f"/big/f{i:05}.txt"), kind="file", version=1) for i in range(ROWS)])
    as_json = len(plain[0].model_dump_json(exclude_none=True))
    with_field = len(plain[0].model_dump_json(exclude_none=True)) + len(f',"etag":"{etag}"')
    print(f"   building an Observation today                  {build:6.2f} us a row")
    print(f"   compact JSON of a three-field row              {as_json} bytes; with an etag field {with_field} (+{with_field - as_json})")


async def main() -> None:
    print(f"machine: {platform.machine()} {platform.system()} {platform.release()}, Python {platform.python_version()}")
    for engine in engines():
        print(f"== {engine}")
        async with storage_on(engine) as (storage, _):
            await one_engine(storage)
    print("== the row itself")
    the_row()


if __name__ == "__main__":
    run(main, deadline=300.0)
