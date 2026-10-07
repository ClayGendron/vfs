"""The renderer registry: resolution, the supertype walk, last wins, and the classified states."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

from vfs.models.media import DOCX, MAX_RENDER_GENERATION_LENGTH, OOXML_TYPES, PDF, PPTX, XLSX
from vfs.rendering import RendererRegistry, Rendering, RenderLimits, RenderSource, generation_of
from vfs.rendering.pdf import PdfRenderer
from vfs.rendering.seam import UNSUPPORTED_GENERATION

if TYPE_CHECKING:
    from vfs.models.media import RenderStatus

LIMITS = RenderLimits()


class _Stub:
    """A host-supplied renderer answering a fixed rendering."""

    name = "stub"
    extra = "stub"
    version: str | None = "9"

    def __init__(self, mimes: tuple[str, ...], rendering: Rendering | None = None) -> None:
        self.mimes = mimes
        self.rendering = rendering or Rendering("ok", "stubbed\n")

    def render(self, source: RenderSource, limits: RenderLimits) -> Rendering:
        return self.rendering


class _Raising(_Stub):
    def render(self, source: RenderSource, limits: RenderLimits) -> Rendering:
        raise RuntimeError("parser exploded")


class TestResolution:
    def test_the_bundled_set_claims_the_four_plain_types(self) -> None:
        registry = RendererRegistry.bundled()
        resolved = [registry.resolve(m) for m in (PDF, DOCX, PPTX, XLSX)]
        assert [r.name for r in resolved if r is not None] == ["pdf", "docx", "pptx", "xlsx"]
        assert registry.resolve("application/octet-stream") is None

    def test_siblings_fall_to_their_plain_renderer(self) -> None:
        registry = RendererRegistry.bundled()
        for ext, name in (("docm", "docx"), ("dotx", "docx"), ("xlsm", "xlsx"), ("pptm", "pptx"), ("ppsx", "pptx")):
            renderer = registry.resolve(OOXML_TYPES[ext])
            assert renderer is not None and renderer.name == name
        pdf = registry.resolve("application/x-pdf")
        assert pdf is not None and pdf.name == "pdf"

    def test_last_registered_wins(self) -> None:
        registry = RendererRegistry.bundled()
        stub = _Stub((PDF,))
        registry.register(stub)
        assert registry.resolve(PDF) is stub
        assert registry.generation(PDF) == "stub/9"
        assert registry.render(RenderSource(b"%PDF", PDF, "a.pdf"), LIMITS).text == "stubbed\n"

    def test_generations_cover_every_renderer_and_the_unsupported_mark(self) -> None:
        registry = RendererRegistry.bundled()
        expected = {generation_of(r) for r in (registry.resolve(m) for m in (PDF, DOCX, PPTX, XLSX)) if r}
        assert registry.generations() == frozenset(expected) | {UNSUPPORTED_GENERATION}
        assert registry.generation("application/octet-stream") == UNSUPPORTED_GENERATION


class TestClassifiedStates:
    def test_an_unregistered_type_is_unsupported(self) -> None:
        rendering = RendererRegistry().render(RenderSource(b"x", "text/x-nothing", "n"), LIMITS)
        assert (rendering.status, rendering.text) == ("unsupported", None)
        assert rendering.detail == "no renderer for text/x-nothing"

    def test_a_missing_extra_is_unavailable_and_names_the_extra(self) -> None:
        class Absent(PdfRenderer):
            def load(self) -> None:
                return None

        registry = RendererRegistry((Absent(),))
        assert registry.generation(PDF) == "pdf/unavailable"
        rendering = registry.render(RenderSource(b"%PDF", PDF, "a.pdf"), LIMITS)
        assert (rendering.status, rendering.text) == ("unavailable", None)
        assert rendering.detail == "the pdf renderer needs vfs[pdf]"

    def test_a_renderer_that_raises_is_a_failed_state(self) -> None:
        registry = RendererRegistry((_Raising((PDF,)),))
        rendering = registry.render(RenderSource(b"%PDF", PDF, "a.pdf"), LIMITS)
        assert (rendering.status, rendering.text) == ("failed", None)
        assert rendering.detail == "stub: RuntimeError: parser exploded"


class TestClaims:
    def test_claims_cover_every_served_type_including_supertypes(self) -> None:
        registry = RendererRegistry.bundled()
        claims = registry.claims()
        assert claims[PDF] == registry.generation(PDF)
        assert claims[OOXML_TYPES["docm"]] == registry.generation(DOCX)
        assert claims["application/x-pdf"] == registry.generation(PDF)
        assert "application/octet-stream" not in claims
        assert RendererRegistry().claims() == {}

    def test_a_generation_wider_than_the_column_is_refused_at_registration(self) -> None:
        wide = _Stub((PDF,))
        wide.version = "v" * MAX_RENDER_GENERATION_LENGTH
        with pytest.raises(ValueError, match="exceeds"):
            RendererRegistry((wide,))


class TestSettledAnswers:
    def test_a_host_renderer_answer_is_settled_before_it_is_served(self) -> None:
        registry = RendererRegistry((_Stub((PDF,), Rendering(cast("RenderStatus", "bogus"), "x\n")),))
        rendering = registry.render(RenderSource(b"%PDF", PDF, "a.pdf"), LIMITS)
        assert (rendering.status, rendering.text) == ("failed", None)
        registry = RendererRegistry((_Stub((PDF,), Rendering("empty", "sentinel\n")),))
        assert registry.render(RenderSource(b"%PDF", PDF, "a.pdf"), LIMITS).text is None
        registry = RendererRegistry((_Stub((PDF,), Rendering("ok", "no newline")),))
        assert registry.render(RenderSource(b"%PDF", PDF, "a.pdf"), LIMITS).text == "no newline\n"
