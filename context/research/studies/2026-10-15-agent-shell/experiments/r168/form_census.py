"""Census of the tier-2 forms spec 168 names, from the same transcripts E2 mined.

Privacy as E2: only command names, flag tokens, and *labels* for script
shapes leave this file. A sed script or awk program is classified by
regex into a shape label (``ranged print``, ``print field``); the text
itself is never written.

    uv run python context/research/studies/2026-10-15-agent-shell/experiments/r168/form_census.py

Writes ``form_census.out`` beside this script.
"""

from __future__ import annotations

import re
import shlex
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "e2"))
from mine_commands import HEREDOC, ROOT, commands_from, split_segments  # noqa: E402

OUT = Path(__file__).with_name("form_census.out")
PROGRAMS = {"cut", "sort", "uniq", "tr", "awk", "sed", "find", "xargs", "jq", "tee", "nl", "diff", "wc", "tac", "rev",
            "paste", "column", "fold", "base64", "comm", "join", "sha256sum", "md5sum", "shasum", "split", "yes", "od",
            "xxd", "strings", "hexdump", "cmp"}
VALUE_FLAGS = {
    "sed": {"-e", "-f"},
    "awk": {"-F", "-v", "-f"},
    "xargs": {"-n", "-I", "-d", "-P", "-L", "-s", "-E"},
    "cut": {"-d", "-f", "-c", "-b"},
    "sort": {"-k", "-t", "-o", "-S"},
    "jq": {"--arg", "--argjson"},
}

SED_SHAPES = [
    ("A,Bp", r"\d+,\d+p"),
    ("Ap", r"\d+p"),
    ("$p", r"\$p"),
    ("A,$p", r"\d+,\$p"),
    ("/re/p", r"/[^/]*/p"),
    ("/re/,/re/p", r"/[^/]*/,/[^/]*/p"),
    ("A,/re/p", r"\d+,/[^/]*/p"),
    ("/re/,$p", r"/[^/]*/,\$p"),
    ("Nq", r"\d+q"),
    ("/re/q", r"/[^/]*/q"),
    ("/re/d", r"/[^/]*/d"),
    ("Nd", r"\d+d"),
    ("A,Bd", r"\d+,\d+d"),
    ("$d", r"\$d"),
    ("s///", r"s(.).*\1.*\1[gIip0-9]*"),
    ("/re/s///", r"/[^/]*/s(.).*\1.*\1[gIip0-9]*"),
    ("A,Bs///", r"\d+,\d+s(.).*\1.*\1[gIip0-9]*"),
    ("y///", r"y(.).*\1.*\1"),
    ("a/i/c text", r"(\d+|\$|/[^/]*/)?[aic]\\?.*"),
    ("A,B{p;...}", r"\d+,\d+\{.*\}"),
    ("=", r"(/[^/]*/)?="),
]
AWK_SHAPES = [
    ("{print $N}", r"\{\s*print\s+\$\d+\s*;?\s*\}"),
    ("{print $NF}", r"\{\s*print\s+\$NF\s*;?\s*\}"),
    ("{print $N,$M...}", r"\{\s*print\s+\$(\d+|NF)(\s*(,|\"[^\"]*\")\s*\$(\d+|NF))+\s*;?\s*\}"),
    ("{print $0}", r"\{\s*print(\s+\$0)?\s*\}"),
    ("NR==N", r"NR\s*==\s*\d+"),
    ("NR range", r"NR\s*>=?\s*\d+\s*&&\s*NR\s*<=?\s*\d+"),
    ("/re/", r"/[^/]*/"),
    ("/re/ {print ...}", r"/[^/]*/\s*\{[^{}]*\}"),
    ("sum END", r"\{\s*\w+\s*\+=\s*\$\d+\s*;?\s*\}\s*END\s*\{[^{}]*\}"),
    ("!seen[$0]++", r"!\s*\w+\[\$\d+\]\+\+"),
    ("{print NR...$0}", r"\{\s*print\s+NR.*\$0\s*\}"),
    ("length filter", r"length(\(\$0\))?\s*[<>]=?\s*\d+"),
    ("cond {print ...}", r"\$\d+\s*[=!<>~]+.*\{[^{}]*\}"),
]
AWK_FEATURES = {
    "BEGIN": r"\bBEGIN\b", "END": r"\bEND\b", "printf": r"\bprintf\b", "gsub/sub": r"\b(g?sub)\s*\(",
    "split": r"\bsplit\s*\(", "substr": r"\bsubstr\s*\(", "length": r"\blength\b", "tolower/upper": r"\bto(lower|upper)\b",
    "if": r"\bif\s*\(", "for": r"\bfor\s*\(", "while": r"\bwhile\s*\(", "array[]": r"\w+\[[^\]]+\]",
    "NR": r"\bNR\b", "NF": r"\bNF\b", "FS/OFS": r"\b(FS|OFS|RS|ORS)\b", "~ match": r"!?~", "next": r"\bnext\b",
    "match()": r"\bmatch\s*\(", "sprintf": r"\bsprintf\b", "getline": r"\bgetline\b", "system()": r"\bsystem\s*\(",
}


def classify(script: str, shapes: list[tuple[str, str]]) -> str:
    stripped = script.strip()
    for label, pattern in shapes:
        if re.fullmatch(pattern, stripped, re.S):
            return label
    if ";" in stripped or "\n" in stripped:
        return "multi-command (other)"
    return "other"


