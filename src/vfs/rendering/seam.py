"""The renderer seam: what a renderer receives, what it returns, the limits it honours.

A renderer turns one binary body into a line-oriented Markdown
*rendering*: ``render(source, limits) -> Rendering``. The source is the
bytes, the sniffed media type and the entry's name; the result is a
value — the text, the unit table (pages, slides, sheets), the status,
the reason, and for images the dimensions. Renderers are synchronous
and CPU-bound; storage hops them off the event loop and owns every
budget beyond the per-render limits passed in.

    class MyRenderer:
        name = "pdf"
        extra = "pdf"
        mimes = ("application/pdf",)

        @property
        def version(self) -> str | None: ...   # None when the library is absent
        def render(self, source: RenderSource, limits: RenderLimits) -> Rendering: ...

A rendering that could not be made is a status with a reason, never a
body: ``Rendering.text`` is ``None`` for every status that leaves no
content row behind.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import json
import re
from dataclasses import dataclass
from functools import cache
from typing import TYPE_CHECKING, Any, ClassVar, Final, NamedTuple, Protocol, runtime_checkable

from vfs.models.media import MAX_RENDER_DETAIL_LENGTH, RENDER_STATUSES, RENDERED_STATUSES
from vfs.models.version import line_count

if TYPE_CHECKING:
    from vfs.models.media import RenderStatus

# One rendering's character budget: the gram index's eligibility ceiling,
# so a rendering served in full is also one the index can carry whole.
RENDER_CHARS: Final = 2 * 1024 * 1024
# Output characters per input byte past the floor: the decompression-bomb
# guard. A hit is always a loud failure, never a cut.
RENDER_RATIO: Final = 100
RENDER_RATIO_FLOOR: Final = 1_000_000
# Embedded objects: how deep a renderer follows containers, and how many
# placeholders one rendering carries before the rest are dropped as partial.
RENDER_EMBEDDED_DEPTH: Final = 1
RENDER_EMBEDDED_COUNT: Final = 1_000
# Units (pages, slides, sheets) one rendering walks before it is cut.
RENDER_PAGES: Final = 10_000
# Wall seconds one render may spend before the text so far is kept as partial.
RENDER_SECONDS: Final = 60.0

# The generation stamped on a bytes entry no renderer claims; a later
# registration changes it, and the skip law retries the entry.
UNSUPPORTED_GENERATION: Final = "none/unsupported"
# The generation suffix of a renderer whose library is not installed.
UNAVAILABLE_VERSION: Final = "unavailable"
# A code point no UTF-8 encoder accepts; replaced before any text reaches a bind.
_LONE_SURROGATE: Final = re.compile("[\ud800-\udfff]")


@dataclass(frozen=True)
class RenderLimits:
    """The caps one render runs inside; a host may lower them, never raise the ratio."""

    chars: int = RENDER_CHARS
    ratio: int = RENDER_RATIO
    embedded_depth: int = RENDER_EMBEDDED_DEPTH
    embedded_count: int = RENDER_EMBEDDED_COUNT
    pages: int = RENDER_PAGES
    seconds: float = RENDER_SECONDS

    def __post_init__(self) -> None:
        for name in ("chars", "ratio", "embedded_depth", "embedded_count", "pages", "seconds"):
            if getattr(self, name) <= 0:
                msg = f"RenderLimits.{name} must be positive, got {getattr(self, name)!r}"
                raise ValueError(msg)
        if self.ratio > RENDER_RATIO:
            msg = f"RenderLimits.ratio may be lowered but never raised past {RENDER_RATIO}, got {self.ratio}"
            raise ValueError(msg)


class RenderSource(NamedTuple):
    """One body to render: its bytes, its sniffed media type, the entry's name."""

    data: bytes
    mime: str
    name: str


class Unit(NamedTuple):
    """One unit of a rendering — a page, slide or sheet — and where its marker sits.

    ``first_line`` is the 1-based line of the unit's marker in the
    rendering; ``hidden`` is the sheet's view flag, text being in the
    file regardless.
    """

    kind: str
    number: int
    label: str | None
    first_line: int
    hidden: bool = False


class Rendering(NamedTuple):
    """What a render produced: the text, its units, where it stands, and why.

    ``text`` is ``None`` for every status that leaves no content row
    (pending, empty, unsupported, unavailable, the failures) and a
    normalised UTF-8 string for ``ok``, ``truncated`` and ``partial``.
    """

    status: RenderStatus
    text: str | None = None
    units: tuple[Unit, ...] = ()
    detail: str | None = None
    width: int | None = None
    height: int | None = None

    @property
    def lines(self) -> int:
        """The line count the entry row records, under the one law text entries use."""
        return 0 if self.text is None else line_count(self.text)


@runtime_checkable
class Renderer(Protocol):
    """A per-format renderer: the types it reads and the means to render one."""

    @property
    def name(self) -> str:
        """The renderer's short name, the first half of its generation string."""
        ...

    @property
    def extra(self) -> str:
        """The uv extra that supplies its parser library (``vfs[<extra>]``)."""
        ...

    @property
    def mimes(self) -> tuple[str, ...]:
        """The exact media types it claims; the registry walks supertypes to them."""
        ...

    @property
    def version(self) -> str | None:
        """The renderer's version with its library's, or ``None`` when the library is absent."""
        ...

    def render(self, source: RenderSource, limits: RenderLimits) -> Rendering:
        """Render one body within *limits*; raises only on the unexpected."""
        ...


