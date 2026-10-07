"""The renderer registry: media type in, renderer out, with the generation it stamps.

Keyed by exact media type, then a supertype walk (a macro-enabled or
template Office type falls to its plain renderer); last registered
wins, so a host-supplied renderer displaces a bundled one. The
registry is built once at storage construction and probes each
renderer's library then: a renderer whose extra is missing answers
``unavailable`` at render time, naming the extra, and never raises.
An unregistered type answers ``unsupported``. Both are stamped with a
generation of their own, so registering a renderer or installing its
extra changes the stamp and the skip law retries the entry.

    registry = RendererRegistry.bundled()
    registry.register(MyLayoutRenderer())          # displaces the pdf renderer
    rendering = registry.render(RenderSource(data, mime, name), RenderLimits())
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vfs.models.media import MAX_RENDER_GENERATION_LENGTH, SUPERTYPES
from vfs.rendering.docx import DocxRenderer
from vfs.rendering.pdf import PdfRenderer
from vfs.rendering.pptx import PptxRenderer
from vfs.rendering.seam import UNSUPPORTED_GENERATION, Rendering, failure, failure_from, generation_of, settle
from vfs.rendering.xlsx import XlsxRenderer

if TYPE_CHECKING:
    from collections.abc import Iterable

    from vfs.rendering.seam import Renderer, RenderLimits, RenderSource


class RendererRegistry:
    """Renderers by media type, and the generation string each type stamps."""

    def __init__(self, renderers: Iterable[Renderer] = ()) -> None:
        self._by_mime: dict[str, Renderer] = {}
        for renderer in renderers:
            self.register(renderer)

    @classmethod
    def bundled(cls) -> RendererRegistry:
        """The shipped renderers: pdf, docx, pptx and xlsx, each behind its extra."""
        return cls((PdfRenderer(), DocxRenderer(), PptxRenderer(), XlsxRenderer()))

    def register(self, renderer: Renderer) -> None:
        """Claim every type *renderer* names; a later registration for a type wins.

        The generation string must fit the entry row's column: a stamp
        the engine would refuse is refused here, once and loudly, rather
        than on every reindex of every length-enforcing engine.
        """
        generation = generation_of(renderer)
        if len(generation) > MAX_RENDER_GENERATION_LENGTH:
            msg = f"renderer generation {generation!r} exceeds {MAX_RENDER_GENERATION_LENGTH} characters"
            raise ValueError(msg)
        for mime in renderer.mimes:
            self._by_mime[mime] = renderer

    def resolve(self, mime: str) -> Renderer | None:
        """The renderer for *mime*: an exact claim, else the first claimed supertype."""
        seen: set[str] = set()
        current: str | None = mime
        while current is not None and current not in seen:
            renderer = self._by_mime.get(current)
            if renderer is not None:
                return renderer
            seen.add(current)
            current = SUPERTYPES.get(current)
        return None

    def generation(self, mime: str) -> str:
        """The generation a rendering of *mime* is stamped with today."""
        renderer = self.resolve(mime)
        return UNSUPPORTED_GENERATION if renderer is None else generation_of(renderer)

    def generations(self) -> frozenset[str]:
        """Every generation a current stamp may carry: one per renderer plus the unsupported mark."""
        return frozenset(generation_of(renderer) for renderer in self._by_mime.values()) | {UNSUPPORTED_GENERATION}

    def claims(self) -> dict[str, str]:
        """``media type → generation`` for every type some renderer serves, directly or by supertype.

        The dirty predicate's per-type truth: a row is current only when
        its stamp equals the generation its own type resolves to today,
        so a type newly claimed re-dirties the rows stamped unsupported.
        Renderer-sized — the claimed types plus the alias table — never
        corpus-sized.
        """
        claimed: dict[str, str] = {}
        for mime in (*self._by_mime, *SUPERTYPES):
            renderer = self.resolve(mime)
            if renderer is not None:
                claimed[mime] = generation_of(renderer)
        return claimed

    def render(self, source: RenderSource, limits: RenderLimits) -> Rendering:
        """Render *source*, or answer the classified state when no renderer can."""
        renderer = self.resolve(source.mime)
        if renderer is None:
            return failure("unsupported", f"no renderer for {source.mime}")
        if renderer.version is None:
            return failure("unavailable", f"the {renderer.name} renderer needs vfs[{renderer.extra}]")
        try:
            rendering = renderer.render(source, limits)
        except Exception as exc:  # a renderer's surprise is a state on the row, never a raise
            return failure_from(exc, renderer.name)
        return settle(rendering, renderer.name)
