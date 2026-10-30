# The development process

## The story

As a developer on vfs, human or AI coding agent, I want the work to be planned and organized so that what I produce is of high quality and so that the people and agents working on the project can collaborate well: hand work to each other, pick up each other's work, question each other's decisions, and trust what has landed.

## The problem today

Work on vfs is planned, but the plan is spread across places that disagree, and nothing holds it together. Measured on `main` at `1198d92`, 2026-10-29.

- **A decision lives in three places.** 87 decision records, a Decisions section in some specs, and the roadmap. Eleven records are still "proposed", one with six leans nobody has confirmed. A spec cites a record by pin number, so a reader needs three documents open to learn one decision (EXECUTED: `ls context/decisions`, `grep Status`).
- **Nothing says who reviews, and no review is kept.** No review file exists in the repository. Past reviews are six research memos and three spec folders named "review". No rule says a reviewer must not be the author, and a landed spec does not have to cite any review (EXECUTED: `find context -iname '*review*'`).
- **Questions are parked, not answered.** 23 of 31 active specs carry an open marker. `open-questions.md` holds questions with no owner and no experiment that would close them (EXECUTED: `grep -rl 'NEEDS CLARIFICATION' context/specs/active`).
- **The spec shape is not followed.** The spec folder is meant to hold a spec, a plan and a task list; across 33 active specs there are 2 plans and 11 task lists. `STATUS.md` is a snapshot that was stale the day after it was written (EXECUTED: `ls context/specs/active/*/plan.md`).
- **The standards contradict the rules.** `standards/commits-and-prs.md` says never push to `main`; `CLAUDE.md` says commit to `main`. `standards/contributing.md` says do not treat the repo as greenfield; `CLAUDE.md` says it is greenfield (READ).
- **The code cites the records it is told not to.** `CLAUDE.md` forbids naming a spec or decision in code; `tests/` does so about 700 times (EXECUTED: `grep -rnoE 'ADR [0-9]{3}|spec [0-9]{3}' tests | wc -l`).
- **Tests first is practised, not written.** Recent landings record a pin "proven to bite", but no rule requires a test to be seen failing before the code (READ: `git log`, the roadmap).
- **Nothing holds the shape.** No test reads `context/`. Of 154 research memos, 131 carry no evidence label and 95 have no Method line (EXECUTED by the research study, 2026-10-29).
- **There is no stage for the why.** Work starts at research or at a spec. What the work is for, and for whom, is a paragraph inside the spec, so research is commissioned without a stated intent (READ).

The cost is the experience the story names: a new worker cannot tell which decision is current, cannot find the review that checked a change, and cannot pick up a spec without first resolving its open markers with the author.

## What we intend to achieve

- **High-quality output.** A change is thought through before it is written, written against a design that was checked, and checked again once it is code. Quality comes from the planning and the checking, not from the effort of one author.
- **Collaboration between agents and people.** A person can set the direction and an agent can carry it out, or the other way round, and each can read what the other did and why. Nobody needs the author in the room to understand the work.
- **Work that can be handed over.** Any piece of work can be picked up by someone who was not there when it started. What it is for, what was learned, what was decided and what remains are written where the next worker will look.
- **Decisions that are questioned, then trusted.** Every decision is written with its reason, where the work is, so a reviewer can challenge it and a later reader can rely on it.
- **Nothing lands on trust alone.** A fresh reader checks the design before it is built and the code before it lands, and the checks are kept as records.

## Part of the story

One written pipeline is how we get there: intent → research → spec → review → code → review → commit. Each stage produces a document in a known shape, in a known place, so an agent or a person can enter the work at any stage and know what comes next. The pipeline is the means. The experience above is the end.

## What this is not

- Not ceremony for its own sake. A small change needs no intention and no research. Every change needs a specification, because the specification is where the design, the decisions and the acceptance criteria live.
- Not a rewrite of the past. Landed work keeps its records as they are. Only new work takes the new shape.
- Not a pull-request flow. A change lands by a commit when the owner asks.

## Done when

1. A new contributor, human or agent, can read one page and know how work moves here, what to write at each stage, and where to put it.
2. A piece of work started by one worker is finished by another using only what is in the repository.
3. Every landed change carries the design review and the code review that checked it, and a reader can find both from the specification.

## What the research must answer

1. What shape does an intention take, when is one written, and how does it link forward? Anthropic's published guidance on the AI software development lifecycle is the first source.
2. What shape do a research memo, a placeholder memo and a study take, and what rule holds each?
3. What is the required shape of a specification, its vocabulary for the kind of change, its lifecycle, and the lint that holds it?
4. What does a review of a specification check, in what format, with what ranking and verdict?
5. Which reusable coding patterns does this repository already follow, and how are they written as one standard a reviewer can check?
6. What does a review of the code check, how do the existing review skills fold into one file, and how is Cloudflare's security-audit skill installed and run as a lens?
7. What is the commit format, the landing order, the gate when there is no pull request, and the changelog convention?
