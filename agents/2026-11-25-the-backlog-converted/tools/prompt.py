# ruff: noqa: E501
"""Print the instructions for one unit of the backlog conversion, for one fresh reader or writer.

Run from the repository root::

    uv run python agents/2026-11-25-the-backlog-converted/tools/prompt.py write 178-2
    uv run python agents/2026-11-25-the-backlog-converted/tools/prompt.py check 178-2
    uv run python agents/2026-11-25-the-backlog-converted/tools/prompt.py review 178-2
    uv run python agents/2026-11-25-the-backlog-converted/tools/prompt.py answer 178-2
    uv run python agents/2026-11-25-the-backlog-converted/tools/prompt.py reread 178-2

The text printed is the whole of what the writer or reader is given. Nothing is added to it:
no summary of the spec, no account of how it was written, no expected verdict.
"""

from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

WORK = "agents/2026-11-25-the-backlog-converted"
CHECK = f"uv run python {WORK}/check_shape.py"
TASKS = json.loads((Path(WORK) / "tools" / "tasks.json").read_text())

RULES = f"""
Ground rules.
- This checkout contains origin/dev in full (git rev-list --left-right --count HEAD...origin/dev prints "N 0"); the tree at HEAD is dev's tree. Cite code at the commit git rev-parse --short=8 origin/dev prints. dev serves SQLite and Postgres, and an unknown dialect on the generic floor; MariaDB, SQL Server and Oracle are not served. The environment is synced to this tree: uv run python imports the current package.
- Open branches of origin that dev does not contain are listed in {WORK}/dev-index.md; read one with git show <branch>:<path>, never check it out. Ignore the claude/* and worktree-agent-* branches.
- Run no git command that changes state (no commit, add, checkout, switch, merge, restore, stash, worktree). Edit no file but the ones named for this task. Other writers work in this checkout at once.
- Every shell command gets a timeout. Never run the test suite and never run uv sync. Read-only probes are encouraged: grep, file reads, scratch scripts in the session scratchpad run with uv run python.
- The file is under agents/, so AGENTS.md's voice rule binds it: objective and impersonal, no person's name, no "I", "we" or "you", nothing about who wrote or decided anything; "Decided <date>: ..." for a ruling. The callers of vfs (agents, developers, ETL pipelines) may be named. One line per paragraph.
- Before returning, run: {CHECK} <the file written> (timeout 60 seconds) and fix every fault it prints, except a "dead link" to another spec of this conversion that {WORK}/state-on-dev.md lists as not written.
"""

DRAFT = {
    "amend": 'A file may exist at {dir}/spec.md. If it holds the section `## The outcome wanted` it is a finished draft against dev: stop and return "already written". Otherwise it is a draft against main at 0ed462f in an older shape; rewrite it in the template\'s shape, keeping what still holds and correcting what moved.',
    "rewrite": 'A file may exist at {dir}/spec.md. If it holds the section `## The outcome wanted` it is a finished draft against dev: stop and return "already written". Otherwise read it as material only and write the spec anew in the template\'s shape.',
    "discard": 'A file may exist at {dir}/spec.md. If it holds the section `## The outcome wanted` it is a finished draft against dev: stop and return "already written". Otherwise dev built most of what it says: write only what remains, anew.',
    "none": 'If {dir}/spec.md exists and holds the section `## The outcome wanted`, stop and return "already written". Otherwise write the spec anew at {dir}/spec.md, creating the directory.',
}


# ---------------------------------------------------------------------------
# The four sets of instructions
# ---------------------------------------------------------------------------


