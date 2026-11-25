"""Check the shape of a spec or a spec review under ``agents/`` against the templates.

Run from the repository root::

    uv run python agents/2026-11-25-the-backlog-converted/check_shape.py agents/<work-directory>/spec.md

Exit status 0 means the shape holds. Every other status prints one line per fault. The
check reads shape only: the sections, the numbering, the basis lines, the verdict words,
the voice and the links. Whether a decision is right is the review's work.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SPEC_SECTIONS = (
    "The problem",
    "Architecture",
    "Decisions",
    "Intent",
    "Design",
    "Scope",
    "Acceptance criteria",
    "Landing notes",
    "One line",
)
REVIEW_SECTIONS = (
    "Decisions, one line each",
    "Acceptance criteria, countable as written",
    "The diagram and the scope",
    "Scale and the production posture",
    "Constitution and AGENTS.md checks",
    "Premortem",
    "Findings, most severe first",
    "Checked and found clean",
    "Disposition",
    "Verdict",
)
REVIEW_OPTIONAL_FIRST = "Questions put to the review, answered first"
BASIS_FORMS = (
    "Basis: ruled,",
    "Basis: verified lean,",
    "Basis: the source spec,",
    "Basis: decided in drafting,",
    "Basis: provisional,",
)
VERDICT_WORDS = ("Fit to build", "Not yet")

FENCE_RE = re.compile(r"^(```|~~~)")
INLINE_CODE_RE = re.compile(r"`[^`]*`")
LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)\s]+)\)")
DATED_LINE_RE = re.compile(r"^\d{4}-\d{2}-\d{2},")
OPEN_RE = re.compile(r"NEEDS CLARIFICATION|\bTBD\b|\bTODO\b")
PERSON_RE = re.compile(r"\b(Clay|I|we|We|you|You|our|Our|my|My|us)\b")
PERSON_ALLOWED_RE = re.compile(r"\bI/O\b|\bUS\b")


# ---------------------------------------------------------------------------
# The two checks
# ---------------------------------------------------------------------------


def spec_faults(path: Path) -> list[str]:
    """Every way the spec at *path* departs from the spec template."""
    text = path.read_text()
    prose = _prose_lines(text)
    faults = _common_faults(path, text, prose)
    headings = [line[3:].strip() for line in prose if line.startswith("## ")]
    if tuple(headings) != SPEC_SECTIONS:
        faults.append(f"sections are {headings}, expected {list(SPEC_SECTIONS)}")
        return faults
    sections = _sections(text)
    if sections["Architecture"].count("```mermaid") != 1:
        faults.append("Architecture holds no single mermaid block")
    if not sections["Intent"].strip().startswith("After this spec,"):
        faults.append('Intent does not begin "After this spec,"')
    faults += _decision_faults(sections["Decisions"])
    criteria = [line for line in sections["Acceptance criteria"].splitlines() if re.match(r"^\d+\. ", line)]
    if not criteria:
        faults.append("Acceptance criteria holds no numbered criterion")
    for index, line in enumerate(criteria, start=1):
        if not line.startswith(f"{index}. "):
            faults.append(f"acceptance criterion {index} is out of sequence")
            break
    return faults


def review_faults(path: Path) -> list[str]:
    """Every way the review at *path* departs from the review template."""
    text = path.read_text()
    prose = _prose_lines(text)
    faults = _common_faults(path, text, prose)
    headings = [line[3:].strip() for line in prose if line.startswith("## ")]
    if headings and headings[0] == REVIEW_OPTIONAL_FIRST:
        headings = headings[1:]
    if tuple(headings) != REVIEW_SECTIONS:
        faults.append(f"sections are {headings}, expected {list(REVIEW_SECTIONS)}")
        return faults
    verdict = [line.strip() for line in _sections(text)["Verdict"].splitlines() if line.strip()]
    if not verdict or not verdict[0].startswith(VERDICT_WORDS):
        faults.append('the Verdict does not begin "Fit to build" or "Not yet"')
    for line in verdict[1:]:
        if DATED_LINE_RE.match(line) and not any(word in line.split(":", 1)[-1] for word in VERDICT_WORDS):
            faults.append(f"a dated verdict line carries no verdict word: {line[:60]}")
    return faults


def standing_verdict(path: Path) -> str:
    """The last dated line of the review's Verdict section, else its first line."""
    lines = [line.strip() for line in _sections(path.read_text()).get("Verdict", "").splitlines() if line.strip()]
    dated = [line for line in lines if DATED_LINE_RE.match(line)]
    return dated[-1] if dated else (lines[0] if lines else "")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _prose_lines(text: str) -> list[str]:
    lines, fenced = [], False
    for line in text.splitlines():
        if FENCE_RE.match(line.strip()):
            fenced = not fenced
            continue
        if not fenced:
            lines.append(line)
    return lines


def _sections(text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current, fenced = None, False
    for line in text.splitlines():
        if FENCE_RE.match(line.strip()):
            fenced = not fenced
        if not fenced and line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return {name: "\n".join(body) for name, body in sections.items()}


def _common_faults(path: Path, text: str, prose: list[str]) -> list[str]:
    faults = []
    if not text.startswith("# "):
        faults.append("line one is not a title")
    for number, line in enumerate(prose, start=1):
        bare = INLINE_CODE_RE.sub("", line)
        if OPEN_RE.search(bare) or re.match(r"^#+\s*open question", bare, re.IGNORECASE):
            faults.append(f"an open question or placeholder word: {line.strip()[:70]}")
        if line.lstrip().startswith(">"):
            continue
        quoted = re.sub(r'"[^"]*"', "", PERSON_ALLOWED_RE.sub("", bare))
        hit = PERSON_RE.search(quoted)
        if hit:
            faults.append(f'the voice names a person or speaks as one ("{hit.group(0)}"): {line.strip()[:70]}')
        for target in LINK_RE.findall(bare):
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            if not (path.parent / target.split("#")[0]).exists():
                faults.append(f"dead link {target}")
    return faults


def _decision_faults(body: str) -> list[str]:
    faults = []
    blocks = re.split(r"^### ", body, flags=re.MULTILINE)[1:]
    if not blocks:
        return ["Decisions holds no numbered decision"]
    for index, block in enumerate(blocks, start=1):
        heading = block.splitlines()[0]
        if not heading.startswith(f"{index}. "):
            faults.append(f"decision {index} is headed {heading[:40]!r}; the numbering has a gap")
            break
        basis = [line.strip() for line in block.splitlines() if line.strip().startswith("Basis:")]
        if len(basis) != 1:
            faults.append(f"decision {index} carries {len(basis)} basis lines, expected one")
        elif not basis[0].startswith(BASIS_FORMS):
            faults.append(f"decision {index} has a basis line in none of the five forms: {basis[0][:50]}")
    return faults


def main(arguments: list[str]) -> int:
    status = 0
    for name in arguments:
        path = Path(name)
        faults = review_faults(path) if path.name.endswith("review.md") else spec_faults(path)
        for fault in faults:
            print(f"{name}: {fault}")
        status |= bool(faults)
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
