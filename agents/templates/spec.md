# Template: a spec

A spec is the one document every change has: a work package one pull request can carry, which decides every choice the build needs and names the test that pins each acceptance criterion. It lives at `agents/YYYY-MM-DD-short-descriptive-title/spec.md`. The directory name is the date the work directory was opened and a title in words; nothing is numbered. A work directory that carries more than one spec names each file for what it specifies and keeps one review file per spec.

## Voice and form

- Objective and impersonal. No person's name, no mention of a person or an agent, no "I", "we" or "you". A ruling is written "Decided 2026-11-15: ..." with its reason.
- One line per paragraph. No header lines under the title: the date is the directory name.
- A claim about the tree is labelled EXECUTED (a command ran), READ (read in a cited file, as `path:line`) or INFERRED (reasoning).
- No open question. No clarification marker, no note that a choice is made later, no heading that opens a list of questions. A choice that sense and precedent do not settle is named in the first paragraph as "Waits on a ruling: ..." with its options, and the spec is not fit to build until the ruling is recorded as a decision.
- Links are relative Markdown links to files that exist. Code is cited as `path:line`.
- Code comments and docstrings written from a spec never name the spec.

## The shape

Line one is the title: a sentence that states the behaviour after the change. A first paragraph follows. It says what kind of change this is (feature, fix, refactor, spike, process, docs) and which flags apply: structural, changes the public API, changes the schema format, needs the engine legs, touches rights, touches the engine, parallel-safe. It names the roadmap story and gate the change serves, the source it was converted from when there is one, the research it stands on, and each spec it depends on with that spec's state (landed, or drafted and not built).

Then nine sections, in this order.

1. `## The problem` What the code does today, at a named commit, and why that is wrong or missing. Labelled facts.
2. `## Architecture` One Mermaid block: solid for what exists, the class `planned` (dashed, `stroke-dasharray: 6 4`) for what the spec adds, the class `retiring` (dotted, `stroke-dasharray: 2 3`) for what it removes. Every component the Design names is drawn. New terms are defined under the block.
3. `## Decisions` Every choice the change needs, as `### N.` headings numbered from 1 without gaps. Each heading is a sentence; its body ends in its reason and then one basis line, in one of four forms:
   - `Basis: ruled, <date>, <where the ruling is recorded>.`
   - `Basis: verified lean, <the roadmap decision or the source marker>; precedent: <the landed code, the archived spec, the memo line or the standard>.`
   - `Basis: the source spec, <section>; still true at <commit> (<how it was checked>).`
   - `Basis: decided in drafting, because <the rule it follows from>.`
   A decision that departs from a landed spec or a standard names the departure.
4. `## Intent` One paragraph beginning "After this spec, ...": the observable state once it is merged, in the caller's terms.
5. `## Design` The files, functions, types and tests that change, with sizes where a ceiling matters, and the order of work: each test first, then the code that passes it. For every statement, loop or in-memory structure added: what grows with input, and the declared budget that bounds it on the least generous engine.
6. `## Scope` In: the decisions by number and the files by path. Out: each neighbouring thing the spec does not do, and where it belongs.
7. `## Acceptance criteria` Numbered. Each is a sentence one test can pin, and it names that test (file and node id, or conformance row) before the test exists. Counts and states, never clocks.
8. `## Landing notes` "Filled in when the pull request is opened." until then. Then: the commits, the reviews by link, the gate's counts, the engine legs run and not run, measurements labelled EXECUTED, the answer to every review finding, differences from the text above with their reasons, and one `**Changelog:**` line.
9. `## One line` The whole change in one sentence.

## What makes a spec fit to build

Its spec review, written to [the review template](review.md) by a reader that did not write the spec, has a standing verdict that begins "Fit to build". One pull request to `dev` then carries the build, green at its end.

## A spec converted from an earlier shape

The first paragraph names the source by path. Every marker in the source becomes a numbered decision with its basis line, or a "Waits on a ruling" line in the first paragraph. Every name, argument, kind, path and count is checked against the tree and the later rulings before it is carried over; the source is evidence of intent, never of the present state of the code. Content the source repeats from a retired record is restated in the spec with its reason, since the record no longer governs.
