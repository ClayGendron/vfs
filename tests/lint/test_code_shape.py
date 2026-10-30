"""The shape of the code and the tooling the process relies on."""

from __future__ import annotations

import hashlib
import json
import re
from typing import TYPE_CHECKING

from tests.lint.shapes import REPO

if TYPE_CHECKING:
    from pathlib import Path

SRC = REPO / "src" / "vfs"
STANDARDS = REPO / "context" / "standards"
SKILLS = REPO / ".claude" / "skills"
SECURITY_SKILL = SKILLS / "security-audit"
SKILLS_LOCK = REPO / "skills-lock.json"
LINT_WORKFLOW = REPO / ".github" / "workflows" / "lint.yml"

DOCUMENT_CITATION = re.compile(r"\b(spec|ADR|story) [0-9]{3}\b")
# vfs's own SHA-256 over the installed skill folder: sorted relative paths and bytes.
SECURITY_SKILL_SHA256 = "ac796659de231c3ab76f6ee012836072bdc82928fb019199925c9062800e16c1"


def folder_sha256(root: Path) -> str:
    """One hash over a folder: each file's relative path and bytes, in sorted order, dotfiles left out."""
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file() and not p.name.startswith(".")):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def test_src_names_no_context_document() -> None:
    hits = [
        f"{path.relative_to(REPO)}:{number}: {line.strip()[:80]}"
        for path in sorted(SRC.rglob("*.py"))
        for number, line in enumerate(path.read_text().splitlines(), 1)
        if DOCUMENT_CITATION.search(line)
    ]
    assert not hits, "\n".join(hits)


def test_the_security_skill_is_installed_unchanged() -> None:
    assert (SECURITY_SKILL / "SKILL.md").exists(), "the security-audit skill is not installed"
    lock = json.loads(SKILLS_LOCK.read_text())
    assert lock["skills"]["security-audit"]["source"] == "cloudflare/security-audit-skill"
    changed = (
        "the skill folder changed since it was pinned: run `npx skills check`, review the update, then pin "
        "folder_sha256(SECURITY_SKILL) as SECURITY_SKILL_SHA256 in a commit of its own, as standards/landing.md says"
    )
    assert folder_sha256(SECURITY_SKILL) == SECURITY_SKILL_SHA256, changed


def test_the_lint_workflow_covers_context() -> None:
    assert LINT_WORKFLOW.exists(), "no .github/workflows/lint.yml"
    text = LINT_WORKFLOW.read_text()
    for needle in ("context/**", "tests/lint/**", "CLAUDE.md", "uv run pytest tests/lint"):
        assert needle in text, f"lint.yml does not mention {needle!r}"


def test_the_standards_agree_with_the_tree() -> None:
    errors: list[str] = [
        f"standards/{gone} still exists"
        for gone in ("commits-and-prs.md", "contributing.md")
        if (STANDARDS / gone).exists()
    ]
    errors += [
        f"standards/{page} is missing" for page in ("how-we-code.md", "landing.md") if not (STANDARDS / page).exists()
    ]
    forbidden = {
        "python-style.md": ("src_old",),
        "testing.md": ("--mssql", "fail_under = 99"),
        "tooling.md": ("uvx", "uv pip"),
        "constitution.md": ("context/decisions/", "open-questions.md"),
    }
    for page, needles in forbidden.items():
        text = (STANDARDS / page).read_text() if (STANDARDS / page).exists() else ""
        errors += [f"standards/{page} still says {needle!r}" for needle in needles if needle in text]
    if "fail_under = 100" not in (STANDARDS / "testing.md").read_text():
        errors.append("standards/testing.md does not say fail_under = 100")
    assert not errors, "\n".join(errors)


def test_the_review_skills_write_review_files() -> None:
    assert (SKILLS / "spec_review" / "SKILL.md").exists(), "no spec_review skill"
    code_review = (SKILLS / "code_review" / "SKILL.md").read_text()
    assert "context/reviews/" in code_review, "code_review does not write to context/reviews/"
    assert "Security" in code_review, "code_review has no Security section"
