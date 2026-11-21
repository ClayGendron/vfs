"""The shell's effects on the two engines vfs serves: each redirection and file program lands in
SQLite and in Postgres as it lands in memory, and lines that append at once lose no line."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import pytest

from tests.support.server_schemas import server_storage
from vfs import AsyncVirtualFileSystem, SQLiteStorage
from vfs.authority import Authority, Principal

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    from vfs import StorageBackend

SYSTEM = Authority.system()
ADA = Authority.of(Principal("ada"))
CONCURRENT_LINES = 20


@asynccontextmanager
async def _engine(name: str, tmp_path: Path) -> AsyncIterator[AsyncVirtualFileSystem]:
    if name == "sqlite":
        storage: StorageBackend = SQLiteStorage(path=tmp_path / "shell.db")
        fs = AsyncVirtualFileSystem(storage=storage)
        try:
            yield fs
        finally:
            await fs.close()
        return
    async with server_storage("VFS_TEST_POSTGRES_URL") as server:
        fs = AsyncVirtualFileSystem(storage=server)
        try:
            yield fs
        finally:
            await fs.close()


ENGINES = [pytest.param("sqlite", id="sqlite"), pytest.param("postgres", marks=pytest.mark.postgres, id="postgres")]


async def _body(fs: AsyncVirtualFileSystem, path: str) -> str:
    result = await fs.read(path, authority=SYSTEM)
    assert result.success, result.error_message
    return result.observations[0].content or ""


@pytest.mark.parametrize("engine", ENGINES)
async def test_each_effect_lands_on_the_engine(engine: str, tmp_path: Path) -> None:
    async with _engine(engine, tmp_path) as fs:
        assert (await fs.mkdir("/ro", authority=SYSTEM)).success
        assert (await fs.mkdir("/w", authority=SYSTEM)).success
        assert (await fs.set_posture("/", "none", authority=SYSTEM)).success
        assert (await fs.grant("/w", "ada", "read_write", authority=SYSTEM)).success
        assert (await fs.grant("/ro", "ada", "read", authority=SYSTEM)).success
        line = (
            "cd /w; echo one > t; echo two > t; echo a >> log; echo b >> log; set -C; echo x > fresh; "
            "echo y > fresh; set +C; touch empty; mkdir -p d/e; echo z > d/e/f; cp t d/copy; mv log d/moved; "
            "rm -r d/e; { echo kept; } > /ro/out; ls; ls d"
        )
        result = await fs.cli(line, authority=ADA)
        assert result.stdout == "d\nempty\nfresh\nt\ncopy\nmoved\n"
        assert "fresh: cannot overwrite existing file" in result.stderr
        assert "/ro/out" in result.stderr
        assert await _body(fs, "/w/t") == "two\n"
        assert await _body(fs, "/w/fresh") == "x\n"
        assert await _body(fs, "/w/empty") == ""
        assert await _body(fs, "/w/d/copy") == "two\n"
        assert await _body(fs, "/w/d/moved") == "a\nb\n"
        assert not (await fs.stat("/w/d/e", authority=SYSTEM)).success
        assert not (await fs.stat("/ro/out", authority=SYSTEM)).success


@pytest.mark.parametrize("engine", ENGINES)
async def test_lines_that_append_at_once_lose_no_line(engine: str, tmp_path: Path) -> None:
    async with _engine(engine, tmp_path) as fs:
        lines = [fs.cli(f"echo line{n} >> /log", authority=ADA) for n in range(CONCURRENT_LINES)]
        results = await asyncio.gather(*lines)
        assert {r.exit_status for r in results} == {0}
        written = (await _body(fs, "/log")).splitlines()
        assert sorted(written) == sorted(f"line{n}" for n in range(CONCURRENT_LINES))
