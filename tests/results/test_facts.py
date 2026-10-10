"""Errors are facts: the contract table owns the words, the renderer attaches every locus last.

Pins the construction law — one constructor, no message argument, a
phrase per kind, a path-free detail — and the two seams' handling of the
second entry, through to the rendered line an agent reads.
"""

from __future__ import annotations

import re
from pathlib import Path as FsPath

import pytest

from vfs import VirtualFileSystem
from vfs.paths import MAX_PATH_LENGTH, Path
from vfs.results import KIND_CONTRACTS, Result, Severity, VFSErrorKind, classified, wrong_kind
from vfs.storage.backends import InMemoryStorage

SRC = FsPath(__file__).resolve().parents[2] / "src" / "vfs"
_PATH_TOKEN = re.compile(r"(?:^|\s)/\S")
_DETAILED = frozenset({VFSErrorKind.invalid, VFSErrorKind.internal})


def _detail_for(kind: VFSErrorKind) -> str | None:
    return "the cause, in words" if kind in _DETAILED else None


# ---------------------------------------------------------------------------
# The table and the constructor
# ---------------------------------------------------------------------------


def test_every_kind_has_a_phrase_that_names_no_locus_and_no_language() -> None:
    for kind in VFSErrorKind:
        contract = KIND_CONTRACTS[kind]
        assert contract.phrase and not _PATH_TOKEN.search(contract.phrase), kind
        for words in (contract.phrase, contract.hint):
            assert "=True" not in words and "kwarg" not in words, kind


@pytest.mark.parametrize("kind", list(VFSErrorKind))
def test_a_message_never_carries_a_path_however_the_fact_is_rebased(kind: VFSErrorKind) -> None:
    fact = classified(kind, Path("/inner/a.md"), target=Path("/inner/b.md"), detail=_detail_for(kind))
    hop = fact.with_mount("/mine").with_mount("/outer")
    for error in (fact, hop):
        assert not _PATH_TOKEN.search(error.message), error.message
        assert error.message.startswith(KIND_CONTRACTS[kind].phrase)
    line = str(Result(ops=("read",), errors=[hop]))
    assert line.startswith(f"ERROR /outer/mine/inner/a.md: {hop.message} (target /outer/mine/inner/b.md)")


def test_the_message_is_the_phrase_then_the_detail() -> None:
    assert classified(VFSErrorKind.not_found).message == "Not found"
    assert classified(VFSErrorKind.conflict, detail="version 3 is current").message == "Conflict: version 3 is current"


@pytest.mark.parametrize("kind", sorted(_DETAILED))
def test_invalid_and_internal_require_a_detail(kind: VFSErrorKind) -> None:
    with pytest.raises(ValueError, match="needs a detail"):
        classified(kind)


def test_fields_ride_in_data_beside_the_second_entry() -> None:
    fact = classified(
        VFSErrorKind.unavailable,
        Path("/a"),
        target=Path("/b"),
        severity=Severity.warning,
        retryable=True,
        data={"retry_after_ms": 50},
    )
    assert fact.data == {"retry_after_ms": 50, "vfs.target": "/b"}
    assert (fact.severity, fact.retryable, fact.path) == (Severity.warning, True, "/a")


def test_a_target_equal_to_the_locus_is_not_recorded() -> None:
    assert classified(VFSErrorKind.not_found, Path("/a"), target=Path("/a")).data is None


def test_wrong_kind_carries_the_occupant_kind_as_detail_and_field() -> None:
    fact = wrong_kind("directory", Path("/d"), target=Path("/d/kid"))
    assert fact.message == "Wrong kind: directory"
    assert fact.data == {"kind": "directory", "vfs.target": "/d/kid"}


# ---------------------------------------------------------------------------
# The seams and the second entry
# ---------------------------------------------------------------------------


def test_the_second_entry_rebases_with_the_locus_and_round_trips() -> None:
    fact = classified(VFSErrorKind.exists, Path("/a"), target=Path("/b"))
    hop = fact.with_mount("/m")
    assert (hop.path, hop.data) == ("/m/a", {"vfs.target": "/m/b"})
    assert hop.without_mount("/m") == fact


# Five 200-byte segments: lawful on its own, past the cap once rebased under a long mount.
_DEEP = Path("/s/" + "/".join(["t" * 200] * 5))
_LONG_MOUNT = "/" + "m" * (MAX_PATH_LENGTH - len(_DEEP))


def test_an_overflowing_second_entry_is_kept_local_under_overflow_once() -> None:
    fact = classified(VFSErrorKind.exists, Path("/a"), target=_DEEP)
    hop = fact.with_mount(_LONG_MOUNT).with_mount("/outer")
    assert hop.path == f"/outer{_LONG_MOUNT}/a"
    assert hop.data == {"vfs.overflow": {"target": str(_DEEP)}}


def test_a_locus_and_a_second_entry_overflow_independently() -> None:
    fact = classified(VFSErrorKind.exists, _DEEP, target=Path("/b"))
    hop = fact.with_mount(_LONG_MOUNT)
    assert hop.path is None
    assert hop.data == {"vfs.overflow": {"local_path": str(_DEEP)}, "vfs.target": f"{_LONG_MOUNT}/b"}


# ---------------------------------------------------------------------------
# The rendered line
# ---------------------------------------------------------------------------


def test_a_missing_file_renders_the_acceptance_line() -> None:
    fact = classified(VFSErrorKind.not_found, Path("/missing.md")).with_mount("/mine")
    expected = (
        "ERROR /mine/missing.md: Not found — Check the path with ls or glob, or create the entry first. (retry: never)"
    )
    assert str(Result(ops=("read",), errors=[fact])) == expected


async def test_a_move_under_a_missing_parent_renders_the_locus_and_the_target() -> None:
    root = VirtualFileSystem()
    await root.add_mount(InMemoryStorage(), "/mine")
    await root.write(path="/mine/a.md", content="x")
    result = await root.move(src="/mine/a.md", dest="/mine/gone/a.md")
    assert result.success is False
    [error] = result.errors
    assert (error.message, error.path, error.data) == ("Not found", "/mine/gone", {"vfs.target": "/mine/gone/a.md"})
    assert str(result).startswith("ERROR /mine/gone: Not found (target /mine/gone/a.md) — ")
    await root.close()


# ---------------------------------------------------------------------------
# The construction door
# ---------------------------------------------------------------------------


def test_no_producer_outside_the_envelope_builds_a_result_error_directly() -> None:
    offenders = [
        str(file.relative_to(SRC))
        for file in SRC.rglob("*.py")
        if "results" not in file.relative_to(SRC).parts and re.search(r"\bResultError\(", file.read_text())
    ]
    assert offenders == []


def test_no_constructor_call_passes_a_message() -> None:
    offenders = [
        str(file.relative_to(SRC))
        for file in SRC.rglob("*.py")
        if re.search(r"(?:classified|_error)\([^)]*\bmessage=", file.read_text(), re.DOTALL)
    ]
    assert offenders == []
