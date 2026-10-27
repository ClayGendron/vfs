"""Which calls does spec 168 unlock? Head words per call, classed by the catalog's tiers.

Privacy as E2: only head words are read; only counts are written.

    uv run python context/research/studies/2026-10-15-agent-shell/experiments/r168/call_tiers.py

Writes ``call_tiers.out`` beside this script. The parse rate is ignored here:
a call counts by its head words only, so these are ceilings, not run rates.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "e2"))
from mine_commands import ROOT, commands_from, head_and_flags, split_segments  # noqa: E402

OUT = Path(__file__).with_name("call_tiers.out")
# Clay, 2026-10-15: awk, jq and the zero-use names arrive as wasm programs (spec 169), not 168 kernels.
SPEC_168 = {"sort", "uniq", "tr", "tee", "diff", "cmp"}
T1 = {"grep", "rg", "cat", "head", "tail", "sed", "ls", "cd", "pwd", "echo", "printf", "wc", "mkdir", "rm", "cp", "mv",
      "touch", "stat", "file", "tree", "find", "test", "[", "true", "false", ":", "export", "unset", "env", "printenv",
      "set", "which", "type", "command", "help", "sleep", "timeout", "time", "date", "basename", "dirname", "seq",
      "whoami", "hostname", "uname", "history", "cut", "nl", "exit", "source", ".", "break", "continue", "shift", "wait",
      "local", "read", "return", "du", "ln", "readlink"}
T2_MEASURED = {"sort", "uniq", "tr", "awk", "tee", "xargs", "diff", "paste", "fold", "base64", "comm", "cmp", "strings",
               "column", "join", "tac", "rev", "jq", "md5sum", "sha256sum", "shasum", "split", "od", "xxd", "hexdump", "yes"}
GUEST = {"python3", "python", "uv run", "perl", "bash", "sh", "node"}


def main() -> None:
    tally: Counter[str] = Counter()
    t2_heads: Counter[str] = Counter()
    for path in ROOT.rglob("*.jsonl"):
        for command in commands_from(path):
            heads = set()
            for segment in split_segments(command):
                name, _ = head_and_flags(segment)
                if name:
                    heads.add(name)
            if not heads:
                tally["no head"] += 1
                continue
            rest = heads - T1
            if not rest:
                tally["T1 only"] += 1
            elif rest <= T2_MEASURED:
                tally["needs T2 (168) and nothing else"] += 1
                t2_heads.update(rest)
                if rest <= SPEC_168:
                    tally["  of which the amended 168 kernels alone serve"] += 1
            elif rest <= T2_MEASURED | GUEST:
                tally["needs T2 or a guest"] += 1
            else:
                tally["needs something else (never class, guest, artefact)"] += 1
    total = sum(tally.values())
    lines = [f"calls\t{total}"]
    lines += [f"{k}\t{v}\t{v / total:.1%}" for k, v in tally.most_common()]
    lines += ["", "T2 heads in the calls 168 alone unlocks"]
    lines += [f"{k}\t{v}" for k, v in t2_heads.most_common()]
    OUT.write_text("\n".join(lines) + "\n")
    print(OUT)


if __name__ == "__main__":
    main()
