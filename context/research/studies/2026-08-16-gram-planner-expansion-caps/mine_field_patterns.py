"""Mine field grep patterns from reference repos (read-only).

Run:  uv run python context/research/studies/2026-08-16-gram-planner-expansion-caps/mine_field_patterns.py > .../field_corpus.json

Three sources, all disclosed in the memo:

1. ripgrep tests/*.rs — ``.arg("...")`` strings, minus flags, flag values,
   created file names (the "ripgrep issue corpus": regression.rs keys tests
   to real issue numbers).
2. ripgrep GUIDE.md / FAQ.md / README.md — patterns in example ``rg '...'``
   invocations.
3. Shell scripts and makefiles of linux, git, postgres, freebsd-src, sqlite,
   zoekt — the first quoted argument of ``grep -E`` / ``egrep`` / ``rg``
   invocations (ERE-family only; BRE ``grep`` without -E is skipped because
   its syntax is not sre-comparable).

Patterns are data (tool inputs), not code. The mined corpus is checked in
beside this script so the memo's numbers stay reproducible if the reference
checkouts drift.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPOS = Path.home() / "Git/Repos"
TESTS = REPOS / "ripgrep/tests"

ARG_RE = re.compile(r'\.arg\((r?)"((?:[^"\\]|\\.)*)"\)')
CREATE_RE = re.compile(r'\.create\w*\(\s*(r?)"((?:[^"\\]|\\.)*)"')

SIMPLE_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "'": "'", "0": "\0"}

# Flags whose next .arg is a value that is NOT a search pattern.
VALUE_FLAGS = {
    "-m", "-A", "-B", "-C", "-g", "-t", "-T", "-j", "-M", "-r", "-f", "-E",
    "--max-count", "--max-depth", "--max-filesize", "--max-columns", "--glob",
    "--iglob", "--type", "--type-not", "--type-add", "--type-clear", "--threads",
    "--replace", "--file", "--encoding", "--path-separator", "--colors",
    "--color", "--sort", "--sortr", "--sort-files", "--pre", "--pre-glob",
    "--context-separator", "--field-context-separator", "--field-match-separator",
    "--regex-size-limit", "--dfa-size-limit", "--ignore-file", "--hostname-bin",
    "--generate", "--engine",
}
# Flags whose next .arg IS a pattern.
PATTERN_FLAGS = {"-e", "--regexp"}


def unescape(raw: str, is_raw: bool) -> str | None:
    if is_raw:
        return raw
    out: list[str] = []
    i = 0
    while i < len(raw):
        ch = raw[i]
        if ch != "\\":
            out.append(ch)
            i += 1
            continue
        if i + 1 >= len(raw):
            return None
        nxt = raw[i + 1]
        if nxt in SIMPLE_ESCAPES:
            out.append(SIMPLE_ESCAPES[nxt])
            i += 2
        elif nxt == "x":
            try:
                out.append(chr(int(raw[i + 2 : i + 4], 16)))
                i += 4
            except ValueError:
                return None
        elif nxt == "u":
            m = re.match(r"u\{([0-9a-fA-F]+)\}", raw[i + 1 :])
            if not m:
                return None
            out.append(chr(int(m.group(1), 16)))
            i += 1 + m.end()
        else:
            return None
    return "".join(out)


def mine_ripgrep_tests() -> list[dict[str, str]]:
    created: set[str] = set()
    out: list[dict[str, str]] = []
    for path in sorted(TESTS.glob("*.rs")):
        text = path.read_text()
        for m in CREATE_RE.finditer(text):
            name = unescape(m.group(2), m.group(1) == "r")
            if name is not None:
                created.add(name)
        prev: str | None = None
        for m in ARG_RE.finditer(text):
            s = unescape(m.group(2), m.group(1) == "r")
            if s is None:
                prev = None
                continue
            take = False
            if prev in PATTERN_FLAGS:
                take = True
            elif prev in VALUE_FLAGS or s.startswith("-"):
                take = False
            elif s and s not in created and not any(
                c == s or c.startswith(s + "/") for c in created
            ):
                take = True
            if take:
                out.append({"pattern": s, "source": f"ripgrep-tests:{path.name}"})
            prev = s
    return out


# rg '...' or rg "..." in doc examples; first quoted arg after flags.
DOC_CMD_RE = re.compile(
    r"""\brg\s+(?:-[\w=-]+\s+)*(?:'((?:[^'\\]|\\.)+)'|"((?:[^"\\]|\\.)+)")"""
)


def mine_ripgrep_docs() -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for name in ("GUIDE.md", "FAQ.md", "README.md"):
        path = REPOS / "ripgrep" / name
        if not path.exists():
            continue
        for m in DOC_CMD_RE.finditer(path.read_text()):
            s = m.group(1) or m.group(2)
            if s and not s.startswith("-"):
                out.append({"pattern": s, "source": f"ripgrep-docs:{name}"})
    return out


# grep -E / egrep / rg in shell scripts: capture flags then first quoted arg.
SH_CMD_RE = re.compile(
    r"""(?:\begrep|\bgrep\s+(?:-\w*E\w*\s+)+|\brg\s+)"""
    r"""(?:-[\w=-]+\s+|--[\w=-]+\s+)*"""
    r"""(?:'([^']+)'|"([^"$`]+)")"""
)

SH_REPOS = ("linux", "git", "postgres", "freebsd-src", "sqlite", "zoekt", "ripgrep")


def mine_shell_scripts() -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for repo in SH_REPOS:
        root = REPOS / repo
        if not root.exists():
            continue
        files: list[Path] = []
        for glob in ("**/*.sh", "**/Makefile", "**/*.mk", "**/*.mak"):
            files.extend(root.glob(glob))
        for path in files:
            try:
                text = path.read_text(errors="ignore")
            except OSError:
                continue
            rel = path.relative_to(REPOS)
            for m in SH_CMD_RE.finditer(text):
                s = m.group(1) or m.group(2)
                if s and not s.startswith("-") and len(s) < 200:
                    out.append({"pattern": s, "source": f"shell:{rel}"})
    return out


def main() -> None:
    corpus: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in mine_ripgrep_tests() + mine_ripgrep_docs() + mine_shell_scripts():
        if item["pattern"] in seen:
            continue
        seen.add(item["pattern"])
        corpus.append(item)
    json.dump(corpus, sys.stdout, indent=1)
    print(f"\ntotal: {len(corpus)}", file=sys.stderr)


if __name__ == "__main__":
    main()