def write_prompt(task: dict) -> str:
    """The instructions for writing one spec against dev."""
    deps = ", ".join(f"{d}/spec.md" for d in task["deps_dirs"]) or "none"
    return f"""Write one specification of the vfs backlog, against the current dev branch, so that a reader who did not write it could find it fit to build.

The unit: key {task["key"]}, "{task["title"]}", gate {task["gate"]}, roadmap stories {", ".join(task["stories"]) or "none named"}. Its source is the numbered spec context/specifications/archive/{task["source"]}/ (spec.md, and plan.md and tasks.md where present).
What dev already holds of it (verdict "{task["verdict"]}"): {task["covered_by"] or "nothing"}.
What remains, which is what this spec specifies: {task["remaining"] or "the whole unit"}
{DRAFT[task["draft"]].format(dir=task["dir"])}
Other specs of this conversion it builds on, which may or may not be written yet: {deps}.
Dependencies and changes the reassessment names: {"; ".join(task["new_deps"]) or "none"}.
Roadmap decisions involved: {", ".join(task["decisions"]) or "none"}.

Read, in this order.
1. agents/templates/spec.md, which is the shape, followed exactly: the first paragraph, the sections in their order, Choices to confirm for what is not settled. Then one worked example on dev: agents/2026-11-21-a-listing-comes-back-a-page-at-a-time/spec.md.
2. {WORK}/reassessment/{task["group"]}.md at the section for {task["key"]}: the state of this unit against dev, and the main input.
3. {WORK}/state-on-dev.md (every unit, its directory and its state; a sibling spec is cited as ../<directory>/spec.md) and {WORK}/dev-index.md.
4. Each dev work directory, built spec or open branch the reassessment names for this unit, read where it covers or touches this unit. A shape this spec relies on from one of them is quoted by its decision number.
5. The study of the source, {WORK}/studies/{task["study_group"]}/{task["source"]}.md, and the decision verifications under {WORK}/decisions/ for the roadmap decisions named: background written against 0ed462f, to be re-checked against dev before anything from it is used.
6. context/standards/roadmap.md at the stories named (as it stands on dev), context/specifications/active/2026-11-15-the-kernels-public-names-and-argument-families-are-ruled.md for names and arguments, context/standards/constitution.md, and documentation/maintainers/how-we-name.md.
7. The source spec, then the tree. Every verb, argument, error kind, module, path, table, column and count is checked against dev before it is written down.

What the spec must hold.
- Only what remains on dev: what dev has built or specified is cited under Builds on, never specified again.
- A unit that state-on-dev.md marks "no spec owed" is never linked as a spec: what that page says dev holds is cited instead.
- Every choice the build would otherwise make is decided with its reason and precedent; what the rulings, the tree and precedent do not settle goes under Choices to confirm, with the side taken (the additive or cheaper-to-reverse one) and why. A choice with no reversible side is not taken: the entry says the build waits for it.
- Cost against AGENTS.md's reference deployment and the least generous engine served (Postgres or SQLite), with declared budgets, never hardcoded sizes.
- Tests named by file and node at the layer the behaviour lives, following the layout that exists under tests/ on dev; counts and states, never clocks; the Postgres leg where storage changes; a leak test where rights change.
- What it was not able to check, under Not checked.
- No more length than deciding everything takes. Do not carry the source's history or status lines.
{RULES}
Return: the file written, the number of decisions, each entry under Choices to confirm with the side taken, and each choice the build waits for."""


def check_prompt(task: dict) -> str:
    """The instructions for checking one written spec against the specs it builds on."""
    deps = ", ".join(f"{d}/spec.md" for d in task["deps_dirs"]) or "no other spec of this conversion"
    return f"""Check one specification against the specifications of this conversion it builds on, now that they are written, and correct what no longer agrees.

The spec is {task["dir"]}/spec.md. It builds on: {deps}. For each place it quotes or relies on one of them (a decision number, a name, an argument, an error kind, a table, a test), open that spec as it stands and compare. Where they disagree, the depended-on spec wins on what it owns: correct this spec's quotation, its design text and any test that used the stale shape. If one of them does not exist yet, leave the quotation and say so under Not checked.
Then confirm that every relative link in the spec resolves. A link to a unit that {WORK}/state-on-dev.md marks "no spec owed" (among them ../2026-11-25-the-dead-run-verb-leaves-every-face/ and ../2026-11-25-chaining-moves-onto-the-result-and-the-query-verbs-lose-rows-in-hand/) is replaced by a link to the dev work directory that page names as holding it, or by a plain sentence where it names none, and any decision that leaned on the missing unit is corrected to what dev holds. Edit only {task["dir"]}/spec.md.
{RULES}
Return whether it was consistent and each correction made."""