def main() -> None:
    flags: dict[str, Counter[str]] = defaultdict(Counter)
    letters: dict[str, Counter[str]] = defaultdict(Counter)
    segments: Counter[str] = Counter()
    sed_shapes: Counter[str] = Counter()
    sed_with_n: Counter[str] = Counter()
    awk_shapes: Counter[str] = Counter()
    awk_features: Counter[str] = Counter()
    awk_programs = 0
    xargs_heads: Counter[str] = Counter()
    find_exec_heads: Counter[str] = Counter()
    find_exec_term: Counter[str] = Counter()
    tr_shapes: Counter[str] = Counter()
    for path in ROOT.rglob("*.jsonl"):
        for command in commands_from(path):
            for segment in split_segments(command):
                try:
                    tokens = shlex.split(HEREDOC.sub("", segment), posix=True)
                except ValueError:
                    continue
                while tokens and re.fullmatch(r"[A-Za-z_]\w*=.*", tokens[0]):
                    tokens = tokens[1:]
                while tokens and tokens[0] in {"time", "command", "builtin", "!", "do", "then", "else", "{", "("}:
                    tokens = tokens[1:]
                if not tokens:
                    continue
                head = tokens[0].rsplit("/", 1)[-1]
                if head not in PROGRAMS:
                    continue
                segments[head] += 1
                args = tokens[1:]
                values = VALUE_FLAGS.get(head, set())
                operands: list[str] = []
                scripts: list[str] = []
                skip = False
                for i, tok in enumerate(args):
                    if skip:
                        skip = False
                        continue
                    if head == "xargs" and not tok.startswith("-"):
                        xargs_heads[tok.rsplit("/", 1)[-1]] += 1
                        break
                    if tok.startswith("-") and len(tok) > 1:
                        name = tok.split("=", 1)[0]
                        base = re.sub(r"\d.*$", "", name) if not name.startswith("--") else name
                        flags[head][base or name] += 1
                        if not name.startswith("--") and head != "find":
                            for ch in name[1:]:
                                if ch.isdigit() or ch in ",.:":
                                    break
                                letters[head][f"-{ch}"] += 1
                        if base in values and base == name and i + 1 < len(args):
                            if head == "sed" and base == "-e":
                                scripts.append(args[i + 1])
                            skip = True
                        if head == "find" and name in {"-exec", "-execdir", "-ok"}:
                            rest = args[i + 1 :]
                            if rest:
                                find_exec_heads[rest[0].rsplit("/", 1)[-1]] += 1
                            find_exec_term["+" if "+" in rest else ";" if ";" in rest else "?"] += 1
                    else:
                        operands.append(tok)
                if head == "sed":
                    if not scripts and operands:
                        scripts = [operands[0]]
                    has_n = any(t == "-n" or (t.startswith("-") and not t.startswith("--") and "n" in t[1:]) for t in args)
                    for s in scripts:
                        label = classify(s, SED_SHAPES)
                        sed_shapes[label] += 1
                        if has_n:
                            sed_with_n[label] += 1
                elif head == "awk" and operands:
                    awk_programs += 1
                    prog = operands[0]
                    awk_shapes[classify(prog, AWK_SHAPES)] += 1
                    for feat, pat in AWK_FEATURES.items():
                        if re.search(pat, prog):
                            awk_features[feat] += 1
                elif head == "tr":
                    sets = operands[:2]
                    kind = []
                    if any("[:" in s for s in sets):
                        kind.append("class")
                    if any(re.search(r"\w-\w", s) for s in sets):
                        kind.append("range")
                    if any("\\" in s for s in sets):
                        kind.append("escape")
                    tr_shapes["+".join(kind) or "literal"] += 1
    lines: list[str] = ["# Form census for spec 168 (labels and flags only)", ""]
    lines.append("## Segments per program")
    for name, count in segments.most_common():
        lines.append(f"{name}\t{count}")
    for name in ("cut", "sort", "uniq", "tr", "awk", "sed", "find", "xargs", "jq", "tee", "nl", "diff", "wc"):
        lines.append("")
        lines.append(f"## {name}: flag tokens (digits stripped), all")
        for flag, count in flags[name].most_common():
            lines.append(f"{flag}\t{count}")
        if name != "find":
            lines.append(f"## {name}: short-flag letters (bundles exploded)")
            for flag, count in letters[name].most_common():
                lines.append(f"{flag}\t{count}")
    lines += ["", "## sed script shapes (all scripts; -e counted per script)"]
    lines += [f"{k}\t{v}\t(with -n: {sed_with_n[k]})" for k, v in sed_shapes.most_common()]
    lines += ["", f"## awk program shapes ({awk_programs} programs)"]
    lines += [f"{k}\t{v}" for k, v in awk_shapes.most_common()]
    lines += ["", "## awk features used (a program may use several)"]
    lines += [f"{k}\t{v}" for k, v in awk_features.most_common()]
    lines += ["", "## xargs: the command it runs"]
    lines += [f"{k}\t{v}" for k, v in xargs_heads.most_common()]
    lines += ["", "## find -exec: the command it runs, and the terminator"]
    lines += [f"{k}\t{v}" for k, v in find_exec_heads.most_common()]
    lines += [f"terminator {k}\t{v}" for k, v in find_exec_term.most_common()]
    lines += ["", "## tr set shapes"]
    lines += [f"{k}\t{v}" for k, v in tr_shapes.most_common()]
    OUT.write_text("\n".join(lines) + "\n")
    print(OUT)


if __name__ == "__main__":
    main()
