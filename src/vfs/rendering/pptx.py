"""The pptx renderer: one slide block per slide, shapes in slide order, on python-pptx.

The slide's title is its heading; every other shape's text follows in
the slide's own order, tables as rows with the first row the header,
pictures as placeholders carrying the shape's name, groups walked
into as deep as the embedded-depth limit allows. The slide's notes are
a sub-block after it. Master and layout text stays off: a footer
rendered on every slide would hit on every slide.
"""

from __future__ import annotations

from io import BytesIO
from time import monotonic
from typing import TYPE_CHECKING, Any

from vfs.models.media import PPTX
from vfs.rendering.markdown import Builder
from vfs.rendering.seam import BundledRenderer, Rendering, failure_from, load_library

if TYPE_CHECKING:
    from vfs.rendering.seam import RenderLimits, RenderSource


class PptxRenderer(BundledRenderer):
    """Slides to slide blocks through python-pptx."""

    name = "pptx"
    extra = "pptx"
    mimes = (PPTX,)
    package = "pptx"
    distribution = "python-pptx"

    def render(self, source: RenderSource, limits: RenderLimits) -> Rendering:
        pptx = self.library
        started = monotonic()
        try:
            presentation = pptx.Presentation(BytesIO(source.data))
        except Exception as exc:  # a file python-pptx cannot open is malformed input, not a surprise
            return failure_from(exc, self.name, "corrupt")
        shapes_enum = load_library("pptx.enum.shapes")
        assert shapes_enum is not None  # the package opened the file; its enum module is present
        shape_types = shapes_enum.MSO_SHAPE_TYPE
        slides = list(presentation.slides)
        builder = Builder(limits, input_bytes=len(source.data), total_units=len(slides), started=started)
        walker = _Shapes(builder, group=shape_types.GROUP, picture=shape_types.PICTURE, depth=limits.embedded_depth)
        for number, slide in enumerate(slides, 1):
            if not builder.unit("slide", number):
                break
            title = slide.shapes.title
            title_id = None if title is None else title.shape_id
            if title is not None:
                builder.heading(2, title.text_frame.text)
            for shape in slide.shapes:
                if shape.shape_id != title_id:
                    walker.walk(shape)
            if slide.has_notes_slide:
                notes = slide.notes_slide.notes_text_frame.text
                if notes.strip():
                    builder.heading(3, "Notes")
                    builder.paragraph(notes)
        return builder.build()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


class _Shapes:
    """The shape walk: text frames, tables, pictures and groups, numbering the pictures.

    Groups are the containers this format nests; *depth* is how many
    levels of them are followed. A group past the limit is dropped and
    the rendering is marked partial.
    """

    def __init__(self, builder: Builder, *, group: Any, picture: Any, depth: int) -> None:
        self._builder = builder
        self._group = group
        self._picture = picture
        self._depth = depth
        self._pictures = 0

    def walk(self, shape: Any, depth: int = 0) -> None:
        if shape.shape_type == self._group:
            if depth >= self._depth:
                self._builder.drop_embedded()
                return
            for member in shape.shapes:
                self.walk(member, depth + 1)
        elif shape.shape_type == self._picture:
            self._pictures += 1
            self._builder.image(shape.name, self._pictures)
        elif shape.has_table:
            self._builder.table([[cell.text for cell in row.cells] for row in shape.table.rows])
        elif shape.has_text_frame:
            for paragraph in shape.text_frame.paragraphs:
                self._builder.paragraph(paragraph.text)
