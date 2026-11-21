"""The renderer seam's values: limits, generations, bounded detail, the unit table on the row, the container check."""

from __future__ import annotations

import binascii
import importlib.metadata
import struct
import zipfile
from io import BytesIO
from typing import TYPE_CHECKING, Any, NamedTuple, cast

import pytest

from tests.support.documents import (
    aliased,
    declared,
    docx_bytes,
    duplicated,
    pptx_bytes,
    recompressed,
    xlsx_bytes,
)
from vfs.deadline import CHECK_EVERY, Deadline
from vfs.models.media import MAX_RENDER_DETAIL_LENGTH
from vfs.rendering import (
    RENDER_CHARS,
    RENDER_SECONDS,
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
from vfs.rendering import seam as seam_module
from vfs.rendering.pdf import PdfRenderer
from vfs.rendering.seam import (
    CONTAINER_BYTES,
    CONTAINER_CHUNK,
    CONTAINER_MEMBERS,
    CONTAINER_RATIO,
    CONTAINER_RATIO_FLOOR,
    OOXML_METHODS,
    RENDER_RATIO,
    WORKBOOK_BYTES,
    bounded_detail,
    container_refusal,
    failure,
    failure_from,
    load_library,
    sanitize,
    settle,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from vfs.models.media import RenderStatus

DOCUMENT = "word/document.xml"
NEVER = Deadline.never()
# A zip local header's offsets: the name and extra lengths, then the name itself.
_LOCAL_LENGTHS_AT = 26
_LOCAL_NAME_AT = 30


class _Reads(NamedTuple):
    """What the zip reader was asked for: members opened, members read whole, and each stream read's size."""

    opens: list[str]
    wholes: list[str]
    chunks: list[tuple[str, int]]


class _Clock:
    """A fake clock that answers 0.0 on its first read and 1e9 on every later one, counting its reads."""

    def __init__(self) -> None:
        self.reads = 0

    def __call__(self) -> float:
        self.reads += 1
        return 0.0 if self.reads == 1 else 1e9


@pytest.fixture
def watch(monkeypatch: pytest.MonkeyPatch) -> Callable[[], _Reads]:
    """Installs, when called, counting spies on the zip reader's member opens, whole reads and stream reads."""

    def install() -> _Reads:
        record = _Reads([], [], [])
        real_open, real_read, real_chunk = zipfile.ZipFile.open, zipfile.ZipFile.read, zipfile.ZipExtFile.read

        def counting_open(self: zipfile.ZipFile, name: Any, *args: Any, **kwargs: Any) -> Any:
            record.opens.append(name if isinstance(name, str) else name.filename)
            return real_open(self, name, *args, **kwargs)

        def counting_read(self: zipfile.ZipFile, name: Any, *args: Any, **kwargs: Any) -> bytes:
            record.wholes.append(name if isinstance(name, str) else name.filename)
            return real_read(self, name, *args, **kwargs)

        def counting_chunk(self: zipfile.ZipExtFile, n: int | None = -1) -> bytes:
            data = real_chunk(self, n)
            record.chunks.append((self.name, len(data)))
            return data

        monkeypatch.setattr(zipfile.ZipFile, "open", counting_open)
        monkeypatch.setattr(zipfile.ZipFile, "read", counting_read)
        monkeypatch.setattr(zipfile.ZipExtFile, "read", counting_chunk)
        return record

    return install


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
    def test_the_library_version_is_read_once_per_process(self, monkeypatch) -> None:
        # Dist-info is a file read per lookup; every renderer instance of a
        # distribution shares the one read, however many registries are built.
        calls: list[str] = []
        real = importlib.metadata.version

        def counting(name: str) -> str:
            calls.append(name)
            return real(name)

        monkeypatch.setattr(importlib.metadata, "version", counting)
        seam_module._distribution_version.cache_clear()
        renderers = [PdfRenderer() for _ in range(3)]
        for renderer in renderers:
            for _ in range(5):
                assert renderer.version is not None
        assert calls == ["pypdf"]


class TestContainerRefusal:
    def test_the_container_limits_are_the_declared_constants(self) -> None:
        """Each container limit is its constant, must be positive, and may be raised by a host."""
        assert CONTAINER_MEMBERS == 65_535
        assert CONTAINER_BYTES == 256 << 20
        assert WORKBOOK_BYTES == 1 << 32
        assert CONTAINER_RATIO == 100
        assert CONTAINER_RATIO_FLOOR == 64 << 20
        assert CONTAINER_CHUNK == 64 << 10
        assert frozenset({0, 8}) == OOXML_METHODS
        defaults = {
            "container_members": CONTAINER_MEMBERS,
            "container_bytes": CONTAINER_BYTES,
            "workbook_bytes": WORKBOOK_BYTES,
            "container_ratio": CONTAINER_RATIO,
        }
        limits = RenderLimits()
        assert {name: getattr(limits, name) for name in defaults} == defaults
        for name, default in defaults.items():
            with pytest.raises(ValueError, match=name):
                RenderLimits(**{name: 0})
            assert getattr(RenderLimits(**{name: 4 * default}), name) == 4 * default

    def test_a_container_within_its_limits_is_not_refused(self) -> None:
        """The three fixtures and a stored docx pass; the overrun test turned ``>=`` refuses every one."""
        assert _check(_docx()) is None
        assert _check(_pptx(), renderer="pptx") is None
        assert _check(_xlsx(), renderer="xlsx") is None
        assert _check(recompressed(_docx(), zipfile.ZIP_STORED)) is None

    def test_a_container_past_the_member_limit_is_refused(self) -> None:
        """At the limit and one past it: the member-count comparison turned ``>=`` fails the first."""
        data = _docx()
        n = len(_members(data))
        detail = f"docx: the container holds {n} members, 1 past the {n - 1}-member limit"
        assert _check(data, RenderLimits(container_members=n - 1)) == Rendering("failed", detail=detail)
        assert _check(data, RenderLimits(container_members=n)) is None

    @pytest.mark.parametrize("method", [12, 14, 93, 99])
    def test_a_member_with_another_compression_method_is_refused(self, method: int) -> None:
        """bzip2, LZMA, zstd and an unknown method each refused by name: the method test deleted passes them."""
        detail = (
            f"docx: member 'word/document.xml' uses compression method {method}, which the Office formats do not use"
        )
        assert _check(declared(_docx(), DOCUMENT, method=method)) == Rendering("corrupt", detail=detail)

    def test_a_member_named_twice_is_refused(self) -> None:
        """A second directory entry for one name, spelled alike or stored differently but read back by zipfile
        as the same name: the names-seen test deleted passes both, and keyed on the stored name passes the second."""
        detail = "docx: member 'word/document.xml' is named twice in the container"
        assert _check(duplicated(_docx(), DOCUMENT)) == Rendering("corrupt", detail=detail)
        assert _check(aliased(_docx(), DOCUMENT)) == Rendering("corrupt", detail=detail)

    def test_the_directory_checks_refuse_in_the_decided_order(self) -> None:
        """Two directory faults answer with the first in the decided order, the member count before any member
        and a member's method before its name: the count moved after the members, or the name test moved
        ahead of the method test, answers the other fault."""
        data = _docx()
        n = len(_members(data))
        detail = f"docx: the container holds {n} members, 1 past the {n - 1}-member limit"
        bzip2 = recompressed(data, zipfile.ZIP_BZIP2)
        assert _check(bzip2, RenderLimits(container_members=n - 1)) == Rendering("failed", detail=detail)
        twice = declared(duplicated(data, DOCUMENT), DOCUMENT, method=12)
        detail = "docx: member 'word/document.xml' uses compression method 12, which the Office formats do not use"
        assert _check(twice) == Rendering("corrupt", detail=detail)

    def test_a_container_declaring_past_the_byte_limit_is_refused(self) -> None:
        """Each family's limit at one past it, and a raised one at it: the total turned ``>=`` fails the last."""
        detail = "docx: the container declares 268435457 uncompressed bytes, 1 past the 268435456-byte limit"
        assert _check(_declaring(_docx(), DOCUMENT, CONTAINER_BYTES + 1)) == Rendering("failed", detail=detail)
        workbook = _declaring(_xlsx(), "xl/workbook.xml", WORKBOOK_BYTES + 1)
        detail = "xlsx: the container declares 4294967297 uncompressed bytes, 1 past the 4294967296-byte limit"
        refused = _check(workbook, renderer="xlsx", byte_limit=RenderLimits().workbook_bytes)
        assert refused == Rendering("failed", detail=detail)
        limit = 32 << 20
        detail = f"docx: the container declares {limit + 1} uncompressed bytes, 1 past the {limit}-byte limit"
        assert _check(_declaring(_docx(), DOCUMENT, limit + 1), byte_limit=limit) == Rendering("failed", detail=detail)
        assert _check(_declaring(_docx(), DOCUMENT, limit), byte_limit=limit) is None

    def test_a_container_declaring_past_its_ratio_is_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Past the floor, past the ratio, past a lowered ratio: the comparison turned ``>=`` fails each
        boundary, and the ratio read from its module constant in place of the limits fails the lowered one."""
        data = _docx()
        size = len(data)
        detail = (
            "docx: the container declares 67108865 uncompressed bytes, "
            f"1 past the 67108864 its {size} bytes allow at 100x"
        )
        assert _check(_declaring(data, DOCUMENT, CONTAINER_RATIO_FLOOR + 1)) == Rendering("failed", detail=detail)
        assert _check(_declaring(data, DOCUMENT, CONTAINER_RATIO_FLOOR)) is None
        monkeypatch.setattr(seam_module, "CONTAINER_RATIO_FLOOR", 0)
        for ratio in (100, 50):
            limits = RenderLimits(container_ratio=ratio)
            allowed = ratio * size
            detail = (
                f"docx: the container declares {allowed + 1} uncompressed bytes, "
                f"1 past the {allowed} its {size} bytes allow at {ratio}x"
            )
            assert _check(_declaring(data, DOCUMENT, allowed + 1), limits) == Rendering("failed", detail=detail)
            assert _check(_declaring(data, DOCUMENT, allowed), limits) is None

    def test_the_check_reads_the_directory_first_and_each_member_once_in_chunks(
        self, watch: Callable[[], _Reads]
    ) -> None:
        """Every directory refusal opens nothing and reads nothing: the verifying pass moved ahead of any
        directory check reads before that check refuses. A pass opens each member once and reads it in chunks:
        a member read whole, the read size dropped, fails the chunk bound."""
        data = _docx()
        members = _members(data)
        directory_refused = [
            (data, RenderLimits(container_members=len(members) - 1)),
            (recompressed(data, zipfile.ZIP_BZIP2), RenderLimits()),
            (duplicated(data, DOCUMENT), RenderLimits()),
            (_declaring(data, DOCUMENT, CONTAINER_BYTES + 1), RenderLimits()),
            (_declaring(data, DOCUMENT, CONTAINER_RATIO_FLOOR + 1), RenderLimits()),
        ]
        for container, limits in directory_refused:
            reads = watch()
            assert _check(container, limits) is not None
            assert (reads.opens, reads.wholes, reads.chunks) == ([], [], [])
        reads = watch()
        assert _check(data) is None
        assert reads.opens == [info.filename for info in members]
        assert reads.wholes == []
        assert max(size for _, size in reads.chunks) <= CONTAINER_CHUNK
        returned = dict.fromkeys(reads.opens, 0)
        for name, size in reads.chunks:
            returned[name] += size
        assert returned == {info.filename: info.file_size for info in members}

    @pytest.mark.parametrize("checksum", ["checksum-kept", "checksum-matched"])
    def test_a_member_whose_stream_runs_past_its_declared_size_is_refused(
        self, watch: Callable[[], _Reads], checksum: str
    ) -> None:
        """A stream one byte past its declaration, its checksum the whole stream's or the cut one's: the copy
        opened at the declared size passes the matched case and names a checksum in the kept one."""
        data = _docx()
        stream = _stream(data, DOCUMENT)
        cut = len(stream) - 1
        crc = binascii.crc32(stream if checksum == "checksum-kept" else stream[:cut])
        overrun = declared(data, DOCUMENT, file_size=cut, crc=crc)
        reads = watch()
        detail = f"docx: member 'word/document.xml' holds more than the {cut} bytes the container declares for it"
        assert _check(overrun) == Rendering("corrupt", detail=detail)
        assert max(size for _, size in reads.chunks) <= CONTAINER_CHUNK

    def test_a_member_whose_stream_fails_its_checksum_is_refused(self) -> None:
        """A declared CRC-32 off in its lowest bit: the checksum comparison deleted passes it."""
        data = _docx()
        (info,) = [info for info in _members(data) if info.filename == DOCUMENT]
        detail = "docx: member 'word/document.xml' does not match the CRC-32 the container declares for it"
        assert _check(declared(data, DOCUMENT, crc=info.CRC ^ 1)) == Rendering("corrupt", detail=detail)

    def test_a_fault_inside_a_member_is_corrupt_and_never_raised(self) -> None:
        """A stream that does not decode, a member flagged encrypted, and a local header naming another member
        each answer ``corrupt`` naming the exception's class: the check's ``except`` narrowed to ``BadZipFile``
        raises out of it on the first two."""
        data = _docx()
        header, stream = _local_offsets(data, DOCUMENT)
        faults = {
            "error": _overwritten(data, stream, b"\xff"),
            "RuntimeError": declared(data, DOCUMENT, flags=0x1),
            "BadZipFile": _overwritten(data, header + _LOCAL_NAME_AT, b"W"),
        }
        for kind, container in faults.items():
            refused = _check(container)
            assert refused is not None and (refused.status, refused.text) == ("corrupt", None)
            assert refused.detail is not None and refused.detail.startswith(f"docx: {kind}: ")

    def test_the_verifying_pass_reads_the_clock_on_the_cadence(
        self, monkeypatch: pytest.MonkeyPatch, watch: Callable[[], _Reads]
    ) -> None:
        """The clock before the first read and before the 64th: the clock test deleted from the read loop
        verifies the whole deck, and a read before the first alone never sees the clock pass."""
        data = _pptx()
        clock = _Clock()
        monkeypatch.setattr("vfs.deadline.monotonic", clock)
        reads = watch()
        detail = "pptx: the container was not verified within 60 seconds"
        limits = RenderLimits(seconds=RENDER_SECONDS)
        assert _check(data, limits, "pptx", deadline=Deadline(at=60.0)) == Rendering("failed", detail=detail)
        assert clock.reads == 2
        assert len(reads.chunks) == CHECK_EVERY
        idle = _Clock()
        monkeypatch.setattr("vfs.deadline.monotonic", idle)
        assert _check(data, renderer="pptx") is None
        assert idle.reads == 0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _docx() -> bytes:
    return docx_bytes(["A wombat digs"])


def _pptx() -> bytes:
    return pptx_bytes([("Echidna", ["spines"])])


def _xlsx() -> bytes:
    return xlsx_bytes({"Budget": {"A1": "numbat"}})


def _members(data: bytes) -> list[zipfile.ZipInfo]:
    with zipfile.ZipFile(BytesIO(data)) as archive:
        return archive.infolist()


def _stream(data: bytes, member: str) -> bytes:
    with zipfile.ZipFile(BytesIO(data)) as archive:
        return archive.read(member)


def _local_offsets(data: bytes, member: str) -> tuple[int, int]:
    """Where *member*'s local header starts, and where its stream starts after the header's name and extra."""
    with zipfile.ZipFile(BytesIO(data)) as archive:
        header = archive.getinfo(member).header_offset
    name_length, extra_length = struct.unpack_from("<HH", data, header + _LOCAL_LENGTHS_AT)
    return header, header + _LOCAL_NAME_AT + name_length + extra_length


def _overwritten(data: bytes, at: int, replacement: bytes) -> bytes:
    return data[:at] + replacement + data[at + len(replacement) :]


def _declaring(data: bytes, member: str, total: int) -> bytes:
    """*data* with *member*'s declared size set so the container declares *total* bytes in all."""
    others = sum(info.file_size for info in _members(data) if info.filename != member)
    return declared(data, member, file_size=total - others)


def _check(
    data: bytes,
    limits: RenderLimits | None = None,
    renderer: str = "docx",
    *,
    byte_limit: int | None = None,
    deadline: Deadline = NEVER,
) -> Rendering | None:
    """The check as a renderer calls it, with the docx family's default byte limit unless one is named."""
    limit = RenderLimits().container_bytes if byte_limit is None else byte_limit
    return container_refusal(data, limits or RenderLimits(), renderer, deadline, byte_limit=limit)
