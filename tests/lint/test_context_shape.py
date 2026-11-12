"""The shape of the documents under ``context/``, held by one test per rule."""

from __future__ import annotations

import subprocess
import sys
from typing import TYPE_CHECKING

from tests.lint import shapes
from tests.lint.allowlist import OPEN_QUESTION_ALLOWANCE

if TYPE_CHECKING:
    import pytest

UNWRAP = shapes.REPO / "scripts" / "unwrap_context.py"

# The two lines a code review's Ownership subsection opens with, and every closing each may end in.
LAYER_MAP_LINE = "Layer map: `vfs.base` on rung 8; adds `vfs.offload` to rung 5; ladder unchanged."
SIZE_LINE = "Size: `src/vfs/base.py` 3,660 to 3,660; allowlist unchanged."
LAYER_MAP_CLOSINGS = (
    "ladder unchanged.",
    "ladder unchanged, the file changed elsewhere: a test was renamed.",
    "ladder changed: `LAYERS` gains `vfs.fanout` on rung 7.",
)
SIZE_CLOSINGS = ("allowlist unchanged.", "allowlist changed: `src/vfs/base.py` lowered from 3,660 to 3,190.")


def report(errors: list[str]) -> str:
    return "\n".join(errors)


def test_documents_are_dated_and_unnumbered() -> None:
    errors = shapes.name_errors()
    assert not errors, report(errors)


def test_new_documents_carry_no_header_lines() -> None:
    errors = [e for p in shapes.new_documents() for e in shapes.header_errors(p)]
    assert not errors, report(errors)


def test_intentions_have_their_sections() -> None:
    errors = [e for p in shapes.direct_documents("intentions") for e in shapes.intention_errors(p)]
    assert not errors, report(errors)


def test_specs_have_their_sections() -> None:
    specs = shapes.dated_specs("specifications/active") + shapes.dated_specs("specifications/archive")
    errors = [e for p in specs for e in shapes.spec_errors(p)]
    assert not errors, report(errors)


def test_reviews_have_their_shape() -> None:
    errors = [e for p in shapes.direct_documents("reviews") for e in shapes.review_errors(p)]
    assert not errors, report(errors)


def _lenses(**lines: tuple[str, ...]) -> str:
    """A code review's five lenses, with the given lines under each lens named in lower case."""
    blocks = [[f"### {lens}", *lines.get(lens.lower(), ()), "The ledger."] for lens in shapes.LENS_SUBSECTIONS]
    body = "\n\n".join(line for block in blocks for line in block)
    return f"# Code review of a change\n\n## Lenses\n\n{body}\n\n## Security\n\n{LAYER_MAP_LINE}\n\n{SIZE_LINE}\n"


