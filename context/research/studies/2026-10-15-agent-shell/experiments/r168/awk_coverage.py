"""How much of the measured awk would two candidate subsets serve? Counts only.

Reuses the skeletons of ``skeletons.py`` (no program text is written).
"Spec list" is spec 168's awk row read generously; "measured subset" is
the subset this review proposes (no arrays beyond ``seen[$0]++``, no
user functions, no getline, no loops, no string functions beyond
sub/gsub/length).

    uv run python context/research/studies/2026-10-15-agent-shell/experiments/r168/awk_coverage.py
"""

from __future__ import annotations

import re
import shlex
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "e2"))
from mine_commands import HEREDOC, ROOT, commands_from, split_segments  # noqa: E402
from skeletons import awk_skeleton  # noqa: E402

OUT = Path(__file__).with_name("awk_coverage.out")
SPEC_LIST = [
    r"\{ ?print \$N ?\}", r"\{ ?print \$NF ?\}", r"NR ?== ?N", r"/R/", r"/R/ ?\{ ?print ?\}", r"/R/ ?\{ ?print \$N ?\}",
    r"\{ ?v ?\+= ?\$N ?;? ?\} ?END ?\{ ?print v ?\}", r"!v\[\$N\]\+\+", r"/R/,/R/", r"NR ?>=? ?N ?&& ?NR ?<=? ?N",
]
OUTSIDE_SUBSET = re.compile(r"v\[|\bsplit\(|\bgetline\b|\bfor ?\(|\bwhile ?\(|\bsubstr\(|\bindex\(|\bint\(|\bsprintf\b|"
                            r"\bmatch\(|\bsystem\(|\bfunction\b|\btolower\b|\btoupper\b|\bdelete\b")


def main() -> None:
    skeletons: Counter[str] = Counter()
    for path in ROOT.rglob("*.jsonl"):
        for command in commands_from(path):
            for segment in split_segments(command):
                try:
                    tokens = shlex.split(HEREDOC.sub("", segment), posix=True)
                except ValueError:
                    continue
                if not tokens or tokens[0].rsplit("/", 1)[-1] != "awk":
                    continue
                rest, skip = [], False
                for tok in tokens[1:]:
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
                    skeletons[awk_skeleton(rest[0])] += 1
    total = sum(skeletons.values())
    spec = sum(n for s, n in skeletons.items() if any(re.fullmatch(p, s) for p in SPEC_LIST))
    seen_idiom = sum(n for s, n in skeletons.items() if re.search(r"!v\[\$N\]\+\+", s))
    subset = sum(n for s, n in skeletons.items() if not OUTSIDE_SUBSET.search(s) or re.fullmatch(r"!v\[\$N\]\+\+", s))
    lines = [
        f"awk programs\t{total}",
        f"served by spec 168's listed forms (exact shapes)\t{spec}\t{spec / total:.0%}",
        f"served by the proposed measured subset\t{subset}\t{subset / total:.0%}",
        f"programs using the !seen[$0]++ idiom\t{seen_idiom}",
    ]
    OUT.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
