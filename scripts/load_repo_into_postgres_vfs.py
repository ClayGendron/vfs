"""Load this repo into a Postgres-backed VFS mount and provision search indexes.

Usage:
    uv run python scripts/load_repo_into_postgres_vfs.py

Optional:
    uv run python scripts/load_repo_into_postgres_vfs.py --db-name my_repo_vfs
    uv run python scripts/load_repo_into_postgres_vfs.py --repo-root /path/to/repo
    uv run python scripts/load_repo_into_postgres_vfs.py --mount /workspace

The script:
1. Creates the target PostgreSQL database if missing.
2. Creates the VFS table if missing.
3. Loads tracked UTF-8 text files from the repo into a mounted PostgresFileSystem.
4. Provisions pg_trgm and Postgres-native grep/glob/full-text indexes.
5. Runs a couple of sanity queries so you know the mount is alive.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import asyncpg
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import create_async_engine

from vfs import VFSClientAsync
from vfs.backends.postgres import PostgresFileSystem


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_NAME = "grover_repo_vfs"
DEFAULT_DB_URL = os.environ.get("GROVER_REPO_DB_URL", f"postgresql+asyncpg://localhost/{DEFAULT_DB_NAME}")
DEFAULT_MOUNT = "/repo"
SKIP_DIRS = {
    ".git",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "__pycache__",
    "node_modules",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-url", default=DEFAULT_DB_URL, help="SQLAlchemy async Postgres URL.")
    parser.add_argument("--db-name", default=None, help="Override the database name portion of --db-url.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT, help="Repo to snapshot into VFS.")
    parser.add_argument("--mount", default=DEFAULT_MOUNT, help="Mount path to load under, e.g. /repo.")
    parser.add_argument(
        "--reset-table",
        action="store_true",
        help="Drop and recreate the VFS table before loading.",
    )
    return parser.parse_args()


def with_db_name(db_url: str, db_name: str | None) -> str:
    if db_name is None:
        return db_url
    parsed = urlparse(db_url)
    return urlunparse(parsed._replace(path=f"/{db_name}"))


def admin_db_url(db_url: str) -> str:
    parsed = urlparse(db_url)
    return urlunparse(parsed._replace(path="/postgres"))


async def ensure_database_exists(db_url: str) -> None:
    parsed = urlparse(db_url)
    db_name = parsed.path.lstrip("/")
    if not db_name:
        raise ValueError("db_url must include a database name")

    admin_url = admin_db_url(db_url).replace("+asyncpg", "")
    conn = await asyncpg.connect(admin_url)
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


def tracked_files(repo_root: Path) -> list[Path]:
    """Prefer git-tracked files so cache/db artifacts don't get loaded."""
    try:
        proc = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=repo_root,
            check=True,
            capture_output=True,
        )
        rels = [Path(part.decode("utf-8")) for part in proc.stdout.split(b"\x00") if part]
        return [repo_root / rel for rel in rels]
    except (subprocess.CalledProcessError, FileNotFoundError):
        out: list[Path] = []
        for path in sorted(repo_root.rglob("*")):
            if not path.is_file():
                continue
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            out.append(path)
        return out


def read_text_file(path: Path) -> str | None:
    try:
        data = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    if "\x00" in data:
        return None
    return data


async def provision_native_search(engine, *, table: str = "vfs_entries") -> None:
    async with engine.begin() as conn:
        await conn.execute(sql_text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.execute(
            sql_text(
                f"""
                ALTER TABLE {table}
                ADD COLUMN IF NOT EXISTS search_tsv tsvector GENERATED ALWAYS AS (
                    to_tsvector('simple', coalesce(content, ''))
                ) STORED
                """
            )
        )
        await conn.execute(
            sql_text(
                f"""
                CREATE INDEX IF NOT EXISTS ix_{table}_search_tsv_gin
                ON {table} USING GIN (search_tsv)
                WHERE content IS NOT NULL
                  AND deleted_at IS NULL
                  AND kind != 'version'
                """
            )
        )
        await conn.execute(
            sql_text(
                f"""
                CREATE INDEX IF NOT EXISTS ix_{table}_path_pattern
                ON {table} (path text_pattern_ops)
                WHERE deleted_at IS NULL
                """
            )
        )
        await conn.execute(
            sql_text(
                f"""
                CREATE INDEX IF NOT EXISTS ix_{table}_path_trgm_gin
                ON {table} USING GIN (path gin_trgm_ops)
                WHERE deleted_at IS NULL
                """
            )
        )
        await conn.execute(
            sql_text(
                f"""
                CREATE INDEX IF NOT EXISTS ix_{table}_content_trgm_gin
                ON {table} USING GIN (content gin_trgm_ops)
                WHERE kind = 'file'
                  AND content IS NOT NULL
                  AND deleted_at IS NULL
                """
            )
        )
        await conn.execute(sql_text(f"ANALYZE {table}"))


async def main() -> None:
    args = parse_args()
    db_url = with_db_name(args.db_url, args.db_name)
    repo_root = args.repo_root.resolve()
    mount = args.mount if args.mount.startswith("/") else f"/{args.mount}"

    print(f"repo_root: {repo_root}")
    print(f"db_url:    {db_url}")
    print(f"mount:     {mount}")
    print()

    await ensure_database_exists(db_url)

    engine = create_async_engine(db_url, echo=False)
    fs = PostgresFileSystem(engine=engine)

    async with engine.begin() as conn:
        if args.reset_table:
            await conn.run_sync(fs._model.metadata.drop_all)
        await conn.run_sync(fs._model.metadata.create_all)

    files = tracked_files(repo_root)
    print(f"tracked files discovered: {len(files)}")

    loaded = 0
    skipped = 0
    skipped_samples: list[str] = []

    client = VFSClientAsync()
    await client.add_mount(mount, fs)
    try:
        for idx, path in enumerate(files, start=1):
            text = read_text_file(path)
            if text is None:
                skipped += 1
                if len(skipped_samples) < 10:
                    skipped_samples.append(str(path.relative_to(repo_root)))
                continue

            rel = path.relative_to(repo_root).as_posix()
            result = await client.write(f"{mount}/{rel}", text, overwrite=True)
            if not result.success:
                raise RuntimeError(result.error_message)

            loaded += 1
            if idx % 100 == 0:
                print(f"loaded {loaded} files...")

        print(f"loaded files:  {loaded}")
        print(f"skipped files: {skipped}")
        if skipped_samples:
            print("sample skipped files:")
            for sample in skipped_samples:
                print(f"  - {sample}")

        await provision_native_search(engine, table=fs._model.__tablename__)

        py_files = await client.glob(f"{mount}/**/*.py")
        login_hits = await client.grep("login", paths=(mount,), max_count=10)

        print()
        print(f"python files: {len(py_files)}")
        print(f"grep 'login' hits: {len(login_hits)}")
    finally:
        await client.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
