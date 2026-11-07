"""Tests for ``vfs.storage.replace`` — the shared text-replacement engine.

The backend-facing edit semantics (``edited_entry``, ``Entry`` re-entry)
are pinned by the storage conformance suite; this file pins the engine
itself: each replacer generator in isolation, the three-level fallback
and error taxonomy of ``replace``, the position/context helpers, and the
sequential threading contract of ``apply_edits``.
"""

from __future__ import annotations

import random
import tracemalloc
from typing import Any

import pytest

from vfs.storage import replace as replace_module
from vfs.storage.replace import (
    FUZZY_WORK_BUDGET,
    REPLACERS,
    EditOperation,
    FuzzyBudget,
    apply_edits,
    block_anchor_replacer,
    get_context_lines,
    get_line_number,
    levenshtein,
    line_trimmed_replacer,
    normalize_line_endings,
    replace,
    simple_replacer,
)

# ----------------------------------------------------------------------
# Helpers: normalize_line_endings, levenshtein, positions and context
# ----------------------------------------------------------------------


def test_normalize_line_endings_converts_crlf() -> None:
    assert normalize_line_endings("a\r\nb\r\nc") == "a\nb\nc"


def test_normalize_line_endings_leaves_unix_and_bare_cr_alone() -> None:
    assert normalize_line_endings("a\nb") == "a\nb"
    assert normalize_line_endings("a\rb") == "a\rb"


@pytest.mark.parametrize(
    ("a", "b", "distance"),
    [
        ("", "", 0),
        ("", "abc", 3),
        ("abc", "", 3),
        ("abc", "abc", 0),
        ("kitten", "sitting", 3),
        ("flaw", "lawn", 2),
        ("a", "b", 1),
    ],
)
def test_levenshtein_known_distances(a: str, b: str, distance: int) -> None:
    assert levenshtein(a, b) == distance


def test_get_line_number_is_one_indexed() -> None:
    content = "first\nsecond\nthird"
    assert get_line_number(content, 0) == 1
    assert get_line_number(content, content.index("second")) == 2
    assert get_line_number(content, content.index("third")) == 3


def test_get_context_lines_marks_matched_lines_and_numbers() -> None:
    content = "\n".join(f"l{i}" for i in range(1, 11))
    start = content.index("l5")
    lines = get_context_lines(content, start, start + 2).split("\n")
    assert lines == [
        "   2   l2",
        "   3   l3",
        "   4   l4",
        "   5 > l5",
        "   6   l6",
        "   7   l7",
        "   8   l8",
    ]


def test_get_context_lines_clamps_at_content_boundaries() -> None:
    content = "\n".join(f"l{i}" for i in range(1, 11))
    top = get_context_lines(content, 0, 2).split("\n")
    assert top[0] == "   1 > l1"
    assert len(top) == 4
    bottom = get_context_lines(content, content.index("l10"), len(content)).split("\n")
    assert bottom[-1] == "  10 > l10"
    assert len(bottom) == 4


def test_get_context_lines_marks_every_line_of_a_multiline_match() -> None:
    content = "\n".join(f"l{i}" for i in range(1, 11))
    marked = get_context_lines(content, content.index("l3"), content.index("l5") + 2)
    assert "   3 > l3" in marked
    assert "   4 > l4" in marked
    assert "   5 > l5" in marked


# ----------------------------------------------------------------------
# simple_replacer — exact matching
# ----------------------------------------------------------------------


def test_simple_replacer_yields_every_occurrence_with_positions() -> None:
    matches = list(simple_replacer("ab-ab-ab", "ab"))
    assert [(m.start, m.end) for m in matches] == [(0, 2), (3, 5), (6, 8)]
    assert all(m.method == "exact" and m.confidence == 1.0 and m.text == "ab" for m in matches)


def test_simple_replacer_does_not_yield_overlapping_matches() -> None:
    assert [(m.start, m.end) for m in simple_replacer("aaaa", "aa")] == [(0, 2), (2, 4)]


def test_simple_replacer_yields_nothing_when_absent() -> None:
    assert list(simple_replacer("abc", "xyz")) == []


# ----------------------------------------------------------------------
# line_trimmed_replacer — whitespace-insensitive per line
# ----------------------------------------------------------------------


def test_line_trimmed_replacer_matches_despite_indentation() -> None:
    content = "def f():\n    return 1\nprint('x')"
    matches = list(line_trimmed_replacer(content, "def f():\nreturn 1"))
    assert len(matches) == 1
    match = matches[0]
    assert match.text == "def f():\n    return 1"
    assert (match.start, match.end) == (0, len("def f():\n    return 1"))
    assert match.method == "line_trimmed"
    assert match.confidence == 0.9


