"""Pure checkers for the shape of the documents under ``context/``.

Every checker takes a path or a text and returns a list of error strings, one per
fault, each naming the file and the missing part. A test asserts the list is empty
and prints it whole, so one run names every file that is wrong. Nothing here reads
behaviour or the clock; everything is a file read and a string match.

    >>> headings("# T\\n\\n## A\\n\\ntext\\n\\n## B\\n")
    ['A', 'B']
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

# The unwrap script stands alone under scripts/; the lint borrows its tree walk and
# its fence rule rather than keeping a second copy of either.
_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "unwrap_context.py"
_SPEC = importlib.util.spec_from_file_location("unwrap_context", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
unwrap_context = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(unwrap_context)

REPO: Path = unwrap_context.REPO
CONTEXT: Path = unwrap_context.CONTEXT
PROCESS_START = "2026-10-29"
markdown_files = unwrap_context.markdown_files
FENCE_RE: re.Pattern[str] = unwrap_context.FENCE_RE

# Direct files in the dated folders that are not documents of the process.
FIXED_NAMES = frozenset({"README.md", "STATUS.md", "MINING.md"})
DATED_FOLDERS = ("intentions", "specifications/active", "specifications/archive", "reviews", "research")

DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
DATED_NAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
NUMBERED_RE = re.compile(r"^[0-9]{3}-")
HEADING_RE = re.compile(r"^## (.+?)\s*$", re.M)
SUBHEADING_RE = re.compile(r"^### (.+?)\s*$", re.M)
DECISION_RE = re.compile(r"^### (\d+)\. ", re.M)
NUMBERED_ITEM_RE = re.compile(r"^\d+\. ")
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
LABEL_RE = re.compile(r"\b(EXECUTED|READ|INFERRED)\b")
TBD_TODO_RE = re.compile(r"\b(TBD|TODO)\b")
MARKER = "[NEEDS CLARIFICATION"

INTENTION_SECTIONS = (
    "The story",
    "The problem today",
    "What we intend to achieve",
    "Part of the story",
    "What this is not",
    "Done when",
    "What the research must answer",
)
INTENTION_OPTIONAL = frozenset({"Part of the story"})
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
SPEC_REVIEW_SECTIONS = (
    "The author's questions, answered first",
    "Decisions, one line each",
    "Acceptance criteria, countable as written",
    "The diagram and the scope",
    "Scale and the production posture",
    "Constitution and CLAUDE.md checks",
    "Premortem",
    "Findings, most severe first",
    "Checked and found clean",
    "Disposition",
    "Verdict",
)
SPEC_REVIEW_OPTIONAL = frozenset({"The author's questions, answered first"})
CODE_REVIEW_SECTIONS = (
    "Scope",
    "Acceptance criteria against evidence",
    "Findings, most severe first",
    "Lenses",
    "Security",
    "Standards checks",
    "Disposition",
    "Verdict",
)
LENS_SUBSECTIONS = ("Contract", "Scale", "Tests", "Ownership", "Adversarial")
SPEC_REVIEW_VERDICTS = ("Fit to build", "Not yet")
CODE_REVIEW_VERDICTS = ("Lands", "Does not land yet")
PIPELINE_STAGES = ("intent", "research", "spec", "review", "code", "review", "commit")


# ---------------------------------------------------------------------------
# Reading the tree
# ---------------------------------------------------------------------------


def direct_documents(folder: str) -> list[Path]:
    """The direct ``*.md`` files of one dated folder, the fixed names left out."""
    return sorted(p for p in (CONTEXT / folder).glob("*.md") if p.name not in FIXED_NAMES)


def document_date(path: Path) -> str | None:
    """The first ``YYYY-MM-DD`` in the path under ``context/``, or None."""
    match = DATE_RE.search(str(path.relative_to(CONTEXT)))
    return match.group(0) if match else None


def is_new(path: Path) -> bool:
    """A document dated on or after the day the process landed."""
    date = document_date(path)
    return date is not None and date >= PROCESS_START


def new_documents() -> list[Path]:
    return [p for p in markdown_files() if is_new(p)]


def dated_specs(folder: str) -> list[Path]:
    """The one-file specs of a specs folder: direct files whose name starts with a date."""
    return [p for p in direct_documents(folder) if DATED_NAME_RE.match(p.name)]


def relative(path: Path) -> str:
    return str(path.relative_to(REPO))


# ---------------------------------------------------------------------------
# Reading one document
# ---------------------------------------------------------------------------


def strip_code(text: str) -> str:
    """The text with fenced blocks and inline code removed."""
    kept: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence:
            kept.append(re.sub(r"`[^`\n]*`", "", line))
    return "\n".join(kept)


def headings(text: str) -> list[str]:
    """The ``## `` headings outside code, in order."""
    return HEADING_RE.findall(strip_code(text))


