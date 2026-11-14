"""The shape of the documents under ``context/``, held by one test per rule."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from typing import TYPE_CHECKING

from tests.lint import shapes
from tests.lint.allowlist import OPEN_QUESTION_ALLOWANCE

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

UNWRAP = shapes.REPO / "scripts" / "unwrap_context.py"

# A release audit's review file in a scratch tree: its name, its eight sections, and its run folder's files.
AUDIT = "2026-11-07-9-9-9-security-audit"
AUDIT_SECTIONS = (
    "Run",
    "Security posture",
    "Confirmed findings",
    "Needs validation",
    "Hardening notes",
    "Positive source patterns",
    "Coverage",
    "Verdict",
)
AUDIT_RUN_FILES = ("run-metadata.json", "findings.json", "coverage-ledger.json")
BLOCKS = "Blocks the release: the one confirmed high."
CLEARS = "Clears the release: no confirmed critical or high."
RULE = "clears only when run_status is complete"


def _record(verdict: str, severity: str) -> dict[str, object]:
    """One record of a run's ``findings.json``, reduced to the two fields the lint reads."""
    return {"verdict": verdict, "severity": {"overall_severity": severity}}


HIGH = _record("confirmed", "high")
CRITICAL = _record("confirmed", "critical")
# A run with no confirmed critical or high: a lead and a rejected record at high do not block it.
CLEAN = (
    _record("confirmed", "medium"),
    _record("confirmed", "low"),
    _record("confirmed", "informational"),
    _record("rejected", "high"),
)
LEAD: dict[str, object] = {"verdict": "needs_validation", "severity": None}
CLEAN_WITH_A_LEAD = (*CLEAN, LEAD)
CONFIRMED_HIGH = '{"verdict": "confirmed", "severity": {"overall_severity": "high"}}'
# A run folder file the lint cannot read as the skill's schema shapes it, and the fault it is refused for.
MALFORMED_RUNS = (
    ("run-metadata.json", "{", "is not JSON"),
    ("run-metadata.json", "[]", "is not a JSON object"),
    ("run-metadata.json", '{"run_id": "run-9"}', "holds no run_status"),
    ("findings.json", "", "is not JSON"),
    ("findings.json", "[" * 100_000, "is not JSON"),
    ("findings.json", "{}", "is not a JSON array"),
    ("findings.json", f'[{CONFIRMED_HIGH}, "x"]', "holds record 2, which is not a JSON object"),
    ("findings.json", '[{"severity": null}]', "holds record 1, whose verdict the skill's schema does not spell"),
    ("findings.json", f"[{CONFIRMED_HIGH.replace('confirmed', 'Confirmed')}]", "holds record 1, whose verdict"),
    ("findings.json", '[{"verdict": "confirmed", "severity": null}]', "holds record 1, confirmed with no severity"),
    ("findings.json", '[{"verdict": "confirmed", "severity": "high"}]', "holds record 1, confirmed with no severity"),
    ("findings.json", '[{"verdict": "confirmed", "severity": {}}]', "holds record 1, confirmed with no severity"),
)

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


def _audit_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A scratch repository the lint reads in place of this one; its ``context/reviews`` is returned."""
    monkeypatch.setattr(shapes, "REPO", tmp_path)
    monkeypatch.setattr(shapes, "CONTEXT", tmp_path / "context")
    reviews = tmp_path / "context" / "reviews"
    reviews.mkdir(parents=True)
    return reviews


def _audit_review(reviews: Path, verdict: str, sections: tuple[str, ...] = AUDIT_SECTIONS) -> Path:
    """A release audit's review file with *sections* in order, its Verdict's first line *verdict*."""
    texts = [verdict if section == "Verdict" else "The run says." for section in sections]
    body = "\n\n".join(f"## {section}\n\n{text}" for section, text in zip(sections, texts, strict=True))
    path = reviews / f"{AUDIT}.md"
    path.write_text(f"# Security audit of 9.9.9\n\nThe record of one run.\n\n{body}\n")
    return path


def _audit_run(
    reviews: Path,
    status: str = "complete",
    findings: tuple[dict[str, object], ...] = (HIGH,),
    files: tuple[str, ...] = AUDIT_RUN_FILES,
) -> Path:
    """The run folder beside the review file, holding *files* of the three the lint requires."""
    folder = reviews / AUDIT
    folder.mkdir()
    contents = {
        "run-metadata.json": {"run_id": "run-9", "run_status": status},
        "findings.json": list(findings),
        "coverage-ledger.json": {"units": []},
    }
    for name in files:
        (folder / name).write_text(json.dumps(contents[name]))
    return folder


def test_a_security_audit_review_has_its_shape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Eight sections in order, one of two verdict words, and a first word the run folder agrees with.

    Guards: the ``run_status`` check dropped or read as anything but ``complete``, ``critical`` or ``high``
    dropped from the blocking set, a severity the skill's schema does not spell read as one that clears,
    the verdict filter dropped so a rejected record or a lead blocks, a section made optional, and the
    rule judged over a verdict that is neither word.
    """
    reviews = _audit_tree(tmp_path, monkeypatch)

    def errors(
        verdict: str,
        sections: tuple[str, ...] = AUDIT_SECTIONS,
        status: str = "complete",
        findings: tuple[dict[str, object], ...] = (HIGH,),
    ) -> list[str]:
        shutil.rmtree(reviews / AUDIT, ignore_errors=True)
        _audit_run(reviews, status, findings)
        return shapes.review_errors(_audit_review(reviews, verdict, sections))

    name = f"context/reviews/{AUDIT}.md"
    assert errors(BLOCKS) == []
    [wrongly_cleared] = errors(CLEARS)
    assert wrongly_cleared.startswith(f"{name}: ") and RULE in wrongly_cleared
    assert "Blocks the release" in wrongly_cleared
    [incomplete] = errors(CLEARS, status="incomplete", findings=CLEAN)
    assert RULE in incomplete
    # The skill writes in_progress before a run ends; any status but complete, the empty one too, blocks.
    for unfinished in ("in_progress", ""):
        [not_complete] = errors(CLEARS, status=unfinished, findings=CLEAN)
        assert RULE in not_complete
        assert errors(BLOCKS, status=unfinished, findings=CLEAN) == []
    # A severity the schema does not spell, such as a mis-cased High, blocks rather than clears.
    [mis_cased] = errors(CLEARS, findings=(*CLEAN, _record("confirmed", "High")))
    assert RULE in mis_cased and mis_cased.endswith("every confirmed record is informational, low or medium")
    assert errors(BLOCKS, findings=(*CLEAN, _record("confirmed", "High"))) == []
    assert errors(CLEARS, findings=CLEAN_WITH_A_LEAD) == []
    [critical] = errors(CLEARS, findings=(*CLEAN, CRITICAL))
    assert RULE in critical
    [wrongly_blocked] = errors(BLOCKS, findings=CLEAN)
    assert RULE in wrongly_blocked and "Clears the release" in wrongly_blocked
    assert errors(BLOCKS, status="incomplete", findings=CLEAN) == []

    [no_coverage] = errors(BLOCKS, tuple(s for s in AUDIT_SECTIONS if s != "Coverage"))
    assert no_coverage == f"{name}: missing section '## Coverage'"
    [ship_it] = errors("Ship it.")
    assert ship_it.startswith(f"{name}: ") and "Clears the release" in ship_it and "Blocks the release" in ship_it


