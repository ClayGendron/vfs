"""The binary side of an entry: its source, its render state, its sniffed type.

An entry's body is text or bytes, never both — ``source`` says which
table holds it. A bytes entry is searchable only through a *rendering*,
a text derived from its bytes by a per-format renderer and stamped on
the entry row; ``render_status`` is where that stands. A rendering that
could not be made is a status with a reason, never a body.

``sniff_mime`` reads the leading bytes: magic decides the family, and
the declared type or the extension may only narrow among the
candidates magic allows (one zip container, the ten Office types).
"""

from __future__ import annotations

from typing import Final, Literal, get_args

Source = Literal["text", "bytes"]
SOURCES: Final[frozenset[str]] = frozenset(get_args(Source))

RenderStatus = Literal[
    "pending",  # written, not yet rendered
    "ok",  # rendered in full
    "truncated",  # rendered up to the character budget
    "partial",  # a time or embedded limit cut it; the text so far is valid
    "empty",  # parsed, no text
    "unsupported",  # no renderer for the type
    "unavailable",  # a renderer exists but its extra is not installed
    "encrypted",
    "corrupt",
    "failed",
]
RENDER_STATUSES: Final[frozenset[str]] = frozenset(get_args(RenderStatus))

# Statuses that leave a content row behind: the text the verbs may serve.
RENDERED_STATUSES: Final[frozenset[str]] = frozenset({"ok", "truncated", "partial"})
# Statuses a renderer has pronounced: everything but the not-yet-attempted one.
SETTLED_STATUSES: Final[frozenset[str]] = RENDER_STATUSES - {"pending"}
# Settled with no text and a reason: no renderer, no library, or a refusal.
FAILURE_STATUSES: Final[frozenset[str]] = SETTLED_STATUSES - RENDERED_STATUSES - {"empty"}

# The bounded reason a failed or cut rendering carries on its entry row.
MAX_RENDER_DETAIL_LENGTH: Final = 1024
# The widest renderer generation the entry row stores (``<name>/<version>``).
MAX_RENDER_GENERATION_LENGTH: Final = 64

OCTET_STREAM: Final = "application/octet-stream"
ZIP: Final = "application/zip"
PDF: Final = "application/pdf"
DOCX: Final = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX: Final = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PPTX: Final = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
# The zip-container Office types by extension: the three plain ones and
# their macro-enabled, template and slideshow siblings.
OOXML_TYPES: Final[dict[str, str]] = {
    "docx": DOCX,
    "docm": "application/vnd.ms-word.document.macroEnabled.12",
    "dotx": "application/vnd.openxmlformats-officedocument.wordprocessingml.template",
    "xlsx": XLSX,
    "xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12",
    "xltx": "application/vnd.openxmlformats-officedocument.spreadsheetml.template",
    "pptx": PPTX,
    "pptm": "application/vnd.ms-powerpoint.presentation.macroEnabled.12",
    "potx": "application/vnd.openxmlformats-officedocument.presentationml.template",
    "ppsx": "application/vnd.openxmlformats-officedocument.presentationml.slideshow",
}
_OOXML_BY_TYPE: Final[frozenset[str]] = frozenset(OOXML_TYPES.values())
# The supertype walk: a sibling type falls to the plain type whose renderer reads it.
SUPERTYPES: Final[dict[str, str]] = {
    OOXML_TYPES["docm"]: DOCX,
    OOXML_TYPES["dotx"]: DOCX,
    OOXML_TYPES["xlsm"]: XLSX,
    OOXML_TYPES["xltx"]: XLSX,
    OOXML_TYPES["pptm"]: PPTX,
    OOXML_TYPES["potx"]: PPTX,
    OOXML_TYPES["ppsx"]: PPTX,
    "application/x-pdf": PDF,
}

# Leading-byte signatures, longest first where one is a prefix of another.
_MAGIC: Final[tuple[tuple[bytes, str], ...]] = (
    (b"%PDF-", PDF),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"II*\x00", "image/tiff"),
    (b"MM\x00*", "image/tiff"),
    (b"PK\x03\x04", ZIP),
)
SNIFF_LENGTH: Final = 16


def sniff_mime(head: bytes, *, declared: str | None = None, ext: str | None = None) -> str:
    """The media type of a body whose first bytes are *head*.

    Magic decides the family. A zip container is one of the Office
    types when the extension or the declared type says so, else a plain
    zip. A body no signature matches keeps the declared type, or is an
    octet stream.
    """
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    for signature, mime in _MAGIC:
        if head.startswith(signature):
            if mime != ZIP:
                return mime
            if ext is not None and ext.lower() in OOXML_TYPES:
                return OOXML_TYPES[ext.lower()]
            if declared in _OOXML_BY_TYPE:
                return declared
            return ZIP
    return declared or OCTET_STREAM
