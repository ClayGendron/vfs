"""Conservative regex/glob pushdown helpers.

This is research code, not production code. It demonstrates the shape of safe
candidate generation:

- extract only literals every match must contain
- never reject patterns just because no literals are available
- leave exact matching to Python

Run:
    uv run python "grep_glob research/pushdown_extract.py"
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class RegexPushdown:
    required_literals: tuple[str, ...]
    can_use_whole_content_regex: bool
    postgres_pattern_prefix: str
    reason: str | None = None


@dataclass(frozen=True)
class GlobPushdown:
    literal_prefix: str | None
    ext: str | None
    like_pattern: str | None


_TOKEN = re.compile(r"\[(?:\\.|[^\]])*\]|\\.|\(\?:|.", re.DOTALL)
_ANCHORS = {"^", "$", r"\A", r"\Z"}
_GLOB_METACHARS = frozenset("*?[{")


def contains_unescaped_anchor(pattern: str) -> bool:
    return any(match.group() in _ANCHORS for match in _TOKEN.finditer(pattern))


def required_regex_literals(pattern: str, *, limit: int = 8) -> tuple[str, ...]:
    """Return literals safe to AND together as LIKE filters.

    This intentionally mirrors the repo's conservative strategy. Alternation
    and quantified groups return no literals because an AND prefilter would be
    unsound.
    """
    if re.search(r"\)[*+?{]", pattern):
        return ()
    if "(?!" in pattern or "(?<!" in pattern:
        return ()

    stripped = re.sub(r"\\.", "", pattern)
    stripped = re.sub(r"\[[^\]]*\]", "", stripped)
    if "|" in stripped:
        return ()

    cleaned = re.sub(r"\\.", " ", pattern)
    cleaned = re.sub(r"\[[^\]]*\]", " ", cleaned)
    cleaned = cleaned.replace("(", " ").replace(")", " ")
    cleaned = re.sub(r"\w[*+?]", " ", cleaned)
    cleaned = re.sub(r"\w\{[^}]*\}", " ", cleaned)
    cleaned = re.sub(r"[.^$]", " ", cleaned)

    seen: set[str] = set()
    out: list[str] = []
    for run in re.findall(r"[A-Za-z0-9_]{3,}", cleaned):
        if run in seen:
            continue
        seen.add(run)
        out.append(run)
        if len(out) >= limit:
            break
    return tuple(out)


def regex_pushdown(pattern: str, *, invert_match: bool = False) -> RegexPushdown:
    if invert_match:
        return RegexPushdown((), False, "", "invert-match makes positive content predicates unsound")
    literals = required_regex_literals(pattern)
    if contains_unescaped_anchor(pattern):
        return RegexPushdown(literals, True, "(?n)", "use PostgreSQL newline-sensitive ARE mode")
    return RegexPushdown(literals, True, "")


def glob_pushdown(pattern: str) -> GlobPushdown:
    full = pattern if pattern.startswith("/") else "/" + pattern
    parts = full.lstrip("/").split("/") if full != "/" else []

    literal_count = 0
    for part in parts:
        if any(ch in _GLOB_METACHARS for ch in part):
            break
        literal_count += 1

    prefix = "/" + "/".join(parts[:literal_count]) if literal_count else None
    ext = None
    if len(parts) >= 2 and parts[-2] == "**" and parts[-1].startswith("*."):
        candidate = parts[-1][2:]
        if candidate and "." not in candidate and not any(ch in _GLOB_METACHARS for ch in candidate):
            ext = candidate.lower()

    like = None
    if "[" not in full:
        chars: list[str] = []
        i = 0
        while i < len(full):
            ch = full[i]
            if ch == "*":
                if i + 1 < len(full) and full[i + 1] == "*":
                    chars.append("%")
                    i += 2
                    if i < len(full) and full[i] == "/":
                        i += 1
                    continue
                chars.append("%")
            elif ch == "?":
                chars.append("_")
            elif ch in {"%", "_", "\\"}:
                chars.append("\\" + ch)
            else:
                chars.append(ch)
            i += 1
        like = "".join(chars)

    return GlobPushdown(prefix, ext, like)


def main() -> None:
    regexes = [
        "Postgres(FileSystem|Backend)",
        r"^TODO",
        r"\bpostgres\b",
        r"(foo|bar)",
        r"foo.*bar",
        r"(foo)+bar",
    ]
    globs = [
        "/src/**/*.py",
        "**/*.py",
        "/src/[fb]oo.py",
        "**/postgres*.py",
    ]

    print("regex pushdown")
    for pattern in regexes:
        print(pattern, "=>", regex_pushdown(pattern))

    print()
    print("glob pushdown")
    for pattern in globs:
        print(pattern, "=>", glob_pushdown(pattern))


if __name__ == "__main__":
    main()