def test_line_trimmed_replacer_pops_a_trailing_empty_find_line() -> None:
    matches = list(line_trimmed_replacer("a\n  b\nc", "b\n"))
    assert len(matches) == 1
    assert matches[0].text == "  b"


def test_line_trimmed_replacer_matches_the_final_line_without_trailing_newline() -> None:
    matches = list(line_trimmed_replacer("a\n  b", "b"))
    assert len(matches) == 1
    assert (matches[0].start, matches[0].end) == (2, 5)


def test_line_trimmed_replacer_yields_nothing_for_an_empty_find() -> None:
    assert list(line_trimmed_replacer("a\nb", "")) == []


def test_line_trimmed_replacer_yields_each_occurrence() -> None:
    matches = list(line_trimmed_replacer("  x = 1\nb\n    x = 1", "x = 1"))
    assert [m.text for m in matches] == ["  x = 1", "    x = 1"]


def test_line_trimmed_replacer_requires_every_line_to_match() -> None:
    assert list(line_trimmed_replacer("a\nb\nc", "a\nz")) == []


# ----------------------------------------------------------------------
# block_anchor_replacer — anchored first/last lines, fuzzy middle
# ----------------------------------------------------------------------


def test_block_anchor_replacer_needs_at_least_three_find_lines() -> None:
    assert list(block_anchor_replacer("a\nb\nc", "a\nb")) == []
    # A trailing newline does not rescue a two-line find.
    assert list(block_anchor_replacer("a\nb\nc", "a\nb\n")) == []


def test_block_anchor_replacer_matches_a_close_single_candidate() -> None:
    content = "def foo():\n    x = 1\n    return x"
    matches = list(block_anchor_replacer(content, "def foo():\n    x = 2\n    return x"))
    assert len(matches) == 1
    match = matches[0]
    assert match.text == content
    assert match.method == "block_anchor"
    assert match.confidence == pytest.approx(0.8)


def test_block_anchor_replacer_rejects_a_dissimilar_single_candidate() -> None:
    content = "def foo():\n    x = 1\n    return x"
    find = "def foo():\n    totally_unrelated_body_zzz\n    return x"
    assert list(block_anchor_replacer(content, find)) == []


def test_block_anchor_replacer_anchors_to_the_nearest_last_line() -> None:
    content = "start\nmidd\nend\nmore\nend"
    matches = list(block_anchor_replacer(content, "start\nmiddle\nend"))
    assert len(matches) == 1
    assert matches[0].text == "start\nmidd\nend"


def test_block_anchor_replacer_picks_the_most_similar_of_multiple_candidates() -> None:
    content = "if a:\n    apple = 1\nend\nif a:\n    zebra = 2\nend"
    matches = list(block_anchor_replacer(content, "if a:\n    apple = 9\nend"))
    assert len(matches) == 1
    assert matches[0].text == "if a:\n    apple = 1\nend"


def test_block_anchor_replacer_rejects_when_every_candidate_is_dissimilar() -> None:
    content = "hdr\nAAAAAAAAAA\nftr\nhdr\nBBBBBBBBBB\nftr"
    assert list(block_anchor_replacer(content, "hdr\nzzzzzzzzzz\nftr")) == []


def test_block_anchor_replacer_yields_nothing_without_anchor_lines() -> None:
    assert list(block_anchor_replacer("a\nb\nc", "a\nb\nmissing")) == []


def test_block_anchor_replacer_scores_empty_middle_lines_as_no_similarity() -> None:
    # Both middles empty: nothing to compare, so similarity stays 0.0.
    assert list(block_anchor_replacer("a\n\nb", "a\n\nb\n")) == []


def test_replacers_priority_order() -> None:
    assert [simple_replacer, line_trimmed_replacer, block_anchor_replacer] == REPLACERS


# ----------------------------------------------------------------------
# replace — fallback strategy and success paths
# ----------------------------------------------------------------------


def test_replace_exact_single_match() -> None:
    result = replace("hello world", "world", "there")
    assert result.success
    assert result.content == "hello there"
    assert result.method_used == "exact"
    assert result.matches is not None and len(result.matches) == 1


def test_replace_falls_back_to_line_trimmed() -> None:
    result = replace("def f():\n    return 1", "def f():\n  return 1", "def f():\n    return 2")
    assert result.success
    assert result.content == "def f():\n    return 2"
    assert result.method_used == "line_trimmed"


def test_replace_falls_back_to_block_anchor() -> None:
    result = replace(
        "def foo():\n    x = 1\n    return x",
        "def foo():\n    x = 2\n    return x",
        "def foo():\n    return 1",
    )
    assert result.success
    assert result.content == "def foo():\n    return 1"
    assert result.method_used == "block_anchor"


