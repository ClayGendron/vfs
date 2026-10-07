"""The PDF renderer: one page block per page, text in content-stream order, on pypdf.

A page with no text layer still gets its marker and nothing else, so a
scanned page is visible as empty rather than silent; a document with
no text on any page is ``empty``. A password-protected file that the
empty password does not open is ``encrypted``; a file pypdf cannot
parse is ``corrupt``. Embedded images are not placeholder-marked here:
reading a PDF's image resources costs a decode per image, and the
first landing keeps the renderer a text pass.
"""

from __future__ import annotations

from io import BytesIO
from time import monotonic
from typing import TYPE_CHECKING

from vfs.models.media import PDF
from vfs.rendering.markdown import Builder
from vfs.rendering.seam import BundledRenderer, Rendering, failure, failure_from

if TYPE_CHECKING:
    from vfs.rendering.seam import RenderLimits, RenderSource


class PdfRenderer(BundledRenderer):
    """Pages to page blocks through pypdf."""

    name = "pdf"
    extra = "pdf"
    mimes = (PDF,)
    package = "pypdf"
    distribution = "pypdf"

    def render(self, source: RenderSource, limits: RenderLimits) -> Rendering:
        pypdf = self.library
        started = monotonic()
        try:
            reader = pypdf.PdfReader(BytesIO(source.data))
            if reader.is_encrypted and not reader.decrypt(""):
                return failure("encrypted", "pdf: password-protected, and the empty password does not open it")
            pages = reader.pages
            builder = Builder(limits, input_bytes=len(source.data), total_units=len(pages), started=started)
            for number, page in enumerate(pages, 1):
                if not builder.unit("page", number):
                    break
                builder.paragraph(page.extract_text())
        except pypdf.errors.PyPdfError as exc:
            return failure_from(exc, self.name, "corrupt")
        return builder.build()
