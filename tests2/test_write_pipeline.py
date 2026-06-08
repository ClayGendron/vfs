"""Slice 2 of story 014 — pipeline restructure inside ``_write_impl``.

Covers behaviors introduced when the new auto-chunk / auto-index pipeline
runs inside ``DatabaseFileSystem._write_impl``:

- Per-entry change detection (unchanged content is a true no-op)
- Auto-chunk: in-memory chunking, batch-fatal conflict, runtime errors
- Auto-index: ONE bulk ``embed_entries`` call, caller-provided embeddings
  win, provider failure aborts cleanly with no DB mutation
- ``Candidate.status`` populated as ``"created"``/``"updated"``/``"unchanged"``
- ``auto_chunk=False`` / ``auto_index=False`` opt-outs

Tests run against a fresh in-memory SQLite ``DatabaseFileSystem``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.conftest import make_sqlite_db
from vfs.models import VFSEntry
from vfs.vector import Vector

if TYPE_CHECKING:
    from collections.abc import Sequence


# ----- helpers --------------------------------------------------------------


class _RecordingProvider:
    """Embedding provider double — records each ``embed_entries`` call."""

    def __init__(self, dimension: int = 3, fail: bool = False) -> None:
        self._dimension = dimension
        self._model_name = "test-model"
        self._fail = fail
        self.calls: list[list[str]] = []
        self.call_count = 0

    async def embed(self, text: str) -> Vector:  # pragma: no cover - unused
        return Vector([0.0] * self._dimension)

    async def embed_batch(self, texts: list[str]) -> list[Vector]:  # pragma: no cover
        return [Vector([0.0] * self._dimension) for _ in texts]

    async def embed_entries(self, entries: Sequence[VFSEntry]) -> list[Vector]:
        self.call_count += 1
        self.calls.append([e.path for e in entries])
        if self._fail:
            msg = "provider boom"
            raise RuntimeError(msg)
        return [
            Vector([float(i + 1), float(i + 2), float(i + 3)])
            for i in range(len(entries))
        ]

    @property
    def dimensions(self) -> int:
        return self._dimension

    @property
    def model_name(self) -> str:
        return self._model_name


def _tiny_chunker(content: str, ext: str | None = None) -> list[tuple[str, int, int]]:
    """Force every line of *content* into its own chunk.

    The default ``split_content`` only chunks at ~2 KB; tests that want to
    observe auto-chunk behavior on small inputs pass this through a
    subclass override.
    """
    lines = content.splitlines() or [content]
    out: list[tuple[str, int, int]] = []
    for i, line in enumerate(lines, start=1):
        out.append((line, i, i))
    return out if len(out) > 1 else []


def _patch_chunker(fs, chunker):
    """Override ``split_content`` on the filesystem's minted entry class."""
    fs._model.split_content = staticmethod(chunker)


# ----- per-entry change detection (story 014 ACs 6, 22) ---------------------


class TestChangeDetection:
    async def test_unchanged_content_preserves_updated_at_byte_identical(self):
        fs = await make_sqlite_db()
        # Initial write
        r = await fs.write(path="/file.txt", content="hello")
        assert r.success
        async with fs._use_session() as s:
            row = await fs._get_object("/file.txt", s)
            original_updated_at = row.updated_at
        # Re-write with identical content — no DB write expected
        r = await fs.write(path="/file.txt", content="hello")
        assert r.success
        async with fs._use_session() as s:
            row = await fs._get_object("/file.txt", s)
            assert row.updated_at == original_updated_at, (
                "updated_at must not refresh for an unchanged-content write"
            )

    async def test_unchanged_content_returns_status_unchanged(self):
        fs = await make_sqlite_db()
        await fs.write(path="/x.txt", content="same")
        r = await fs.write(path="/x.txt", content="same")
        assert r.success
        assert len(r.candidates) == 1
        assert r.candidates[0].status == "unchanged"
        assert r.candidates[0].path == "/x.txt"

    async def test_changed_content_returns_status_updated(self):
        fs = await make_sqlite_db()
        await fs.write(path="/y.txt", content="v1")
        r = await fs.write(path="/y.txt", content="v2")
        assert r.success
        statuses = {c.path: c.status for c in r.candidates if c.kind == "file"}
        assert statuses["/y.txt"] == "updated"

    async def test_new_file_returns_status_created(self):
        fs = await make_sqlite_db()
        r = await fs.write(path="/new.txt", content="hi")
        assert r.success
        statuses = [c.status for c in r.candidates if c.kind == "file"]
        assert statuses == ["created"]

    async def test_mixed_batch_handles_each_entry_independently(self):
        fs = await make_sqlite_db()
        # Seed
        await fs.write(
            entries=[
                VFSEntry(path="/a.txt", content="a-v1"),
                VFSEntry(path="/b.txt", content="b-v1"),
            ]
        )
        # Re-submit with a.txt unchanged, b.txt changed, c.txt new
        r = await fs.write(
            entries=[
                VFSEntry(path="/a.txt", content="a-v1"),  # unchanged
                VFSEntry(path="/b.txt", content="b-v2"),  # changed
                VFSEntry(path="/c.txt", content="c-v1"),  # new
            ]
        )
        assert r.success
        statuses = {c.path: c.status for c in r.candidates if c.kind == "file"}
        assert statuses == {
            "/a.txt": "unchanged",
            "/b.txt": "updated",
            "/c.txt": "created",
        }


