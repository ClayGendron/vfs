# ruff: noqa: E501
"""Write ``state-on-dev.md``: every unit of the backlog conversion and the state of its spec.

Run from the repository root, after any spec or review of the conversion is written::

    uv run python agents/2026-11-25-the-backlog-converted/tools/state.py

The page is generated whole from ``tools/units.json`` and from the files on disk, and is
never edited by hand. A spec counts as written when it holds the template's first section,
and a written spec's title is read from its first line, since a spec may narrow its unit.
Its review state is the standing verdict of the latest file under its ``reviews/`` folder.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

WORK = Path("agents/2026-11-25-the-backlog-converted")
UNITS = json.loads((WORK / "tools" / "units.json").read_text())
DATED_LINE = re.compile(r"^\d{4}-\d{2}-\d{2},")

HEAD = """# The 88 units of the backlog, sorted against dev: {fit} specs are fit to build, {not_yet} are reviewed and not yet fit, {unreviewed} are written and not reviewed, {missing} are not written, and {none} units owe none

The map in [units.md](units.md) was drawn against `main` at `0ed462f`, before `dev` was merged into the work branch. This page sorts the same 88 units against `dev` and says what state each is in; it was last generated against `dev` at `{dev}` by `tools/state.py`, which writes it whole. The reasons are in the ten files under [reassessment/](reassessment/), one section per unit; the open branches of `origin` that `dev` does not hold are in [dev-index.md](dev-index.md).

A unit's verdict is one of five. "still-needed" means nothing of it is on `dev`. "partly-covered" means `dev` built or specified part and the spec covers the rest. "built-on-dev" and "specified-on-dev" mean a work directory of `dev` already holds it, so this conversion writes nothing. "moot" means `dev` removed its ground: an engine that is no longer served, or a decision that went the other way.

The gate is the roadmap's: `b` lands before the beta freeze of 0.1.0, `f` before the final 0.1.0, `a` rides any alpha, `0.2` and `0.1.x` come after 0.1.0, and "unplaced" has no roadmap story.

A written spec has the shape of [the spec template](../templates/spec.md). A spec is fit to build when the last dated line of its review's Verdict begins "Fit to build". No spec of this conversion has been reviewed: each is written, was checked or corrected against the specs beside it, and owes a spec review before it is built. What that check found and no spec settles is in [found-on-the-way.md](found-on-the-way.md).

| Unit | Gate | Title | Against dev | Spec | What dev holds |
|---|---|---|---|---|---|
"""


def standing_verdict(review: Path) -> str:
    """The last dated line of the review's Verdict section, else its first line."""
    text = review.read_text()
    body = text.split("\n## Verdict", 1)[1] if "\n## Verdict" in text else ""
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    dated = [line.split(":", 1)[1].strip() for line in lines if DATED_LINE.match(line) and ":" in line]
    return dated[-1] if dated else (lines[0] if lines else "")


def spec_state(unit: dict) -> tuple[str, str]:
    """The count a unit falls under and the text of its Spec cell."""
    if not unit["spec_owed"]:
        return "none", "no spec owed"
    directory = Path(unit["dir"])
    spec = directory / "spec.md"
    if not spec.exists() or "## The outcome wanted" not in spec.read_text():
        return "missing", f"not written; the path it takes is `{unit['dir']}/spec.md`"
    link = f"[spec](../{directory.name}/spec.md)"
    reviews = sorted((directory / "reviews").glob("*spec-review*.md")) if (directory / "reviews").is_dir() else []
    if not reviews:
        return "unreviewed", f"written, not reviewed: {link}"
    verdict = standing_verdict(reviews[-1])
    review = f"[review](../{directory.name}/reviews/{reviews[-1].name})"
    if verdict.startswith("Fit to build"):
        return "fit", f"fit to build: {link}, {review}"
    return "not_yet", f"reviewed, not yet fit: {link}, {review}"


def main() -> int:
    dev = subprocess.run(
        ["git", "rev-parse", "--short=8", "origin/dev"], capture_output=True, text=True, timeout=30, check=True
    ).stdout.strip()
    counts = dict.fromkeys(("fit", "not_yet", "unreviewed", "missing", "none"), 0)
    rows = []
    for unit in UNITS:
        bucket, cell = spec_state(unit)
        counts[bucket] += 1
        spec = Path(unit["dir"]) / "spec.md"
        title = (
            spec.read_text().split("\n", 1)[0].removeprefix("# ")
            if bucket not in ("none", "missing")
            else unit["title"]
        )
        holds = (
            unit["dev_holds"] if not unit["spec_owed"] or unit["dev_holds"] else "nothing of it is on `dev`"
        ).replace("|", "\\|")
        rows.append(
            f"| {unit['key']} | {unit['gate']} | {title.replace('|', chr(92) + '|')} | {unit['verdict']} | {cell} | {holds[:400]} |"
        )
    (WORK / "state-on-dev.md").write_text(HEAD.format(dev=dev, **counts) + "\n".join(rows) + "\n")
    sys.stdout.write(", ".join(f"{name} {count}" for name, count in counts.items()) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
