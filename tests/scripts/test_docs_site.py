"""The docs app stays out of the Python package, its check workflow runs the docs check, and MkDocs is gone."""

from __future__ import annotations

import re
import subprocess
import tomllib
from pathlib import Path
from typing import Any, NamedTuple

import yaml

REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github" / "workflows" / "docs-site.yml"

# What the check workflow watches: the pages, the app, the docstrings, the scripts, the lock and itself.
WATCHED = {
    "documentation/**",
    "docs-app/**",
    "src/vfs/**",
    "scripts/docs_export.py",
    "scripts/docs.sh",
    "pyproject.toml",
    "uv.lock",
    ".github/workflows/docs-site.yml",
}

# What git must never track for the docs app: build output, the export, and the tools' own folders.
IGNORED = (
    "docs-app/build/index.html",
    "docs-app/.svelte-kit/output/x",
    "docs-app/src/lib/generated/api.json",
    "docs-app/test-results/x",
    "docs-app/playwright-report/index.html",
    "docs-app/node_modules/x/index.js",
)


# The widest line a code block in a page may hold: it fits the page's column on a phone without scrolling sideways.
CODE_WIDTH = 64

# The fence that shows what a call prints. Its lines are shown as printed, however wide: wrapping one would
# misstate the output, so an output block scrolls sideways and the limit binds every other block.
OUTPUT = "text"

_FENCE = re.compile(r"^\s*(```|~~~)(\w*)")


class _WideLine(NamedTuple):
    """One line of a fenced block that is wider than the limit."""

    number: int
    width: int
    language: str


def _wide_code_lines(text: str, width: int) -> list[_WideLine]:
    """Each line inside a fenced block that is wider than *width*, with the language its fence names."""
    wide: list[_WideLine] = []
    language: str | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        fence = _FENCE.match(line)
        if fence:
            language = fence[2] if language is None else None
        elif language is not None and len(line) > width:
            wide.append(_WideLine(number, len(line), language))
    return wide


def test_no_line_of_code_in_a_page_is_wider_than_64_characters() -> None:
    """A wider line makes a reader scroll code sideways; raising the limit or skipping a fence lets one back in."""
    probe = "```text\n" + "x" * 65 + "\n```\n" + "y" * 200 + "\n~~~python\n" + "z" * 64 + "\n~~~\n```\n" + "w" * 65
    assert _wide_code_lines(probe, CODE_WIDTH) == [_WideLine(2, 65, "text"), _WideLine(9, 65, "")]
    wide = [
        f"{page.relative_to(REPO).as_posix()}:{line.number} is {line.width} characters wide"
        for page in sorted((REPO / "documentation").rglob("*.md"))
        for line in _wide_code_lines(page.read_text(encoding="utf-8"), CODE_WIDTH)
        if line.language != OUTPUT
    ]
    assert wide == []


def _pyproject() -> dict[str, Any]:
    with (REPO / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)


def test_the_docs_app_is_no_part_of_the_package() -> None:
    """A Python file under the app, or a wheel that takes more than ``src``, would ship the docs with the library."""
    tracked = subprocess.run(
        ["git", "ls-files", "docs-app"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.split()
    assert [path for path in tracked if path.endswith(".py")] == []
    maturin = _pyproject()["tool"]["maturin"]
    assert maturin["python-source"] == "src"
    assert "include" not in maturin
    ignored = subprocess.run(
        ["git", "check-ignore", *IGNORED], cwd=REPO, capture_output=True, text=True, check=False
    ).stdout.split()
    assert ignored == list(IGNORED)


def test_the_check_workflow_runs_the_docs_check() -> None:
    """A dropped path would let a docstring or a page change land unchecked; a wider permission is never needed."""
    workflow: dict[Any, Any] = yaml.safe_load(WORKFLOW.read_text())
    triggers = workflow[True]  # PyYAML reads the key `on` as the boolean true
    assert set(triggers) == {"push", "pull_request"}
    assert triggers["push"]["branches"] == ["main"]
    assert set(triggers["push"]["paths"]) == WATCHED
    assert set(triggers["pull_request"]["paths"]) == WATCHED
    assert workflow["permissions"] == {"contents": "read"}
    steps = [step.get("run", "") for job in workflow["jobs"].values() for step in job["steps"]]
    browser = next(index for index, run in enumerate(steps) if "playwright install" in run and "chromium" in run)
    check = next(index for index, run in enumerate(steps) if run.strip() == "scripts/docs.sh check")
    assert browser < check


def test_mkdocs_no_longer_builds_the_new_pages() -> None:
    """Two renderers for one set of pages means every page is checked by two tools with two sets of rules."""
    gone = (
        "mkdocs-documentation.yml",
        "overrides",
        "documentation/stylesheets",
        "documentation/javascripts",
        "documentation/index.md",
        "documentation/introduction.md",
    )
    assert [path for path in gone if (REPO / path).exists()] == []
    groups = _pyproject()["dependency-groups"]
    named = [str(requirement) for group in groups.values() for requirement in group]
    assert [name for name in named if "mkdocs-material" in name or "mkdocstrings" in name] == []