# ----- auto-chunk (story 014 ACs 3, 4, 5, 7, 17) ----------------------------


class TestAutoChunk:
    async def test_auto_chunk_produces_chunks_atomically(self):
        fs = await make_sqlite_db()
        _patch_chunker(fs, _tiny_chunker)
        content = "line one\nline two\nline three\n"
        r = await fs.write(path="/code.py", content=content)
        assert r.success
        # File row should exist with index_content=False (auto-chunk flipped it).
        async with fs._use_session() as s:
            file_row = await fs._get_object("/code.py", s)
            assert file_row is not None
            assert file_row.index_content is False
            # Chunk rows under the file's metadata root.
            for line_no in (1, 2, 3):
                chunk = await fs._get_object(
                    f"/.vfs/code.py/__meta__/chunks/1/{line_no}_{line_no}",
                    s,
                )
                assert chunk is not None
                assert chunk.kind == "chunk"
                assert chunk.index_content is True

    async def test_auto_chunk_short_content_keeps_flag(self):
        fs = await make_sqlite_db()
        # Default chunker only splits >2 KB, so short content keeps the flag.
        r = await fs.write(path="/short.txt", content="just one line")
        assert r.success
        async with fs._use_session() as s:
            row = await fs._get_object("/short.txt", s)
            assert row is not None
            assert row.index_content is True
            # No chunks under it.
            chunks = await fs._fetch_children_batched({"/short.txt": row}, s)
        assert all(c.kind != "chunk" for c in chunks["/short.txt"])

    async def test_auto_chunk_conflict_rejects_whole_batch(self):
        fs = await make_sqlite_db()
        # File with index_content=True (default) plus pre-built chunk for it.
        r = await fs.write(
            entries=[
                VFSEntry(path="/conflict.py", content="src"),  # default index_content=True
                VFSEntry(
                    path="/.vfs/conflict.py/__meta__/chunks/c1",
                    content="chunk content",
                ),
            ]
        )
        assert not r.success
        assert r.candidates == []
        assert any("conflict.py" in e and "index_content=True" in e for e in r.errors)
        # No DB mutation — neither file nor chunk exists.
        async with fs._use_session() as s:
            assert await fs._get_object("/conflict.py", s) is None
            assert await fs._get_object("/.vfs/conflict.py/__meta__/chunks/c1", s) is None

    async def test_auto_chunk_conflict_with_index_content_false_succeeds(self):
        fs = await make_sqlite_db()
        r = await fs.write(
            entries=[
                VFSEntry(path="/coexist.py", content="src", index_content=False),
                VFSEntry(
                    path="/.vfs/coexist.py/__meta__/chunks/c1",
                    content="chunk content",
                ),
            ]
        )
        assert r.success
        async with fs._use_session() as s:
            assert await fs._get_object("/coexist.py", s) is not None
            assert await fs._get_object("/.vfs/coexist.py/__meta__/chunks/1/c1", s) is not None

    async def test_re_chunk_cascades_old_chunks(self):
        fs = await make_sqlite_db()
        _patch_chunker(fs, _tiny_chunker)
        # Initial write produces 3 chunks at version 1.
        await fs.write(path="/code.py", content="a\nb\nc\n")
        async with fs._use_session() as s:
            assert await fs._get_object("/.vfs/code.py/__meta__/chunks/1/3_3", s) is not None
        # Re-write with different content — only 2 chunks, none matching by
        # content. The new chunks land in the version-2 namespace and the
        # whole version-1 chunk dir is vacated (no carry-forward).
        await fs.write(path="/code.py", content="d\ne\n")
        async with fs._use_session() as s:
            assert await fs._get_object("/.vfs/code.py/__meta__/chunks/1/3_3", s) is None
            assert await fs._get_object("/.vfs/code.py/__meta__/chunks/1", s) is None
            new_chunk_1 = await fs._get_object("/.vfs/code.py/__meta__/chunks/2/1_1", s)
            new_chunk_2 = await fs._get_object("/.vfs/code.py/__meta__/chunks/2/2_2", s)
            assert new_chunk_1 is not None
            assert new_chunk_1.content == "d"
            assert new_chunk_2 is not None
            assert new_chunk_2.content == "e"

    async def test_auto_chunk_runtime_error_aborts_with_no_mutation(self):
        fs = await make_sqlite_db()

        def boom(content: str, ext: str | None = None) -> list[tuple[str, int, int]]:
            msg = "split blew up"
            raise RuntimeError(msg)

        _patch_chunker(fs, boom)
        # Big enough that chunk() doesn't short-circuit on empty list.
        big = "x" * 5000
        r = await fs.write(path="/explode.py", content=big)
        assert not r.success
        assert r.candidates == []
        assert any("Auto-chunk failed" in e for e in r.errors)
        async with fs._use_session() as s:
            assert await fs._get_object("/explode.py", s) is None


