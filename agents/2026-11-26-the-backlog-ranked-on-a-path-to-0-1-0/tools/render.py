"""Write ranked-list.md from records.json and plan.json.

The ranking's data is records.json, one record per line, and plan.json, the waves and the
choices. This script turns them into the table a person reads, so a change to a tier or a
wave is made in the data and the page is written again.

Run it from the work directory with the system interpreter, since it imports nothing from vfs:

    python3 tools/render.py
"""

from __future__ import annotations

import json
from pathlib import Path

WORK = Path(__file__).resolve().parent.parent
AGENT_DAYS = {"S": 1.0, "M": 3.0, "L": 7.5, "XL": 15.0}
BUILT_STATES = frozenset({"built", "on-branch"})
STATE_WORDS = {
    "built": "built",
    "on-branch": "built on a branch",
    "partly-built": "partly built",
    "not-built": "not built",
    "no-spec": "no spec",
    "study-done": "study done",
    "moot": "moot",
}
MOVE_WORDS = {
    "sooner": "sooner than the roadmap",
    "later": "later than the roadmap",
    "new": "not on the roadmap",
    "cut": "folded",
}
REST = (
    ("later", "After 0.1.0", "Each can follow the release without breaking a public name."),
    ("fold", "Dropped or folded", "The behaviour is kept and the separate spec is closed."),
    ("done", "Built on dev", "Nothing remains but what a follow-up spec names."),
    ("ref", "Reference material", "Studies, reviews and indexes. Nothing in them is built."),
)

# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render(records: list[dict], plan: dict) -> str:
    """Return the whole page: one table per wave, then the tiers outside the waves."""
    active = sum(1 for r in records if r["wave"])
    later = sum(1 for r in records if r["tier"] == "later")
    lines = [
        f"# Every work directory under `agents/`, ranked: {active} items in six waves, "
        f"{later} after 0.1.0, and what is built or folded",
        "",
        f"Written from `records.json` and `plan.json` by `tools/render.py`, against `dev` at `{plan['dev']}` "
        f"on {plan['written']}. It is generated: a change is made in the data and the page is written again. "
        "The reasoning is in [ranking.md](ranking.md). A size is effort on the roadmap's scale, S a day or less, "
        "M two to four days, L one to two weeks, XL more than two weeks, and is an estimate from a skim.",
        "",
    ]
    for wave in plan["waves"]:
        rows = [r for r in records if r["wave"] == wave["wave"]]
        days = sum(AGENT_DAYS.get(r["size"], 0.0) for r in rows if r["state"] not in BUILT_STATES)
        musts = sum(1 for r in rows if r["tier"] == "must")
        lines += [
            f"## Wave {wave['wave']}: {wave['name']}",
            "",
            f"{wave['goal']} The claim it makes true: {wave['claim_it_makes_true']} {wave['note']}",
            "",
            f"{len(rows)} items, {musts} of them must, about {days:g} agent-days in series.",
            "",
            "| Rank | Item | Tier | Size | State | Roadmap | Reason |",
            "|---|---|---|---|---|---|---|",
        ]
        lines += [_row(r, ranked=True) for r in rows]
        lines.append("")
    for tier, heading, blurb in REST:
        rows = [r for r in records if r["tier"] == tier]
        lines += [f"## {heading}", "", f"{blurb} {len(rows)} items.", ""]
        lines += ["| Item | Size | State | Roadmap | Reason |", "|---|---|---|---|---|"]
        lines += [_row(r, ranked=False) for r in rows]
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _row(record: dict, *, ranked: bool) -> str:
    state = STATE_WORDS.get(record["state"], record["state"])
    cells = [_item(record), record["size"] or "", state, _roadmap(record), _cell(record["reason"])]
    if ranked:
        cells[0:1] = [str(record["rank"]), cells[0], record["tier"]]
    return "| " + " | ".join(cells) + " |"


def _item(record: dict) -> str:
    title = _cell(record["title"])
    if record["kind"] == "gap":
        return f"{title} (no work directory on dev)"
    return f"[{title}](../{record['id']}/)"


def _roadmap(record: dict) -> str:
    gate = record["roadmap_gate"]
    placed = "unplaced" if gate in ("unplaced", "none", None) else f"gate {gate}"
    if record["roadmap_story"]:
        placed = f"{record['roadmap_story']}, {placed}"
    move = MOVE_WORDS.get(record["move"] or "")
    return f"{placed}; {move}" if move else placed


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


if __name__ == "__main__":
    data = json.loads((WORK / "records.json").read_text())
    (WORK / "ranked-list.md").write_text(render(data, json.loads((WORK / "plan.json").read_text())))