def test_a_new_code_review_states_the_layer_map_and_the_size(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both lines, each with its word, under Ownership alone, from the start date on.

    Guards: the date comparison turned round, a line read from a subsection before or after or from
    the whole file, a label that does not begin its line, a word on another line or inside a longer
    word, and a word in backticks lost to a read with code stripped.
    """
    start = shapes.LAYER_LINES_START

    def errors(date: str = start, **lines: tuple[str, ...]) -> list[str]:
        return shapes.layer_line_errors("a-code-review.md", date, _lenses(**lines))

    assert errors(ownership=(LAYER_MAP_LINE, SIZE_LINE)) == []
    [no_size] = errors(ownership=(LAYER_MAP_LINE,))
    assert no_size.startswith("a-code-review.md: ") and "Size:" in no_size
    [wordless_size] = errors(ownership=(LAYER_MAP_LINE, "Size: `src/vfs/base.py` 3,660 to 3,660."))
    assert "allowlist" in wordless_size
    [wordless_map] = errors(ownership=("Layer map: `vfs.base` on rung 8.", SIZE_LINE))
    assert "ladder" in wordless_map
    assert len(errors(tests=(LAYER_MAP_LINE, SIZE_LINE))) == 2
    assert len(errors(adversarial=(LAYER_MAP_LINE, SIZE_LINE))) == 2
    under_security = f"{_lenses()}\n### Ownership\n\n{LAYER_MAP_LINE}\n\n{SIZE_LINE}\n"
    assert len(shapes.layer_line_errors("a-code-review.md", start, under_security)) == 2
    [bulleted] = errors(ownership=(f"- {LAYER_MAP_LINE}", SIZE_LINE))
    assert "Layer map:" in bulleted
    [apart] = errors(ownership=("Layer map: `vfs.base` on rung 8.", "The ladder is unchanged.", SIZE_LINE))
    assert "Layer map:" in apart
    in_backticks = ("Layer map: `ladder unchanged`.", "Size: `tests/lint/allowlist.py` unchanged.")
    assert errors(ownership=in_backticks) == []
    longer_words = ("Layer map: the ladders are unchanged.", "Size: the allowlists are unchanged.")
    assert len(errors(ownership=longer_words)) == 2
    assert errors("2026-11-01") == []
    for closing in LAYER_MAP_CLOSINGS:
        assert errors(ownership=(f"Layer map: no module of `src/vfs` touched; {closing}", SIZE_LINE)) == []
    for closing in SIZE_CLOSINGS:
        assert errors(ownership=(LAYER_MAP_LINE, f"Size: no module of `src/vfs` touched; {closing}")) == []

    written_before = shapes.CONTEXT / "reviews" / "2026-11-12-bounded-work-has-one-home-code-review.md"
    assert shapes.review_errors(written_before) == []
    monkeypatch.setattr(shapes, "LAYER_LINES_START", "2026-11-12")
    assert len(shapes.review_errors(written_before)) == 2


def test_a_heading_inside_a_fence_does_not_end_the_ownership_subsection() -> None:
    """A fenced line that looks like a heading is no heading, so the two lines are still found.

    Guards: the section or the subsection cut at a ``## `` or ``### `` line inside a fenced block.
    """
    fence = ("```", "## run the gate", "### and each of its legs", "```")
    both = (LAYER_MAP_LINE, SIZE_LINE)
    start = shapes.LAYER_LINES_START
    assert shapes.layer_line_errors("a-code-review.md", start, _lenses(contract=fence, ownership=both)) == []
    assert shapes.layer_line_errors("a-code-review.md", start, _lenses(ownership=(*fence, *both))) == []
    assert len(shapes.layer_line_errors("a-code-review.md", start, _lenses(ownership=fence, adversarial=both))) == 2


def _scanned_documents() -> list[tuple[str, int]]:
    """Every document the open-question rule reads, with its hit count."""
    paths = [
        *shapes.direct_documents("intentions"),
        *shapes.direct_documents("research"),
        *shapes.direct_documents("reviews"),
        *shapes.direct_documents("specifications/active"),
        *shapes.direct_documents("specifications/archive"),
        *shapes.CONTEXT.glob("specifications/*/*/spec.md"),
        shapes.CONTEXT / "README.md",
        shapes.REPO / "AGENTS.md",
    ]
    return [(shapes.relative(p), len(shapes.open_question_hits(p.read_text()))) for p in paths]


def test_no_document_holds_an_open_question() -> None:
    errors = [
        f"{name}: {count} open-question line(s), {OPEN_QUESTION_ALLOWANCE.get(name, 0)} allowed"
        for name, count in _scanned_documents()
        if count > OPEN_QUESTION_ALLOWANCE.get(name, 0)
    ]
    assert not errors, report(errors)


def test_the_marker_allowlist_only_shrinks() -> None:
    counts = dict(_scanned_documents())
    errors = [
        f"{name}: allows {allowed} but the file holds {counts.get(name, 0)}; lower the entry"
        for name, allowed in OPEN_QUESTION_ALLOWANCE.items()
        if allowed > counts.get(name, 0)
    ]
    errors += [
        f"{name}: the ratchet admits only documents written before the process"
        for name in OPEN_QUESTION_ALLOWANCE
        if shapes.is_new(shapes.REPO / name)
    ]
    assert not errors, report(errors)


def test_landed_specs_link_their_reviews() -> None:
    errors = [e for p in shapes.dated_specs("specifications/archive") for e in shapes.landed_spec_errors(p)]
    assert not errors, report(errors)


def test_links_resolve() -> None:
    errors = [e for p in shapes.new_documents() for e in shapes.link_errors(p)]
    assert not errors, report(errors)


def test_paragraphs_are_one_line() -> None:
    run = subprocess.run([sys.executable, str(UNWRAP), "--check"], capture_output=True, text=True, check=False)
    assert run.returncode == 0 and not run.stdout, run.stdout + run.stderr


def test_the_unwrap_script_exists() -> None:
    assert UNWRAP.exists(), f"{UNWRAP} is missing"


def test_unwrap_keeps_a_hard_break_inside_a_paragraph() -> None:
    unwrap = shapes.unwrap_context.unwrap
    assert unwrap(["line one", "line two  ", "line three"]) == ["line one line two  ", "line three"]
    assert unwrap(["a\\", "b"]) == ["a\\", "b"]
    assert unwrap(["[a]: x", "[b]: y"]) == ["[a]: x", "[b]: y"]
    assert unwrap(["col | col", "--- | ---", "1 | 2"]) == ["col | col", "--- | ---", "1 | 2"]
    assert unwrap(["```", "~~~", "code", "```", "after"]) == ["```", "~~~", "code", "```", "after"]


def test_new_memos_label_their_claims() -> None:
    memos = [p for p in shapes.direct_documents("research") if shapes.is_new(p)]
    errors = [e for p in memos for e in shapes.memo_label_errors(p)]
    assert not errors, report(errors)


def test_the_process_pages_say_what_they_must() -> None:
    errors = shapes.process_page_errors()
    assert not errors, report(errors)
