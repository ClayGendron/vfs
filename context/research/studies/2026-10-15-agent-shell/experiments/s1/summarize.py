"""Join runner outputs into admission tables.

    uv run python -I summarize.py corpus.jsonl results/*.jsonl
Prints: per-parser admit counts; per-construct admit counts (e2 regexes);
and every refusal with the parser's message.
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

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

corpus = {r["id"]: r for r in (json.loads(l) for l in Path(sys.argv[1]).read_text().splitlines() if l.strip())}
results: dict[str, dict[int, dict]] = defaultdict(dict)
for p in sys.argv[2:]:
    for l in Path(p).read_text().splitlines():
        if not l.strip():
            continue
        o = json.loads(l)
        results[o["dialect"]][o["id"]] = o

dialects = sorted(results)
n = len(corpus)
print(f"## Admission per parser ({n} commands)\n")
print("| parser | admitted | refused | % admitted |")
print("|---|---:|---:|---:|")
for d in dialects:
    ok = sum(1 for i in corpus if results[d].get(i, {}).get("ok"))
    print(f"| {d} | {ok} | {n - ok} | {100 * ok / n:.0f}% |")

print("\n## Admission per construct (commands containing the construct)\n")
print("| construct | n | " + " | ".join(dialects) + " |")
print("|---|---:|" + "---:|" * len(dialects))
for name, rx in CONSTRUCTS.items():
    ids = [i for i, r in corpus.items() if rx.search(r["cmd"])]
    if not ids:
        continue
    cells = [str(sum(1 for i in ids if results[d].get(i, {}).get("ok"))) for d in dialects]
    print(f"| {name} | {len(ids)} | " + " | ".join(cells) + " |")

print("\n## Refusals\n")
for d in dialects:
    bad = [(i, results[d][i]) for i in sorted(corpus) if i in results[d] and not results[d][i].get("ok")]
    print(f"### {d}: {len(bad)} refused")
    for i, o in bad:
        head = corpus[i]["cmd"].split("\n")[0][:70]
        print(f"- {i}: `{head}` -> {o.get('error', '')[:160]}")
    print()