def test_a_security_audit_review_needs_its_run_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The review file's run folder sits beside it whole and readable, and never stands without its file.

    Guards: the folder check dropped; any one of the three files left unchecked; a file the lint cannot
    read as the skill's schema shapes it raising out of the lint or letting the run clear, each of the
    faults below unchecked, and the records read only up to the first that blocks; and the orphan check
    dropped or widened to a folder the walk does not prune, by which a folder named to be pruned would
    hide from every prose check.
    """
    reviews = _audit_tree(tmp_path, monkeypatch)
    folder = f"context/reviews/{AUDIT}/"
    review = _audit_review(reviews, BLOCKS)
    [no_folder] = shapes.review_errors(review)
    assert "run folder" in no_folder and folder in no_folder
    for absent in AUDIT_RUN_FILES:
        shutil.rmtree(reviews / AUDIT, ignore_errors=True)
        _audit_run(reviews, files=tuple(f for f in AUDIT_RUN_FILES if f != absent))
        [missing] = shapes.review_errors(review)
        assert absent in missing and folder in missing

    for file, text, fault in MALFORMED_RUNS:
        for verdict in (CLEARS, BLOCKS):
            shutil.rmtree(reviews / AUDIT)
            (_audit_run(reviews, findings=CLEAN) / file).write_text(text)
            [unreadable] = shapes.review_errors(_audit_review(reviews, verdict))
            assert f"{folder}{file} {fault}" in unreadable and "never clears" in unreadable

    shutil.rmtree(reviews / AUDIT)
    _audit_run(reviews)
    _audit_review(reviews, BLOCKS)
    for walked in (reviews / "2026-11-07-other" / "x-security-audit", reviews / f"{AUDIT}-notes"):
        walked.mkdir(parents=True)
    assert shapes.name_errors() == []

    review.unlink()
    [orphan] = shapes.name_errors()
    assert orphan.startswith(f"context/reviews/{AUDIT}: ") and f"{AUDIT}.md" in orphan
    (reviews / AUDIT).rename(reviews / "notes-security-audit")
    [misnamed] = shapes.name_errors()
    assert misnamed.startswith("context/reviews/notes-security-audit: ")


def test_the_walk_prunes_only_a_release_audit_run_folder(tmp_path: Path) -> None:
    """The walk leaves out a run folder directly under the walked root's ``reviews/`` and nothing else.

    Guards: the prune anchored at the module's ``CONTEXT`` instead of the walk's own root, and the
    prune widened past ``reviews/``, below its direct children, to another folder named ``reviews``,
    or to a name that only holds the suffix.
    """
    root = tmp_path / "context"
    run = root / "reviews" / AUDIT / "REPORT.md"
    kept = [
        root / "reviews" / f"{AUDIT}.md",
        root / "reviews" / "2026-11-07-other" / "notes.md",
        root / "reviews" / "2026-11-07-other" / "x-security-audit" / "b.md",
        root / "research" / "x-security-audit" / "a.md",
        root / "research" / "reviews" / AUDIT / "c.md",
        root / "reviews" / f"{AUDIT}-notes" / "d.md",
    ]
    for path in (run, *kept):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# A\n")
    assert shapes.markdown_files(root) == sorted(kept)


def test_a_release_audit_name_spells_its_version_with_dashes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A version's dots are written as dashes in a release audit's name; a dotted name is refused.

    Guards: a dot admitted by ``DATED_NAME_RE``.
    """
    reviews = _audit_tree(tmp_path, monkeypatch)
    (reviews / "2026-11-07-0.1.0a1-security-audit.md").write_text("# A\n")
    [dotted] = shapes.name_errors()
    assert dotted == "context/reviews/2026-11-07-0.1.0a1-security-audit.md: not named YYYY-MM-DD-descriptive-slug.md"
    assert shapes.DATED_NAME_RE.match("2026-11-07-0-1-0a1-security-audit.md")


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
