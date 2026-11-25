"""The frontier rule that merges sorted listing streams into one page, against an oracle that lists all and slices."""

from __future__ import annotations

import random

import pytest

from vfs.models import Observation
from vfs.paths import Path
from vfs.results import Result
from vfs.results.paging import frontier_page, paged


def row(path: str) -> Observation:
    return Observation(path=Path(path), kind="file")


def stream_page(rows: list[str], after: str | None, limit: int) -> tuple[list[str], str | None]:
    """One stream's own page: its sorted rows strictly after ``after``, ``limit`` of them, keyed on the last."""
    rest = [path for path in rows if after is None or path > after]
    if len(rest) > limit:
        return rest[:limit], rest[limit - 1]
    return rest, None


def drain(streams: list[list[str]], extras: list[str], limit: int, fetch: int) -> tuple[list[str], int]:
    """Drain a merged listing page by page, each stream paged at ``fetch`` rows; return the rows and the pages."""
    seen: list[str] = []
    after: str | None = None
    pages = 0
    while True:
        pages += 1
        rows: list[str] = []
        keys: list[str | None] = []
        for stream in streams:
            got, key = stream_page(stream, after, fetch)
            rows += got
            keys.append(key)
        page, after = frontier_page([*rows, *extras], keys, after=after, limit=limit, path_of=str)
        seen += page
        if after is None:
            return seen, pages
        assert pages < 10_000


class TestFrontierPage:
    def test_one_finished_stream_is_its_rows_after_the_key(self) -> None:
        assert frontier_page(["/b", "/a", "/c"], [None], after="/a", limit=None, path_of=str) == (["/b", "/c"], None)

    def test_a_page_past_its_limit_keys_on_its_last_row(self) -> None:
        assert frontier_page(["/a", "/b", "/c"], [None], after=None, limit=2, path_of=str) == (["/a", "/b"], "/b")

    def test_a_page_of_exactly_limit_rows_from_finished_streams_has_no_key(self) -> None:
        assert frontier_page(["/a", "/b"], [None, None], after=None, limit=2, path_of=str) == (["/a", "/b"], None)

    def test_no_row_passes_the_smallest_unfinished_key(self) -> None:
        page = frontier_page(["/a", "/c", "/b", "/d"], ["/c", None], after=None, limit=10, path_of=str)
        assert page == (["/a", "/b", "/c"], "/c")

    def test_a_short_page_carries_the_frontier(self) -> None:
        assert frontier_page([], ["/m/z"], after="/a", limit=5, path_of=str) == ([], "/m/z")

    def test_no_stream_and_no_limit_lists_everything_in_path_order(self) -> None:
        assert frontier_page(["/b", "/a"], [], after=None, limit=None, path_of=str) == (["/a", "/b"], None)

    @pytest.mark.parametrize("seed", range(1_000))
    def test_drained_pages_equal_the_whole_listing(self, seed: int) -> None:
        rng = random.Random(seed)
        names = sorted({f"/{rng.choice('abcde')}/{rng.randrange(60):02d}" for _ in range(rng.randrange(1, 90))})
        streams: list[list[str]] = [[] for _ in range(rng.randrange(1, 9))]
        extras: list[str] = []
        for name in names:
            if rng.random() < 0.1:
                extras.append(name)
            else:
                rng.choice(streams).append(name)
        limit = rng.randrange(1, 12)
        seen, pages = drain(streams, extras, limit, fetch=rng.choice([limit, limit + 1, 2 * limit]))
        assert seen == names
        assert len(seen) == len(set(seen))
        assert pages <= len(names) + 1


class TestPaged:
    def test_paged_sets_the_rows_and_the_key_and_keeps_the_errors(self) -> None:
        result = Result(ops=("ls",), observations=[row("/c"), row("/a"), row("/b")])
        page = paged(result, [None], after=None, limit=2)
        assert page.paths == ("/a", "/b")
        assert page.next_after == "/b"
        assert page.ops == ("ls",)

    def test_paged_with_no_cursor_leaves_the_result_alone(self) -> None:
        result = Result(ops=("ls",), observations=[row("/c"), row("/a")])
        assert paged(result, [], after=None, limit=None) is result
