"""Skeletons of the awk programs and sed scripts the census left as "other".

Privacy as E2: a skeleton keeps only the language's own tokens. String
literals become "S", regex bodies become /R/, numbers become N, and every
identifier outside the language's keyword set becomes v. No argument text
leaves this file.

    uv run python context/research/studies/2026-10-15-agent-shell/experiments/r168/skeletons.py

Writes ``skeletons.out`` beside this script.
"""

from __future__ import annotations

import re
import shlex
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "e2"))
from mine_commands import HEREDOC, ROOT, commands_from, split_segments  # noqa: E402

OUT = Path(__file__).with_name("skeletons.out")
FLOOR = 3  # a rarer skeleton may carry a fragment the regex masking missed; it is not written
AWK_WORDS = {"BEGIN", "END", "print", "printf", "if", "else", "for", "while", "in", "next", "exit", "NR", "NF", "FNR",
             "FS", "OFS", "RS", "ORS", "FILENAME", "length", "substr", "split", "gsub", "sub", "match", "sprintf",
             "tolower", "toupper", "index", "int", "getline", "system", "delete", "RSTART", "RLENGTH"}


def _shell_parts(text: str) -> str:
    """Replace shell expansions inside a script with a fixed token before anything else."""
    out, depth, i = [], 0, 0
    while i < len(text):
        if text.startswith("$((", i) or text.startswith("$(", i):
            depth, j = 0, i + 1
            while j < len(text):
                depth += text[j] == "("
                depth -= text[j] == ")"
                j += 1
                if depth == 0:
                    break
            out.append("$(C)")
            i = j
            continue
        out.append(text[i])
        i += 1
    s = "".join(out)
    s = re.sub(r"\$\{[^}]*\}", "$v", s)
    return re.sub(r"\$(?![pdq](\W|$))[A-Za-z_]\w*", "$v", s)


def awk_skeleton(prog: str) -> str:
    s = re.sub(r'"(\\.|[^"\\])*"', '"S"', prog)
    s = re.sub(r"(^|[\s(!~,{;&|])/(\\.|[^/\\\n])+/", r"\1/R/", s)
    s = re.sub(r"\$\d+", "$N", s)
    s = re.sub(r"\b\d+(\.\d+)?\b", "N", s)
    s = re.sub(r"\b[A-Za-z_]\w*\b", lambda m: m.group(0) if m.group(0) in AWK_WORDS or m.group(0) == "N" or m.group(0) == "S" or m.group(0) == "R" else "v", s)
    return re.sub(r"\s+", " ", s).strip()


def sed_skeleton(script: str) -> str:
    s = _shell_parts(script)
    s = re.sub(r"s(.)(\\.|(?!\1).)*\1(\\.|(?!\1).)*\1([gIip0-9]*)", r"s/R/S/\4", s, flags=re.S)
    s = re.sub(r"/(\\.|[^/\\\n])+/", "/R/", s)
    s = re.sub(r"\d+", "N", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def main() -> None:
    awk: Counter[str] = Counter()
    sed: Counter[str] = Counter()
    for path in ROOT.rglob("*.jsonl"):
        for command in commands_from(path):
            for segment in split_segments(command):
                try:
                    tokens = shlex.split(HEREDOC.sub("", segment), posix=True)
                except ValueError:
                    continue
                while tokens and re.fullmatch(r"[A-Za-z_]\w*=.*", tokens[0]):
                    tokens = tokens[1:]
                if not tokens:
                    continue
                head, args = tokens[0].rsplit("/", 1)[-1], tokens[1:]
                if head == "awk":
                    rest, skip = [], False
                    for i, tok in enumerate(args):
                        if skip:
                            skip = False
                            continue
                        if tok in {"-F", "-v", "-f"}:
                            skip = True
                            continue
                        if tok.startswith("-") and len(tok) > 1:
                            continue
                        rest.append(tok)
                    if rest:
                        awk[awk_skeleton(rest[0])] += 1
                elif head == "sed":
                    scripts, operands, skip = [], [], False
                    for i, tok in enumerate(args):
                        if skip:
                            skip = False
                            continue
                        if tok == "-e" and i + 1 < len(args):
                            scripts.append(args[i + 1])
                            skip = True
                            continue
                        if tok.startswith("-") and len(tok) > 1:
                            continue
                        operands.append(tok)
                    if not scripts and operands:
                        scripts = [operands[0]]
                    if "-i" in args and args.index("-i") + 1 < len(args) and args[args.index("-i") + 1] == "":
                        sed["(-i followed by an empty-string argument: the BSD in-place form)"] += 1
                    flagset = "".join(sorted({c for t in args if t.startswith("-") and not t.startswith("--") for c in t[1:] if c.isalpha()}))
                    for sc in scripts:
                        sed[f"[-{flagset}] {sed_skeleton(sc)}"] += 1
    lines = ["# awk skeletons (count, skeleton)"]
    lines += [f"{v}\t{k}" for k, v in awk.most_common() if v >= FLOOR]
    lines += [f"({sum(1 for v in awk.values() if v < FLOOR)} skeletons seen fewer than {FLOOR} times omitted)"]
    lines += ["", f"(distinct awk skeletons: {len(awk)}; programs: {sum(awk.values())})"]
    lines += ["", "# sed skeletons (count, [flags] skeleton)"]
    lines += [f"{v}\t{k}" for k, v in sed.most_common() if v >= FLOOR]
    lines += [f"({sum(1 for v in sed.values() if v < FLOOR)} skeletons seen fewer than {FLOOR} times omitted)"]
    lines += ["", f"(distinct sed skeletons: {len(sed)}; scripts: {sum(sed.values())})"]
    OUT.write_text("\n".join(lines) + "\n")
    print(OUT)


if __name__ == "__main__":
    main()