def test_replace_all_replaces_every_exact_match() -> None:
    result = replace("a b a b a", "a", "c", replace_all=True)
    assert result.success
    assert result.content == "c b c b c"
    assert result.method_used == "exact"


def test_replace_normalizes_crlf_in_content_and_arguments() -> None:
    result = replace("line1\r\nline2\r\n", "line1\r\nline2", "one\r\ntwo")
    assert result.success
    assert result.content == "one\ntwo\n"


# ----------------------------------------------------------------------
# replace — error taxonomy
# ----------------------------------------------------------------------


def test_replace_rejects_an_empty_old_string() -> None:
    result = replace("content", "", "new")
    assert not result.success
    assert result.error is not None and "cannot be empty" in result.error


def test_replace_rejects_identical_old_and_new() -> None:
    result = replace("content", "same", "same")
    assert not result.success
    assert result.error is not None and "must be different" in result.error


def test_replace_reports_not_found() -> None:
    result = replace("hello", "absent", "new")
    assert not result.success
    assert result.error == "old_string not found in file content."


def test_replace_rejects_replace_all_on_a_fuzzy_match() -> None:
    result = replace("def f():\n    return 1", "def f():\n  return 1", "new", replace_all=True)
    assert not result.success
    assert result.error is not None
    assert "replace_all applies only to exact matches" in result.error
    assert "line_trimmed" in result.error


def test_replace_reports_ambiguous_matches_with_line_context() -> None:
    result = replace("x = 1\nother\nx = 1", "x = 1", "y = 2")
    assert not result.success
    assert result.error is not None
    assert "Found 2 matches" in result.error
    assert "Match at line 1" in result.error
    assert "Match at line 3" in result.error
    assert "   1 > x = 1" in result.error
    assert result.matches is not None and len(result.matches) == 2


# ----------------------------------------------------------------------
# apply_edits — sequential composition
# ----------------------------------------------------------------------


def test_apply_edits_of_an_empty_sequence_returns_the_input() -> None:
    result = apply_edits("unchanged", [])
    assert result.success
    assert result.content == "unchanged"


def test_apply_edits_threads_each_edit_through_the_previous_result() -> None:
    edits = [EditOperation(old="hello", new="world"), EditOperation(old="world twice", new="done")]
    result = apply_edits("hello twice", edits)
    assert result.success
    assert result.content == "done"


def test_apply_edits_honors_replace_all_per_operation() -> None:
    result = apply_edits("a b a", [EditOperation(old="a", new="c", replace_all=True)])
    assert result.success
    assert result.content == "c b c"


def test_apply_edits_stops_at_the_first_failure() -> None:
    edits = [EditOperation(old="absent", new="x"), EditOperation(old="hello", new="y")]
    result = apply_edits("hello", edits)
    assert not result.success
    assert result.content is None
    assert result.error == "old_string not found in file content."


# ----------------------------------------------------------------------
# The fuzzy fallback is linear and budgeted
# ----------------------------------------------------------------------

BUDGET_REFUSAL = (
    "old_string has no exact match, and the fuzzy fallback reached its work budget. Send the exact text to replace."
)


def _counted(monkeypatch: pytest.MonkeyPatch, name: str) -> list[int]:
    """Count the calls of the module attribute *name* by wrapping it in place."""
    calls: list[int] = []
    real = getattr(replace_module, name)

    def counting(*args: Any, **kwargs: Any) -> Any:
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(replace_module, name, counting)
    return calls


@pytest.mark.parametrize("lines", [1_000, 2_000])
def test_the_anchor_search_bisects_once_per_first_anchor(monkeypatch: pytest.MonkeyPatch, lines: int) -> None:
    bisections = _counted(monkeypatch, "bisect_left")
    result = replace("b\n" + "a\n" * lines, "a\nx\nb", "z")
    assert result.error == "old_string not found in file content."
    assert len(bisections) == lines


def test_the_fuzzy_fallback_stops_at_its_work_budget() -> None:
    refused = replace("a\n" + "x" * 2_400 + "\nb\n", "a\n" + "x" * 2_399 + "y" + "\nb", "z")
    assert refused.success is False
    assert refused.error == BUDGET_REFUSAL
    matched = replace("a\n" + "x" * 600 + "\nb\n", "a\n" + "x" * 599 + "y" + "\nb", "z")
    assert matched.success is True
    assert matched.method_used == "block_anchor"


