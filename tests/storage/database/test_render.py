"""The render stage of reindex against real sqlite rows: renderings land and are searchable, the
skip law and the generation law, dedup, the guarded landing, every status as a stamped state with
no body, the lease, the offload hop, and the limits and registry a host configures.
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any

import pytest
from sqlalchemy import event, func, select, update

from tests.support.database_helpers import _url
from tests.support.documents import (
    docx_bytes,
    encrypted_pdf_bytes,
    pdf_bytes,
    pptx_bytes,
    surrogate_pdf_bytes,
    xlsx_bytes,
)
from vfs.models import Entry
from vfs.models.media import DOCX, OCTET_STREAM, OOXML_TYPES, PDF, RENDERED_STATUSES
from vfs.models.version import line_count
from vfs.paths import Path
from vfs.rendering import Builder, RendererRegistry, Rendering, RenderLimits, RenderSource
from vfs.rendering.pdf import PdfRenderer
from vfs.results import Result, Severity, VFSErrorKind
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database import backend as backend_module
from vfs.storage.backends.database import render as render_module
from vfs.storage.backends.database.dialects import ValueCap
from vfs.storage.backends.database.indexing import lease_lost
from vfs.storage.backends.database.render import RenderReport, RenderRow, land_renderings, render_rows
from vfs.storage.backends.database.seams import installed

QUOKKA_PDF = pdf_bytes(["The quokka smiles", None, "Last page"])
WOMBAT_DOCX = docx_bytes(["A wombat digs"], title="Burrows")
SHEET = xlsx_bytes({"Budget": {"A1": "numbat", "B2": 42}})
DECK = pptx_bytes([("Echidna", ["spines"])])


def _mount(tmp_path: Any, **options: Any) -> DatabaseStorage:
    return DatabaseStorage(url=_url(tmp_path), **options)


async def _put(storage: DatabaseStorage, path: str, data: bytes) -> None:
    assert (await storage.write(entries=[Entry(path=Path(path), data=data)], parents=True)).success is True


async def _row(storage: DatabaseStorage, path: str) -> Any:
    entry = storage._host.tables.entry
    async with storage._host.engine.connect() as conn:
        return (await conn.execute(select(entry).where(entry.c.path == path))).one()


async def _content_rows(storage: DatabaseStorage) -> dict[str, str]:
    tables = storage._host.tables
    stmt = select(tables.entry.c.path, tables.content.c.content).select_from(tables.content_joined())
    async with storage._host.engine.connect() as conn:
        return {row.path: row.content for row in await conn.execute(stmt) if row.content is not None}


async def _chunk_count(storage: DatabaseStorage, path: str) -> int:
    tables = storage._host.tables
    stmt = (
        select(func.count())
        .select_from(tables.chunks.join(tables.entry, tables.entry.c.entry_id == tables.chunks.c.entry_id))
        .where(tables.entry.c.path == path)
    )
    async with storage._host.engine.connect() as conn:
        return (await conn.execute(stmt)).scalar_one()


def _record_into(storage: DatabaseStorage, statements: list[str]) -> None:
    @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
    def record(conn, cursor, statement, parameters, context, executemany) -> None:
        statements.append(statement)


def _content_writes(statements: list[str]) -> list[str]:
    return [s for s in statements if s.startswith(("DELETE", "INSERT")) and "vfs_content" in s]


def _report(result: Result) -> dict[str, int]:
    return (result.model_extra or {})["rendering"]


def _counts(**named: int) -> dict[str, int]:
    """The full six-key report with every unnamed count zero."""
    return {"rendered": 0, "empty": 0, "unsupported": 0, "failed": 0, "cached": 0, "unrendered": 0, **named}


# ---------------------------------------------------------------------------
# Renderings land, and the verbs see them
# ---------------------------------------------------------------------------


class TestRenderings:
    async def test_reindex_renders_every_format_and_grep_hits_under_the_right_marker(self, tmp_path) -> None:
        storage = _mount(tmp_path)
        await _put(storage, "/docs/q.pdf", QUOKKA_PDF)
        await _put(storage, "/docs/w.docx", WOMBAT_DOCX)
        await _put(storage, "/docs/n.xlsx", SHEET)
        await _put(storage, "/docs/e.pptx", DECK)
        result = await storage.reindex()
        assert result.success is True
        assert _report(result) == _counts(rendered=4)
        for path, needle, marker in (
            ("/docs/q.pdf", "quokka", "<!-- page 1 -->"),
            ("/docs/w.docx", "wombat", None),
            ("/docs/n.xlsx", "numbat", "<!-- sheet 1: Budget -->"),
            ("/docs/e.pptx", "spines", "<!-- slide 1 -->"),
        ):
            hits = await storage.grep(pattern=needle)
            assert [str(row.path) for row in hits.observations] == [path]
            [hit] = hits.observations
            text = (await storage.read(path=Path(path))).observations[0].content
            assert text is not None and needle in text
            assert hit.matches is not None and hit.matches[0].match is not None
            above = text.splitlines()[: hit.matches[0].match - 1]
            if marker is not None:
                assert above and marker in above
            stat = (await storage.stat(path=Path(path))).observations[0]
            assert stat.render_status == "ok"
            assert (await _row(storage, path)).lines == line_count(text)
        row = await _row(storage, "/docs/q.pdf")
        assert row.render_source_hash == row.content_hash
        assert row.render_generation == storage.renderers.generation(PDF)
        assert row.render_units is not None and '"kind":"page"' in row.render_units
        glean = await storage.glean(query="quokka")
        assert [str(row.path) for row in glean.observations] == ["/docs/q.pdf"]
        await storage.close()

    async def test_the_rendering_is_chunked_in_the_same_run(self, tmp_path) -> None:
        # A first reindex chunk-stamps the pending row as ineligible under
        # its bytes hash; the landing must reset that so the text splits.
        storage = _mount(tmp_path, renderers=RendererRegistry((_Absent(),)))
        await _put(storage, "/q.pdf", QUOKKA_PDF)
        assert (await storage.reindex()).success is True
        row = await _row(storage, "/q.pdf")
        assert (row.render_status, row.chunked, row.indexable) == ("unavailable", True, False)
        await storage.close()
        storage = _mount(tmp_path)
        assert (await storage.reindex()).success is True
        row = await _row(storage, "/q.pdf")
        assert (row.chunked, row.indexable) == (True, True)
        assert row.chunk_source_hash == row.content_hash
        assert await _chunk_count(storage, "/q.pdf") >= 1
        await storage.close()

    async def test_a_text_only_mount_reports_no_rendering_extra(self, tmp_path) -> None:
        storage = _mount(tmp_path)
        assert (await storage.write(entries=[Entry(path=Path("/a.md"), content="# a\n")])).success is True
        result = await storage.reindex()
        assert result.success is True
        assert "rendering" not in (result.model_extra or {})
        await storage.close()

    async def test_the_extra_survives_the_embed_step(self, tmp_path) -> None:
        from vfs.embedding import HashEmbeddingProvider

        storage = _mount(tmp_path, embedder=HashEmbeddingProvider())
        await _put(storage, "/q.pdf", QUOKKA_PDF)
        result = await storage.reindex()
        assert result.success is True
        extras = result.model_extra or {}
        assert "rendering" in extras and "embedding" in extras
        await storage.close()


# ---------------------------------------------------------------------------
# The skip law, the generation law, dedup
# ---------------------------------------------------------------------------


class TestSkipLaw:
    async def test_a_same_bytes_overwrite_renders_once_more_and_settles(self, tmp_path) -> None:
        # The write clears the stamp and drops the rendering, so the skip
        # law has nothing to compare: one re-render, then settled again.
        storage = _mount(tmp_path)
        await _put(storage, "/q.pdf", QUOKKA_PDF)
        assert (await storage.reindex()).success is True
        await _put(storage, "/q.pdf", QUOKKA_PDF)
        assert (await _row(storage, "/q.pdf")).render_status == "pending"
        result = await storage.reindex()
        assert _report(result) == _counts(rendered=1)
        assert (await _row(storage, "/q.pdf")).render_status == "ok"
        assert "rendering" not in ((await storage.reindex()).model_extra or {})
        await storage.close()

    async def test_a_settled_row_is_not_touched_again(self, tmp_path) -> None:
        storage = _mount(tmp_path)
        await _put(storage, "/q.pdf", QUOKKA_PDF)
        await _put(storage, "/z.bin", b"\x00\x01")
        assert (await storage.reindex()).success is True
        statements: list[str] = []
        _record_into(storage, statements)
        result = await storage.reindex()
        assert result.success is True
        assert "rendering" not in (result.model_extra or {})
        assert _content_writes(statements) == []
        await storage.close()

    async def test_changed_bytes_re_render(self, tmp_path) -> None:
        storage = _mount(tmp_path)
        await _put(storage, "/q.pdf", QUOKKA_PDF)
        assert (await storage.reindex()).success is True
        await _put(storage, "/q.pdf", pdf_bytes(["A bilby instead"]))
        result = await storage.reindex()
        assert _report(result)["rendered"] == 1
        text = (await storage.read(path=Path("/q.pdf"))).observations[0].content
        assert text is not None and "bilby" in text and "quokka" not in text
        assert [str(r.path) for r in (await storage.grep(pattern="quokka")).observations] == []
        await storage.close()

    async def test_a_generation_change_re_renders_every_entry_of_the_type(self, tmp_path) -> None:
        storage = _mount(tmp_path)
        await _put(storage, "/a.pdf", QUOKKA_PDF)
        await _put(storage, "/b.pdf", pdf_bytes(["Second file"]))
        await _put(storage, "/w.docx", WOMBAT_DOCX)
        assert (await storage.reindex()).success is True
        entry = storage._host.tables.entry
        async with storage._host.engine.begin() as conn:
            await conn.execute(update(entry).where(entry.c.mime_type == PDF).values(render_generation="pdf/0+old"))
        result = await storage.reindex()
        assert _report(result) == _counts(rendered=2)
        row = await _row(storage, "/a.pdf")
        assert row.render_generation == storage.renderers.generation(PDF)
        assert (row.chunked, row.indexable) == (True, True) and await _chunk_count(storage, "/a.pdf") >= 1
        await storage.close()

    async def test_twins_render_once(self, tmp_path) -> None:
        storage = _mount(tmp_path)
        await _put(storage, "/one.pdf", QUOKKA_PDF)
        await _put(storage, "/two.pdf", QUOKKA_PDF)
        result = await storage.reindex()
        assert _report(result) == _counts(rendered=1, cached=1)
        texts = await _content_rows(storage)
        assert texts["/one.pdf"] == texts["/two.pdf"]
        # A later copy borrows the settled rendering across runs too.
        await _put(storage, "/three.pdf", QUOKKA_PDF)
        result = await storage.reindex()
        assert _report(result) == _counts(cached=1)
        assert (await _row(storage, "/three.pdf")).render_status == "ok"
        await storage.close()

    async def test_a_failed_twin_lends_its_verdict(self, tmp_path) -> None:
        storage = _mount(tmp_path)
        await _put(storage, "/a.docx", b"PK\x03\x04junk")
        await _put(storage, "/b.docx", b"PK\x03\x04junk")
        result = await storage.reindex()
        assert _report(result) == _counts(cached=1, failed=1)
        for path in ("/a.docx", "/b.docx"):
            assert (await _row(storage, path)).render_status == "corrupt"
        await storage.close()

    async def test_a_donor_without_its_content_row_is_not_borrowed(self, tmp_path) -> None:
        storage = _mount(tmp_path)
        await _put(storage, "/one.pdf", QUOKKA_PDF)
        assert (await storage.reindex()).success is True
        tables = storage._host.tables
        async with storage._host.engine.begin() as conn:
            await conn.execute(tables.content.delete())
        await _put(storage, "/two.pdf", QUOKKA_PDF)
        result = await storage.reindex()
        assert _report(result)["rendered"] == 1
        await storage.close()


# ---------------------------------------------------------------------------
# Failure is a state, never a body
# ---------------------------------------------------------------------------


class _Slow:
    """A renderer that spends the wall budget between units."""

    name = "slow"
    extra = "slow"
    mimes = (PDF,)
    version: str | None = "1"

    def render(self, source: RenderSource, limits: RenderLimits) -> Rendering:
        builder = Builder(limits, input_bytes=len(source.data), total_units=2)
        assert builder.unit("page", 1)
        builder.paragraph("first page text")
        time.sleep(limits.seconds + 0.02)
        builder.unit("page", 2)
        return builder.build()


class _Raising(_Slow):
    name = "boom"

    def render(self, source: RenderSource, limits: RenderLimits) -> Rendering:
        raise RuntimeError("no parser today")


class _Absent(PdfRenderer):
    def load(self) -> None:
        return None


class TestStatuses:
    @pytest.mark.parametrize(
        ("path", "data", "status", "fragment"),
        [
            ("/locked.pdf", encrypted_pdf_bytes(["hidden"]), "encrypted", "password"),
            ("/bad.docx", b"PK\x03\x04junk", "corrupt", "BadZipFile"),
            ("/blob.bin", b"\x00\x01\x02", "unsupported", "no renderer"),
            ("/scan.pdf", pdf_bytes([None]), "empty", "no text"),
        ],
    )
    async def test_each_state_is_stamped_with_its_reason_and_no_body(
        self, tmp_path, path: str, data: bytes, status: str, fragment: str
    ) -> None:
        storage = _mount(tmp_path)
        await _put(storage, path, data)
        result = await storage.reindex()
        assert result.success is True
        row = await _row(storage, path)
        assert row.render_status == status
        assert row.render_detail is not None and fragment in row.render_detail
        assert row.render_source_hash == row.content_hash
        assert row.lines == 0
        assert path not in await _content_rows(storage)
        read = await storage.read(path=Path(path))
        [shown] = read.observations
        if status == "empty":
            assert shown.content == "" and read.errors == []
        else:
            assert shown.content is None
            assert [e.kind for e in read.errors] == [VFSErrorKind.unsupported]
        assert (await storage.grep(pattern=".")).observations == []
        counted = "empty" if status == "empty" else "unsupported" if status == "unsupported" else "failed"
        assert _report(result) == _counts(**{counted: 1})
        # Settled: the next run leaves it alone.
        again = await storage.reindex()
        assert "rendering" not in (again.model_extra or {})
        await storage.close()

    async def test_a_missing_extra_is_unavailable_and_an_install_retries(self, tmp_path) -> None:
        storage = _mount(tmp_path, renderers=RendererRegistry((_Absent(),)))
        await _put(storage, "/q.pdf", QUOKKA_PDF)
        result = await storage.reindex()
        assert _report(result) == _counts(unsupported=1)
        row = await _row(storage, "/q.pdf")
        assert (row.render_status, row.render_generation) == ("unavailable", "pdf/unavailable")
        assert row.render_detail == "the pdf renderer needs vfs[pdf]"
        assert "/q.pdf" not in await _content_rows(storage)
        await storage.close()
        # The same mount opened with the extra present: the generation differs, the skip law retries.
        storage = _mount(tmp_path)
        result = await storage.reindex()
        assert _report(result)["rendered"] == 1
        row = await _row(storage, "/q.pdf")
        assert row.render_status == "ok"
        # The landing reset the chunk stamp the pending row had earned, so the text split in the same run.
        assert (row.chunked, row.indexable) == (True, True) and row.chunk_source_hash == row.content_hash
        assert await _chunk_count(storage, "/q.pdf") >= 1
        assert [str(r.path) for r in (await storage.glean(query="quokka")).observations] == ["/q.pdf"]
        await storage.close()

    async def test_a_raising_renderer_is_failed(self, tmp_path) -> None:
        storage = _mount(tmp_path, renderers=RendererRegistry((_Raising(),)))
        await _put(storage, "/q.pdf", QUOKKA_PDF)
        assert (await storage.reindex()).success is True
        row = await _row(storage, "/q.pdf")
        assert (row.render_status, row.render_detail) == ("failed", "boom: RuntimeError: no parser today")
        assert "/q.pdf" not in await _content_rows(storage)
        await storage.close()

    async def test_a_cut_rendering_is_truncated_with_an_info_note_on_read(self, tmp_path) -> None:
        storage = _mount(tmp_path, render_limits=RenderLimits(chars=60))
        await _put(storage, "/q.pdf", QUOKKA_PDF)
        assert (await storage.reindex()).success is True
        row = await _row(storage, "/q.pdf")
        assert row.render_status == "truncated"
        read = await storage.read(path=Path("/q.pdf"))
        assert read.observations[0].content is not None
        assert read.observations[0].content.endswith("<!-- truncated: 2 of 3 units -->\n")
        [note] = read.errors
        assert (note.kind, note.severity) == (VFSErrorKind.truncated, Severity.info)
        assert [str(r.path) for r in (await storage.grep(pattern="quokka")).observations] == ["/q.pdf"]
        await storage.close()

    async def test_the_time_budget_keeps_the_text_so_far_as_partial(self, tmp_path) -> None:
        storage = _mount(tmp_path, renderers=RendererRegistry((_Slow(),)), render_limits=RenderLimits(seconds=0.01))
        await _put(storage, "/q.pdf", QUOKKA_PDF)
        assert (await storage.reindex()).success is True
        row = await _row(storage, "/q.pdf")
        assert row.render_status == "partial"
        assert (await _content_rows(storage))["/q.pdf"] == "<!-- page 1 -->\nfirst page text\n"
        await storage.close()

    def test_the_limits_are_validated_at_construction(self) -> None:
        with pytest.raises(ValueError, match="chars"):
            RenderLimits(chars=-1)


# ---------------------------------------------------------------------------
# The guarded landing and the lease
# ---------------------------------------------------------------------------


class TestLanding:
    async def test_bytes_replaced_mid_render_are_not_stamped_with_the_old_text(self, tmp_path) -> None:
        storage = _mount(tmp_path)
        await _put(storage, "/q.pdf", QUOKKA_PDF)
        fresh = pdf_bytes(["A bilby instead"])

        async def rival() -> None:
            await _put(storage, "/q.pdf", fresh)

        with installed("reindex:before-render-land", rival):
            result = await storage.reindex()
        assert result.success is True
        row = await _row(storage, "/q.pdf")
        assert row.render_status == "pending"
        assert "/q.pdf" not in await _content_rows(storage)
        assert _report(result)["unrendered"] == 1
        [warning] = [e for e in result.errors if e.kind == VFSErrorKind.unavailable]
        assert warning.severity == Severity.warning and warning.retryable is True
        result = await storage.reindex()
        assert _report(result)["rendered"] == 1
        text = (await storage.read(path=Path("/q.pdf"))).observations[0].content
        assert text is not None and "bilby" in text
        await storage.close()

    async def test_a_lost_lease_stops_before_the_landing(self, tmp_path) -> None:
        storage = _mount(tmp_path)
        await _put(storage, "/q.pdf", QUOKKA_PDF)
        lost = asyncio.Event()

        async def rival_claimed() -> None:
            lost.set()

        with installed("reindex:before-render-land", rival_claimed):
            result, report = await storage._render_step(storage._host.tables, lost)
        assert result is not None and lease_lost(result)
        assert report.rendered == 0
        assert (await _row(storage, "/q.pdf")).render_status == "pending"
        await storage.close()

    async def test_a_preset_lost_flag_renders_nothing(self, tmp_path) -> None:
        storage = _mount(tmp_path)
        await _put(storage, "/q.pdf", QUOKKA_PDF)
        lost = asyncio.Event()
        lost.set()
        result = await storage._reindex_phases(storage._host.tables, lost)
        assert result.success is False and lease_lost(result)
        assert (await _row(storage, "/q.pdf")).render_status == "pending"
        await storage.close()

    async def test_a_failing_landing_ends_the_run_classified(self, tmp_path, monkeypatch) -> None:
        storage = _mount(tmp_path)
        await _put(storage, "/q.pdf", QUOKKA_PDF)

        async def refused(*args: Any, **kwargs: Any) -> Result:
            return Result(
                ops=("reindex",), errors=[backend_module.ResultError(kind=VFSErrorKind.unavailable, message="disk")]
            )

        monkeypatch.setattr(backend_module, "land_renderings", refused)
        result = await storage.reindex()
        assert result.success is False
        assert result.errors[0].message == "disk"
        await storage.close()

    async def test_an_identical_rival_stamp_is_a_no_op(self, tmp_path) -> None:
        # The guard: a row already carrying this exact stamp is not rewritten.
        storage = _mount(tmp_path)
        await _put(storage, "/q.pdf", QUOKKA_PDF)
        assert (await storage.reindex()).success is True
        row = await _row(storage, "/q.pdf")
        item = render_module.Rendered(
            row.entry_id, row.content_hash, row.render_generation, Rendering("ok", "other text\n"), cached=False
        )
        report = RenderReport()
        async with storage._host.session_factory() as session, session.begin():
            tables = storage._host.tables
            await land_renderings(session, tables, storage._host.profile, 500, [item], report)
        assert report.rendered == 0  # the guarded UPDATE reached no row: its rowcount is the proof
        assert "other text" not in (await _content_rows(storage))["/q.pdf"]
        await storage.close()

    async def test_an_empty_landing_is_a_no_op(self, tmp_path) -> None:
        storage = _mount(tmp_path)
        await storage.first_touch()
        async with storage._host.session_factory() as session:
            result = await land_renderings(
                session, storage._host.tables, storage._host.profile, 500, [], RenderReport()
            )
        assert result.success is True
        await storage.close()

    def test_a_row_whose_blob_vanished_is_skipped(self) -> None:
        row = RenderRow(1, "e1", "q.pdf", PDF, "h" * 64, 10)
        assert render_rows([row], {}, RendererRegistry.bundled(), RenderLimits(), {}) == []


# ---------------------------------------------------------------------------
# Residency and the offload hop
# ---------------------------------------------------------------------------


class TestPaging:
    async def test_pages_advance_by_keyset_and_cut_by_bytes(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(backend_module, "RENDER_PAGE_ROWS", 2)
        monkeypatch.setattr(backend_module, "BLOB_PAGE_BYTES", 1)
        storage = _mount(tmp_path)
        for index in range(5):
            await _put(storage, f"/d{index}.pdf", pdf_bytes([f"Document number {index}"]))
        landings = 0
        real = backend_module.land_renderings

        async def counting(*args: Any, **kwargs: Any) -> Result:
            nonlocal landings
            landings += 1
            return await real(*args, **kwargs)

        monkeypatch.setattr(backend_module, "land_renderings", counting)
        result = await storage.reindex()
        assert _report(result)["rendered"] == 5
        assert landings == 5  # one landing per bytes cut: every file rode alone
        await storage.close()

    async def test_rendering_leaves_the_event_loop(self, tmp_path) -> None:
        threads: list[int] = []

        class Recording(_Slow):
            def render(self, source: RenderSource, limits: RenderLimits) -> Rendering:
                threads.append(threading.get_ident())
                return Rendering("ok", "rendered off the loop\n")

        storage = _mount(tmp_path, renderers=RendererRegistry((Recording(),)))
        await _put(storage, "/q.pdf", QUOKKA_PDF)
        assert (await storage.reindex()).success is True
        assert threads and all(ident != threading.get_ident() for ident in threads)
        await storage.close()

    async def test_a_host_renderer_displaces_the_bundled_one(self, tmp_path) -> None:
        class Layout:
            name = "layout"
            extra = "layout"
            mimes = (PDF, DOCX)
            version: str | None = "2"

            def render(self, source: RenderSource, limits: RenderLimits) -> Rendering:
                return Rendering("ok", f"layout of {source.name}\n")

        registry = RendererRegistry.bundled()
        registry.register(Layout())
        storage = _mount(tmp_path, renderers=registry)
        await _put(storage, "/q.pdf", QUOKKA_PDF)
        await _put(storage, "/w.docx", WOMBAT_DOCX)
        await _put(storage, "/n.xlsx", SHEET)
        assert (await storage.reindex()).success is True
        texts = await _content_rows(storage)
        assert texts["/q.pdf"] == "layout of q.pdf\n"
        assert texts["/w.docx"] == "layout of w.docx\n"
        assert "numbat" in texts["/n.xlsx"]
        assert (await _row(storage, "/q.pdf")).render_generation == "layout/2"
        assert storage.renderers is registry
        assert {r.render_status for r in [await _row(storage, p) for p in ("/q.pdf", "/w.docx")]} <= RENDERED_STATUSES
        await storage.close()


# ---------------------------------------------------------------------------
# One bad row never stops the mount
# ---------------------------------------------------------------------------


class TestPoison:
    async def test_a_lone_surrogate_in_the_text_lands_cleaned_and_the_mount_keeps_indexing(self, tmp_path) -> None:
        storage = _mount(tmp_path)
        await _put(storage, "/bad.pdf", surrogate_pdf_bytes())
        await _put(storage, "/good.pdf", QUOKKA_PDF)
        assert (await storage.write(entries=[Entry(path=Path("/notes.md"), content="# notes\n")])).success is True
        result = await storage.reindex()
        assert result.success is True
        assert _report(result) == _counts(rendered=2)
        assert (await _row(storage, "/bad.pdf")).render_status == "ok"
        assert (await _content_rows(storage))["/bad.pdf"] == "<!-- page 1 -->\n\ufffd\n"
        assert [str(r.path) for r in (await storage.grep(pattern="quokka")).observations] == ["/good.pdf"]
        assert (await _row(storage, "/notes.md")).chunked is True
        await storage.close()

    async def test_a_landing_the_engine_refuses_lands_the_row_as_failed_and_the_rest_proceed(
        self, tmp_path, monkeypatch
    ) -> None:
        storage = _mount(tmp_path)
        await _put(storage, "/bad.pdf", pdf_bytes(["poison text"]))
        await _put(storage, "/good.pdf", QUOKKA_PDF)
        bad_id = (await _row(storage, "/bad.pdf")).entry_id
        real = backend_module.land_renderings

        async def refusing(*args: Any, rendered: list[Any], report: Any, **kwargs: Any) -> Result:
            poisoned = [item for item in rendered if item.entry_id == bad_id and item.rendering.status == "ok"]
            if poisoned:
                refusal = backend_module.ResultError(kind=VFSErrorKind.unavailable, message="engine refused the bind")
                return Result(ops=("reindex",), errors=[refusal])
            return await real(*args, rendered=rendered, report=report, **kwargs)

        monkeypatch.setattr(backend_module, "land_renderings", refusing)
        result = await storage.reindex()
        assert result.success is True
        assert _report(result) == _counts(rendered=1, failed=1)
        bad = await _row(storage, "/bad.pdf")
        assert (bad.render_status, bad.render_detail) == ("failed", "landing refused: engine refused the bind")
        assert (await _row(storage, "/good.pdf")).render_status == "ok"
        assert "/bad.pdf" not in await _content_rows(storage)
        assert "rendering" not in ((await storage.reindex()).model_extra or {})
        await storage.close()

    async def test_a_row_refused_even_as_failed_ends_the_run_classified(self, tmp_path, monkeypatch) -> None:
        storage = _mount(tmp_path)
        await _put(storage, "/q.pdf", QUOKKA_PDF)

        async def refusing(*args: Any, **kwargs: Any) -> Result:
            return Result(
                ops=("reindex",), errors=[backend_module.ResultError(kind=VFSErrorKind.unavailable, message="down")]
            )

        monkeypatch.setattr(backend_module, "land_renderings", refusing)
        result = await storage.reindex()
        assert result.success is False
        assert result.errors[0].message == "down"
        await storage.close()


# ---------------------------------------------------------------------------
# The skip law, per type
# ---------------------------------------------------------------------------


class _Bin:
    name = "bin"
    extra = "bin"
    mimes = (OCTET_STREAM,)
    version: str | None = "1"

    def render(self, source: RenderSource, limits: RenderLimits) -> Rendering:
        return Rendering("ok", f"zebrafish {len(source.data)} bytes\n")


class TestRetryByType:
    async def test_an_unsupported_row_is_retried_once_its_type_is_claimed(self, tmp_path) -> None:
        storage = _mount(tmp_path)
        await _put(storage, "/old.bin", b"\x00\x01\x02")
        result = await storage.reindex()
        assert _report(result) == _counts(unsupported=1)
        await storage.close()
        registry = RendererRegistry.bundled()
        registry.register(_Bin())
        storage = _mount(tmp_path, renderers=registry)
        result = await storage.reindex()
        assert _report(result) == _counts(rendered=1)
        row = await _row(storage, "/old.bin")
        assert (row.render_status, row.render_generation) == ("ok", "bin/1")
        assert [str(r.path) for r in (await storage.grep(pattern="zebrafish")).observations] == ["/old.bin"]
        await storage.close()

    async def test_a_sibling_type_stamped_unsupported_is_retried_through_its_supertype(self, tmp_path) -> None:
        storage = _mount(tmp_path, renderers=RendererRegistry())
        await _put(storage, "/w.docm", WOMBAT_DOCX)
        assert (await _row(storage, "/w.docm")).mime_type == OOXML_TYPES["docm"]
        assert _report(await storage.reindex()) == _counts(unsupported=1)
        await storage.close()
        storage = _mount(tmp_path)
        assert _report(await storage.reindex()) == _counts(rendered=1)
        assert (await _row(storage, "/w.docm")).render_generation == storage.renderers.generation(DOCX)
        await storage.close()

    async def test_a_stamp_from_other_bytes_is_dirty(self, tmp_path) -> None:
        # Unreachable through the verbs (every write clears the stamp); the
        # defensive arm of the skip law is pinned by direct SQL.
        storage = _mount(tmp_path)
        await _put(storage, "/q.pdf", QUOKKA_PDF)
        assert (await storage.reindex()).success is True
        entry = storage._host.tables.entry
        async with storage._host.engine.begin() as conn:
            await conn.execute(update(entry).values(render_source_hash="f" * 64))
        assert _report(await storage.reindex()) == _counts(rendered=1)
        row = await _row(storage, "/q.pdf")
        assert row.render_source_hash == row.content_hash
        await storage.close()

    async def test_trashed_rows_are_neither_rendered_nor_counted(self, tmp_path) -> None:
        storage = _mount(tmp_path)
        await _put(storage, "/gone.pdf", pdf_bytes(["trashed text"]))
        assert (await storage.delete(path=Path("/gone.pdf"))).success is True
        await _put(storage, "/live.pdf", QUOKKA_PDF)
        result = await storage.reindex()
        assert _report(result) == _counts(rendered=1)
        assert [e for e in result.errors if e.kind == VFSErrorKind.unavailable] == []
        trashed = [r for r in (await storage.ls(path=Path("/.vfs/trash"))).observations if r.path.name == "gone.pdf"]
        assert trashed == [] or trashed[0].render_status == "pending"
        await storage.close()


# ---------------------------------------------------------------------------
# Bounded statements, pinned
# ---------------------------------------------------------------------------


class TestBounds:
    async def test_rendering_texts_insert_in_byte_bounded_pages(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(render_module, "BLOB_PAGE_BYTES", 1)
        storage = _mount(tmp_path)
        for index in range(3):
            await _put(storage, f"/d{index}.pdf", pdf_bytes([f"Document number {index}"]))
        statements: list[str] = []
        _record_into(storage, statements)
        assert _report(await storage.reindex()) == _counts(rendered=3)
        inserts = [s for s in statements if s.startswith("INSERT") and "vfs_content" in s]
        assert len(inserts) == 3  # one statement per rendering: every text rode alone under a 1-byte page
        await storage.close()

    async def test_dirty_pages_are_keyset_bounded(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(backend_module, "RENDER_PAGE_ROWS", 2)
        storage = _mount(tmp_path)
        for index in range(5):
            await _put(storage, f"/d{index}.pdf", pdf_bytes([f"Document number {index}"]))
        pages: list[int] = []
        real = backend_module.select_render_dirty

        async def recording(*args: Any, **kwargs: Any) -> list[Any]:
            page = await real(*args, **kwargs)
            pages.append(len(page))
            return page

        monkeypatch.setattr(backend_module, "select_render_dirty", recording)
        assert _report(await storage.reindex()) == _counts(rendered=5)
        assert pages == [2, 2, 1, 0]
        await storage.close()

    async def test_a_body_past_the_engine_cap_is_refused_naming_the_setting(self, tmp_path) -> None:
        storage = _mount(tmp_path)
        await storage.first_touch()
        storage._host.value_cap = ValueCap(8, "max_allowed_packet")
        result = await storage.write(entries=[Entry(path=Path("/big.bin"), data=b"abcdefghi")])
        assert result.success is False
        [error] = result.errors
        assert (error.kind, error.retryable) == (VFSErrorKind.unsupported, False)
        assert "Body of 9 bytes on the wire exceeds this engine's max_allowed_packet of 8 bytes" in error.message
        assert (await storage.write(entries=[Entry(path=Path("/ok.bin"), data=b"abcdefgh")])).success is True
        # Measured as the driver sends it: five NULs are ten bytes on the wire.
        nul = await storage.write(entries=[Entry(path=Path("/nul.bin"), data=bytes(5))])
        assert nul.success is False and "Body of 10 bytes on the wire" in nul.errors[0].message
        text = await storage.write(entries=[Entry(path=Path("/t.md"), content="x" * 9)])
        assert text.success is False and "Body of 9 bytes on the wire" in text.errors[0].message
        await storage.close()

    async def test_copy_moves_bodies_in_bounded_pages(self, tmp_path, monkeypatch) -> None:
        from vfs.storage import ResolvedPair
        from vfs.storage.backends.database import topology as topology_module

        monkeypatch.setattr(topology_module, "BLOB_PAGE_BYTES", 1)
        storage = _mount(tmp_path)
        for index in range(3):
            await _put(storage, f"/src/d{index}.pdf", pdf_bytes([f"Document number {index}"]))
        assert (await storage.write(entries=[Entry(path=Path("/src/t.md"), content="text\n")], parents=True)).success
        statements: list[str] = []
        _record_into(storage, statements)
        copied = await storage.copy(operations=[ResolvedPair(src=Path("/src"), dest=Path("/dst"))])
        assert copied.success is True
        blob_inserts = [s for s in statements if s.startswith("INSERT") and "vfs_blobs" in s]
        assert len(blob_inserts) == 3  # one page per binary under a 1-byte page
        for index in range(3):
            back = await storage.read(path=Path(f"/dst/d{index}.pdf"), columns=frozenset({"data"}))
            assert back.observations[0].data == pdf_bytes([f"Document number {index}"])
        assert (await storage.read(path=Path("/dst/t.md"))).observations[0].content == "text\n"
        await storage.close()