# ---------------------------------------------------------------------------
# Generation strings and bounded detail
# ---------------------------------------------------------------------------


def generation_of(renderer: Renderer) -> str:
    """``<name>/<version>``, or ``<name>/unavailable`` when the library is missing.

    Installing the extra changes the generation, so the skip law
    retries every entry stamped unavailable on the next reindex.
    """
    version = renderer.version
    return f"{renderer.name}/{UNAVAILABLE_VERSION if version is None else version}"


def sanitize(text: str) -> str:
    """*text* with NULs dropped and lone surrogates replaced — a string every engine's driver can bind.

    A parser may hand back either (pypdf decodes ToUnicode maps with
    surrogatepass; a host renderer's exception may quote raw bytes), and
    Postgres ``TEXT`` refuses NULs while every driver refuses a lone
    surrogate. Cleaned once here, at the seam, so no rendering or reason
    can wedge the landing.
    """
    cleaned = text.replace("\x00", "")
    try:
        cleaned.encode("utf-8")
    except UnicodeEncodeError:
        cleaned = _LONE_SURROGATE.sub("\ufffd", cleaned)
    return cleaned


def bounded_detail(text: str) -> str:
    """*text* cleaned and cut to the entry row's detail column, never free-form beyond it."""
    clean = sanitize(text)
    return clean if len(clean) <= MAX_RENDER_DETAIL_LENGTH else clean[: MAX_RENDER_DETAIL_LENGTH - 1] + "…"


def settle(rendering: Rendering, renderer: str) -> Rendering:
    """*rendering* as the row may carry it: a known settled status, text iff the status serves text.

    The registry applies this to every renderer's answer, bundled or
    host-supplied: an unknown or pending status is a ``failed`` state
    naming the renderer; a rendered status with no text is ``failed``;
    a no-body status drops any text it carried; served text is cleaned,
    trailing blank lines trimmed, and ended with one newline, so the
    stored line count is the text's.
    """
    status = rendering.status
    if status not in RENDER_STATUSES or status == "pending":
        return failure("failed", f"{renderer}: returned the status {status!r}, which a rendering cannot carry")
    if status in RENDERED_STATUSES:
        if rendering.text is None:
            return failure("failed", f"{renderer}: returned {status!r} with no text")
        text = sanitize(rendering.text).rstrip("\n") + "\n"
        detail = None if rendering.detail is None else bounded_detail(rendering.detail)
        return Rendering(status, text, tuple(rendering.units), detail, rendering.width, rendering.height)
    detail = None if rendering.detail is None else bounded_detail(rendering.detail)
    return Rendering(status, None, tuple(rendering.units), detail, rendering.width, rendering.height)


def failure(status: RenderStatus, detail: str) -> Rendering:
    """A rendering that is a status with its reason and no body."""
    assert status not in RENDERED_STATUSES
    return Rendering(status=status, detail=bounded_detail(detail))


def failure_from(exc: BaseException, renderer: str, status: RenderStatus = "failed") -> Rendering:
    """The classified form of a renderer's exception: class, capped message, renderer."""
    message = str(exc).strip() or "no message"
    return failure(status, f"{renderer}: {type(exc).__name__}: {message}")


# ---------------------------------------------------------------------------
# The unit table as JSON on the entry row
# ---------------------------------------------------------------------------


def units_to_json(units: tuple[Unit, ...]) -> str | None:
    """The unit table serialised for the entry row; ``None`` when there are no units."""
    if not units:
        return None
    return json.dumps([unit._asdict() for unit in units], separators=(",", ":"))


def units_from_json(text: str | None) -> tuple[Unit, ...]:
    """The unit table read back from the entry row; absent is empty."""
    if text is None:
        return ()
    return tuple(Unit(**item) for item in json.loads(text))


# ---------------------------------------------------------------------------
# Bundled renderers: a library resolved once, a version derived from it
# ---------------------------------------------------------------------------


@cache
def load_library(package: str) -> Any | None:
    """Import *package* once per process; ``None`` when the extra is not installed."""
    try:
        return importlib.import_module(package)
    except ImportError:
        return None


class BundledRenderer:
    """Base of the shipped renderers: one parser library, probed at construction.

    A subclass names its ``package`` (the import name) and
    ``distribution`` (the installed project the version comes from) and
    bumps ``revision`` when its own output changes; the generation then
    changes on either, and the skip law re-renders.
    """

    name: ClassVar[str]
    extra: ClassVar[str]
    mimes: ClassVar[tuple[str, ...]]
    package: ClassVar[str]
    distribution: ClassVar[str]
    revision: ClassVar[int] = 1

    def __init__(self) -> None:
        self._library = self.load()
        # The version is read once: dist-info metadata costs a file read per lookup.
        self._version = (
            None
            if self._library is None
            else f"{self.revision}+{self.distribution}-{importlib.metadata.version(self.distribution)}"
        )

    def load(self) -> Any | None:
        """Resolve the parser library; a test may override this to stage its absence."""
        return load_library(self.package)

    @property
    def available(self) -> bool:
        return self._library is not None

    @property
    def library(self) -> Any:
        """The parser module; only valid once ``available`` has answered true."""
        assert self._library is not None
        return self._library

    @property
    def version(self) -> str | None:
        return self._version