def review_prompt(task: dict) -> str:
    """The instructions for the first review of one spec by a reader that did not write it."""
    today = datetime.datetime.now(tz=datetime.UTC).date().isoformat()
    return f"""Review one specification before it is built, and end "Fit to build" or "Not yet".

The spec is {task["dir"]}/spec.md, read as it stands in this checkout. Follow agents/templates/review.md exactly: what the review is given and not given, the thirteen-step checklist, the ranking, and the file's headings in their order. Read with it the documents the spec cites at the lines it cites, context/standards/constitution.md, AGENTS.md, and the live tree, read-only. Run one to three probes of the tree to test what the spec says the code does today.
Write one file: {task["dir"]}/reviews/{today}-spec-review.md (create the folder). Identify the draft read by the first twelve hex digits of sha256sum {task["dir"]}/spec.md. Leave the Disposition as "Awaits the answers." Edit nothing else, the spec included.
A dependency under Builds on that is drafted and not built does not by itself hold the verdict; the shape quoted from it is checked against that spec's text. An entry under Choices to confirm that takes the additive or cheaper-to-reverse side holds; one the build waits for is a High.
Before returning, run: {CHECK} <the review file> (timeout 60 seconds) and fix every fault it prints.
{RULES}
Return the verdict line and the findings by number and title."""


def answer_prompt(task: dict) -> str:
    """The instructions for answering a review's findings and amending the spec."""
    return f"""Answer each finding of one spec review, amending the specification where the finding holds.

The spec is {task["dir"]}/spec.md and its review is the latest file under {task["dir"]}/reviews/. Read agents/templates/review.md, sections "The ranking" and "The rounds", then the review whole, then the spec. For each finding, most severe first, test it against the tree and the documents it cites. Where it holds, amend the spec: a High is fixed in the design, a Medium by adding the evidence it names (a probe run and reported, a test named, a quotation corrected), a Low by writing in its fix text. Where it does not hold, the spec stays and the reason is given. Then replace the review's Disposition body with one line per finding, in the review's order: "H1. fixed: <what the spec now says, and in which section>" or "M2. kept because <the reason, with its evidence>". Edit the spec and the Disposition section of the review, and nothing else: no other heading of the review, its findings and its Verdict included, is touched.
Before returning, run: {CHECK} <the spec> <the review file> (timeout 60 seconds) and fix every fault it prints.
{RULES}
Return each Disposition line."""


def reread_prompt(task: dict) -> str:
    """The instructions for re-reading an amended spec against its review's Disposition."""
    today = datetime.datetime.now(tz=datetime.UTC).date().isoformat()
    return f"""Re-read one amended specification against the Disposition of its review, and add the dated verdict line.

The spec is {task["dir"]}/spec.md and its review is the latest file under {task["dir"]}/reviews/. Follow the section "The rounds" of agents/templates/review.md. For each Disposition line, open the spec at the place the line names and append to the line "READ, confirmed" or "Not confirmed: <why>". A line that says "kept because" is confirmed only when its reason holds against the template's ranking. Then add below the first verdict one line: `{today}, re-read on <the first twelve hex digits of sha256sum of the spec>: <Fit to build: one sentence. / Not yet: the findings still open.>` The first verdict stays as written. Edit only the review file.
Before returning, run: {CHECK} <the review file> (timeout 60 seconds) and fix every fault it prints.
{RULES}
Return the dated line added."""


PROMPTS = {
    "write": write_prompt,
    "check": check_prompt,
    "review": review_prompt,
    "answer": answer_prompt,
    "reread": reread_prompt,
}


def main(arguments: list[str]) -> int:
    if len(arguments) != 2 or arguments[0] not in PROMPTS or arguments[1] not in TASKS:
        sys.stderr.write("usage: prompt.py write|check|review|answer|reread <unit key of tools/tasks.json>\n")
        return 2
    sys.stdout.write(PROMPTS[arguments[0]](TASKS[arguments[1]]) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
