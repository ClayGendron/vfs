"""Mine Claude Code transcripts for the commands an agent actually issues.

Reads every ``~/.claude/projects/**/*.jsonl`` transcript, takes the ``command``
of each Bash tool call, and counts ONLY command names, their flags, and shell
constructs. Arguments, paths, and any other text are never written out, so
the report is a frequency table and nothing else.

Heredoc bodies and quoted strings (``python -c '...'``) are never split into
segments: the splitter is quote-aware and replaces each heredoc body with a
marker before splitting on unquoted ``|``, ``||``, ``&&``, ``;`` and newlines.

    uv run python context/research/studies/2026-10-15-agent-shell/experiments/e2/mine_commands.py

Writes ``commands.md`` beside this script.
"""

from __future__ import annotations

import json
import re
import shlex
from collections import Counter
from pathlib import Path

ROOT = Path.home() / ".claude" / "projects"
OUT = Path(__file__).with_name("commands.md")

HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?^[ \t]*\2[ \t]*$", re.S | re.M)
CONSTRUCTS = {
    "pipe |": re.compile(r"(?<!\|)\|(?!\|)"),
    "and &&": re.compile(r"&&"),
    "or ||": re.compile(r"\|\|"),
    "redirect >": re.compile(r"(?<![0-9&])>(?!>)"),
    "append >>": re.compile(r">>"),
    "stderr 2>&1": re.compile(r"2>&1"),
    "stdin <": re.compile(r"(?<!<)<(?![<(])"),
    "heredoc <<": re.compile(r"<<"),
    "subst $(...)": re.compile(r"\$\("),
    "backticks": re.compile(r"`"),
    "process subst <(": re.compile(r"<\("),
    "for loop": re.compile(r"\bfor\b.*\bdo\b", re.S),
    "while loop": re.compile(r"\bwhile\b.*\bdo\b", re.S),
    "if": re.compile(r"\bif\b.*\bthen\b", re.S),
    "case": re.compile(r"\bcase\b.*\bin\b", re.S),
    "function": re.compile(r"\bfunction\b|\w+\(\)\s*\{"),
    "subshell ( )": re.compile(r"(?<![$<>])\((?!\))"),
    "background &": re.compile(r"&\s*$", re.M),
    "glob *": re.compile(r"(?<![\w\"'])\*"),
    "brace {a,b}": re.compile(r"\{[^}\s]*,[^}\s]*\}"),
    "var $X": re.compile(r"\$[A-Za-z_{]"),
    "arith $((": re.compile(r"\$\(\("),
    "test [[": re.compile(r"\[\["),
}
WRAPPERS = {"sudo", "env", "time", "nohup", "xargs", "command", "builtin", "exec", "timeout", "do", "then", "else", "!"}
KEYWORDS = {"for", "while", "until", "if", "fi", "done", "esac", "case", "in", "function", "elif", "select"}
BRACKETS = {"{", "}", "(", ")"}
SUBCOMMAND_HEADS = {"git", "gh", "uv", "cargo", "npm", "npx", "pnpm", "docker", "pip", "brew", "kubectl", "go", "rustup"}


def commands_from(path: Path):
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            message = record.get("message") or {}
            content = message.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == "Bash":
                    command = (block.get("input") or {}).get("command")
                    if isinstance(command, str):
                        yield command


def split_segments(command: str) -> list[str]:
    """Split on unquoted ``|``, ``||``, ``&&``, ``;``, newline; keep quoted text and $( ) whole."""
    text = HEREDOC.sub("<<HEREDOC_BODY", command)
    segments: list[str] = []
    buf: list[str] = []
    quote: str | None = None
    depth = 0
    i = 0
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if quote:
            buf.append(ch)
            if ch == "\\" and quote == '"':
                buf.append(nxt)
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch == "\\":
            buf.append(ch + nxt)
            i += 2
            continue
        elif ch in ("'", '"'):
            quote = ch
            buf.append(ch)
        elif ch == "$" and nxt == "(":
            depth += 1
            buf.append("$(")
            i += 2
            continue
        elif ch == ")" and depth:
            depth -= 1
            buf.append(ch)
        elif depth == 0 and (ch in ";\n" or ch == "|" or (ch == "&" and nxt == "&")):
            segments.append("".join(buf))
            buf = []
            if (ch == "|" and nxt == "|") or (ch == "&" and nxt == "&"):
                i += 2
                continue
        else:
            buf.append(ch)
        i += 1
    segments.append("".join(buf))
    return [s.strip() for s in segments if s.strip()]


def head_and_flags(segment: str):
    if segment.startswith("#"):
        return None, []
    try:
        tokens = shlex.split(segment, posix=True)
    except ValueError:
        tokens = segment.split()
    tokens = [t for t in tokens if t and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", t)]
    while tokens and (tokens[0] in WRAPPERS or tokens[0] in BRACKETS):
        tokens = tokens[1:]
    if not tokens or tokens[0] in KEYWORDS:
        return None, []
    head = tokens[0].rsplit("/", 1)[-1]
    if not re.fullmatch(r"[A-Za-z0-9_.+-]+", head):
        return None, []
    sub = tokens[1] if head in SUBCOMMAND_HEADS and len(tokens) > 1 and not tokens[1].startswith("-") else None
    name = f"{head} {sub}" if sub else head
    flags = [t.split("=", 1)[0] for t in tokens[1:] if t.startswith("-") and len(t) > 1]
    return name, flags


def main() -> None:
    calls = 0
    files = 0
    names: Counter[str] = Counter()
    flags: Counter[str] = Counter()
    constructs: Counter[str] = Counter()
    segments_per_call: Counter[int] = Counter()
    for path in ROOT.rglob("*.jsonl"):
        files += 1
        for command in commands_from(path):
            calls += 1
            for label, pattern in CONSTRUCTS.items():
                if pattern.search(command):
                    constructs[label] += 1
            parts = split_segments(command)
            segments_per_call[min(len(parts), 10)] += 1
            for part in parts:
                name, part_flags = head_and_flags(part)
                if name is None:
                    continue
                names[name] += 1
                for flag in part_flags:
                    flags[f"{name} {flag}"] += 1
    lines = [
        "# Agent command frequency (Claude Code transcripts on this machine)",
        "",
        f"Transcripts: {files}. Bash tool calls: {calls}. Distinct command names: {len(names)}. "
        "Only names, flags and constructs are recorded.",
        "",
        "## Commands (pipeline segments, by head word)",
        "",
        "| command | count | share |",
        "|---|---:|---:|",
    ]
    total = sum(names.values()) or 1
    lines += [f"| `{n}` | {c} | {100 * c / total:.1f}% |" for n, c in names.most_common(150)]
    lines += ["", "## Shell constructs (calls containing at least one)", "", "| construct | calls | share |", "|---|---:|---:|"]
    lines += [f"| {k} | {v} | {100 * v / (calls or 1):.1f}% |" for k, v in constructs.most_common()]
    lines += ["", "## Segments per call", "", "| segments | calls |", "|---|---:|"]
    lines += [f"| {k}{'+' if k == 10 else ''} | {v} |" for k, v in sorted(segments_per_call.items())]
    lines += ["", "## Flags (top 200, command + flag)", "", "| flag | count |", "|---|---:|"]
    lines += [f"| `{k}` | {v} |" for k, v in flags.most_common(200)]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({files} transcripts, {calls} calls, {len(names)} distinct commands)")


if __name__ == "__main__":
    main()
