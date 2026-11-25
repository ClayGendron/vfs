# Template: a spec

A spec is the one document a piece of work has: it says what the work makes true, why, and how it is built and tested, and it decides every choice the build would otherwise invent. It lives at `agents/YYYY-MM-DD-short-descriptive-title/spec.md`. The directory name is the date the work directory was opened and a title in words, a sentence about the behaviour, with no number. This page writes down the shape the specs on `dev` already share; [the listing spec](../2026-11-21-a-listing-comes-back-a-page-at-a-time/spec.md) and [the indexed-verbs spec](../2026-11-21-the-shell-serves-the-indexed-verbs/spec.md) are worked examples of it.

## Voice and form

- Objective and impersonal, as AGENTS.md requires of everything under `agents/`: no person's name, no "I", "we" or "you", and nothing about who wrote or decided what. A ruling is written "Decided 2026-11-15: ..." with its reason.
- One line per paragraph. Short sentences, one idea each; every term of art defined the first time it is used, or in Terms.
- A claim about the tree is checked at a named commit and cited as `path:line`; a claim that was run says so.
- Links are relative Markdown links to files that exist.
- Code comments and docstrings written from a spec never name the spec.

## The first paragraph

Under the title, which is a sentence stating the behaviour after the change, one paragraph says what state the spec is in ("A draft, written on 2026-11-25. It is not reviewed, and nothing is built."), the commit of `dev` it was checked against, the roadmap story and gate it serves, the source it was converted from when there is one, and what it rests on.

## The sections

In this order. The ones marked optional are left out when they would be empty; every other one is present.

1. `## The outcome wanted` What a caller can do once the work is built, in the caller's terms, and how that is seen.
2. `## Builds on` Each landed spec, built work directory or code path this work stands on, and each work it waits for with its state (built on `dev`, specified on `dev` and not built, on an open branch with its name, or a unit of this conversion). For a dependency that is not built, the shape relied on is quoted by its spec's decision number, so that a disagreement can be read off the page, and the build order is stated.
3. `## Terms` (optional) The words this spec uses in a sense of its own.
4. `## What the code does today` (optional) The facts the problem rests on, each cited.
5. `## The problem` What is wrong or missing, and why it matters, at the scale AGENTS.md's reference deployment sets.
6. `## Decisions` Numbered. Each is a sentence followed by its reason and, where one exists, the precedent: the landed code, the archived spec, the research memo line or the public standard it follows. A decision that departs from a landed spec or a standard names the departure. Every default, error kind, budget, name and file the build would otherwise choose is decided here.
7. `## Cost` (optional for a change with no statement, loop or structure that grows) For each statement, loop or in-memory structure added: the multiplier of the reference deployment it rides on (per verb call, per file write, per index visit, per batch, per corpus, per lock), the arithmetic, and the declared budget that bounds it on the least generous engine served. A read never waits on a writer; a lock is held for a commit.
8. `## Left as it is` (optional) What the change deliberately does not touch, and why.
9. `## Tests` Each behaviour as one test that pins it, named by file and node, at the layer the behaviour lives, written before the code; counts and states, never clocks. A rights change carries a leak test. A storage change names the Postgres leg.
10. `## Scope` In: the files and modules by path. Out: each neighbouring thing not done, and where it belongs.
11. `## What the docs must say` (optional) The pages and docstrings that change.
12. `## Earlier decisions this reverses` (optional) Each, with where it was made.
13. `## Not checked` What was not run or read in writing the spec, said plainly.
14. `## Choices to confirm` (optional) Each choice that the rulings on record, the tree and the precedent do not settle. The spec takes one side, the one that is additive or the cheaper to reverse, and builds on it; the entry names the options, the side taken and why, so that a ruling can overturn it before the build. A choice with no reversible side is not taken; the entry says the build waits for it.
15. `## One line` The whole change in one sentence.

## What makes a spec fit to build

A reader that did not write the spec reviews it with the `spec_review` skill and ends "Fit to build" or "Not yet"; the review goes in a `reviews/` folder of the work directory. Fit to build means fit to build in its turn, once the work it names under Builds on has landed in the order it states.

## A spec converted from an earlier one

The first paragraph names the source by path. Every open choice in the source is decided, or listed under Choices to confirm. Every name, argument, kind, path and count is checked against `dev` before it is carried over: the source is evidence of intent, never of the present state of the code. A rule the source took from a retired decision record is restated as a decision with its reason, or dropped.
