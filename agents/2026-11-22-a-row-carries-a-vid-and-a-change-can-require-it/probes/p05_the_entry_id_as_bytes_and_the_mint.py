"""The entry id read as its 16 stored bytes on each engine, and the mint as decision 2 of the etag spec writes it.

Decision 5 adds ``ULIDBytes``, the entry id column read with no
conversion to text, and ``entry_key_of(text)``, which turns the 26
characters into the same 16 bytes. The spec's "Not checked" asks whether
the native ``uuid`` column of Postgres hands back the same bytes. Both
are sketched here as the spec words them and run against 1,000 rows
that today's ``write`` stored:

- what Python type the driver hands for the column, and
- for each row, whether the bytes read through the sketch equal
  ``entry_key_of`` of the text read through today's ``ULIDKey``, and
  equal the bytes the ULID library gives.

Then the mint: 1,000 etags of the spec's shape, whether equal inputs
give equal etags across two mint objects, whether another mount identity
or version 0 gives another, whether ``"absent"`` has the shape of an
etag, and whether blake2b accepts the key and the ``person`` the spec names.

    VFS_TEST_POSTGRES_URL=postgresql+asyncpg://vfs:vfs@localhost:54320/vfs \
        uv run python agents/2026-11-22-a-row-carries-an-etag-and-a-change-can-require-it/probes/p05_the_entry_id_as_bytes_and_the_mint.py
"""

from __future__ import annotations

import hashlib
from collections import Counter
from typing import TYPE_CHECKING, Any

from sqlalchemy import BINARY, Uuid, select, type_coerce
from sqlalchemy.types import TypeDecorator
from ulid import ULID

from harness import engines, run, storage_on
from vfs.models import Entry
from vfs.paths import Path

if TYPE_CHECKING:
    from sqlalchemy.engine import Dialect
    from sqlalchemy.types import TypeEngine

ETAG_LENGTH = 20
ABSENT = "absent"
_CROCKFORD_TO_BASE32 = str.maketrans("0123456789ABCDEFGHJKMNPQRSTVWXYZ", "0123456789abcdefghijklmnopqrstuv")


class ULIDBytes(TypeDecorator[bytes]):
    """The sketch of decision 5: the identity column read as its 16 stored bytes."""

    impl = Uuid
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(Uuid())
        return dialect.type_descriptor(BINARY(16))

    def process_result_value(self, value: Any, dialect: Dialect) -> bytes | None:
        if value is None:
            return None
        return value.bytes if dialect.name == "postgresql" else bytes(value)


def entry_key_of(text: str) -> bytes:
    """The sketch of decision 5: the 26 characters as the 16 bytes, by one translate and one int()."""
    return int(text.translate(_CROCKFORD_TO_BASE32), 32).to_bytes(16, "big")


def is_etag(value: object) -> bool:
    return isinstance(value, str) and len(value) == ETAG_LENGTH and all(c in "0123456789abcdef" for c in value)


class EtagMint:
    """The sketch of decision 2."""

    def __init__(self, mount_identity: str) -> None:
        self._key = mount_identity.encode("ascii")

    def mint(self, entry_key: bytes, version: int) -> str:
        return hashlib.blake2b(
            entry_key + version.to_bytes(8, "big"), digest_size=10, key=self._key, person=b"vfs.etag.1"
        ).hexdigest()


async def the_bytes(engine: str) -> None:
    async with storage_on(engine) as (storage, _):
        entries = [Entry(path=Path(f"/rows/f{i:04}.txt"), content=str(i)) for i in range(1_000)]
        assert (await storage.write(entries=entries, parents=True)).success
        entry = storage._host.tables.entry
        async with storage._host.session_factory() as session:
            connection = await session.connection()
            driver_row = (await connection.exec_driver_sql(f"SELECT entry_id FROM {entry.fullname} LIMIT 1")).fetchone()
            assert driver_row is not None
            stmt = select(entry.c.entry_id, type_coerce(entry.c.entry_id, ULIDBytes()).label("entry_key"))
            rows = (await session.execute(stmt)).all()
        driver_type = type(driver_row[0])
        print(f"   the driver hands the column as {driver_type.__module__}.{driver_type.__qualname__}")
        differs = sum(1 for text, key in rows if entry_key_of(text) != key)
        library = sum(1 for text, key in rows if ULID.from_str(text).bytes != key)
        widths = Counter(len(key) for _, key in rows)
        kinds = Counter(type(key).__name__ for _, key in rows)
        print(f"   rows {len(rows)}; byte widths {dict(widths)}; python types {dict(kinds)}")
        print(f"   rows where ULIDBytes != entry_key_of(text): {differs}")
        print(f"   rows where ULIDBytes != ULID.from_str(text).bytes: {library}")
        print(f"   the mount identity is {len(storage._host.mount_identity or '')} ascii characters")


def the_mint() -> None:
    mount = str(ULID())
    mint, twin, other = EtagMint(mount), EtagMint(mount), EtagMint(str(ULID()))
    keys = [ULID().bytes for _ in range(1_000)]
    etags = [mint.mint(key, 1) for key in keys]
    print(f"   1,000 mints: {sum(map(is_etag, etags))} have the shape; {len(set(etags))} distinct")
    print(f"   a twin mint of the same mount differs on {sum(a != twin.mint(k, 1) for a, k in zip(etags, keys, strict=True))}")
    print(f"   another mount's mint equals on {sum(a == other.mint(k, 1) for a, k in zip(etags, keys, strict=True))}")
    print(f"   version 0 equals version 1 on {sum(a == mint.mint(k, 0) for a, k in zip(etags, keys, strict=True))}")
    print(f"   version 2**63 - 1 mints: {is_etag(mint.mint(keys[0], 2**63 - 1))}")
    print(f"   is_etag('absent') is {is_etag(ABSENT)}; is_etag(etag.upper()) is {is_etag(etags[0].upper())}")
    print(f"   blake2b limits: key {hashlib.blake2b.MAX_KEY_SIZE} bytes (the identity is {len(mount)}), "
          f"person {hashlib.blake2b.PERSON_SIZE} bytes (the spec's is {len(b'vfs.etag.1')})")  # fmt: skip
    first = Counter(etag[0] for etag in etags)
    print(f"   first characters seen: {''.join(sorted(first))}")


async def main() -> None:
    for engine in engines():
        print(f"== {engine}: the entry id as bytes")
        await the_bytes(engine)
    print("== the mint")
    the_mint()


if __name__ == "__main__":
    run(main)
