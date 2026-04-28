# ruff: noqa: T201
"""Bulk-load Git/Repos files into Postgres VFS as token-overlapped chunks.

Usage:
    uv run python scripts/load_git_repos_chunks_postgres_vfs.py --reset-table

Defaults:
    repo root: /Users/claygendron/Git/Repos
    database:  pg_trgrm_test_git_repos

This is an ETL loader, not an interactive writer. It uses VFS path conventions
and row shape, but loads rows with Postgres COPY for throughput:

- one lightweight `kind='file'` row per source file
- many searchable `kind='chunk'` rows under `/.vfs/.../__meta__/chunks/...`
- partial trigram index over chunk content only
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import re
import uuid
from bisect import bisect_right
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse, urlunparse

import asyncpg
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import create_async_engine

from vfs.backends.postgres import PostgresFileSystem
from vfs.paths import chunk_path, extract_extension, parent_path, split_path

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sqlalchemy.ext.asyncio import AsyncEngine


DEFAULT_REPOS_ROOT = Path("/Users/claygendron/Git/Repos")
DEFAULT_DB_NAME = "pg_trgrm_test_git_repos"
DEFAULT_DB_URL = os.environ.get(
    "GROVER_CHUNK_DB_URL",
    f"postgresql+asyncpg://localhost/{DEFAULT_DB_NAME}",
)
DEFAULT_CHUNK_TOKENS = 256
DEFAULT_OVERLAP_TOKENS = 32
TOKEN_RE = re.compile(r"\S+")
SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "__pycache__",
    "node_modules",
    ".next",
    "dist",
    "build",
}
COPY_COLUMNS = (
    "id",
    "path",
    "external_id",
    "name",
    "parent_path",
    "kind",
    "content",
    "version_diff",
    "content_hash",
    "mime_type",
    "ext",
    "lines",
    "size_bytes",
    "tokens",
    "lexical_tokens",
    "line_start",
    "line_end",
    "version_number",
    "is_snapshot",
    "created_by",
    "source_path",
    "target_path",
    "edge_type",
    "edge_weight",
    "edge_distance",
    "embedding",
    "owner_id",
    "original_path",
    "created_at",
    "updated_at",
    "deleted_at",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-url", default=DEFAULT_DB_URL)
    parser.add_argument("--db-name", default=None)
    parser.add_argument("--repos-root", type=Path, default=DEFAULT_REPOS_ROOT)
    parser.add_argument("--chunk-tokens", type=int, default=DEFAULT_CHUNK_TOKENS)
    parser.add_argument("--overlap-tokens", type=int, default=DEFAULT_OVERLAP_TOKENS)
    parser.add_argument("--batch-size", type=int, default=10_000)
    parser.add_argument("--reset-table", action="store_true")
    parser.add_argument("--max-files", type=int, default=None)
    parser.add_argument("--maintenance-work-mem", default="4GB")
    parser.add_argument("--logged", action="store_true", help="Keep vfs_entries logged during the bulk load.")
    return parser.parse_args()


def with_db_name(db_url: str, db_name: str | None) -> str:
    if db_name is None:
        return db_url
    parsed = urlparse(db_url)
    return urlunparse(parsed._replace(path=f"/{db_name}"))


def admin_db_url(db_url: str) -> str:
    parsed = urlparse(db_url)
    return urlunparse(parsed._replace(path="/postgres"))


def asyncpg_url(db_url: str) -> str:
    return db_url.replace("+asyncpg", "")


async def ensure_database_exists(db_url: str) -> None:
    parsed = urlparse(db_url)
    db_name = parsed.path.lstrip("/")
    if not db_name:
        raise ValueError("db_url must include a database name")

    conn = await asyncpg.connect(asyncpg_url(admin_db_url(db_url)))
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", db_name)
        if exists:
            print(f"database exists: {db_name}")
            return
        quoted = '"' + db_name.replace('"', '""') + '"'
        await conn.execute(f"CREATE DATABASE {quoted}")
        print(f"created database: {db_name}")
    finally:
        await conn.close()


def iter_files(repos_root: Path, *, limit: int | None = None) -> Iterable[Path]:
    yielded = 0
    for root, dirnames, filenames in os.walk(repos_root):
        root_path = Path(root)
        dirnames[:] = [name for name in dirnames if name not in SKIP_DIRS]
        for filename in filenames:
            path = root_path / filename
            if any(part in SKIP_DIRS for part in path.relative_to(repos_root).parts):
                continue
            yield path
            yielded += 1
            if limit is not None and yielded >= limit:
                return


def read_text_file(path: Path) -> str | None:
    try:
        data = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    if "\x00" in data:
        return None
    return data


def token_windows(text: str, *, chunk_tokens: int, overlap_tokens: int) -> Iterable[tuple[str, int, int, int, int]]:
    step = chunk_tokens - overlap_tokens
    if step <= 0:
        raise ValueError("overlap_tokens must be smaller than chunk_tokens")

    line_starts = [0]
    line_starts.extend(match.end() for match in re.finditer("\n", text))

    chunk_no = 0
    start_token = 0
    window: list[tuple[int, int]] = []
    for match in TOKEN_RE.finditer(text):
        window.append((match.start(), match.end()))
        if len(window) < chunk_tokens:
            continue
        yield chunk_from_window(text, line_starts, window, chunk_no, start_token)
        del window[:step]
        chunk_no += 1
        start_token += step

    if window:
        yield chunk_from_window(text, line_starts, window, chunk_no, start_token)


def chunk_from_window(
    text: str,
    line_starts: list[int],
    window: list[tuple[int, int]],
    chunk_no: int,
    start_token: int,
) -> tuple[str, int, int, int, int]:
    start_char = window[0][0]
    end_char = window[-1][1]
    line_start = bisect_right(line_starts, start_char)
    line_end = bisect_right(line_starts, max(end_char - 1, start_char))
    return text[start_char:end_char], chunk_no, start_token, line_start, line_end


def virtual_file_path(path: Path, repos_root: Path) -> str:
    return "/" + path.relative_to(repos_root).as_posix()


def content_metadata(content: str) -> tuple[str, int, int]:
    encoded = content.encode()
    return hashlib.sha256(encoded).hexdigest(), len(encoded), content.count("\n") + 1 if content else 0


def vfs_row(
    *,
    path: str,
    kind: str,
    content: str,
    original_path: str,
    now: datetime,
    line_start: int | None = None,
    line_end: int | None = None,
) -> tuple[object, ...]:
    content_hash, size_bytes, lines = content_metadata(content)
    _, name = split_path(path)
    token_count = len(TOKEN_RE.findall(content))
    return (
        str(uuid.uuid4()),
        path,
        None,
        name,
        parent_path(path),
        kind,
        content,
        None,
        content_hash,
        None,
        extract_extension(path) if kind == "file" else None,
        lines,
        size_bytes,
        token_count,
        token_count,
        line_start,
        line_end,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        original_path,
        now,
        now,
        None,
    )


def iter_rows_for_file(
    path: Path,
    *,
    repos_root: Path,
    chunk_tokens: int,
    overlap_tokens: int,
) -> Iterable[tuple[object, ...]]:
    content = read_text_file(path)
    if content is None or TOKEN_RE.search(content) is None:
        return

    file_path = virtual_file_path(path, repos_root)
    original_path = str(path)
    if len(file_path) > 950 or len(original_path) > 4096:
        return

    now = datetime.now(UTC)
    yield vfs_row(path=file_path, kind="file", content="", original_path=original_path, now=now)

    for chunk, chunk_no, start_token, line_start, line_end in token_windows(
        content,
        chunk_tokens=chunk_tokens,
        overlap_tokens=overlap_tokens,
    ):
        cpath = chunk_path(file_path, f"chunk-{chunk_no:06d}-tok-{start_token:09d}")
        if len(cpath) > 1024:
            continue
        yield vfs_row(
            path=cpath,
            kind="chunk",
            content=chunk,
            original_path=original_path,
            now=now,
            line_start=line_start,
            line_end=line_end,
        )


async def prepare_bulk_load(engine: AsyncEngine, *, table: str, reset_table: bool, logged: bool) -> None:
    fs = PostgresFileSystem(engine=engine)
    async with engine.begin() as conn:
        if reset_table:
            await conn.run_sync(fs._model.metadata.drop_all)
        await conn.run_sync(fs._model.metadata.create_all)
        if not logged:
            await conn.execute(sql_text(f"ALTER TABLE {table} SET UNLOGGED"))
        for index_name in (
            f"ix_{table}_ext",
            f"ix_{table}_ext_kind",
            f"ix_{table}_kind",
            f"ix_{table}_owner_id",
            f"ix_{table}_parent_path",
            f"ix_{table}_path",
            f"ix_{table}_source_path",
            f"ix_{table}_target_path",
        ):
            await conn.execute(sql_text(f"DROP INDEX IF EXISTS {index_name}"))


async def provision_chunk_search(engine: AsyncEngine, *, table: str, maintenance_work_mem: str) -> None:
    async with engine.begin() as conn:
        await conn.execute(sql_text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.execute(sql_text("SET max_parallel_maintenance_workers = 0"))
        await conn.execute(sql_text(f"SET maintenance_work_mem = '{maintenance_work_mem}'"))
        await conn.execute(sql_text(f"CREATE UNIQUE INDEX IF NOT EXISTS ix_{table}_path ON {table} (path)"))
        await conn.execute(sql_text(f"CREATE INDEX IF NOT EXISTS ix_{table}_kind ON {table} (kind)"))
        await conn.execute(
            sql_text(
                f"""
                CREATE INDEX IF NOT EXISTS ix_{table}_chunk_content_trgm_gin
                ON {table} USING GIN (content gin_trgm_ops)
                WITH (fastupdate = off)
                WHERE kind = 'chunk'
                  AND content IS NOT NULL
                  AND deleted_at IS NULL
                """
            )
        )
        await conn.execute(
            sql_text(
                f"""
                CREATE INDEX IF NOT EXISTS ix_{table}_chunk_path_pattern
                ON {table} (path text_pattern_ops)
                WHERE kind = 'chunk'
                  AND deleted_at IS NULL
                """
            )
        )
        await conn.execute(sql_text(f"ANALYZE {table}"))


async def flush(conn: asyncpg.Connection, rows: list[tuple[object, ...]]) -> None:
    await conn.copy_records_to_table(
        "vfs_entries",
        records=rows,
        columns=COPY_COLUMNS,
        schema_name="public",
    )


async def main() -> None:
    args = parse_args()
    db_url = with_db_name(args.db_url, args.db_name)
    repos_root = args.repos_root.resolve()

    print(f"repos_root: {repos_root}")
    print(f"db_url:     {db_url}")
    print(f"chunking:   {args.chunk_tokens} tokens, {args.overlap_tokens} overlap")
    print(f"batch_size: {args.batch_size}")
    print()

    await ensure_database_exists(db_url)
    engine = create_async_engine(db_url, echo=False)
    try:
        await prepare_bulk_load(engine, table="vfs_entries", reset_table=args.reset_table, logged=args.logged)

        loaded_files = 0
        loaded_chunks = 0
        skipped = 0
        seen = 0
        pending: list[tuple[object, ...]] = []
        copy_conn = await asyncpg.connect(asyncpg_url(db_url))
        try:
            for idx, path in enumerate(iter_files(repos_root, limit=args.max_files), start=1):
                seen = idx
                row_count = 0
                chunk_count = 0
                for row in iter_rows_for_file(
                    path,
                    repos_root=repos_root,
                    chunk_tokens=args.chunk_tokens,
                    overlap_tokens=args.overlap_tokens,
                ):
                    row_count += 1
                    chunk_count += int(row[5] == "chunk")
                    pending.append(row)
                    if len(pending) >= args.batch_size:
                        await flush(copy_conn, pending)
                        pending.clear()

                if chunk_count == 0:
                    skipped += 1
                    continue
                loaded_files += int(row_count > 0)
                loaded_chunks += chunk_count
                if idx % 500 == 0:
                    print(
                        f"seen={seen} loaded_files={loaded_files} "
                        f"loaded_chunks={loaded_chunks} skipped={skipped}"
                    )

            if pending:
                await flush(copy_conn, pending)
        finally:
            await copy_conn.close()

        print(f"seen:          {seen}")
        print(f"loaded_files:  {loaded_files}")
        print(f"loaded_chunks: {loaded_chunks}")
        print(f"skipped:       {skipped}")

        await provision_chunk_search(
            engine,
            table="vfs_entries",
            maintenance_work_mem=args.maintenance_work_mem,
        )
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    sql_text(
                        """
                        SELECT
                          count(*) FILTER (WHERE kind = 'file' AND deleted_at IS NULL) AS files,
                          count(*) FILTER (WHERE kind = 'chunk' AND deleted_at IS NULL) AS chunks
                        FROM vfs_entries
                        """
                    )
                )
            ).first()
            print(f"database files/chunks: {row.files}/{row.chunks}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
