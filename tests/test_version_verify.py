"""Tests for version chain integrity verification."""

from __future__ import annotations

import re

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select

from grover.backends.database import DatabaseFileSystem
from grover.models.database.version import FileVersionModel
from grover.models.internal.results import FileOperationResult
from grover.providers.versioning import SNAPSHOT_INTERVAL


def _parse_verify_message(message: str) -> tuple[int, int, int]:
    """Parse 'Verified: N checked, N passed, N failed' → (checked, passed, failed)."""
    m = re.search(r"(\d+) checked, (\d+) passed, (\d+) failed", message)
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    # "No versions to verify" → (0, 0, 0)
    return 0, 0, 0


async def _make_fs():
    """Create a stateless DatabaseFileSystem + session factory + engine."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    fs = DatabaseFileSystem()
    return fs, factory, engine


class TestVerifyChainHealthy:
    """Healthy version chains should pass verification."""

    async def test_verify_chain_healthy(self):
        """Write file + 5 edits (6 versions). All should verify."""
        fs, factory, engine = await _make_fs()
        async with factory() as session:
            await fs.write("/f.py", "version 1\n", session=session)
            for i in range(2, 7):
                await fs.write("/f.py", f"version {i}\n", session=session)

            file_rec = (await session.execute(select(fs.file_model).where(fs.file_model.path == "/f.py"))).scalar_one()

            result = await fs.version_provider.verify_chain(session, file_rec)

            assert result.success is True
            checked, passed, failed = _parse_verify_message(result.message)
            assert checked == 6
            assert passed == 6
            assert failed == 0
        await engine.dispose()

    async def test_verify_chain_single_version(self):
        """Single write (1 snapshot). Should verify."""
        fs, factory, engine = await _make_fs()
        async with factory() as session:
            await fs.write("/f.py", "only version\n", session=session)

            file_rec = (await session.execute(select(fs.file_model).where(fs.file_model.path == "/f.py"))).scalar_one()

            result = await fs.version_provider.verify_chain(session, file_rec)

            assert result.success is True
            checked, passed, _ = _parse_verify_message(result.message)
            assert checked == 1
            assert passed == 1
        await engine.dispose()

    async def test_verify_chain_no_versions(self):
        """File record with no version records should succeed with 0 checked."""
        fs, factory, engine = await _make_fs()
        async with factory() as session:
            # Create a file, then delete all its version records manually
            await fs.write("/f.py", "content\n", session=session)
            file_rec = (await session.execute(select(fs.file_model).where(fs.file_model.path == "/f.py"))).scalar_one()

            # Delete all version records
            versions = (
                (await session.execute(select(FileVersionModel).where(FileVersionModel.file_id == file_rec.id)))
                .scalars()
                .all()
            )
            for v in versions:
                await session.delete(v)
            await session.flush()

            result = await fs.version_provider.verify_chain(session, file_rec)

            assert result.success is True
            checked, _, _ = _parse_verify_message(result.message)
            assert checked == 0
        await engine.dispose()

    async def test_verify_chain_across_snapshot_interval(self):
        """Write SNAPSHOT_INTERVAL + 1 edits. Second snapshot should also pass."""
        fs, factory, engine = await _make_fs()
        async with factory() as session:
            await fs.write("/f.py", "v1\n", session=session)
            for i in range(2, SNAPSHOT_INTERVAL + 2):
                await fs.write("/f.py", f"v{i}\n", session=session)

            file_rec = (await session.execute(select(fs.file_model).where(fs.file_model.path == "/f.py"))).scalar_one()

            total_versions = SNAPSHOT_INTERVAL + 1
            result = await fs.version_provider.verify_chain(session, file_rec)

            assert result.success is True
            checked, passed, _ = _parse_verify_message(result.message)
            assert checked == total_versions
            assert passed == total_versions
        await engine.dispose()


class TestVerifyChainCorrupted:
    """Corrupted version chains should be detected."""

    async def test_verify_chain_corrupted_diff(self):
        """Corrupt version 3's content. Version 3+ should fail."""
        fs, factory, engine = await _make_fs()
        async with factory() as session:
            await fs.write("/f.py", "line 1\n", session=session)
            await fs.write("/f.py", "line 1\nline 2\n", session=session)
            await fs.write("/f.py", "line 1\nline 2\nline 3\n", session=session)

            file_rec = (await session.execute(select(fs.file_model).where(fs.file_model.path == "/f.py"))).scalar_one()

            # Corrupt version 2's diff content (it's a diff, not snapshot)
            v2_rec = (
                await session.execute(
                    select(FileVersionModel).where(
                        FileVersionModel.file_id == file_rec.id,
                        FileVersionModel.version == 2,
                    )
                )
            ).scalar_one()
            v2_rec.content = "garbage diff data\n"
            session.add(v2_rec)
            await session.flush()

            result = await fs.version_provider.verify_chain(session, file_rec)

            assert result.success is False
            _, _passed, failed = _parse_verify_message(result.message)
            assert failed > 0
        await engine.dispose()

    async def test_verify_chain_corrupted_snapshot(self):
        """Corrupt version 1's snapshot content. Dependent versions should fail."""
        fs, factory, engine = await _make_fs()
        async with factory() as session:
            await fs.write("/f.py", "line1\nline2\nline3\n", session=session)
            await fs.write("/f.py", "line1\nline2\nline3\nline4\n", session=session)

            file_rec = (await session.execute(select(fs.file_model).where(fs.file_model.path == "/f.py"))).scalar_one()

            # Corrupt snapshot to a single-line value
            v1_rec = (
                await session.execute(
                    select(FileVersionModel).where(
                        FileVersionModel.file_id == file_rec.id,
                        FileVersionModel.version == 1,
                    )
                )
            ).scalar_one()
            v1_rec.content = "X\n"
            session.add(v1_rec)
            await session.flush()

            result = await fs.version_provider.verify_chain(session, file_rec)

            assert result.success is False
            _, _, failed = _parse_verify_message(result.message)
            assert failed > 0
        await engine.dispose()

    async def test_verify_chain_corrupted_hash(self):
        """Corrupt a version's content_hash (content is fine). Should detect."""
        fs, factory, engine = await _make_fs()
        async with factory() as session:
            await fs.write("/f.py", "good content\n", session=session)

            file_rec = (await session.execute(select(fs.file_model).where(fs.file_model.path == "/f.py"))).scalar_one()

            # Corrupt the stored hash (content is correct)
            v1_rec = (
                await session.execute(
                    select(FileVersionModel).where(
                        FileVersionModel.file_id == file_rec.id,
                        FileVersionModel.version == 1,
                    )
                )
            ).scalar_one()
            v1_rec.content_hash = "0000000000000000000000000000000000000000000000000000000000000000"
            session.add(v1_rec)
            await session.flush()

            result = await fs.version_provider.verify_chain(session, file_rec)

            assert result.success is False
            _, _, failed = _parse_verify_message(result.message)
            assert failed == 1
        await engine.dispose()

    async def test_verify_chain_reconstruction_error(self):
        """Delete snapshot record leaving only diffs. Error captured, not raised."""
        fs, factory, engine = await _make_fs()
        async with factory() as session:
            await fs.write("/f.py", "v1\n", session=session)
            await fs.write("/f.py", "v1\nv2\n", session=session)

            file_rec = (await session.execute(select(fs.file_model).where(fs.file_model.path == "/f.py"))).scalar_one()

            # Delete version 1 (the snapshot), leaving only the diff
            v1_rec = (
                await session.execute(
                    select(FileVersionModel).where(
                        FileVersionModel.file_id == file_rec.id,
                        FileVersionModel.version == 1,
                    )
                )
            ).scalar_one()
            await session.delete(v1_rec)
            await session.flush()

            # Should NOT raise — errors are captured in the result
            result = await fs.version_provider.verify_chain(session, file_rec)

            assert isinstance(result, FileOperationResult)
        await engine.dispose()


