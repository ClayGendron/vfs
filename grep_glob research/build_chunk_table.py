"""Build newline-aligned file chunks for grep candidate selection.

This is research/prototype code for the local `git_repos_vfs` database.
It is intentionally batch-oriented: rebuild chunks from live file rows, then
query chunks for candidates and verify final grep semantics in Python.

Run:
    uv run python "grep_glob research/build_chunk_table.py"
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
from collections.abc import Iterable

import asyncpg


DEFAULT_DSN = "postgresql://localhost/git_repos_vfs"
DEFAULT_TARGET_BYTES = 64 * 1024


def chunks_for_file(
    *,
    entry_id: str,
    path: str,
    ext: str | None,
    content: str,
    content_hash: str | None,
    updated_at: object,
    target_bytes: int,
) -> Iterable[tuple[object, ...]]:
    lines = content.splitlines(keepends=True)
    if not lines:
        yield (entry_id, path, ext, 0, 1, 1, "", content_hash, updated_at)
        return

    chunk_no = 0
    line_start = 1
    current: list[str] = []
    current_bytes = 0

    for idx, line in enumerate(lines, start=1):
        line_bytes = len(line.encode("utf-8"))
        if current and current_bytes + line_bytes > target_bytes:
            text = "".join(current)
            yield (entry_id, path, ext, chunk_no, line_start, idx - 1, text, content_hash, updated_at)
            chunk_no += 1
            line_start = idx
            current = []
            current_bytes = 0
        current.append(line)
        current_bytes += line_bytes

    if current:
        text = "".join(current)
        yield (entry_id, path, ext, chunk_no, line_start, line_start + len(current) - 1, text, content_hash, updated_at)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    parser.add_argument("--target-bytes", type=int, default=DEFAULT_TARGET_BYTES)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--truncate", action="store_true")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    conn = await asyncpg.connect(args.dsn)
    try:
        if args.truncate:
            await conn.execute("TRUNCATE public.vfs_entry_chunks")

        rows = conn.cursor(
            """
            SELECT id, path, ext, content, content_hash, updated_at
            FROM public.vfs_entries
            WHERE kind = 'file'
              AND deleted_at IS NULL
              AND content IS NOT NULL
            ORDER BY path
            """,
            prefetch=args.batch_size,
        )

        pending: list[tuple[object, ...]] = []
        files = 0
        chunks = 0
        async with conn.transaction():
            async for row in rows:
                content_hash = row["content_hash"]
                if content_hash is None:
                    content_hash = hashlib.sha256(row["content"].encode("utf-8")).hexdigest()
                for chunk in chunks_for_file(
                    entry_id=row["id"],
                    path=row["path"],
                    ext=row["ext"],
                    content=row["content"],
                    content_hash=content_hash,
                    updated_at=row["updated_at"],
                    target_bytes=args.target_bytes,
                ):
                    pending.append(chunk)
                    chunks += 1
                files += 1

                if len(pending) >= args.batch_size:
                    await write_chunks(conn, pending)
                    pending.clear()
                    print(f"chunked files={files} chunks={chunks}")

            if pending:
                await write_chunks(conn, pending)

        print(f"done files={files} chunks={chunks}")
    finally:
        await conn.close()


async def write_chunks(conn: asyncpg.Connection, rows: list[tuple[object, ...]]) -> None:
    await conn.executemany(
        """
        INSERT INTO public.vfs_entry_chunks (
          entry_id, path, ext, chunk_no, line_start, line_end,
          content, content_hash, updated_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        ON CONFLICT (entry_id, chunk_no) DO UPDATE SET
          path = EXCLUDED.path,
          ext = EXCLUDED.ext,
          line_start = EXCLUDED.line_start,
          line_end = EXCLUDED.line_end,
          content = EXCLUDED.content,
          content_hash = EXCLUDED.content_hash,
          updated_at = EXCLUDED.updated_at
        """,
        rows,
    )


if __name__ == "__main__":
    asyncio.run(main())
