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
    for needle in ("context/**", "tests/lint/**", "AGENTS.md", "uv run pytest tests/lint"):
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
        "python-style.md": ("src_old", "there is no sync facade", "SyncVirtualFileSystem"),
        "roadmap.md": ("SyncVirtualFileSystem", "SyncSession"),
        "testing.md": ("--mssql", "fail_under = 99"),
        "tooling.md": ("uvx", "uv pip"),
        "constitution.md": ("context/decisions/", "open-questions.md"),
        # the bump script rewrites pyproject.toml alone and locks by itself; the lane has started
        "release.md": ("src/vfs/__init__.py", "macos-13", "Before the first v2 release", "No release is planned"),
    }
    for page, needles in forbidden.items():
        text = (STANDARDS / page).read_text() if (STANDARDS / page).exists() else ""
        errors += [f"standards/{page} still says {needle!r}" for needle in needles if needle in text]
    required = {
        "testing.md": ("fail_under = 100",),
        "release.md": ("--pre", "--final", "--set", "workflow_dispatch", "--prerelease", "0.1.0a1", "0.1.0b1", "musl"),
        "python-style.md": ("vfs.sync", "AsyncVirtualFileSystem"),
    }
    for page, needles in required.items():
        text = (STANDARDS / page).read_text() if (STANDARDS / page).exists() else ""
        errors += [f"standards/{page} does not say {needle!r}" for needle in needles if needle not in text]
    assert not errors, "\n".join(errors)


def test_the_readme_tells_the_truth_after_the_yank() -> None:
    """The README ships in the wheel and names no dead release; the install guide carries the pin and the musl note."""
    readme = (REPO / "README.md").read_text()
    assert "previous-generation API" not in readme, "the README still says PyPI ships the previous-generation API"
    assert "0.0.22" not in readme, "the README still names the yanked release"
    # Under pip a bare install fails while a yanked final sits beside the alphas; the install line is the pin.
    assert 'pip install "vfs-py>=0.1.0a1,<0.2"' in readme, "the README's install line lacks the pre-release marker"
    assert "pip install vfs-py\n" not in readme, "the README shows the bare install line, which fails under pip"
    guide = (REPO / "docs" / "how-to" / "install.md").read_text()
    assert "vfs-py>=0.1.0a1,<0.2" in guide, "the install guide gives no pin with a pre-release marker"
    assert "python:3.13-slim" in guide, "the install guide does not name a glibc image for the Alpine note"
    assert "how-to/install.md" in (REPO / "mkdocs.yml").read_text(), "the install guide is not in the docs nav"


def test_the_review_skills_write_review_files() -> None:
    assert (SKILLS / "spec_review" / "SKILL.md").exists(), "no spec_review skill"
    code_review = (SKILLS / "code_review" / "SKILL.md").read_text()
    assert "context/reviews/" in code_review, "code_review does not write to context/reviews/"
    assert "Security" in code_review, "code_review has no Security section"