class TestBackendVerifyVersions:
    """Backend-level verify_versions / verify_all_versions tests."""

    async def test_backend_verify_versions_healthy(self):
        """DatabaseFileSystem.verify_versions on a healthy file."""
        fs, factory, engine = await _make_fs()
        async with factory() as session:
            await fs.write("/f.py", "v1\n", session=session)
            await fs.write("/f.py", "v2\n", session=session)

            result = await fs.verify_versions("/f.py", session=session)
            assert result.success is True
            checked, passed, _ = _parse_verify_message(result.message)
            assert checked == 2
            assert passed == 2
            assert result.file.path == "/f.py"
        await engine.dispose()

    async def test_backend_verify_versions_not_found(self):
        """verify_versions on a nonexistent path returns success=False."""
        fs, factory, engine = await _make_fs()
        async with factory() as session:
            result = await fs.verify_versions("/nope.py", session=session)
            assert result.success is False
            assert "not found" in result.message.lower()
        await engine.dispose()

    async def test_backend_verify_all_versions_multiple_files(self):
        """verify_all_versions checks all non-deleted, non-directory files."""
        fs, factory, engine = await _make_fs()
        async with factory() as session:
            await fs.write("/a.py", "a\n", session=session)
            await fs.write("/b.py", "b\n", session=session)
            await fs.write("/c.py", "c\n", session=session)

            results = await fs.verify_all_versions(session=session)
            assert len(results) == 3
            assert all(r.success for r in results)
        await engine.dispose()

    async def test_backend_verify_all_versions_skips_directories(self):
        """verify_all_versions only checks files, not directories."""
        fs, factory, engine = await _make_fs()
        async with factory() as session:
            await fs.mkdir("/mydir", session=session)
            await fs.write("/mydir/f.py", "content\n", session=session)

            results = await fs.verify_all_versions(session=session)
            # Only the file, not the directory
            assert len(results) == 1
            assert results[0].file.path == "/mydir/f.py"
        await engine.dispose()

    async def test_backend_verify_all_versions_with_corruption(self):
        """verify_all_versions reports mixed results when one file is corrupted."""
        fs, factory, engine = await _make_fs()
        async with factory() as session:
            await fs.write("/good.py", "good\n", session=session)
            await fs.write("/bad.py", "bad\n", session=session)

            # Corrupt /bad.py's hash
            file_rec = (
                await session.execute(select(fs.file_model).where(fs.file_model.path == "/bad.py"))
            ).scalar_one()
            v1_rec = (
                await session.execute(
                    select(FileVersionModel).where(
                        FileVersionModel.file_id == file_rec.id,
                        FileVersionModel.version == 1,
                    )
                )
            ).scalar_one()
            v1_rec.content_hash = "0" * 64
            session.add(v1_rec)
            await session.flush()

            results = await fs.verify_all_versions(session=session)
            assert len(results) == 2
            paths = {r.file.path: r for r in results}
            assert paths["/good.py"].success is True
            assert paths["/bad.py"].success is False
        await engine.dispose()
