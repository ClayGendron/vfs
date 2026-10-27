"""Share of corpus commands containing each shell construct.

Uses the same regexes as experiments/e2/mine_commands.py (the Claude Code
transcript miner) so the corpus can be compared with the measured traffic.

    uv run python -I context/.../experiments/s1/corpus_stats.py corpus.jsonl
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Copied from experiments/e2/mine_commands.py so both reports agree.
CONSTRUCTS = {
    "pipe |": re.compile(r"(?<!\|)\|(?!\|)"),
    "and &&": re.compile(r"&&"),
    "subshell ( )": re.compile(r"(?<![$<>])\((?!\))"),
    "glob *": re.compile(r"(?<![\w\"'])\*"),
    "stderr 2>&1": re.compile(r"2>&1"),
    "redirect >": re.compile(r"(?<![0-9&])>(?!>)"),
    "heredoc <<": re.compile(r"<<"),
    "var $X": re.compile(r"\$[A-Za-z_{]"),
    "stdin <": re.compile(r"(?<!<)<(?![<(])"),
    "for loop": re.compile(r"\bfor\b.*\bdo\b", re.S),
    "backticks": re.compile(r"`"),
    "subst $(...)": re.compile(r"\$\("),
    "append >>": re.compile(r">>"),
    "or ||": re.compile(r"\|\|"),
    "function": re.compile(r"\bfunction\b|\w+\(\)\s*\{"),
    "if": re.compile(r"\bif\b.*\bthen\b", re.S),
    "brace {a,b}": re.compile(r"\{[^}\s]*,[^}\s]*\}"),
    "test [[": re.compile(r"\[\["),
    "arith $((": re.compile(r"\$\(\("),
    "case": re.compile(r"\bcase\b.*\bin\b", re.S),
    "while loop": re.compile(r"\bwhile\b.*\bdo\b", re.S),
    "background &": re.compile(r"&\s*$", re.M),
    "process subst <(": re.compile(r"<\("),
}
# Measured shares from experiments/e2/commands.md (12,627 Bash tool calls).
E2 = {
    "pipe |": 74.3, "and &&": 44.5, "subshell ( )": 27.9, "glob *": 25.2,
    "stderr 2>&1": 16.4, "redirect >": 14.2, "heredoc <<": 12.1, "var $X": 12.1,
    "stdin <": 4.8, "for loop": 4.6, "backticks": 4.4, "subst $(...)": 3.7,
    "append >>": 1.7, "or ||": 1.4, "function": 1.2, "if": 0.9, "brace {a,b}": 0.9,
    "test [[": 0.8, "arith $((": 0.6, "case": 0.5, "while loop": 0.4,
    "background &": 0.2, "process subst <(": 0.1,
}


def main(path: str) -> None:
    rows = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    n = len(rows)
    print(f"| construct | corpus ({n}) | corpus % | e2 % |")
    print("|---|---:|---:|---:|")
    for name, rx in CONSTRUCTS.items():
        hits = sum(1 for r in rows if rx.search(r["cmd"]))
        print(f"| {name} | {hits} | {100 * hits / n:.1f} | {E2[name]} |")
    segs = [max(1, len(re.split(r"\|\||&&|(?<!\|)\|(?!\|)|;|\n", r["cmd"]))) for r in rows]
    segs.sort()
    print(f"\nsegments per call: median {segs[n // 2]}, max {segs[-1]}, 10+ {sum(s >= 10 for s in segs)}")


if __name__ == "__main__":
    main(sys.argv[1])