# ----- auto-index + bulk embed (story 014 ACs 10, 11, 13) -------------------


class TestAutoIndex:
    async def test_bulk_embed_called_at_most_once(self):
        provider = _RecordingProvider()
        fs = await make_sqlite_db(embedding_provider=provider)
        # 50 entries in one batch.
        entries = [
            VFSEntry(path=f"/bulk/f{i:03d}.txt", content=f"content-{i}")
            for i in range(50)
        ]
        r = await fs.write(entries=entries)
        assert r.success
        assert provider.call_count == 1
        assert len(provider.calls[0]) == 50

    async def test_bulk_embed_preserves_input_order(self):
        provider = _RecordingProvider()
        fs = await make_sqlite_db(embedding_provider=provider)
        await fs.write(
            entries=[
                VFSEntry(path="/order/a.txt", content="aaa"),
                VFSEntry(path="/order/b.txt", content="bbb"),
                VFSEntry(path="/order/c.txt", content="ccc"),
            ]
        )
        # Vectors come back in input order; assignment must match.
        async with fs._use_session() as s:
            for i, name in enumerate(("a", "b", "c")):
                row = await fs._get_object(f"/order/{name}.txt", s)
                assert row is not None
                assert list(row.embedding) == [float(i + 1), float(i + 2), float(i + 3)]

    async def test_caller_provided_embedding_excluded_from_bulk_call(self):
        provider = _RecordingProvider()
        fs = await make_sqlite_db(embedding_provider=provider)
        await fs.write(
            entries=[
                VFSEntry(
                    path="/explicit.txt",
                    content="hello",
                    embedding=Vector([9.9, 9.9, 9.9]),
                ),
                VFSEntry(path="/auto.txt", content="hello"),
            ]
        )
        # Provider was called only with the auto.txt entry.
        assert provider.call_count == 1
        assert provider.calls[0] == ["/auto.txt"]
        async with fs._use_session() as s:
            explicit = await fs._get_object("/explicit.txt", s)
            assert list(explicit.embedding) == [9.9, 9.9, 9.9]

    async def test_unchanged_entries_skip_embedding_call(self):
        provider = _RecordingProvider()
        fs = await make_sqlite_db(embedding_provider=provider)
        await fs.write(path="/idem.txt", content="content")
        baseline_calls = provider.call_count
        # Re-write same content — no provider call.
        await fs.write(path="/idem.txt", content="content")
        assert provider.call_count == baseline_calls

    async def test_provider_failure_aborts_with_no_db_mutation(self):
        failing = _RecordingProvider(fail=True)
        fs = await make_sqlite_db(embedding_provider=failing)
        r = await fs.write(path="/fail.txt", content="abc")
        assert not r.success
        assert r.candidates == []
        assert any("Embedding provider failed" in e for e in r.errors)
        async with fs._use_session() as s:
            assert await fs._get_object("/fail.txt", s) is None

    async def test_no_embedding_provider_skips_call_entirely(self):
        # Default fixture has no provider. Should still write file and chunks.
        fs = await make_sqlite_db()
        r = await fs.write(path="/np.txt", content="hello")
        assert r.success
        async with fs._use_session() as s:
            row = await fs._get_object("/np.txt", s)
            assert row is not None
            assert row.embedding is None


