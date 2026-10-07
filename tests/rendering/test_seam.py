"""The renderer seam's values: limits, generations, bounded detail, the unit table on the row."""

from __future__ import annotations

import importlib.metadata
from typing import TYPE_CHECKING, cast

import pytest

from vfs.models.media import MAX_RENDER_DETAIL_LENGTH
from vfs.rendering import (
    RENDER_CHARS,
    UNSUPPORTED_GENERATION,
    BundledRenderer,
    Renderer,
    Rendering,
    RenderLimits,
    Unit,
    generation_of,
    units_from_json,
    units_to_json,
)
from vfs.rendering.pdf import PdfRenderer
from vfs.rendering.seam import RENDER_RATIO, bounded_detail, failure, failure_from, load_library, sanitize, settle

if TYPE_CHECKING:
    from vfs.models.media import RenderStatus


class TestLimits:
    def test_defaults_are_the_declared_constants(self) -> None:
        limits = RenderLimits()
        assert limits.chars == RENDER_CHARS
        assert limits.ratio == RENDER_RATIO

    @pytest.mark.parametrize("field", ["chars", "ratio", "embedded_depth", "embedded_count", "pages", "seconds"])
    def test_every_cap_must_be_positive(self, field: str) -> None:
        with pytest.raises(ValueError, match=field):
            RenderLimits(**{field: 0})

    def test_the_ratio_may_be_lowered_never_raised(self) -> None:
        assert RenderLimits(ratio=RENDER_RATIO - 1).ratio == RENDER_RATIO - 1
        with pytest.raises(ValueError, match="never raised"):
            RenderLimits(ratio=RENDER_RATIO + 1)


class TestGenerations:
    def test_a_bundled_renderer_names_itself_its_revision_and_its_library(self) -> None:
        renderer = PdfRenderer()
        assert isinstance(renderer, Renderer)
        assert renderer.version is not None
        assert generation_of(renderer) == f"pdf/{renderer.version}"
        assert renderer.version.startswith(f"{PdfRenderer.revision}+pypdf-")

    def test_a_missing_library_is_the_unavailable_generation(self) -> None:
        class Absent(PdfRenderer):
            def load(self) -> None:
                return None

        renderer = Absent()
        assert renderer.available is False
        assert renderer.version is None
        assert generation_of(renderer) == "pdf/unavailable"
        assert UNSUPPORTED_GENERATION == "none/unsupported"

    def test_load_library_answers_the_module_or_none(self) -> None:
        assert load_library("json") is not None
        assert load_library("vfs_no_such_package_anywhere") is None

    def test_the_base_class_exposes_its_library_once_available(self) -> None:
        class Json(BundledRenderer):
            name = "json"
            extra = "json"
            mimes = ("application/json",)
            package = "json"
            distribution = "pypdf"

        assert Json().library.dumps({}) == "{}"


class TestRenderings:
    def test_lines_count_the_text_and_none_has_none(self) -> None:
        assert Rendering("ok", "a\nb\n").lines == 3  # the one law: newlines plus the final line
        assert Rendering("empty").lines == 0

    def test_detail_is_bounded_to_the_row(self) -> None:
        short = "x" * MAX_RENDER_DETAIL_LENGTH
        assert bounded_detail(short) == short
        long = "y" * (MAX_RENDER_DETAIL_LENGTH + 50)
        cut = bounded_detail(long)
        assert len(cut) == MAX_RENDER_DETAIL_LENGTH
        assert cut.endswith("…")

    def test_a_failure_carries_no_body(self) -> None:
        rendering = failure("corrupt", "bad zip")
        assert (rendering.status, rendering.text, rendering.detail) == ("corrupt", None, "bad zip")

    def test_a_failure_from_an_exception_names_the_class_and_renderer(self) -> None:
        rendering = failure_from(ValueError("boom"), "pdf")
        assert rendering.status == "failed"
        assert rendering.detail == "pdf: ValueError: boom"
        assert failure_from(RuntimeError(), "docx", "corrupt").detail == "docx: RuntimeError: no message"


class TestUnitTable:
    def test_round_trips_through_json_and_absent_is_empty(self) -> None:
        units = (Unit("page", 1, None, 1), Unit("sheet", 2, "Budget", 9, True))
        text = units_to_json(units)
        assert text is not None and "Budget" in text
        assert units_from_json(text) == units
        assert units_to_json(()) is None
        assert units_from_json(None) == ()


class TestSanitising:
    def test_nuls_are_dropped_and_lone_surrogates_replaced(self) -> None:
        assert sanitize("a\x00b") == "ab"
        assert sanitize("x\ud800y") == "x\ufffdy"
        assert sanitize("plain") == "plain"

    def test_detail_is_sanitised_before_it_is_bounded(self) -> None:
        assert bounded_detail("PK\x00\x03 header") == "PK\x03 header"
        assert failure_from(ValueError("bad \ud800 byte"), "host").detail == "host: ValueError: bad \ufffd byte"


class TestSettling:
    def test_an_unknown_or_pending_status_is_failed(self) -> None:
        bogus = settle(Rendering(cast("RenderStatus", "bogus"), "text\n"), "host")
        assert (bogus.status, bogus.text) == ("failed", None)
        assert bogus.detail == "host: returned the status 'bogus', which a rendering cannot carry"
        assert settle(Rendering("pending"), "host").status == "failed"

    def test_a_rendered_status_needs_text_and_a_no_body_status_drops_it(self) -> None:
        assert settle(Rendering("ok"), "host").detail == "host: returned 'ok' with no text"
        dropped = settle(Rendering("empty", "sentinel\n", detail="x"), "host")
        assert (dropped.status, dropped.text, dropped.detail) == ("empty", None, "x")
        assert settle(Rendering("failed", "boom text\n"), "host").text is None

    def test_served_text_is_cleaned_and_ends_with_one_newline(self) -> None:
        settled = settle(Rendering("ok", "a\x00b\ud800\n\n\n", units=(Unit("page", 1, None, 1),)), "host")
        assert settled.text == "ab\ufffd\n"
        assert settled.lines == 2
        assert settled.units == (Unit("page", 1, None, 1),)
        assert settle(Rendering("partial", "no newline", detail="d" * 2000), "host").text == "no newline\n"


class TestVersionCaching:
    def test_the_library_version_is_read_once_at_construction(self, monkeypatch) -> None:
        calls: list[str] = []
        real = importlib.metadata.version

        def counting(name: str) -> str:
            calls.append(name)
            return real(name)

        monkeypatch.setattr(importlib.metadata, "version", counting)
        renderer = PdfRenderer()
        for _ in range(5):
            assert renderer.version is not None
        assert calls == ["pypdf"]