def section_text(text: str, heading: str) -> str:
    """The text under one ``## `` heading, up to the next one; empty when absent."""
    plain = strip_code(text)
    match = re.search(rf"^## {re.escape(heading)}\s*$(.*?)(?=^## |\Z)", plain, re.M | re.S)
    return match.group(1) if match else ""


def raw_section_text(text: str, heading: str) -> str:
    """The text under one ``## `` heading with its code kept, for fence checks."""
    match = re.search(rf"^## {re.escape(heading)}\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    return match.group(1) if match else ""


def first_paragraph(text: str) -> str:
    """The first non-blank line after the title line."""
    lines = text.splitlines()
    body = lines[1:] if lines and lines[0].startswith("# ") else lines
    return next((line.strip() for line in body if line.strip()), "")


def standing_verdict(text: str) -> str:
    """The Verdict section's standing line: the last line that begins with a date, else the first."""
    lines = [line.strip() for line in section_text(text, "Verdict").splitlines() if line.strip()]
    if not lines:
        return ""
    dated = [line for line in lines if DATE_RE.match(line)]
    return dated[-1] if dated else lines[0]


def verdict_word(line: str) -> str:
    """The verdict with any leading date signature stripped."""
    return re.sub(r"^\d{4}-\d{2}-\d{2},[^:]*:\s*", "", line)


def section_order_errors(name: str, found: list[str], required: tuple[str, ...], optional: frozenset[str]) -> list[str]:
    """Errors when *found* is not *required* in order, the optional ones aside."""
    expected = [h for h in required if h not in optional or h in found]
    if found == expected:
        return []
    missing = [h for h in expected if h not in found]
    extra = [h for h in found if h not in required]
    errors: list[str] = [f"{name}: missing section '## {h}'" for h in missing]
    errors += [f"{name}: unexpected section '## {h}'" for h in extra]
    if not missing and not extra:
        errors.append(f"{name}: sections out of order: {found}")
    return errors


# ---------------------------------------------------------------------------
# The checkers, one per rule
# ---------------------------------------------------------------------------


def name_errors() -> list[str]:
    """Every direct document is dated and descriptive; nothing anywhere is numbered."""
    errors: list[str] = []
    for folder in DATED_FOLDERS:
        errors += [
            f"{relative(p)}: not named YYYY-MM-DD-descriptive-slug.md"
            for p in direct_documents(folder)
            if not DATED_NAME_RE.match(p.name)
        ]
        errors += [
            f"{relative(p)}: a numbered document name"
            for p in (CONTEXT / folder).glob("*.md")
            if NUMBERED_RE.match(p.name)
        ]
    studies = (CONTEXT / "research" / "studies").glob("*/*.md")
    errors += [f"{relative(p)}: a numbered study name" for p in studies if NUMBERED_RE.match(p.name)]
    return errors


def header_errors(path: Path) -> list[str]:
    """A new document has no ``- **`` bullet before its first ``## `` heading."""
    errors = []
    for line in path.read_text().splitlines():
        if line.startswith("## "):
            break
        if line.startswith("- **"):
            errors.append(f"{relative(path)}: header line before the first section: {line[:60]}")
    return errors


def intention_errors(path: Path) -> list[str]:
    """An intention has its sections in order, a numbered Done when, and a last section that is a list or None."""
    text = path.read_text()
    errors: list[str] = section_order_errors(relative(path), headings(text), INTENTION_SECTIONS, INTENTION_OPTIONAL)
    done = [line.strip() for line in section_text(text, "Done when").splitlines() if line.strip()]
    if not done or not all(NUMBERED_ITEM_RE.match(line) for line in done):
        errors.append(f"{relative(path)}: 'Done when' is not a numbered list")
    last = [line.strip() for line in section_text(text, INTENTION_SECTIONS[-1]).splitlines() if line.strip()]
    if last != ["None."] and not (last and all(NUMBERED_ITEM_RE.match(line) for line in last)):
        errors.append(f"{relative(path)}: '{INTENTION_SECTIONS[-1]}' is neither a numbered list nor 'None.'")
    return errors


def spec_errors(path: Path) -> list[str]:
    """A spec has its nine sections in order, a Mermaid fence, and gap-free numbered decisions."""
    text = path.read_text()
    errors: list[str] = section_order_errors(relative(path), headings(text), SPEC_SECTIONS, frozenset())
    if "```mermaid" not in raw_section_text(text, "Architecture"):
        errors.append(f"{relative(path)}: no mermaid fence under Architecture")
    numbers = [int(n) for n in DECISION_RE.findall(section_text(text, "Decisions"))]
    if numbers != list(range(1, len(numbers) + 1)) or not numbers:
        errors.append(f"{relative(path)}: decisions are not numbered 1 to N: {numbers}")
    return errors


def review_errors(path: Path) -> list[str]:
    """A review is a spec review or a code review, with its headings in order and a verdict word."""
    name = relative(path)
    text = path.read_text()
    found = headings(text)
    if path.name.endswith("-spec-review.md"):
        errors = section_order_errors(name, found, SPEC_REVIEW_SECTIONS, SPEC_REVIEW_OPTIONAL)
        verdicts = SPEC_REVIEW_VERDICTS
    elif path.name.endswith("-code-review.md"):
        errors = section_order_errors(name, found, CODE_REVIEW_SECTIONS, frozenset())
        lenses = SUBHEADING_RE.findall(section_text(text, "Lenses"))
        if lenses != list(LENS_SUBSECTIONS):
            errors.append(f"{name}: Lenses subsections are {lenses}, not {list(LENS_SUBSECTIONS)}")
        verdicts = CODE_REVIEW_VERDICTS
    else:
        return [f"{name}: a review is named …-spec-review.md or …-code-review.md"]
    lines = [line.strip() for line in section_text(text, "Verdict").splitlines() if line.strip()]
    first = lines[0] if lines else ""
    if not first.startswith(verdicts):
        errors.append(f"{name}: the Verdict's first line does not begin with one of {verdicts}")
    return errors


def open_question_hits(text: str) -> list[str]:
    """Lines, outside code, holding the marker, TBD, TODO, or a heading beginning 'open question'."""
    hits = []
    for line in strip_code(text).splitlines():
        heading = re.sub(r"[^a-z0-9 ]", "", line.lower()).strip() if line.startswith("#") else ""
        if MARKER in line or TBD_TODO_RE.search(line) or heading.startswith("open question"):
            hits.append(line.strip()[:100])
    return hits


def landed_spec_errors(path: Path) -> list[str]:
    """An archived spec links a signed spec review and a signed code review, or is withdrawn."""
    name = relative(path)
    text = path.read_text()
    if first_paragraph(text).startswith("Withdrawn:"):
        return []
    slug = path.name[len("YYYY-MM-DD-") : -len(".md")]
    notes = strip_code(section_text(text, "Landing notes"))
    links = [Path(link.split("#")[0]).name for link in LINK_RE.findall(notes)]
    errors: list[str] = []
    wanted = (("-spec-review.md", SPEC_REVIEW_VERDICTS[0]), ("-code-review.md", CODE_REVIEW_VERDICTS[0]))
    for suffix, verdicts in wanted:
        reviews = [link for link in links if link.endswith(suffix) and slug in link]
        if not reviews:
            errors.append(f"{name}: landed, but its landing notes link no {suffix} for '{slug}'")
            continue
        for review in reviews:
            review_path = CONTEXT / "reviews" / review
            if not review_path.exists():
                errors.append(f"{name}: links {review}, which does not exist")
            elif not verdict_word(standing_verdict(review_path.read_text())).startswith(verdicts):
                errors.append(f"{name}: {review}'s standing verdict does not begin with '{verdicts}'")
    return errors


def link_errors(path: Path) -> list[str]:
    """Every relative Markdown link resolves; active/<name> resolves when archive/<name> exists."""
    errors = []
    for target in LINK_RE.findall(strip_code(path.read_text())):
        if "://" in target or target.startswith(("#", "mailto:")):
            continue
        resolved = (path.parent / target.split("#")[0]).resolve()
        moved = Path(str(resolved).replace("/specifications/active/", "/specifications/archive/"))
        if REPO not in resolved.parents:
            errors.append(f"{relative(path)}: dead link (outside the repository) {target}")
        elif not resolved.exists() and not moved.exists():
            errors.append(f"{relative(path)}: dead link {target}")
    return errors


def memo_label_errors(path: Path) -> list[str]:
    """A new memo labels at least one claim, unless it is a placeholder."""
    text = path.read_text()
    if "placeholder" in first_paragraph(text).lower() or LABEL_RE.search(strip_code(text)):
        return []
    return [f"{relative(path)}: no EXECUTED, READ or INFERRED label and not a placeholder"]


def process_page_errors() -> list[str]:
    """The process pages say what the spec requires of them."""
    readme = (CONTEXT / "README.md").read_text()
    errors: list[str] = [
        f"context/README.md: does not name the stage '{s}'" for s in PIPELINE_STAGES if s not in readme
    ]
    if "```mermaid" not in readme:
        errors.append("context/README.md: no mermaid fence")
    reviews_readme = CONTEXT / "reviews" / "README.md"
    templates = reviews_readme.read_text() if reviews_readme.exists() else ""
    errors += [
        f"context/reviews/README.md: no template beginning '{t}'"
        for t in ("# Spec review:", "# Code review of")
        if t not in templates
    ]
    if "froze" not in first_paragraph((CONTEXT / "specifications/STATUS.md").read_text()):
        errors.append("context/specifications/STATUS.md: first paragraph does not say it froze")
    return errors