# ----- constructor flags (story 014 ACs 1, 22) ------------------------------


class TestIndexedContentHash:
    """Story 030 Phase 1 — the ``indexed_content_hash`` watermark.

    With ``auto_index=True`` the inline index path stamps
    ``indexed_content_hash = content_hash`` on every row whose content it
    folds into the index; with ``auto_index=False`` it leaves the watermark
    null (stale) for a later ``index()`` to reconcile.
    """

    async def test_indexed_file_stamps_watermark_to_content_hash(self):
        fs = await make_sqlite_db()
        await fs.write(path="/doc.txt", content="hello world")
        async with fs._use_session() as s:
            row = await fs._get_object("/doc.txt", s)
            assert row is not None
            assert row.index_content is True
            assert row.indexed_content_hash == row.content_hash

    async def test_auto_index_false_leaves_watermark_null(self):
        fs = await make_sqlite_db(auto_index=False)
        await fs.write(path="/doc.txt", content="hello world")
        async with fs._use_session() as s:
            row = await fs._get_object("/doc.txt", s)
            assert row is not None
            assert row.index_content is True
            assert row.indexed_content_hash is None

    async def test_edit_advances_watermark_to_new_hash(self):
        fs = await make_sqlite_db()
        await fs.write(path="/doc.txt", content="first")
        async with fs._use_session() as s:
            first = await fs._get_object("/doc.txt", s)
            first_hash = first.indexed_content_hash
        await fs.write(path="/doc.txt", content="second")
        async with fs._use_session() as s:
            row = await fs._get_object("/doc.txt", s)
            assert row.indexed_content_hash == row.content_hash
            assert row.indexed_content_hash != first_hash

    async def test_chunk_rows_carry_watermark_parent_does_not(self):
        fs = await make_sqlite_db()
        _patch_chunker(fs, _tiny_chunker)
        await fs.write(path="/code.py", content="line one\nline two\nline three\n")
        async with fs._use_session() as s:
            parent = await fs._get_object("/code.py", s)
            # Parent was chunked → index_content flipped False → never stamped.
            assert parent.index_content is False
            assert parent.indexed_content_hash is None
            for line_no in (1, 2, 3):
                chunk = await fs._get_object(
                    f"/.vfs/code.py/__meta__/chunks/1/{line_no}_{line_no}", s
                )
                assert chunk is not None
                assert chunk.indexed_content_hash == chunk.content_hash


class TestAutoFlags:
    async def test_auto_chunk_false_skips_chunking(self):
        fs = await make_sqlite_db(auto_chunk=False)
        _patch_chunker(fs, _tiny_chunker)
        await fs.write(path="/noauto.py", content="a\nb\nc\n")
        async with fs._use_session() as s:
            row = await fs._get_object("/noauto.py", s)
            assert row is not None
            assert row.index_content is True  # NOT flipped
            assert await fs._get_object("/.vfs/noauto.py/__meta__/chunks/1_1", s) is None

    async def test_auto_index_false_skips_embedding_call(self):
        provider = _RecordingProvider()
        fs = await make_sqlite_db(embedding_provider=provider, auto_index=False)
        await fs.write(path="/noembed.txt", content="content")
        assert provider.call_count == 0
        async with fs._use_session() as s:
            row = await fs._get_object("/noembed.txt", s)
            assert row is not None
            assert row.embedding is None
