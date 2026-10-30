"""The shape of the documents under ``context/``, held by one test per rule."""

from __future__ import annotations

import subprocess
import sys

from tests.lint import shapes
from tests.lint.allowlist import OPEN_QUESTION_ALLOWANCE

UNWRAP = shapes.REPO / "scripts" / "unwrap_context.py"


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
    specs = shapes.dated_specs("specs/active") + shapes.dated_specs("specs/archive")
    errors = [e for p in specs for e in shapes.spec_errors(p)]
    assert not errors, report(errors)


def test_reviews_have_their_shape() -> None:
    errors = [e for p in shapes.direct_documents("reviews") for e in shapes.review_errors(p)]
    assert not errors, report(errors)


def _scanned_documents() -> list[tuple[str, int]]:
    """Every document the open-question rule reads, with its hit count."""
    paths = [
        *shapes.direct_documents("intentions"),
        *shapes.direct_documents("research"),
        *shapes.direct_documents("reviews"),
        *shapes.direct_documents("specs/active"),
        *shapes.direct_documents("specs/archive"),
        *shapes.CONTEXT.glob("specs/*/*/spec.md"),
        shapes.CONTEXT / "README.md",
        shapes.REPO / "CLAUDE.md",
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
    errors = [e for p in shapes.dated_specs("specs/archive") for e in shapes.landed_spec_errors(p)]
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
