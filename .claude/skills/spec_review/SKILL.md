---
name: spec_review
description: Review a specification before it is built — one fresh agent checks every decision, every acceptance criterion, the diagram, the scope, the scale posture and the constitution, runs a premortem, ranks findings High, Medium or Low, and writes the dated review file under context/reviews/ whose verdict is "Fit to build" or "Not yet". Use when the user asks to "review the spec", for a "spec review", to "review before build", or "is this spec fit to build".
---

# Spec review — one fresh reader, one dated file, two verdict words

Review a specification before any code is written for it, and write
the review as a file the repository keeps. The build may start only
when the file's standing verdict begins "Fit to build". This is a
single-agent skill: one reviewer, no fan-out, no orchestration.

A **spec review** is the review a spec gets before it is built. A
**finding** is one defect the reviewer names. The **Disposition** is
the section where the author answers each finding. The **verdict** is
the one-sentence decision that ends the file. A **fresh reviewer** is
an agent or a person who did not write the spec and has not seen the
author's reasoning.

## Who reviews, and what the reviewer is given

The reviewer did not write the spec. When the reviewer is a sub-agent
of the author's session, the review's first paragraph says so ("a
fresh sub-agent of the author's session; not the author").

The reviewer **gets**:

- the path of the spec and the commit (or the uncommitted draft) to
  read it at;
- the intention it serves, the research memo and studies it cites,
  and the architecture pages it names, by path;
- `context/standards/constitution.md`, `CLAUDE.md`, and
  `context/reviews/README.md` (the template and the checklist);
- the live tree, read-only, and the session scratchpad for probes;
- the author's **questions** — the places the author was least sure —
  as questions only;
- the time box.

The reviewer **must not get**, and must refuse to read if offered:

- the author's summary of the spec, or any paraphrase of what it
  decides;
- the author's session transcript, reasoning, or the plan that
  produced the draft;
- a hint of the expected verdict ("should be quick", "I think it is
  ready");
- the author's proposed answers to its own questions;
- write access to the spec, `src/` or `tests/`.

The brief carries questions, not answers. If the brief carries an
answer, set it aside and say in the first paragraph that it was
offered and not read.

## The time box

The box is **25 minutes**. It is **45 minutes** when the spec touches
the storage backend, a verb's contract, the public surface, more than
one architecture page, or the gate (`scripts/ci.sh`, `tests/lint/`, a
workflow under `.github/workflows/`). State the box and where you
stood when it ran out in the first paragraph. A box that runs out is
not a verdict: write what was reached, name the step you stopped at,
and a second reviewer may pick up from there.

## The thirteen steps

Work them in this order. Label every claim EXECUTED (you ran it), READ
(you read the file cited) or INFERRED (your reasoning); say so once in
the first paragraph, then label each line.

1. **Answer the author's questions first.** If the brief asked any,
   answer each one, labelled, before anything else. Do not read any
   answer the author proposed. These go in the optional first section
   of the file.
2. **Read the whole spec once, silently, before writing a finding.**
   Then read the intention it serves, the research memo at the lines
   the spec cites, and the architecture pages it names.
3. **Decisions.** Each decision is a `### N.` heading, numbered without
   gaps, each a sentence whose body ends in its reason. Check each
   holds against the research line, the ruling, or the constitution
   article it rests on. A decision with no reason is a Medium. A
   decision that contradicts a landed spec, a standard, or a frozen
   record without naming the departure is a High. One line per
   decision in the file.
4. **No open question.** The spec carries no `[NEEDS CLARIFICATION`
   marker, no placeholder word that promises a later answer, no "to be
   decided at build time", and no heading that opens a list of
   questions. Every choice the developer would otherwise invent — a
   default, an error class, a chunk size, a name, a heading string — is
   decided. An undecided choice is a High: the build would decide it
   silently.
5. **Acceptance criteria, countable as written.** Each criterion names
   a test file and node id, a conformance row, a count, a file, a diff,
   or a command and its exit code, before that test exists. It never
   names a clock. A criterion that is a wish ("fast enough", "works at
   scale") is a Medium. One line per criterion in the file.
6. **Scope is one landing.** One commit to `main`, by one developer,
   green at the end (slices only when each is green on its own). A
   spec that is several landings is a Medium, with the cut proposed. A
   commit sequence that is red before its last commit is a High.
7. **The diagram.** The Architecture section holds one Mermaid block in
   the dialect of `context/architecture/` — solid is built, `planned`
   is dashed (`stroke-dasharray: 6 4`), `retiring` is dotted
   (`stroke-dasharray: 2 3`) — and names the page it will change.
   Every component the Design names appears in the diagram, and nothing
   in the diagram is missing from the Design. A missing diagram is a
   Medium; a diagram that disagrees with the Design is a High.
8. **Scale posture and the production posture.** For each statement,
   loop or in-memory structure the Design adds: what grows with input,
   and what bounds it. The bound is a declared budget
   (`membership_budget`, `chunked()`), never a hardcoded size. The
   floor is the least generous supported engine (Oracle's 1,000-element
   `IN` list, SQL Server's ~2,100 binds), never SQLite. A 10,000-file
   batch is a supported call. Anything unbounded is a High. A
   suboptimal profile named honestly, with its future direction, is
   not a finding; a designed scale cap is. Read `CLAUDE.md`'s
   "Production posture" section for the full list.
9. **The constitution.** Article 1: name which of the five primitives
   (Namespace, Entry, Candidate, Mount, Revision) the spec manipulates
   or composes; a sixth first-class thing is a High. Articles 2 to 5 as
   touched. `CLAUDE.md`'s rules as touched: no numpy, no designed scale
   cap, no pure-Python fallback for a hot path, imports at the top,
   `assert` narrows and never validates, count never clock, no document
   names in code comments.
10. **Dependencies.** Every spec this one builds on is named with its
    state (landed, or active and not yet built). A spec that assumes a
    dependency's shape the live tree does not have is a Medium, with
    the build order proposed. A file two active specs both rewrite
    must be named by both.
11. **One to three probes of the live tree.** By command or by
    `path:line`, check that the spec's claims about today's code are
    true: the function exists, the seam is where the spec says, the
    count in The problem matches, the test file is named right. Record
    each probe and what it showed in the first paragraph. A false claim
    is a Medium, or a High when a decision rests on it.
12. **Premortem.** Spend three minutes: the spec was built as written
    and failed, in production or in review. Write the three most likely
    reasons, one line each. Each becomes a finding or a line in
    "Checked and found clean".
13. **Rank, write the fix text, write the ledger, write the verdict.**
    Rank by the table below. Each Low carries its fix text — the exact
    sentence the spec should carry — so it needs no round. State for
    each Medium what evidence would close it. Write "Checked and found
    clean" so a short findings list is not mistaken for a short read.
    Then the verdict.

## The ranking

- **High** — a wrong design the build would carry: a decision that
  breaks the constitution, a standard or a landed spec without naming
  the departure; a statement or structure that grows without bound with
  batch size; a choice left for the developer to invent; a red commit
  by design. The spec is not fit to build until it is fixed.
- **Medium** — a guarantee not evidenced: a criterion that cannot be
  counted; a dependency not named or named in the wrong state; a
  missing diagram; a claim about the live tree that is false; a
  decision with no reason. State what evidence closes it. One Medium
  per review is normal.
- **Low** — a write-in: a sentence the spec should carry, given in the
  finding as fix text. A Low needs no round.
- A **note** has no rank: an observation with no fix the spec must
  take. It goes in "Checked and found clean" or beside the finding it
  qualifies, never in the ranked list.

Number findings H1, H2, M1, L1 and so on, most severe first. Each
finding cites the spec by section link, states the defect in one
sentence, the consequence if built, and the fix text when you can
write it.

## The verdict and the re-sign protocol

The Verdict section's first line is the verdict, on the commit or
draft reviewed. There are two forms and no third:

- **Fit to build.** Nothing High or Medium stands. The developer may
  start. This line is your signature on that commit of the spec.
- **Not yet: <the Highs, or the Mediums>.** A High or a Medium stands.

"Fit to build once X" is not a verdict; it is "Not yet: X". A hedge
("probably fine", "mostly ready") is refused.

The rounds: you write the file and commit nothing; the author answers
every finding in the Disposition, one line each ("fixed: <what the
spec now says>" or "kept because <reason>"), and amends the spec. You
re-read the amended spec against each Disposition line, append "READ,
confirmed" or "Not confirmed: <why>" to each, and sign again as a new
line below the first verdict beginning `YYYY-MM-DD, re-read on
<commit>:` followed by the verdict word. The first verdict stays above
it. **The last such dated line is the standing verdict.** A fixed
finding needs a re-signature in the same file; a changed Decision after
"Fit to build", or a scope that grew, needs a new dated review file. A
finding the author keeps against your rank goes to Clay in one line of
the Disposition; his word in the spec's Decisions closes it.

## The review file

Write one file: `context/reviews/YYYY-MM-DD-<spec-slug>-spec-review.md`.
The date is the review's own day, so a second review on a later day is
a new file. The slug is the spec's file name after its date
(`2026-10-30-the-ranged-read.md` gives `the-ranged-read`). No number
anywhere in the name. The shape is the one `context/reviews/README.md`
gives; it is reproduced here so this skill stands alone:

- Title: `# Spec review: <spec title>`.
- An opening paragraph with **no header bullets**: who you are (and
  the sub-agent note when it applies), the spec as a Markdown link and
  the commit or draft read, what you were given and that you were not
  given the author's summary, transcript, reasoning or expected
  verdict, every probe you re-ran with what it showed, the box and
  where you stood, and the sentence "Labels: EXECUTED means I ran it;
  READ means I read the file cited; INFERRED means my reasoning."
- Then these `## ` headings, in this order, exactly:
  1. `The author's questions, answered first` (optional; only when the
     author asked any)
  2. `Decisions, one line each`
  3. `Acceptance criteria, countable as written`
  4. `The diagram and the scope`
  5. `Scale and the production posture`
  6. `Constitution and CLAUDE.md checks`
  7. `Premortem`
  8. `Findings, most severe first`
  9. `Checked and found clean`
  10. `Disposition`
  11. `Verdict`

"The diagram and the scope" holds three lines: the diagram (which
page it redraws, every touched component shown, built and planned
marked, agrees with the Design), the scope (one landing or not, why),
and the dependencies with their state or "none". "Disposition" is
written by the author and confirmed by you; leave it with one line
saying it awaits the author when you first write the file.

Like every document under `context/`, the review has **one-line
paragraphs** (a paragraph is one line of any length; a list item is
one line) and cites by **Markdown link**, never by number: the spec,
the intention, the studies and the standards as relative links from
`context/reviews/`, the live code as `path:line`. No header bullets,
no Status or Date lines; the date is the file name. The worked example
is `context/reviews/2026-10-29-the-development-process-spec-review.md`.

## House rules

- **The repository is read-only except for the one review file.**
  Never edit the spec, `src/`, `tests/` or any other document; never
  run a git command that changes state (no commit, checkout, restore,
  stash, worktree). The author commits the review file.
- **Probes run from the repo root through `uv`** (`uv run python
  <scratch script>`, `uv run pytest <node id>`), and scratch scripts
  go only under the session scratchpad.
- **A finding needs evidence**: the spec line it reads, and for a
  live-tree claim the command or `path:line` that shows it. A feeling
  is a note, not a finding.
- **Never write a placeholder into the file.** Every section is
  written or marked "none" with the reason; the lint reads the file
  and refuses a placeholder word or an open question.
