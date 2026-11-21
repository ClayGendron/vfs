"""Render the benchmark JSON as Markdown tables.

    uv run python agents/2026-11-21-linux-grep-benchmark/report.py results.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

TOOLS = ("generic", "rg", "vfs")


def main() -> None:
    report = json.loads(Path(sys.argv[1]).read_text())
    out: list[str] = [f"vfs first call on a fresh process (opens the database): {report['vfs_first_call_ms']:.1f} ms", ""]

    out += ["## Session replay: the 39 stages the session ran", ""]
    out += ["| # | stage | lines | generic ms | rg ms | vfs ms | vfs first ms | agree |", "|---|---|---|---|---|---|---|---|"]
    totals = dict.fromkeys(TOOLS, 0.0)
    by_kind: dict[str, dict[str, float]] = {}
    for stage in report["stages"]:
        for tool in TOOLS:
            totals[tool] += stage[tool]["median_ms"]
            by_kind.setdefault(stage["kind"], dict.fromkeys(TOOLS, 0.0))[tool] += stage[tool]["median_ms"]
        agree = "yes" if all(stage["agree"].values()) else f"NO {stage['agree']}"
        source = stage["source"].replace("|", "\\|")
        source = source if len(source) <= 70 else source[:67] + "..."
        out.append(
            f"| {stage['command']} | `{source}` | {stage['lines']['generic']} | {stage['generic']['median_ms']:.1f} "
            f"| {stage['rg']['median_ms']:.1f} | {stage['vfs']['median_ms']:.1f} | {stage['vfs_first_ms']:.1f} | {agree} |"
        )
    out += ["", "| stage kind | count | generic ms | rg ms | vfs ms |", "|---|---|---|---|---|"]
    for kind, sums in by_kind.items():
        count = sum(1 for stage in report["stages"] if stage["kind"] == kind)
        out.append(f"| {kind} | {count} | {sums['generic']:.1f} | {sums['rg']:.1f} | {sums['vfs']:.1f} |")
    out.append(
        f"| **all** | {len(report['stages'])} | {totals['generic']:.1f} | {totals['rg']:.1f} | {totals['vfs']:.1f} |"
    )

    if report["repo_grep"]:
        out += ["", "## Repo-wide grep: each session pattern over the whole tree", ""]
        out += [
            "| pattern | hits gen/rg/vfs | files | generic ms | rg ms | vfs ms | vfs first ms | vfs notes |",
            "|---|---|---|---|---|---|---|---|",
        ]
        totals = dict.fromkeys(TOOLS, 0.0)
        for row in report["repo_grep"]:
            for tool in TOOLS:
                totals[tool] += row[tool]["median_ms"]
            pattern = row["pattern"].replace("|", "\\|")
            pattern = pattern if len(pattern) <= 60 else pattern[:57] + "..."
            hits = "/".join(str(row["hits"][tool]) for tool in TOOLS)
            notes = "; ".join(note[:80] for note in row["vfs"]["notes"]) or ""
            out.append(
                f"| `{pattern}` | {hits} | {row['files']['rg']} | {row['generic']['median_ms']:.0f} "
                f"| {row['rg']['median_ms']:.0f} | {row['vfs']['median_ms']:.0f} | {row['vfs_first_ms']:.0f} | {notes} |"
            )
        out.append(
            f"| **total** | | | {totals['generic']:.0f} | {totals['rg']:.0f} | {totals['vfs']:.0f} | | |"
        )
        out += ["", "## Repo-wide glob", "", "| case | count gen/rg/vfs | generic ms | rg ms | vfs ms |", "|---|---|---|---|---|"]
        for row in report["repo_glob"]:
            counts = "/".join(str(row["count"][tool]) for tool in TOOLS)
            out.append(
                f"| {row['case']} | {counts} | {row['generic']['median_ms']:.0f} | {row['rg']['median_ms']:.0f} "
                f"| {row['vfs']['median_ms']:.0f} |"
            )
    print("\n".join(out))


if __name__ == "__main__":
    main()
