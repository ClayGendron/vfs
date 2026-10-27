"""Build the command x source matrix and the corpus-by-class totals.

Inputs (all produced by hand-run shell one-liners recorded in the report):
  lists/<source>.txt      one command name per line, per source tree
  ../e2/commands.md       the executed Claude Code corpus (head-word table)

Outputs (written next to this script):
  matrix.md               command x source table, ranked by corpus count then
                          by how many sources ship the command
  classes.md              corpus share summed per class (a-f) and per tier

Run from the vfs repo root:
  uv run python -I context/research/studies/2026-10-15-agent-shell/experiments/s2/matrix.py
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
LISTS = HERE / "lists"
CORPUS = HERE.parent / "e2" / "commands.md"

UNIX = ["busybox", "toybox", "uutils", "sbase", "plan9port", "9front"]
AGENT = ["just-bash", "bashkit-all", "just-bash-py", "lifo", "amla-sandbox"]
SOURCES = UNIX + AGENT
SHORT = {
    "busybox": "bb",
    "toybox": "tb",
    "uutils": "uu",
    "sbase": "sb",
    "plan9port": "p9p",
    "9front": "9f",
    "just-bash": "jb",
    "bashkit-all": "bk",
    "just-bash-py": "jbp",
    "lifo": "lf",
    "amla-sandbox": "am",
}

# Class per command: the catalog's own judgement (see the report). a = vfs
# verb builtin, b = pure text program, c = shell builtin, d = wasm program,
# e = guest interpreter, f = never. Anything not listed is "f?" (unclassified).
CLASS: dict[str, str] = {}
for name in "cat ls grep rg find tree stat mkdir rm rmdir mv cp touch ln readlink realpath du df file".split():
    CLASS[name] = "a"
for name in (
    "head tail sed awk wc cut sort uniq tr nl tac rev fold paste comm join column expand unexpand "
    "diff cmp strings od xxd hexdump base64 base32 md5sum sha1sum sha256sum sha512sum cksum sum "
    "split csplit fmt pr tsort shuf numfmt seq yes tee xargs jq yq xan tar gzip gunzip zcat zip unzip"
).split():
    CLASS[name] = "b"
for name in (
    "cd pwd echo printf export unset env printenv alias unalias true false test [ [[ set shift "
    "source . eval exec exit return break continue local declare typeset readonly read mapfile "
    "readarray getopts trap wait time timeout sleep date which type command hash help history "
    "basename dirname expr let caller dirs pushd popd umask ulimit jobs fg bg kill disown "
    "compgen complete enable builtin shopt fc logout suspend times bind"
).split():
    CLASS[name] = "c"
for name in "sqlite3 python3 python perl node js-exec ruby bash sh".split():
    CLASS[name] = "e"
for name in (
    "ps pkill pgrep curl wget docker git gh ssh scp sftp sudo su mount umount chmod chown chgrp "
    "uptime nproc sysctl pmset open psql pdftotext tokei cargo uv npm npx pip make systemctl top "
    "free hostname whoami id who users uname tty ping dig host ifconfig ip netstat route nc "
    "odbcinst vfs"
).split():
    CLASS[name] = "f"

TIER = {
    "a": "T1 builtin",
    "b": "T2 text program",
    "c": "T1/T2 shell builtin",
    "d": "T3 wasm",
    "e": "T4 guest",
    "f": "never (host)",
}


def load_lists() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for src in SOURCES:
        path = LISTS / f"{src}.txt"
        out[src] = {ln.strip() for ln in path.read_text().splitlines() if ln.strip()}
    return out


def load_corpus() -> tuple[Counter[str], Counter[str], int]:
    """Return (count by full head, count by first word, total segments)."""
    full: Counter[str] = Counter()
    head: Counter[str] = Counter()
    in_table = False
    for line in CORPUS.read_text().splitlines():
        if line.startswith("## Commands"):
            in_table = True
            continue
        if in_table and line.startswith("## "):
            break
        m = re.match(r"\| `([^`]+)` \| (\d+) \| ", line)
        if in_table and m:
            name, n = m.group(1), int(m.group(2))
            full[name] += n
            head[name.split()[0]] += n
    # The table lists segments with count >= 2; the stated total is 12627
    # calls but segments sum higher. Use the table's own sum as the base.
    total = sum(full.values())
    return full, head, total


def main() -> None:
    lists = load_lists()
    full, head, total = load_corpus()
    universe = set().union(*lists.values()) | set(head)
    # Drop corpus noise: bare numbers and stray flags that the miner caught as heads.
    universe = {c for c in universe if not re.fullmatch(r"-.*|\d+|.*\.sh|[A-Z].*", c)}

    rows = []
    for cmd in universe:
        ships = [SHORT[s] for s in SOURCES if cmd in lists[s]]
        n_unix = sum(cmd in lists[s] for s in UNIX)
        n_agent = sum(cmd in lists[s] for s in AGENT)
        rows.append((head.get(cmd, 0), n_agent, n_unix, cmd, ships))
    rows.sort(key=lambda r: (-r[0], -r[1], -r[2], r[3]))

    lines = [
        "# Command x source matrix",
        "",
        f"Sources: {', '.join(f'{SHORT[s]}={s} ({len(lists[s])})' for s in SOURCES)}.",
        f"Corpus: {total} pipeline segments (e2/commands.md, head-word table).",
        "",
        "| command | corpus n | share | agent peers (of 5) | unix (of 6) | class | ships in |",
        "|---|---:|---:|---:|---:|---|---|",
    ]
    for n, n_agent, n_unix, cmd, ships in rows:
        if n == 0 and n_agent == 0:
            continue  # unix-only commands are summarised separately
        share = f"{100 * n / total:.2f}%" if n else ""
        lines.append(
            f"| `{cmd}` | {n or ''} | {share} | {n_agent} | {n_unix} | {CLASS.get(cmd, '?')} | {' '.join(ships)} |"
        )
    (HERE / "matrix.md").write_text("\n".join(lines) + "\n")

    # Intersections.
    agent_all = set.intersection(*(lists[s] for s in ["just-bash", "bashkit-all", "just-bash-py", "lifo"]))
    agent_any = set.union(*(lists[s] for s in AGENT))
    unix_any = set.union(*(lists[s] for s in UNIX))
    unix_only = sorted(unix_any - agent_any)
    posix_core = lists["toybox"] & lists["busybox"] & lists["uutils"] & lists["sbase"]

    # Corpus by class.
    by_class: Counter[str] = Counter()
    unclassified: Counter[str] = Counter()
    for cmd, n in head.items():
        if re.fullmatch(r"-.*|\d+|.*\.sh|[A-Z].*", cmd):
            by_class["noise (miner artefact)"] += n
            continue
        cls = CLASS.get(cmd)
        if cls is None:
            unclassified[cmd] += n
            by_class["unclassified"] += n
        else:
            by_class[cls] += n
    out = [
        "# Corpus share by class and tier",
        "",
        f"Base: {total} pipeline segments.",
        "",
        "| class | tier | segments | share |",
        "|---|---|---:|---:|",
    ]
    for cls in ["a", "b", "c", "d", "e", "f", "unclassified", "noise (miner artefact)"]:
        n = by_class.get(cls, 0)
        out.append(f"| {cls} | {TIER.get(cls, '')} | {n} | {100 * n / total:.1f}% |")
    out += [
        "",
        f"Unclassified heads: {', '.join(f'{c} ({n})' for c, n in unclassified.most_common())}",
        "",
        f"Shipped by all four full agent shells (just-bash, bashkit, just-bash-py, lifo): {len(agent_all)}",
        "",
        ", ".join(sorted(agent_all)),
        "",
        f"Shipped by every classic set (toybox, busybox, uutils, sbase): {len(posix_core)}",
        "",
        ", ".join(sorted(posix_core)),
        "",
        f"Unix-only (in some classic set, in no agent shell): {len(unix_only)}",
        "",
        ", ".join(unix_only),
    ]
    (HERE / "classes.md").write_text("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
