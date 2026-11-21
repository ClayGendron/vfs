"""Project the crossover measurement onto a remote database: add a round trip per statement and transfer per byte.

A model, not a measurement. The in-hand path is charged the scope's file bytes; the index path's posting-list
and candidate bytes are not measured and are charged nothing, which flatters the index path for common patterns.

    uv run python agents/2026-11-21-linux-grep-benchmark/project.py crossover.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SCENARIOS = (
    ("local SQLite", 0.0, None),
    ("same region: 1 ms RTT, 1 Gbit/s", 1.0, 125e6),
    ("cross region: 20 ms RTT, 1 Gbit/s", 20.0, 125e6),
)


def main() -> None:
    rows = json.loads(Path(sys.argv[1]).read_text())
    header = " | ".join(f"{name}: index / in hand ms" for name, _, _ in SCENARIOS)
    print(f"| scope | files | MB | pattern | {header} |")
    print("|---|---|---|---|" + "---|" * len(SCENARIOS))
    for row in rows:
        cells = []
        for _, rtt, bandwidth in SCENARIOS:
            index = row["index"]["median_ms"] + row["index"]["statements"] * rtt
            statements = row["list"]["statements"] + row["in_hand"]["statements"]
            transfer = row["bytes"] / bandwidth * 1000 if bandwidth else 0.0
            in_hand = row["list"]["median_ms"] + row["in_hand"]["median_ms"] + statements * rtt + transfer
            winner = "hand" if in_hand < index else "index"
            cells.append(f"{index:.0f} / {in_hand:.0f} **{winner}**")
        print(f"| {row['scope']} | {row['files']} | {row['bytes'] / 1e6:.1f} | {row['pattern']} | {' | '.join(cells)} |")


if __name__ == "__main__":
    main()
