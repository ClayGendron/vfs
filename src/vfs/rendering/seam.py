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
content row behind. An Office renderer measures its zip container's
directory and verifies every member's stream against it before its
library opens it (:func:`container_refusal`).
"""

from __future__ import annotations

import binascii
import copy
import importlib
import importlib.metadata
import json
import re
import zipfile
from dataclasses import dataclass
from functools import cache
from io import BytesIO
from typing import TYPE_CHECKING, Any, ClassVar, Final, NamedTuple, Protocol, runtime_checkable

from vfs.deadline import CHECK_EVERY
from vfs.models.media import MAX_RENDER_DETAIL_LENGTH, RENDER_STATUSES, RENDERED_STATUSES
from vfs.models.version import line_count

if TYPE_CHECKING:
    from vfs.deadline import Deadline
    from vfs.models.media import RenderStatus

# One rendering's character budget: the gram index's eligibility ceiling,
# so a rendering served in full is also one the index can carry whole.
RENDER_CHARS: Final = 2 * 1024 * 1024
# Output characters per input byte past the floor: it bounds the rendering's text, never what a parser
# decompresses to make it. A hit is always a loud failure, never a cut.
RENDER_RATIO: Final = 100
RENDER_RATIO_FLOOR: Final = 1_000_000
# Embedded objects: how deep a renderer follows containers, and how many
# placeholders one rendering carries before the rest are dropped as partial.
RENDER_EMBEDDED_DEPTH: Final = 1
RENDER_EMBEDDED_COUNT: Final = 1_000
# Units (pages, slides, sheets) one rendering walks before it is cut.
RENDER_PAGES: Final = 10_000
# Wall seconds one render runs under: a container still being verified is refused, and a rendering stops at its
# next unit or table row and keeps its text as partial; a library's own open is not interrupted.
RENDER_SECONDS: Final = 60.0

# Members one Office container's directory may list: the most a zip directory counts without
# its ZIP64 extension, above the members of a deck at the renderer's own slide cap.
CONTAINER_MEMBERS: Final = 65_535
# Uncompressed bytes a docx or pptx container may declare in all: those libraries hold and parse every
# part they read, at up to about twelve times its bytes in memory, so this bounds what one render holds.
CONTAINER_BYTES: Final = 256 << 20
# Uncompressed bytes an xlsx container may declare in all: its library streams its sheets, so this
# admits a full-height sheet of ordinary width; it is the most a 32-bit size field can state.
WORKBOOK_BYTES: Final = 1 << 32
# Declared bytes per stored byte, applied only past the floor of declared bytes, so a small
# document with compressible parts is never refused by it.
CONTAINER_RATIO: Final = 100
CONTAINER_RATIO_FLOOR: Final = 64 << 20
# The most one read of a member's stream returns while the container is verified, so the
# verifying pass holds about one chunk of output and one of input at a time.
CONTAINER_CHUNK: Final = 64 << 10
# The compression methods the Office formats use; any other is refused before a member is read,
# because the others decompress without a bound per call on some supported interpreters.
OOXML_METHODS: Final = frozenset({zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED})

# The generation stamped on a bytes entry no renderer claims; a later
# registration changes it, and the skip law retries the entry.
UNSUPPORTED_GENERATION: Final = "none/unsupported"
# The generation suffix of a renderer whose library is not installed.
UNAVAILABLE_VERSION: Final = "unavailable"
# A code point no UTF-8 encoder accepts; replaced before any text reaches a bind.
_LONE_SURROGATE: Final = re.compile("[\ud800-\udfff]")


@dataclass(frozen=True)
class RenderLimits:
    """The caps one render runs inside.

    The text limits (``chars``, ``ratio``, ``pages``, ``seconds``, the
    embedded caps) act as the rendering is built; the container limits
    (``container_members``, ``container_bytes`` for a library that holds
    what it reads, ``workbook_bytes`` for one that streams its sheets,
    ``container_ratio``) act before an Office library opens its zip
    container, on what its directory declares, and every member's
    stream is then verified against its declaration. A host may raise or
    lower any of them but the output ratio, which may only be lowered; a
    raise does not retry an entry already refused. They bound what a
    renderer will process, never what vfs stores.
    """

    chars: int = RENDER_CHARS
    ratio: int = RENDER_RATIO
    embedded_depth: int = RENDER_EMBEDDED_DEPTH
    embedded_count: int = RENDER_EMBEDDED_COUNT
    pages: int = RENDER_PAGES
    seconds: float = RENDER_SECONDS
    container_members: int = CONTAINER_MEMBERS
    container_bytes: int = CONTAINER_BYTES
    workbook_bytes: int = WORKBOOK_BYTES
    container_ratio: int = CONTAINER_RATIO

    def __post_init__(self) -> None:
        for name in (
            "chars",
            "ratio",
            "embedded_depth",
            "embedded_count",
            "pages",
            "seconds",
            "container_members",
            "container_bytes",
            "workbook_bytes",
            "container_ratio",
        ):
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
# Container measurement
# ---------------------------------------------------------------------------


def container_refusal(
    data: bytes, limits: RenderLimits, renderer: str, deadline: Deadline, *, byte_limit: int
) -> Rendering | None:
    """The refusal of an Office zip container past its limits, or ``None`` once it is measured and verified.

    The directory is read first, and alone: the member count against
    ``limits.container_members``; each member's compression method
    against :data:`OOXML_METHODS` and its name against the names seen;
    the declared total against *byte_limit*, the caller's own family's
    field (``container_bytes`` for a library that holds what it reads,
    ``workbook_bytes`` for one that streams its sheets); and the total
    against ``limits.container_ratio`` times the container's size, past
    :data:`CONTAINER_RATIO_FLOOR`. A ratio past deflate's ceiling, about
    1,032 to 1, refuses nothing a verified stream could hold, so a host
    that raises it that far has turned it off. Only then is every
    member's stream read once, in reads of at most
    :data:`CONTAINER_CHUNK` bytes, *deadline* asked before the first
    read and before every ``CHECK_EVERY``-th.

    When this answers ``None``, every member is stored or deflated, is
    named once, and has a stream no longer than its declared size whose
    CRC-32 matches the declared one. So every read a library makes of a
    member decompresses at most that member's declared size, and one
    read of every member decompresses at most the declared total, which
    the limits bound. It does not bound what a library's parser spends
    on the bytes it is handed, nor a library reading one member twice.

    The cost is one parse of the directory, about 580 bytes held a
    member while it runs, and one decompression of every member with
    one chunk held at a time. A limit, or a container still being
    verified at the deadline, is ``failed``; a container the Office
    formats do not admit, or one zipfile cannot read, is ``corrupt``.
    It never raises.
    """
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            members = archive.infolist()
            count, cap = len(members), limits.container_members
            if count > cap:
                return failure(
                    "failed",
                    f"{renderer}: the container holds {count} members, {count - cap} past the {cap}-member limit",
                )
            names: set[str] = set()
            total = 0
            for member in members:
                name = member.filename
                if member.compress_type not in OOXML_METHODS:
                    return failure(
                        "corrupt",
                        f"{renderer}: member {name!r} uses compression method {member.compress_type}, "
                        "which the Office formats do not use",
                    )
                if name in names:
                    return failure("corrupt", f"{renderer}: member {name!r} is named twice in the container")
                names.add(name)
                total += member.file_size
            if total > byte_limit:
                return failure(
                    "failed",
                    f"{renderer}: the container declares {total} uncompressed bytes, "
                    f"{total - byte_limit} past the {byte_limit}-byte limit",
                )
            allowed = max(CONTAINER_RATIO_FLOOR, limits.container_ratio * len(data))
            if total > allowed:
                return failure(
                    "failed",
                    f"{renderer}: the container declares {total} uncompressed bytes, {total - allowed} past the "
                    f"{allowed} its {len(data)} bytes allow at {limits.container_ratio}x",
                )
            return _verify(archive, members, limits, renderer, deadline)
    except Exception as exc:  # a container zipfile cannot read is malformed input, as each library would find it
        return failure_from(exc, renderer, "corrupt")


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
        version = None if self._library is None else _distribution_version(self.distribution)
        self._version = None if version is None else f"{self.revision}+{self.distribution}-{version}"

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


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _verify(
    archive: zipfile.ZipFile, members: list[zipfile.ZipInfo], limits: RenderLimits, renderer: str, deadline: Deadline
) -> Rendering | None:
    """Every member's stream read once against its declared size and CRC-32, *deadline* asked on the cadence.

    Each member is opened as a copy of its entry that declares one byte
    more and carries no checksum: zipfile cuts a stream at the size it is
    given and checks a CRC only when the entry has one, so the extra byte
    shows an overrun whatever the declared checksum says, and the
    checksum is folded here over the whole stream read. Reads are
    counted across the container, so the clock is read once every
    ``CHECK_EVERY`` reads, members included.
    """
    reads = 0
    for member in members:
        probe = copy.copy(member)
        probe.file_size = member.file_size + 1
        del probe.CRC
        seen = 0
        crc = 0
        with archive.open(probe) as stream:
            while True:
                if reads % CHECK_EVERY == 0 and deadline.expired():
                    return failure(
                        "failed", f"{renderer}: the container was not verified within {limits.seconds:g} seconds"
                    )
                chunk = stream.read(CONTAINER_CHUNK)
                reads += 1
                if not chunk:
                    break
                seen += len(chunk)
                if seen > member.file_size:
                    return failure(
                        "corrupt",
                        f"{renderer}: member {member.filename!r} holds more than the {member.file_size} bytes "
                        "the container declares for it",
                    )
                crc = binascii.crc32(chunk, crc)
        if crc != member.CRC:
            return failure(
                "corrupt",
                f"{renderer}: member {member.filename!r} does not match the CRC-32 the container declares for it",
            )
    return None


@cache
def _distribution_version(distribution: str) -> str:
    """The installed version of *distribution*, read once per process: dist-info is a file read per lookup."""
    return importlib.metadata.version(distribution)
