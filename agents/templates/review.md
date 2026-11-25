# Template: a spec review

A spec review reads a spec before any code is written for it and ends "Fit to build" or "Not yet". It is written by a reader that did not write the spec and was given no account of how the spec was written. It lives beside the spec, at `agents/YYYY-MM-DD-short-descriptive-title/spec-review.md`; a work directory with several specs names each review `<spec file name without .md>-review.md`. A review made on a later day, after a decision changed or the scope grew, is a new file with its date appended to the name.

## Voice and form

The rules of [the spec template](spec.md) hold: objective and impersonal, no person or agent named, one line per paragraph, every claim labelled EXECUTED, READ or INFERRED, links that resolve, no open question and no placeholder word. A section with nothing to say is marked "none" with the reason.

## What the review is given, and what it is not

Given: the spec by path and the commit or draft read; the documents the spec cites; [the constitution](../../context/standards/constitution.md); `AGENTS.md`; the live tree, read-only; and questions about the draft, as questions only. Not given, and set aside unread if offered: a summary of the spec, the reasoning or transcript behind it, proposed answers to the questions, or an expected verdict. The review edits nothing but its own file and runs no git command that changes state.

## The checklist

1. **Questions first.** Each question put to the review is answered, labelled, before anything else.
2. **The whole spec is read once** before a finding is written, then the documents it cites at the lines it cites.
3. **The first paragraph.** The kind and each flag are checked against the Design and the Scope. A flag the change needs and the paragraph does not name is a Medium. A "Waits on a ruling" line is a High until the ruling is a decision.
4. **Decisions.** Each is a `### N.` heading that is a sentence, with a body that ends in its reason and a basis line. A decision with no reason is a Medium. A basis line whose precedent does not say what the decision claims, when read, is a Medium. A provisional decision holds when its options are named, its reason is given and the option taken is the additive one or the cheaper to reverse; one that takes the irreversible option is a High. A decision that contradicts a landed spec, a later ruling or a standard without naming the departure is a High.
5. **No choice left to the build.** Every default, error class, chunk size and name the build would otherwise invent is decided. An undecided choice is a High.
6. **Acceptance criteria.** Each names the test that will pin it and counts something; none names a clock. A wish is a Medium.
7. **Scope.** One pull request, green at its end. A spec that is several is a Medium, with the cut proposed.
8. **The diagram.** One Mermaid block; every component the Design names is drawn and nothing drawn is missing from the Design. A missing diagram is a Medium; one that disagrees with the Design is a High.
9. **Scale and the production posture.** For each statement, loop or structure the Design adds: what grows with input and the declared budget that bounds it. The floor is the least generous supported engine, never SQLite; a 10,000-file batch is a supported call; the multipliers of the reference deployment in `AGENTS.md` are named and multiplied. Anything unbounded is a High. A read that waits on a writer, or a lock held past a commit, is a High.
10. **The constitution and AGENTS.md.** Which of the five primitives the spec manipulates or composes; a sixth first-class thing is a High. No numpy, no designed scale cap, no pure-Python fallback on a hot path, imports at the top, `assert` narrows and never validates, counts and never clocks.
11. **Dependencies and the live tree.** Every spec or roadmap story this one builds on is named with its state and the build order. A shape relied on from a dependency that is not landed is quoted by that spec's decision number or that story's acceptance line; the quoted place is read, and a shape that the dependency does not state, or states differently, is a Medium. A dependency that is drafted and not built does not by itself hold the verdict. One to three probes, by command or `path:line`, that the spec's claims about today's code are true; a false claim is a Medium, or a High when a decision rests on it.
12. **Premortem.** The spec was built as written and failed in production or in review: the three most likely reasons. Each becomes a finding or a line under "Checked and found clean".
13. **Rank, fix text, ledger, verdict.**

## The ranking

- **High.** A wrong design the build would carry. The spec is not fit to build until it is fixed.
- **Medium.** A guarantee not evidenced. The finding states what evidence closes it.
- **Low.** A write-in. The finding carries its fix text, the exact sentence the spec should hold, so it needs no round and does not hold the verdict.
- A note has no rank and goes under "Checked and found clean".

Findings are numbered H1, H2, M1, L1 and so on, most severe first.

## The rounds

The review is written with its findings and its verdict. Each finding is then answered in the Disposition, one line each, "fixed: <what the spec now says>" or "kept because <reason>", and the spec is amended. The amended spec is re-read against each Disposition line, which gains "READ, confirmed" or "Not confirmed: <why>", and a dated line is added below the first verdict: `YYYY-MM-DD, re-read on <draft digest or commit>: <verdict>`. The first verdict stays. The last dated line is the standing verdict. "Fit once X" is "Not yet: X".

## The file

```markdown
# Spec review: <spec title>

Reviewed: [the spec](spec.md), <the commit, or "an uncommitted draft over `<commit>`, SHA-256 beginning `<twelve hex digits>`">. Read with it: <the documents, by link>. Not read: any summary of the spec, any account of how it was written, any expected verdict. Probes run: <each probe of the live tree and what it showed, or none>. Not reached: <what the review did not check, or "nothing">.

Labels: EXECUTED means a command ran for this review; READ means the cited file was read; INFERRED means reasoning.

## Questions put to the review, answered first

1. **<The question.>** <The answer, labelled.>

## Decisions, one line each

1. Decision 1: <holds / does not hold: why>, on <what it rests on>.

## Acceptance criteria, countable as written

1. <Criterion>: countable / not countable: <what it counts and the test that pins it, or what it lacks>.

## The diagram and the scope

- Diagram: <every touched component drawn; built and planned marked; agrees with the Design>.
- Scope: <one pull request / not one: why>.
- Depends on: <each dependency with its state, or "none">.

## Scale and the production posture

- <Each statement, loop or structure that grows with input, the multiplier it rides on, and the bound it declares; or "nothing grows with input".>

## Constitution and AGENTS.md checks

- Primitives: <which of the five, and that no sixth is added>.
- Articles touched: <each, and whether it holds>.
- Posture: <the 10,000-file batch, the least generous engine, no unbounded statement, no numpy, no designed cap, reads never wait>.

## Premortem

<The three most likely reasons the built spec failed, and which finding each became, or why none.>

## Findings, most severe first

1. **H1. <Title>** (<the spec section>): <the defect in one sentence>. Consequence if built: <what the code would carry>. Fix text: <the sentence the spec should carry>.
2. **M1. <Title>** (<the spec section>): <the guarantee not evidenced>. Closes with: <the evidence>.
3. **L1. <Title>** (<the spec section>): <the write-in>. Fix text: <the sentence>.

## Checked and found clean

<The sections, decisions and criteria read and passed.>

## Disposition

Awaits the answers.

## Verdict

<Fit to build: <one sentence>. / Not yet: <the Highs, or the Mediums>.> On <the draft digest or commit>.
```

The first section is left out when no question was put. Every other heading is present, in this order.
