"""The ``Chunk`` model — one indexed unit of a file's content.

A chunk is entry-scoped metadata, not a namespace entry: its identity is
``(file, chunk_index)`` — the owning file's path plus its position in the
split — mirroring the ``chunks`` table's ``(entry_id, chunk_index)`` key. It
carries no ``path`` or ``name`` and is never placed in the namespace.

:meth:`Chunk.split` is the single construction door: it dispatches the split
by file extension (notebooks, tree-sitter grammars, recursive separators) and
enumerates the resulting chunks in order.

    Chunk.split(file=Path("/src/auth.py"), content=source, ext="py")
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from pydantic import BaseModel, field_validator, model_validator

from vfs.models.chunking import (
    NOTEBOOK_EXTENSION,
    grammar_for_extension,
    split_code,
    split_code_batch,
    split_notebook,
    split_with_line_ranges,
)
from vfs.models.entry import ContentHash  # noqa: TC001 — Pydantic needs this at runtime for field resolution
from vfs.models.vector import Vector  # noqa: TC001 — Pydantic needs this at runtime for field resolution
from vfs.paths import Path  # noqa: TC001 — Pydantic needs this at runtime for field resolution

if TYPE_CHECKING:
    from collections.abc import Sequence


class Chunk(BaseModel):
    """One split unit of a file, addressed by its owning file + index.

    ``file`` references the owning file by its path — a reference, not this
    chunk's own address. ``content_hash`` is measured from ``content`` when not
    supplied; ``encoded`` is the gram-index dirty flag; ``embedding`` is
    populated by the indexing pipeline, never at split time.
    """

    file: Path
    chunk_index: int
    line_start: int
    line_end: int
    content: str
    content_hash: ContentHash | None = None
    encoded: bool = False
    embedding: Vector | None = None

    @field_validator("content")
    @classmethod
    def _reject_null_bytes(cls, value: str) -> str:
        """Reject null bytes in stored text — they are invalid in SQL text columns."""
        if "\x00" in value:
            msg = "content contains null bytes"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def _validate_shape(self) -> Chunk:
        if self.file == "/":
            msg = "file must reference a file, not the root"
            raise ValueError(msg)
        if self.chunk_index < 0:
            msg = f"chunk_index must be >= 0, got {self.chunk_index}"
            raise ValueError(msg)
        if self.line_start < 1 or self.line_end < self.line_start:
            msg = f"invalid line range: {self.line_start}..{self.line_end}"
            raise ValueError(msg)
        if self.content_hash is None:
            self.content_hash = hashlib.sha256(self.content.encode()).hexdigest()
        return self

    @classmethod
    def split(cls, *, file: Path, content: str, ext: str | None) -> list[Chunk]:
        """Split *content* into ordered chunks for *file* — the one construction door.

        Dispatches on the file extension *ext* (no leading dot): notebooks use
        ``split_notebook``, extensions with a tree-sitter grammar use
        structure-aware ``split_code``, and everything else falls back to the
        recursive separator splitter. An empty list signals "no split
        required" — content too short to form a trigram produces no chunks.
        """
        pieces = cls._split_content(content, ext)
        return [
            cls(file=file, chunk_index=index, content=text, line_start=start, line_end=end)
            for index, (text, start, end) in enumerate(pieces)
        ]

    @classmethod
    def split_batch(cls, files: Sequence[tuple[Path, str, str | None]]) -> list[list[Chunk]]:
        """:meth:`split` for many ``(file, content, ext)`` rows at once.

        Grammar-routed files cross the engine seam in a single batch call,
        so the native engine parses them in parallel; notebooks and
        fallback extensions split per row exactly as :meth:`split` would.
        Results are index-aligned with the input.
        """
        routed = [
            (index, grammar)
            for index, (_file, _content, ext) in enumerate(files)
            if ext != NOTEBOOK_EXTENSION and (grammar := grammar_for_extension(ext))
        ]
        code_pieces = split_code_batch([(files[index][1], grammar) for index, grammar in routed])
        pieces_by_index = dict(zip((index for index, _grammar in routed), code_pieces, strict=True))
        out: list[list[Chunk]] = []
        for index, (file, content, ext) in enumerate(files):
            pieces = pieces_by_index.get(index)
            if pieces is None:
                pieces = split_notebook(content) if ext == NOTEBOOK_EXTENSION else split_with_line_ranges(content)
            out.append(
                [
                    cls(file=file, chunk_index=chunk_index, content=text, line_start=start, line_end=end)
                    for chunk_index, (text, start, end) in enumerate(pieces)
                ],
            )
        return out

    @staticmethod
    def _split_content(content: str, ext: str | None) -> list[tuple[str, int, int]]:
        if ext == NOTEBOOK_EXTENSION:
            return split_notebook(content)
        if grammar := grammar_for_extension(ext):
            return split_code(content, language=grammar)
        return split_with_line_ranges(content)
