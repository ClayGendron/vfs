"""The arithmetic behind the cadence figures: file visits per day under Clay's proposal and under the measured practice.

Run with ``uv run python -I cadence_arithmetic.py``; the printed table is pasted into the study as EXECUTED evidence.
Every input is a named constant so a reader can change one and rerun.
"""

from __future__ import annotations

FILES = 10_000_000
WORK_HOURS = 10
DAY_EDIT_SHARE = 0.01
NIGHT_EDIT_SHARE = 0.10
PROPOSED_FULL_PER_DAY = 6
PROPOSED_PARTIAL_MINUTES = 15
GITHUB_DOCS = 15_500_000_000
GITHUB_FULL_HOURS = 18
GITHUB_DOCS_PER_SECOND = 120_000


def main() -> None:
    day_edits = int(FILES * DAY_EDIT_SHARE)
    night_edits = int(FILES * NIGHT_EDIT_SHARE)
    organic = day_edits + night_edits
    full_visits = PROPOSED_FULL_PER_DAY * FILES
    partials_per_day = 24 * 60 // PROPOSED_PARTIAL_MINUTES
    partials_in_work_hours = WORK_HOURS * 60 // PROPOSED_PARTIAL_MINUTES
    edits_per_work_partial = day_edits / partials_in_work_hours
    print(f"corpus                              {FILES:>14,}")
    print(f"organic writes, working day (1%)    {day_edits:>14,}")
    print(f"organic writes, nightly batch (10%) {night_edits:>14,}")
    print(f"organic writes per day              {organic:>14,}")
    print(f"six full rebuilds, file visits      {full_visits:>14,}")
    print(f"full visits / organic writes        {full_visits / organic:>14.1f}x")
    print(f"one full rebuild / organic writes   {FILES / organic:>14.1f}x")
    print(f"partial passes per day              {partials_per_day:>14,}")
    print(f"edits per 15-min pass, work hours   {edits_per_work_partial:>14,.0f}  ({edits_per_work_partial / FILES:.4%} of corpus)")
    print(f"weekly full rebuild (Graph default) {FILES / 7 / organic:>14.2f}x organic writes per day")
    print(f"28-day full crawl (Glean default)   {FILES / 28 / organic:>14.2f}x organic writes per day")
    print(f"GitHub full reindex rate            {GITHUB_DOCS / (GITHUB_FULL_HOURS * 3600):>14,.0f} docs/s over {GITHUB_FULL_HOURS} h")
    print(f"GitHub stated publish rate          {GITHUB_DOCS_PER_SECOND:>14,} docs/s")
    print(f"10M files at GitHub's publish rate  {FILES / GITHUB_DOCS_PER_SECOND / 60:>14.1f} minutes per full rebuild")


if __name__ == "__main__":
    main()
