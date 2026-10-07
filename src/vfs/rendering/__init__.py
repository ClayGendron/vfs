"""Renderers: a binary body in, a line-oriented Markdown rendering out.

The seam (:mod:`~vfs.rendering.seam`) names what a renderer receives
and returns; the registry (:mod:`~vfs.rendering.registry`) maps a
media type to its renderer and the generation it stamps; the bundled
renderers read PDF, docx, pptx and xlsx behind their extras.
"""

from vfs.rendering.docx import DocxRenderer
from vfs.rendering.markdown import Builder, unit_marker
from vfs.rendering.pdf import PdfRenderer
from vfs.rendering.pptx import PptxRenderer
from vfs.rendering.registry import RendererRegistry
from vfs.rendering.seam import (
    RENDER_CHARS,
    RENDER_SECONDS,
    UNSUPPORTED_GENERATION,
    BundledRenderer,
    Renderer,
    Rendering,
    RenderLimits,
    RenderSource,
    Unit,
    generation_of,
    units_from_json,
    units_to_json,
)
from vfs.rendering.xlsx import XlsxRenderer

__all__ = [
    "RENDER_CHARS",
    "RENDER_SECONDS",
    "UNSUPPORTED_GENERATION",
    "Builder",
    "BundledRenderer",
    "DocxRenderer",
    "PdfRenderer",
    "PptxRenderer",
    "RenderLimits",
    "RenderSource",
    "Renderer",
    "RendererRegistry",
    "Rendering",
    "Unit",
    "XlsxRenderer",
    "generation_of",
    "unit_marker",
    "units_from_json",
    "units_to_json",
]
