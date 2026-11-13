"""The rows-in-hand filters pinned over a fake row source, with no router.

The source records every call it is handed and answers from canned
rows, so each node counts exactly which rows a filter reached storage
for, and with which columns and authority.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from vfs.authority import Authority
from vfs.chain import glob_rows_in_hand, grep_rows_in_hand, judge_in_hand
from vfs.deadline import Deadline
from vfs.models import Observation
from vfs.paths import Path
from vfs.pattern_matching import PatternError, compile_gates, compile_verifier
from vfs.results import ErrorKind, Result, classified

if TYPE_CHECKING:
    from vfs.paths import ObjectKind

AUTHORITY = Authority.anonymous()


class _Source:
    """A row source that records each call's keywords and answers *read* and *stat* from canned rows."""

    def __init__(self, *, read: list[Observation] | None = None, stat: list[Observation] | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._read = read or []
        self._stat = stat or []

    async def read(
        self, *, observations: list[Observation], columns: frozenset[str], authority: Authority | None
    ) -> Result:
        self.calls.append(("read", {"observations": observations, "columns": columns, "authority": authority}))
        return Result(ops=("read",), observations=self._read)

    async def stat(
        self, *, observations: list[Observation], columns: frozenset[str], authority: Authority | None
    ) -> Result:
        self.calls.append(("stat", {"observations": observations, "columns": columns, "authority": authority}))
        return Result(ops=("stat",), observations=self._stat)


def _row(path: str, *, kind: ObjectKind | None = None, content: str | None = None) -> Observation:
    """A row as a caller holds it: its path, and the kind and content facts it carries."""
    populated = {"path"} | ({"kind"} if kind is not None else set()) | ({"content"} if content is not None else set())
    return Observation(path=Path(path), kind=kind, content=content, populated=frozenset(populated))


async def _grep(source: _Source, rows: list[Observation], pattern: str) -> Result:
    """Chained grep for *pattern* with every other keyword at the verb's default."""
    return await grep_rows_in_hand(
        source,
        rows,
        pattern=pattern,
        ext=(),
        ext_not=(),
        globs=(),
        globs_not=(),
        case_mode="sensitive",
        fixed_strings=False,
        word_regexp=False,
        invert_match=False,
        before_context=0,
        after_context=0,
        output_mode="lines",
        max_count=None,
        columns=None,
        authority=AUTHORITY,
    )


async def test_chained_grep_reads_absent_content_through_the_source_only() -> None:
    """Guards: chained grep reading every candidate, or a row that already holds
    its content; and a read made anywhere but through the source it was handed."""
    held = _row("/a.txt", kind="file", content="a needle here")
    absent = _row("/b.txt", kind="file")
    other = _row("/c.txt", kind="file", content="nothing to find")
    source = _Source(read=[_row("/b.txt", kind="file", content="the needle again")])
    result = await _grep(source, [held, absent, other], "needle")
    [(method, call)] = source.calls
    assert method == "read"
    assert call["observations"] == [absent]
    assert call["columns"] == frozenset({"content"})
    assert call["authority"] is AUTHORITY
    assert [str(row.path) for row in result.observations] == ["/a.txt", "/b.txt"]
    assert result.errors == []


async def test_chained_glob_stats_only_the_rows_without_a_kind() -> None:
    """Guards: chained glob statting every kept row, or a row that already
    carries its kind."""
    rows = [_row("/a.txt", kind="file"), _row("/b.txt"), _row("/c.txt", kind="directory"), _row("/d.txt")]
    source = _Source(stat=[_row("/b.txt", kind="file"), _row("/d.txt", kind="directory")])
    result = await glob_rows_in_hand(
        source,
        rows,
        arms=("*.txt",),
        ext=(),
        ext_not=(),
        globs_not=(),
        kind="file",
        deadline=Deadline.never(),
        authority=AUTHORITY,
    )
    [(method, call)] = source.calls
    assert method == "stat"
    assert call["observations"] == [rows[1], rows[3]]
    assert call["columns"] == frozenset()
    assert call["authority"] is AUTHORITY
    assert result.observations == rows[:2]
    assert (result.ops, result.errors) == (("glob",), [])


async def test_an_invalid_pattern_is_refused_before_the_source_is_touched() -> None:
    """Guards: the refusal answering under another op, carrying a path, or
    minted after a read."""
    source = _Source()
    result = await _grep(source, [_row("/a.txt", kind="file")], "(")
    assert source.calls == []
    assert (result.ops, result.observations) == (("grep",), [])
    [error] = result.errors
    assert (error.kind, error.path) == (ErrorKind.invalid, None)
    with pytest.raises(PatternError) as cause:
        compile_verifier("(", fixed_strings=False, word_regexp=False, case_mode="sensitive")
    assert error.message == classified(ErrorKind.invalid, detail=f"grep pattern '(': {cause.value}").message


async def test_chained_glob_past_its_deadline_serves_what_was_judged() -> None:
    """Guards: the filter judging under a wall of its own in place of the
    deadline its caller read."""
    source = _Source()
    result = await glob_rows_in_hand(
        source,
        [_row("/a.txt"), _row("/b.txt")],
        arms=("*.txt",),
        ext=(),
        ext_not=(),
        globs_not=(),
        kind=None,
        deadline=Deadline(at=-1.0),
        authority=AUTHORITY,
    )
    assert source.calls == []
    assert result.observations == []
    [error] = result.errors
    assert error.kind is ErrorKind.truncated


async def test_judging_in_hand_keeps_order_and_duplicates() -> None:
    """Guards: the judge folding duplicate rows into one, or reordering what it admits."""
    first, second, third = _row("/a.txt"), _row("/b.md"), _row("/a.txt")
    gates = compile_gates(("*.txt",), (), ext=(), ext_not=())
    kept, completed = await judge_in_hand(gates, [first, second, third], Deadline.never())
    assert (len(kept), completed) == (2, True)
    assert kept[0] is first
    assert kept[1] is third