def test_empty_middle_lines_spend_the_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    granted: list[int] = []
    real_spend = FuzzyBudget.spend

    def spend(self: FuzzyBudget, units: int) -> bool:
        allowed = real_spend(self, units)
        if allowed:
            granted.append(units)
        return allowed

    monkeypatch.setattr(FuzzyBudget, "spend", spend)
    distances = _counted(monkeypatch, "levenshtein")
    result = replace("a\n" * 4_000 + "b", "a\n" + "\n" * 4_000 + "b", "z")
    assert result.error == BUDGET_REFUSAL
    assert sum(granted) <= FUZZY_WORK_BUDGET
    assert len(distances) <= 4_000_000


def test_the_line_trimmed_scan_spends_the_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    anchored = _counted(monkeypatch, "_block_anchor")
    result = replace("a\n" * 5_000, "  a\n" * 2_500 + "b", "z")
    assert result.error == BUDGET_REFUSAL
    assert anchored == []


def test_a_300_line_near_miss_still_matches() -> None:
    rng = random.Random(7)
    alphabet = "abcdefghijklmnopqrstuvwxyz _-()"
    middle = ["".join(rng.choice(alphabet) for _ in range(60)) for _ in range(298)]
    content_lines = ["BEGIN " + "s" * 54, *middle, "END " + "e" * 56]
    find_lines = [
        content_lines[0],
        *(line[:-1] + ("!" if line[-1] != "!" else "?") for line in middle),
        content_lines[-1],
    ]
    content = "head\n" + "\n".join(content_lines) + "\ntail\n"
    result = replace(content, "\n".join(find_lines), "replaced")
    assert result.success is True
    assert result.method_used == "block_anchor"
    assert result.content == "head\nreplaced\ntail\n"


def test_a_many_match_failure_lists_three_and_splits_once(monkeypatch: pytest.MonkeyPatch) -> None:
    splits = _counted(monkeypatch, "_lines_of")
    result = replace("a\n" * 12_000, "  a", "z")
    assert result.success is False
    assert result.error is not None and result.error.startswith("Found 12000 matches")
    assert result.error.count("Match at line") == 3
    for line in (1, 2, 3):
        assert f"Match at line {line}:" in result.error
    assert result.error.endswith("... and 11997 more matches")
    assert result.matches is not None and len(result.matches) == 12_000
    assert len(splits) == 1


def _matrix_levenshtein(a: str, b: str) -> int:
    rows = [list(range(len(b) + 1))]
    for i, x in enumerate(a, 1):
        row = [i]
        for j, y in enumerate(b, 1):
            row.append(min(rows[-1][j] + 1, row[j - 1] + 1, rows[-1][j - 1] + (x != y)))
        rows.append(row)
    return rows[-1][-1]


def test_the_two_row_levenshtein_matches_the_matrix() -> None:
    rng = random.Random(11)
    for _ in range(200):
        a = "".join(rng.choice("abc") for _ in range(rng.randint(0, 30)))
        b = "".join(rng.choice("abc") for _ in range(rng.randint(0, 30)))
        assert levenshtein(a, b) == _matrix_levenshtein(a, b), (a, b)


def test_a_repeated_first_line_costs_one_comparison_per_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    granted: list[int] = []
    real_spend = FuzzyBudget.spend

    def spend(self: FuzzyBudget, units: int) -> bool:
        allowed = real_spend(self, units)
        if allowed:
            granted.append(units)
        return allowed

    monkeypatch.setattr(FuzzyBudget, "spend", spend)
    block = ["},", *(f'"key{n}": {n},' for n in range(99))]
    content = "\n".join(["},"] * 25_000 + ["    " + line for line in block] + ["},"] * 25_000)
    result = replace(content, "\n".join(block), "edited")
    assert result.method_used == "line_trimmed"
    assert sum(granted) < 200_000


def test_tied_block_anchor_candidates_edit_the_first() -> None:
    result = replace("a\nxx\nb\nq\na\nxx\nb\n", "a\nxy\nb", "z")
    assert result.content == "z\nq\na\nxx\nb\n"


def test_a_step_that_exactly_fits_is_granted() -> None:
    budget = FuzzyBudget(10)
    assert budget.spend(10) is True
    assert budget.left == 0
    assert budget.exhausted is False
    assert budget.spend(1) is False
    assert budget.exhausted is True


def test_an_exact_match_is_answered_whatever_the_budget_holds() -> None:
    budget = FuzzyBudget(0)
    budget.spend(1)
    result = replace("abc", "b", "x", budget=budget)
    assert result.content == "axc"


def test_levenshtein_keeps_its_rows_to_the_shorter_string() -> None:
    tracemalloc.start()
    try:
        assert levenshtein("b", "a" * 20_000) == 20_000
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 100_000
