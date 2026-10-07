"""The preview selector: window choice, bolding, folding, caps, the head fallback, and its operation counts."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import Mock

from vfs.results import preview
from vfs.results.preview import (
    LINE_CHAR_CAP,
    PREVIEW_CHAR_CAP,
    WINDOW_LINES,
    Preview,
    select_preview,
)

if TYPE_CHECKING:
    import pytest

# The study's three example chunks, reproduced from the repository text they were cut from.
ROWS_PY = (
    "x = 1\n"
    "y = 2\n"
    "        # Reindex single-runner lease: holder token + last-heartbeat epoch\n"
    "        # millis. NULL holder or a stale heartbeat means the lease is free.\n"
    '        Column("reindex_holder", String(ULID_LENGTH)),\n'
    '        Column("reindex_heartbeat", BigInteger),\n'
    "z = 3\n"
)
MODELS_INIT = (
    "a\n"
    "b\n"
    "``entry`` holds the namespace ``Entry`` plus ``Observation``/``Match``;\n"
    "``chunk``, ``version``, and ``edge`` are the entry-scoped metadata models,\n"
    "one per table; ``rows``, ``vector``, ``versioning``, ``chunking``, and\n"
    "``code_grams`` carry the supporting column, embedding, and content machinery.\n"
)


class TestWindowSelection:
    def test_the_study_example_with_six_terms(self) -> None:
        got = select_preview(ROWS_PY, 469, ["reindex", "lease", "heartbeat", "epoch", "postings", "publish"])
        assert got == Preview(
            "        # **Reindex** single-runner **lease**: holder token + last-**heartbeat** **epoch**\n"
            "        # millis. NULL holder or a stale **heartbeat** means the **lease** is free.\n"
            '        Column("**reindex**_holder", String(ULID_LENGTH)),\n'
            '        Column("**reindex**_**heartbeat**", BigInteger),',
            471,
            474,
            True,
        )

    def test_the_study_example_bolds_substrings_inside_identifiers(self) -> None:
        # ``chunk`` bolds ``chunking``; ``line_start`` occurs nowhere and costs nothing.
        got = select_preview(MODELS_INIT, 1, ["chunk", "line_start", "embedding"])
        assert got.start == 3 and got.end == 6 and got.matched is True
        assert "``**chunk**ing``" in got.text and "**embedding**," in got.text

    def test_the_best_window_wins_and_ties_go_to_the_earliest(self) -> None:
        text = "quiet\nneedle here\nquiet\nquiet\nquiet\nquiet\nneedle here\nquiet\n"
        got = select_preview(text, 1, ["needle"])
        assert (got.start, got.end) == (1, 4)  # every one-hit window ties; the earliest wins
        assert got.text == "quiet\n**needle** here\nquiet\nquiet"

    def test_coverage_beats_repetition(self) -> None:
        # One line with both terms outranks lines repeating one term.
        text = "alpha alpha alpha\n" * 5 + "beta and alpha\n"
        got = select_preview(text, 1, ["alpha", "beta"], window=1)
        assert got.text == "**beta** and **alpha**" and (got.start, got.end) == (6, 6)

    def test_a_whole_word_hit_outranks_a_substring_hit(self) -> None:
        got = select_preview("embeddings\nembed\n", 1, ["embed"], window=1)
        assert got.text == "**embed**" and got.start == 2

    def test_bounds_are_absolute_and_within_the_chunk(self) -> None:
        got = select_preview("a\nb\nneedle\nc\nd\ne\n", 100, ["needle"])
        assert got.start >= 100 and got.end <= 105 and got.end - got.start + 1 <= WINDOW_LINES
        assert got.start <= 102 <= got.end


class TestFolding:
    def test_matching_is_case_insensitive_and_bolds_the_original_spelling(self) -> None:
        got = select_preview("The Needle and the NEEDLE\n", 1, ["needle"])
        assert got.text == "The **Needle** and the **NEEDLE**"

    def test_an_unfolded_term_still_matches(self) -> None:
        assert select_preview("needle\n", 1, ["NEEDLE"]).text == "**needle**"

    def test_a_fold_that_changes_length_keeps_the_spans_aligned(self) -> None:
        # ß folds to ``ss`` — two folded characters map back onto one original.
        got = select_preview("Straße und Straßenbahn ende\n", 1, ["strasse", "ende"])
        assert got.text == "**Straße** und **Straße**nbahn **ende**"

    def test_the_turkic_i_prefold_matches_the_dotted_capital(self) -> None:
        assert select_preview("İstanbul is a city\n", 5, ["istanbul"]).text == "**İstanbul** is a city"


class TestBolding:
    def test_overlapping_spans_merge_so_markers_never_nest(self) -> None:
        got = select_preview("reindex_heartbeat\n", 1, ["reindex_heart", "heartbeat"])
        assert got.text == "**reindex_heartbeat**"

    def test_adjacent_spans_stay_distinct(self) -> None:
        assert select_preview("reindex_heartbeat\n", 1, ["reindex", "heartbeat"]).text == "**reindex**_**heartbeat**"

    def test_duplicate_and_empty_terms_are_harmless(self) -> None:
        assert select_preview("needle\n", 1, ["needle", "", "needle"]).text == "**needle**"


class TestCaps:
    def test_a_long_line_is_trimmed_around_its_first_span(self) -> None:
        line = "x" * 200 + " needle " + "y" * 200
        got = select_preview(line + "\n", 1, ["needle"])
        assert got.text.startswith("…") and got.text.endswith("…") and "**needle**" in got.text
        assert len(got.text) <= LINE_CHAR_CAP + 2 + 4  # source cap + two ellipses + one bold pair

    def test_a_long_line_with_an_early_span_is_cut_at_the_tail(self) -> None:
        got = select_preview("needle " + "y" * 300 + "\n", 1, ["needle"])
        assert got.text.startswith("**needle** ") and got.text.endswith("…") and got.text.count("…") == 1

    def test_a_long_line_without_spans_keeps_its_head(self) -> None:
        got = select_preview("z" * 400 + "\n", 1, [])
        assert got.text == "z" * LINE_CHAR_CAP + "…"

    def test_trimming_never_cuts_through_a_marker(self) -> None:
        line = "x" * 150 + " needle needle needle needle " + "y" * 150
        got = select_preview(line + "\n", 1, ["needle"])
        assert got.text.count("**") % 2 == 0

    def test_the_preview_cap_drops_trailing_lines_but_keeps_the_first(self) -> None:
        text = "\n".join("needle " + "y" * 150 for _ in range(4)) + "\n"
        got = select_preview(text, 1, ["needle"])
        assert len(got.text) <= PREVIEW_CHAR_CAP and got.text.count("\n") < WINDOW_LINES - 1
        assert (got.start, got.end) == (1, 1 + got.text.count("\n"))
        only = select_preview("needle " + "y" * 150 + "\n", 1, ["needle"], preview_cap=10)
        assert only.text.startswith("**needle**")  # the first line is always kept

    def test_the_window_override_is_honoured(self) -> None:
        got = select_preview("a\nb\nc\nd\ne\nf\n", 1, [], window=2)
        assert got == Preview("a\nb", 1, 2, False)


class TestHeadFallback:
    def test_no_term_in_the_chunk_takes_the_head_window_unbolded(self) -> None:
        got = select_preview("no hits\nat all\nthree\nfour\nfive\n", 7, ["zzz"])
        assert got == Preview("no hits\nat all\nthree\nfour", 7, 10, False)

    def test_no_terms_at_all_takes_the_head_window(self) -> None:
        assert select_preview("one\ntwo\n", 1, []) == Preview("one\ntwo", 1, 2, False)

    def test_an_empty_chunk_is_an_empty_preview_at_its_start(self) -> None:
        assert select_preview("", 3, ["a"]) == Preview("", 3, 3, False)
        assert select_preview("\n", 3, ["a"]) == Preview("", 3, 3, False)

    def test_a_short_chunk_is_shown_whole(self) -> None:
        assert select_preview("only\n", 9, ["only"]) == Preview("**only**", 9, 9, True)


class TestOperationCounts:
    """The speed contract, pinned by counting the work rather than timing it.

    One fold of the whole chunk plus one per query term; two line splits
    (the original text and the folded text); a fold-offset map only when
    folding changed a line's length; and line scoring only on the lines a
    term occurs in. A clock would measure the CI runner; these counts
    measure the algorithm, so they hold on any hardware.
    """

    SPIED = ("fold_content", "split_lines", "_fold_offsets", "_score_line")

    @staticmethod
    def _spies(monkeypatch: pytest.MonkeyPatch) -> dict[str, Mock]:
        spies = {name: Mock(wraps=getattr(preview, name)) for name in TestOperationCounts.SPIED}
        for name, spy in spies.items():
            monkeypatch.setattr(preview, name, spy)
        return spies

    def test_study_shaped_chunks_fold_once_and_score_only_the_hit_lines(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # The study's shape: 28-line ASCII chunks, a term on one line in nine (four hit lines each).
        words = ["the", "index", "builds", "postings", "for", "every", "entry", "and", "router", "merges", "rows"]
        lines = [" ".join(words[(i + j) % len(words)] for j in range(9)) for i in range(28)]
        for i in range(0, 28, 9):
            lines[i] += " chunk_index embedding"
        chunks = [("\n".join(lines[k % 28 :] + lines[: k % 28]) + "\n", 1 + k) for k in range(1_000)]
        terms = ["chunk", "line_start", "embedding"]
        hit_lines_per_chunk = 4
        spies = self._spies(monkeypatch)
        for content, line_start in chunks:
            select_preview(content, line_start, terms)
        assert spies["fold_content"].call_count == len(chunks) * (1 + len(terms))
        assert spies["split_lines"].call_count == 2 * len(chunks)
        assert spies["_fold_offsets"].call_count == 0
        assert spies["_score_line"].call_count == len(chunks) * hit_lines_per_chunk

    def test_a_chunk_holding_no_term_stops_at_the_gate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # The any-term gate decides in one search: no folded split, no line scored.
        spies = self._spies(monkeypatch)
        assert select_preview("alpha\nbeta\ngamma\n", 1, ["delta"]) == Preview("alpha\nbeta\ngamma", 1, 3, False)
        assert spies["fold_content"].call_count == 2
        assert spies["split_lines"].call_count == 1
        assert spies["_score_line"].call_count == 0
