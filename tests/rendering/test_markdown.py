"""The Markdown builder: the marker grammar, the table rules, normalisation, the budgets, the verdict."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from vfs.deadline import CHECK_EVERY
from vfs.rendering import Builder, RenderLimits, unit_marker
from vfs.rendering.markdown import flatten, kept_length, table_cell, truncation_marker
from vfs.rendering.seam import RENDER_RATIO_FLOOR

if TYPE_CHECKING:
    from collections.abc import Iterator

    import pytest


def _build(limits: RenderLimits | None = None, *, input_bytes: int = 1_000, total_units: int | None = None) -> Builder:
    return Builder(limits or RenderLimits(), input_bytes=input_bytes, total_units=total_units)


def _clock(monkeypatch: pytest.MonkeyPatch, *, readings: int) -> list[int]:
    """The Builder's clock as a counter, ``0.0`` for its first *readings* reads and past any deadline after;
    answers the count of reads."""
    reads = [0]

    def clock() -> float:
        reads[0] += 1
        return 0.0 if reads[0] <= readings else RenderLimits().seconds + 1.0

    monkeypatch.setattr("vfs.rendering.markdown.monotonic", clock)
    return reads


class TestMarkers:
    def test_one_grammar_for_every_kind(self) -> None:
        assert unit_marker("page", 3) == "<!-- page 3 -->"
        assert unit_marker("sheet", 2, "Budget") == "<!-- sheet 2: Budget -->"
        assert unit_marker("sheet", 2, "  ") == "<!-- sheet 2 -->"

    def test_a_label_cannot_close_the_comment_early(self) -> None:
        assert unit_marker("sheet", 1, "a --> b") == "<!-- sheet 1: a - -> b -->"

    def test_the_truncation_notice(self) -> None:
        assert truncation_marker(3, 10) == "<!-- truncated: 3 of 10 units -->"

    def test_units_record_their_marker_line_and_hidden_flag(self) -> None:
        builder = _build()
        assert builder.unit("sheet", 1, "A")
        builder.paragraph("x")
        assert builder.unit("sheet", 2, "B", hidden=True)
        builder.paragraph("y")
        rendering = builder.build()
        assert rendering.text == "<!-- sheet 1: A -->\nx\n\n<!-- sheet 2: B -->\ny\n"
        assert [(u.kind, u.number, u.label, u.first_line, u.hidden) for u in rendering.units] == [
            ("sheet", 1, "A", 1, False),
            ("sheet", 2, "B", 4, True),
        ]


class TestTables:
    def test_cells_escape_pipes_collapse_breaks_and_blank_none(self) -> None:
        assert table_cell(None) == ""
        assert table_cell("a|b") == "a\\|b"
        assert table_cell("line1\nline2\t x") == "line1 line2 x"
        assert flatten(" a \x00 b ") == "a b"

    def test_first_row_is_the_header_and_short_rows_are_padded(self) -> None:
        builder = _build()
        assert builder.table([["h1", "h2"], ["a"], ["b", None]]) is True
        assert builder.build().text == "| h1 | h2 |\n| --- | --- |\n| a |  |\n| b |  |\n"

    def test_an_empty_table_emits_nothing(self) -> None:
        builder = _build()
        assert builder.table([]) is True
        assert builder.build().status == "empty"


class TestNormalisation:
    def test_trailing_spaces_blank_runs_and_nuls_are_normalised(self) -> None:
        builder = _build()
        builder.paragraph("one  \n\n\n\ntwo\x00 ")
        builder.paragraph("")
        builder.heading(2, "  Head  ing ")
        builder.heading(3, "   ")
        assert builder.build().text == "one\n\ntwo\n\n## Head ing\n"

    def test_heading_levels_clamp_to_six(self) -> None:
        builder = _build()
        builder.heading(9, "deep")
        builder.heading(0, "shallow")
        assert builder.build().text == "###### deep\n\n# shallow\n"

    def test_images_are_placeholder_lines(self) -> None:
        builder = _build()
        builder.image("a photo", 1)
        builder.image(None, 2)
        builder.paragraph("p")
        assert builder.build().text == "![a photo](embedded:1)\n\n![](embedded:2)\n\np\n"


class TestVerdicts:
    def test_ok_when_text_was_emitted(self) -> None:
        builder = _build()
        builder.paragraph("hello")
        rendering = builder.build()
        assert (rendering.status, rendering.detail) == ("ok", None)

    def test_empty_when_only_markers_were_emitted(self) -> None:
        builder = _build(total_units=2)
        assert builder.unit("page", 1)
        assert builder.unit("page", 2)
        rendering = builder.build()
        assert (rendering.status, rendering.text, rendering.detail) == ("empty", None, "no text in 2 units")

    def test_the_character_budget_cuts_at_a_unit_boundary_with_a_notice(self) -> None:
        builder = _build(RenderLimits(chars=50), total_units=5)
        for number in range(1, 6):
            if not builder.unit("page", number):
                break
            builder.paragraph("twelve chars")
        rendering = builder.build()
        assert rendering.status == "truncated"
        assert rendering.detail == "1 of 5 units within 50 characters"
        assert rendering.text is not None
        assert rendering.text.endswith("<!-- truncated: 1 of 5 units -->\n")
        assert len(rendering.units) == 2

    def test_an_oversized_unit_is_cut_inside_its_table(self) -> None:
        builder = _build(RenderLimits(chars=40), total_units=1)
        assert builder.unit("sheet", 1, "S")
        assert builder.table([["h"], *([[f"r{i}"] for i in range(50)])]) is False
        rendering = builder.build()
        assert rendering.status == "truncated"
        assert rendering.detail == "0 of 1 units within 40 characters"

    def test_the_page_cap_cuts_too(self) -> None:
        builder = _build(RenderLimits(pages=1), total_units=3)
        assert builder.unit("page", 1)
        builder.paragraph("x")
        assert builder.unit("page", 2) is False
        assert builder.build().status == "truncated"

    def test_the_wall_clock_makes_the_text_so_far_partial(self) -> None:
        builder = _build(RenderLimits(seconds=0.01), total_units=2)
        assert builder.boundary(1)
        builder.paragraph("kept")
        time.sleep(0.02)
        assert builder.boundary(2) is False
        rendering = builder.build()
        assert (rendering.status, rendering.text) == ("partial", "kept\n")
        assert rendering.detail == "1 of 2 units within 0.01 seconds"

    def test_dropped_embedded_objects_make_it_partial(self) -> None:
        builder = _build(RenderLimits(embedded_count=1))
        builder.paragraph("text")
        builder.image("one", 1)
        builder.image("two", 2)
        rendering = builder.build()
        assert rendering.status == "partial"
        assert rendering.detail == "embedded objects past 1 dropped"
        assert rendering.text == "text\n\n![one](embedded:1)\n"

    def test_the_ratio_guard_is_a_loud_failure(self) -> None:
        builder = _build(RenderLimits(ratio=1), input_bytes=10)
        builder.paragraph("x" * (RENDER_RATIO_FLOOR + 10))
        rendering = builder.build()
        assert (rendering.status, rendering.text) == ("failed", None)
        assert rendering.detail is not None and "exceed 1x the 10-byte input" in rendering.detail

    def test_the_cut_wins_over_the_clock(self) -> None:
        builder = _build(RenderLimits(chars=24, seconds=0.01), total_units=2)
        assert builder.unit("page", 1)
        builder.paragraph("yes")
        builder.paragraph("more words")  # does not fit: cut inside unit 1
        time.sleep(0.02)
        assert builder.unit("page", 2) is False
        assert builder.build().status == "truncated"


class TestBudgetsOnEveryLine:
    def test_a_paragraph_unit_is_cut_inside_itself_never_past_the_budget(self) -> None:
        builder = _build(RenderLimits(chars=100), total_units=1)
        assert builder.unit("page", 1)
        builder.paragraph("\n".join(f"line {i:03d} of the long page" for i in range(40)))
        rendering = builder.build()
        assert rendering.status == "truncated"
        assert rendering.text is not None and len(rendering.text) <= 100 + len("<!-- truncated: 0 of 1 units -->\n") + 1
        assert rendering.detail == "0 of 1 units within 100 characters"
        assert builder.stopped

    def test_a_cut_rendering_with_its_notice_fits_a_large_budget(self) -> None:
        budget = 2_000
        builder = _build(RenderLimits(chars=budget), total_units=50)
        for number in range(1, 51):
            if not builder.unit("page", number):
                break
            builder.paragraph("x" * 90)
        rendering = builder.build()
        assert rendering.status == "truncated"
        assert rendering.text is not None and len(rendering.text) <= budget

    def test_nothing_is_appended_after_a_cut(self) -> None:
        builder = _build(RenderLimits(chars=30), total_units=2)
        assert builder.unit("page", 1)
        builder.paragraph("twelve chars")
        builder.paragraph("another dozen chars here")  # cuts
        builder.heading(2, "late heading")
        builder.image("late", 1)
        assert builder.table([["late"]]) is False
        assert builder.boundary(2) is False
        text = builder.build().text
        assert text is not None and "late" not in text

    def test_the_unit_cap_names_itself_and_spares_markerless_blocks(self) -> None:
        builder = _build(RenderLimits(pages=2), total_units=3)
        for number in (1, 2):
            assert builder.unit("slide", number)
            builder.paragraph("text")
        assert builder.unit("slide", 3) is False
        rendering = builder.build()
        assert rendering.status == "truncated"
        assert rendering.detail == "2 of 3 units within the 2-unit cap"
        blocks = _build(RenderLimits(pages=2), total_units=5)
        for number in range(1, 6):
            assert blocks.boundary(number)
            blocks.paragraph(f"block {number}")
        assert blocks.build().status == "ok"

    def test_the_ratio_floor_spares_small_renderings(self) -> None:
        builder = _build(RenderLimits(ratio=1), input_bytes=1)
        builder.paragraph("x" * 500)
        assert builder.build().status == "ok"

    def test_a_bomb_stops_the_builder_before_the_verdict(self) -> None:
        builder = _build(RenderLimits(ratio=1), input_bytes=10)
        builder.paragraph("x" * (RENDER_RATIO_FLOOR + 10))
        assert builder.stopped
        builder.paragraph("never appended")
        assert builder.build().status == "failed"


class TestMarkersAndClock:
    def test_a_document_line_that_reads_as_a_marker_is_escaped(self) -> None:
        builder = _build(total_units=2)
        assert builder.unit("page", 1)
        builder.paragraph("<!-- page 2 -->\nreal text")
        assert builder.unit("page", 2)
        builder.paragraph("more")
        rendering = builder.build()
        assert rendering.text is not None
        assert rendering.text.splitlines().count("<!-- page 2 -->") == 1
        assert "\\<!-- page 2 -->" in rendering.text
        assert rendering.units[1].first_line == 5

    def test_the_clock_starts_where_the_renderer_says(self) -> None:
        late = Builder(RenderLimits(seconds=1), input_bytes=10, total_units=1, started=time.monotonic() - 5)
        assert late.boundary(1) is False
        assert late.build().status == "failed"

    def test_step_reads_the_clock_before_every_check_every_th_step(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The clock is read on every 64th step and the first stop is remembered, closing the open unit incomplete:
        a step that never reads the clock, or that counts the stopped unit complete, fails."""
        reads = _clock(monkeypatch, readings=2)
        builder = Builder(RenderLimits(), input_bytes=10, total_units=1, started=0.0)
        assert builder.unit("sheet", 1, "S")
        builder.paragraph("kept")
        assert [builder.step() for _ in range(1_000)] == [True] * 127 + [False] * 873
        assert reads == [3]
        rendering = builder.build()
        assert (rendering.status, rendering.text) == ("partial", "<!-- sheet 1: S -->\nkept\n")
        assert rendering.detail == "0 of 1 units within 60 seconds"
        # A Builder a cut has stopped answers false at once and reads no clock.
        reads = _clock(monkeypatch, readings=1)
        cut = Builder(RenderLimits(chars=5), input_bytes=10, total_units=1, started=0.0)
        assert cut.unit("sheet", 1, "S") is False
        assert [cut.step() for _ in range(CHECK_EVERY)] == [False] * CHECK_EVERY
        assert reads == [1]

    def test_a_clock_stop_before_any_text_is_never_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A clock stop after a marker keeps the marker as partial and one before any line is failed, while a cut
        before any text stays empty with the clock out: testing for text before the clock fails."""
        _clock(monkeypatch, readings=1)
        two = Builder(RenderLimits(), input_bytes=10, total_units=2, started=0.0)
        assert two.unit("sheet", 1, "S")
        assert two.unit("sheet", 2, "T") is False
        rendering = two.build()
        assert (rendering.status, rendering.text) == ("partial", "<!-- sheet 1: S -->\n")
        assert (rendering.detail, len(rendering.units)) == ("1 of 2 units within 60 seconds", 1)
        # A structural heading is kept with the marker, the blank after it trimmed.
        _clock(monkeypatch, readings=1)
        headed = Builder(RenderLimits(), input_bytes=10, total_units=1, started=0.0)
        assert headed.unit("sheet", 1, "S")
        headed.heading(2, "S", structural=True)
        assert [headed.step() for _ in range(CHECK_EVERY)][-1] is False
        rendering = headed.build()
        assert (rendering.status, rendering.text) == ("partial", "<!-- sheet 1: S -->\n\n## S\n")
        assert rendering.detail == "0 of 1 units within 60 seconds"
        _clock(monkeypatch, readings=0)
        one = Builder(RenderLimits(), input_bytes=10, total_units=1, started=0.0)
        assert one.boundary(1) is False
        rendering = one.build()
        assert (rendering.status, rendering.text, rendering.units) == ("failed", None, ())
        assert rendering.detail == "0 of 1 units within 60 seconds, before any line was written"
        _clock(monkeypatch, readings=1)
        cut = Builder(RenderLimits(chars=5), input_bytes=10, total_units=1, started=0.0)
        assert cut.unit("sheet", 1, "S") is False
        assert cut.out_of_time()
        rendering = cut.build()
        assert (rendering.status, rendering.detail) == ("empty", "no text in 1 units")

    def test_a_table_is_cut_by_the_clock_between_rows(self) -> None:
        builder = _build(RenderLimits(seconds=0.01), total_units=1)
        assert builder.unit("sheet", 1, "S")
        time.sleep(0.02)
        assert builder.table([["h"], ["r1"], ["r2"]]) is False
        rendering = builder.build()
        assert rendering.status == "partial"
        assert rendering.detail == "0 of 1 units within 0.01 seconds"

    def test_a_dropped_container_marks_the_rendering_partial(self) -> None:
        builder = _build()
        builder.paragraph("kept")
        builder.drop_embedded()
        rendering = builder.build()
        assert (rendering.status, rendering.text) == ("partial", "kept\n")


class TestTableFit:
    def test_a_header_whose_separator_does_not_fit_is_cut(self) -> None:
        # The header row fits the budget; its separator line does not.
        builder = _build(RenderLimits(chars=20), total_units=1)
        assert builder.boundary(1)
        assert builder.table([["abc", "de"], ["x", "y"]]) is False
        rendering = builder.build()
        assert rendering.status == "truncated"
        assert rendering.text == "| abc | de |\n\n<!-- truncated: 0 of 1 units -->\n"


class TestWhatIsLeft:
    def test_remaining_counts_down_and_is_zero_once_stopped(self) -> None:
        """Each line and its blank come off the budget, and a refused line leaves nothing; ignoring the stop fails."""
        builder = _build(RenderLimits(chars=100))
        assert builder.remaining == 100
        builder.paragraph("abc")
        assert builder.remaining == 100 - len("abc\n") - 1
        builder.paragraph("de")
        assert builder.remaining == 100 - len("abc\n") - 1 - len("de\n") - 1
        builder.paragraph("x" * 200)
        assert builder.stopped
        assert builder.remaining == 0

    def test_kept_length_drops_whitespace_and_nuls(self) -> None:
        """Whitespace of every kind and NULs cost nothing a line rule cannot drop; counting NULs fails."""
        assert kept_length("") == 0
        assert kept_length(" a\tb\n　c\x00 ") == 3
        assert kept_length("\x00\x00") == 0
        assert kept_length("|") == 1

    def test_a_table_with_a_width_draws_each_row_after_the_line_before(self) -> None:
        """Rows are pulled one at a time after the line before is written; reading every row first fails."""
        builder = _build(RenderLimits(chars=30))
        pulls: list[int] = []

        def rows() -> Iterator[list[str]]:
            for row in (["h"], ["a", "b"], ["c", "d"], ["e", "f"]):
                pulls.append(builder.remaining)
                yield row

        assert builder.table(rows(), width=2) is False
        assert pulls == [30, 30 - len("| h |  |\n") - len("| --- | --- |\n")]
        # A stopped Builder draws no row, and even an empty table is refused by it.
        assert builder.table(rows(), width=2) is False
        assert builder.table([], width=2) is False
        rendering = builder.build()
        assert rendering.status == "truncated"
        assert rendering.text is not None and rendering.text.startswith("| h |  |\n| --- | --- |\n")
