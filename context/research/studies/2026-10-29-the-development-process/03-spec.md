# 03 — The specification: its required shape, its Kind vocabulary, and the lint that holds it

This is a study for [the development-process memo](../../2026-10-29-the-development-process-seven-studies-and-what-they-recommend.md), owned by Clay Gendron. Its question: what is the required shape of a specification (header lines, sections, the architecture diagram, the decisions, the acceptance criteria, the landing notes)? What vocabulary does its Kind line use? What lint rule holds the shape? Already decided by Clay before this study: one file per spec, not a folder; no ADRs, so every decision is a numbered entry in the spec with its reason; every spec carries an architecture diagram; a spec holds no open question; every change needs a spec; and (ruled during this study) no numbers in document file names, so every intention, spec and review is `YYYY-MM-DD-descriptive-slug.md`. Its method: read vfs's own spec machinery (`context/README.md`, `context/specs/README.md`, `STATUS.md`, `open-questions.md`, the intention, specs 181 and 174 in `active/`, spec 144 in `archive/`, the `plan.md` of 165 and the `tasks.md` of 174) and its architecture pages (`README.md`, page 04, page 02, `glossary.md`, `build_html.py`); read the sibling project wasi-python at commit `1431ba6f` (2026-10-28; working tree carries three untracked files, `.agents/`, `skills-lock.json`, `snapshot_demo.py`, nothing modified), its `context/README.md` specification and review rules, specs 141 and 150, `reviews/README.md`, and the lint in `tests/lint/test_writing_conventions.py` with `tests/harness/scan.py`; fetched five online templates; counted markers and ADR statuses with `grep`. Nothing was copied; shapes are described and the recommended skeleton is written fresh. Time box 30 minutes; the box was met.

## Sources

- vfs at the working tree of 2026-10-29 (HEAD `1198d92`): `context/README.md`, `context/specs/README.md`, `context/specs/STATUS.md`, `context/open-questions.md`, `context/intentions/2026-10-29-the-development-process.md`, `context/specs/active/181-the-public-surface-regrouped-by-kernel-group/spec.md`, `context/specs/active/174-write-preconditions-and-the-guarded-append/spec.md` and its `tasks.md`, `context/specs/active/165-the-permission-ladder-list-and-contribute/plan.md`, `context/specs/archive/144-endpoint-liveness-under-lock/spec.md`, `context/architecture/README.md`, `02-the-kernel-and-the-facets.md`, `04-one-call-end-to-end.md`, `glossary.md`, `build_html.py`.
- wasi-python `~/Git/Repos/wasi_python` at `1431ba6f` (Apache-2.0): `context/README.md`, `context/specifications/141-the-access-lists-on-the-way-to-the-cache-are-read.md`, `context/specifications/150-a-starting-image-the-embedder-chooses.md`, `context/reviews/README.md`, `tests/lint/test_writing_conventions.py`, `tests/harness/scan.py`.
- Online, all read 2026-10-29: spec-kit's methodology <https://github.com/github/spec-kit/blob/main/spec-driven.md> and spec template <https://github.com/github/spec-kit/blob/main/templates/spec-template.md>; the Rust RFC template <https://github.com/rust-lang/rfcs/blob/master/0000-template.md>; the Kubernetes KEP template <https://github.com/kubernetes/enhancements/blob/master/keps/NNNN-kep-template/README.md>; PEP 12 <https://peps.python.org/pep-0012/>; Oxide RFD 1 <https://rfd.shared.oxide.computer/rfd/0001>.

Labels: **READ** means read from the file or page cited. **EXECUTED** means a command was run and its output seen. **INFERRED** means reasoned from what was read.

## What the sources say

### vfs today

- **READ.** `context/README.md` names a four-stage pipeline (research → decide → specify → code) and tells authors to mark uncertainty with `[NEEDS CLARIFICATION: …]` and to pointer each marker in `open-questions.md`. The marker is called "a first-class citizen".
- **READ.** `context/specs/README.md` makes a spec a folder, `NNN-slug/`, with three files: `spec.md` (what and why; "stable"), `plan.md` (how; "regenerable"), `tasks.md` (do; "disposable"). A small fix may be `spec.md` alone. Numbers are sequential and never reused. The lifecycle is: born from a decision; drafted with markers; plan and tasks written; executed; on landing moved to `archive/` with its status line naming the commit; residue flows backward to `decisions/` and `research/`.
- **EXECUTED.** `ls context/specs/active` shows 31 folders. `grep -l 'NEEDS CLARIFICATION'` matches 23 of their `spec.md` files; the counts run from 1 (eight specs) to 9 (spec 180), 72 marker lines in all. Only four active folders hold a `plan.md` or `tasks.md` beyond `spec.md`: 162 and 165 (both), 167 and 174–181 (`tasks.md` only). So the three-file shape is already honoured mostly in the breach.
- **READ.** Spec 181's header has six lines: Status, Date, Owner, Kind, Depends on, Decisions it implements, Research it stands on. Its body is `## Intent`, `## Terms used below`, ten numbered design sections, `## Scope`, `## Acceptance criteria` (19 counted, "counts and states, never clocks"), `## ADR amendments this spec needs`, `## Rebase notes`, `## Open markers`, `## Landing notes` ("Filled in on landing"). Spec 174 has the same spine with `## Terms`, `## 0. What the code does today`, ten numbered sections, Scope, 26 criteria, ADR amendments, Rebase notes, Landing notes.
- **READ.** Archived spec 144 (328 lines) has Status (landed, commit, the ADR it amended), Born from, Amends, Date, Owner, Kind, Depends on, Relates to; then `## Intent`, `## Decided semantics` (six numbered pins, each with its reason in the same paragraph), recorded follow-ups, and a `## Landing note` with the local gate's counts, the four engine legs' counts, and scale figures. This is the closest thing vfs already has to the decided shape: decisions numbered in the spec, reasons attached, landing notes with evidence.
- **READ.** The `plan.md` of 165 holds: Approach (three slices, each green), Trade-offs taken (seven one-line pairs of choice and reason), Risks (three, each with a mitigation). The `tasks.md` of 174 holds: five tasks in landing order, each naming the functions it touches, the criteria it discharges, and the test node ids it adds, with a preamble saying which tasks run the engine legs and a scale review.
- **READ.** `STATUS.md` is "a periodic true-up of story specs against the code", "a snapshot, not a live index". Its top entries are long prose paragraphs per landing day. One entry says spec 162 is "built, uncommitted, awaiting Clay's review" while the specs README says active folders may hold work "in progress"; the file carries state that only a reader of git can verify.
- **READ.** `open-questions.md` is 404 lines, live-only, with the resolved entries split to an archive file. Each entry has Asked, Context, Blocking, Options considered, Status. Some entries say "Blocking: nothing" and are parked; some say "owned by spec 080; do not fix inline".
- **READ.** The architecture README: one diagram per page; a status line (drawn date, commit, code-as-is or decided target); the picture in Mermaid; *Reading the picture* in short sentences; a *Terms this diagram introduces* table; *What is planned, and where*; *Open*. Legend: solid is built, dashed is planned and names its spec or ADR, dotted is built but retiring, italics inside a group is a planned verb. Pages are revised in place; when a spec lands, the box it planned turns solid. Every term goes to `glossary.md` with a page pointer. Mermaid is checked by rendering.
- **EXECUTED.** The eleven pages use five Mermaid kinds: `flowchart TB` (17), `flowchart LR` (8), `sequenceDiagram` (2), `classDiagram` (1), `stateDiagram-v2` (1). Planned elements are marked by a class definition named `planned` with a dash pattern of 6 on 4 and a 2-pixel stroke (six pages); retiring by a class `retiring` with a 2-on-3 dash (one page). Nodes are assigned with `class a,b planned`. Page 02 labels planned boxes with the spec that decides them in the box text.
- **READ.** `build_html.py` renders every fenced `mermaid` block as a figure with pan and zoom, orders pages by their numeric prefix, and stamps the commit. Nothing in it depends on where a page's Mermaid comes from, so a spec's diagram can be the same dialect with no tooling change.
- **READ.** The intention `2026-10-29-the-development-process.md` sets the seven stages, "no ADRs", "every spec shows its shape", "nothing lands unreviewed", "no open questions" (what cannot be decided becomes a placeholder research memo and the spec waits), and done-when 3: `scripts/ci.sh` fails when a specification lacks its header or sections, holds an open question, or claims to be landed without citing a review file that exists.
- **EXECUTED.** `git log --oneline -25` shows commit subjects naming specs by number (`specs 174–181`, `ADR 087`). The owner's ruling during this study changes that: subjects and landing notes name a spec by its title.
- **EXECUTED.** `grep` over `context/decisions/` for a Status of "proposed" matches ten ADR files (022, 058, 069, 081–087); the intention's count is eleven. ADRs 081–087 carry "lean pending Clay" pins. Nothing under `tests/` today scans `context/`: there is no lint over the documents.

### wasi-python (the sibling project, already on the one-file shape)

- **READ.** Its `context/README.md`: specifications are one file each, `NNN-slug.md`, born from research, small enough for one developer, retired on landing. Each has a header (status, date, owner, kind, depends on, research it stands on), an intent paragraph, the design, scope in and out, counted acceptance criteria, and landing notes filled in when it lands. "There is no list of open questions": every choice is made in the spec with its reason; what cannot be decided gets a *placeholder* research memo naming the question, the experiment, and what it blocks, and the spec waits. Decisions are recorded "in the specification that carries them, in a Decisions section at its head". A decision only the owner can make is asked and then recorded in `decisions.md`, a newest-first log.
- **READ.** Spec 141 (178 lines, landed-class): header Status, Date, Owner, Kind, Depends on, Research it stands on; a labels line; `## The problem`; `## Decisions` with ten `### N. <sentence>` entries, each paragraph ending in its reason ("Reason: …"); `## Intent` ("After this specification, …"); `## Design` (files, functions, sizes, "the commits, in order"); `## Scope` (In: Decisions 1 to 10. Out: eight bullets); `## Acceptance criteria` (eight, each naming a test file, a job or a command, "counted, not timed"); `## Landing notes` (status, branch and shas, seen-failing evidence with the failing line, measurements EXECUTED, the run id, verification, the disposition of every review finding, differences from the text); `## One line`.
- **READ.** Spec 150 (346 lines, structural): the same spine plus `## Research` between the problem and the decisions, fifteen decisions, a Kind line that names every module touched with its line count today and its ceiling after. Its Status line names the pre-build review file and the date it was revised against it.
- **READ.** The Kind line vocabulary seen across 141 and 150: **parallel-safe**, **not structural** / **structural**, **runner code**, **defence in depth**, "a change to a security check", **reviewed before it is built**, "changes the public API" (from the README: a spec that changes `tests/public_api.txt` says so and lists the lines). Each word is a trigger: structural means a pre-build review scored on eight rows; changes the public API means the snapshot is regenerated and the allowing rule cited.
- **READ.** The lint. `test_specifications_have_their_header_and_sections` globs every spec and asserts no errors from `spec_shape_errors`, which checks that each of five header fields (Status, Owner, Kind, Depends on, Research it stands on) appears as a bold bullet at a line start, and that each of six sections (Decisions, Intent, Design, Scope, Acceptance criteria, Landing notes) appears as an `## ` heading. It checks presence, not order. `test_specifications_have_no_open_question` runs `open_question_hits` over every spec plus the README and AGENTS.md: after stripping fenced code and inline code, any heading containing "question" is a hit, and any line matching TBD, TODO or "open question" (case-insensitive) is a hit. `landed_review_errors` reads the Status line; when it starts with "landed" it takes the text after `## Landing notes` and requires at least one `reviews/<file>.md` citation whose file exists. A fourth helper checks a released version has a structural review scoring eight named rows. An allowlist tuple pattern elsewhere in the same test file admits a phrase in a named file "and an entry that admits nothing fails, so the tuple only ever shrinks" — a ratchet.
- **READ.** Reviews are named after the spec with `-spec-` or `-pr-` before the date; a landing cites its review in the landing notes; a reviewer is never the author.

### Online prior art

- **READ.** spec-kit (GitHub). Three artifacts: `spec.md` (user stories with priorities, edge cases, numbered functional requirements FR-NNN, key entities, numbered success criteria SC-NNN, assumptions; no tech stack), `plan.md` (requirements to technical decisions; supporting research, data-model, contracts, quickstart files), `tasks.md` (derived tasks, `[P]` for parallel). A constitution of nine articles governs the translation (library-first, CLI, test-first, simplicity, anti-abstraction, integration-first). `[NEEDS CLARIFICATION: …]` is required wherever the author would otherwise guess, and a checklist requires none remain before the spec is complete. This is the source of vfs's current folder shape and its marker.
- **READ.** Rust RFC template. Four header lines (feature name, start date, RFC PR, tracking issue). Sections: Summary, Motivation, Guide-level explanation (teach it as if it existed), Reference-level explanation, Drawbacks, Rationale and alternatives, Prior art, Unresolved questions (three kinds: before merge, before stabilisation, out of scope), Future possibilities. Unresolved questions are expected and sorted by when they must close.
- **READ.** Kubernetes KEP template. A release sign-off checklist; Summary; Motivation with Goals and Non-Goals; Proposal with user stories, caveats, risks and mitigations; Design Details with Test Plan, Graduation Criteria, Upgrade/Downgrade, Version Skew; a Production Readiness questionnaire (rollout, monitoring, dependencies, scalability, troubleshooting); Implementation History; Drawbacks; Alternatives. Metadata lives in a sidecar `kep.yaml` (status, stage, milestone, owners, reviewers, approvers) which the template page does not describe.
- **READ.** PEP 12. Header fields: PEP, Title, Author, Sponsor, PEP-Delegate, Discussions-To, Status, Type, Topic, Requires, Created, Python-Version, Post-History, Replaces, Superseded-By, Resolution. Type: Standards Track, Informational, Process. Status: Draft, Active, Accepted, Provisional, Deferred, Rejected, Withdrawn, Final, Superseded. Sections: Abstract, Motivation, Rationale, Specification, Backwards Compatibility, Security Implications, How to Teach This, Reference Implementation, Rejected Ideas, Open Issues, Footnotes, Copyright.
- **READ.** Oxide RFD 1. Header attributes: authors, state, discussion (a PR link), labels. States: prediscussion, ideation, discussion, published, committed (the system now works this way), abandoned. Zero-padded numbers, one branch per RFD. Content: the viable options with benefits and drawbacks, the reasoning with data and references, the determination; cost, customer, performance and security trade-offs where they apply; depth matched to urgency.
- **INFERRED.** Every template but spec-kit's is a single file. Every template keeps a header of a few machine-readable fields and a fixed set of headings. Three of five (Rust, PEP, spec-kit) make room for open questions; two (KEP via its approvers marking `implementable`, Oxide via `committed`) require the document to be decided before work proceeds. wasi-python is the only one that forbids open questions outright and holds that with a test. The decided vfs shape sits with wasi-python, KEP and Oxide: a spec is a decided document, and what cannot be decided waits outside it.

## What vfs does today

**What works.** The header lines already carry the right facts: status with dates and commits, kind as a sentence naming the modules touched, dependencies, the research cited by section. The best specs (144, 174, 181) already number their decisions, attach reasons, count their criteria, forbid clocks, and leave a landing-notes slot. Spec 144's landing note is a model of evidence: local gate counts, four engine legs' counts, scale figures as ratios. The architecture pages give a Mermaid dialect, a legend, and a terms table that a spec can reuse unchanged.

**What the folder shape costs.** The three-file shape was adopted from spec-kit, which generates all three by command. vfs writes them by hand, and the counts show the result: 31 active folders, 4 with a `plan.md` or `tasks.md` beyond the spec. The plan's durable content (slices, trade-offs with reasons, risks with mitigations) is the same content a decisions section holds; the task list's durable content (the commit order, which test each task adds) is one paragraph of the design. What is lost if the two files go: nothing a landed spec needs. What is kept: the "commits, in order" paragraph and the test-per-criterion naming, which move into the one file. A session's live task list is session state, not repository memory; it belongs in the session's plan, not in `context/`.

**What `STATUS.md` tried to do.** A cross-spec true-up so one page shows where everything stands. It rots by construction: it copies state from spec status lines and git, and the copy drifts (an entry still says 162 is "uncommitted"). With one file per spec, a dated name, and a Status line whose first word is a fixed vocabulary, `ls context/specs/active` plus a `grep` of Status lines is the index, and it cannot drift. Recommend: freeze `STATUS.md` with a top note and stop updating it; a generated table of Status lines, if wanted, is a lint fixture, not a hand-written page.

**What `open-questions.md` tried to do.** An intake for every `[NEEDS CLARIFICATION]` marker so no unknown was lost. It grew to 404 lines of entries that mostly say "Blocking: nothing", because the marker was cheap to write and the entry was the tax. The decided rule replaces it: a spec decides or waits; what it waits on is a placeholder research memo (stage 2's study owns that memo's shape) that names the experiment. Recommend: freeze `open-questions.md` with a top note; each live entry is either closed by a Decision in the spec that owns it, or becomes a placeholder memo, or is dropped as parked-with-nothing-blocking.

## The recommended format

The shape is one file, dated, with eight fixed header lines and nine fixed sections in a fixed order. Say it again: one file, eight header lines, nine sections, in order. The skeleton:

````markdown
# <Title: the change as a sentence a reader can say aloud>

- **Status:** draft — drafted YYYY-MM-DD from <the intention or research, by relative path>. (Later: reviewed, building, built, landed — see the lifecycle.)
- **Date:** YYYY-MM-DD
- **Owner:** Clay Gendron
- **Kind:** <one primary word, then the flags, then the modules touched with their line counts today and after>
- **Depends on:** <each dependency as a relative path to its spec, with what it needs from it; or "nothing">
- **Intention:** <relative path to the intention, or "none: <one reason the change needs no intention>">
- **Research it stands on:** <relative paths with the sections cited; or "none: <one reason>">
- **Reviews:** <filled as they are written: the spec review and the code review, by relative path; "none yet" while drafting>

Labels: EXECUTED means run and seen; READ means read from the file cited; INFERRED means reasoned.

## The problem

What the code does today, at a named commit, and why that is wrong or missing. Facts here are labelled EXECUTED or READ; a probe run for the draft is described with its command.

## Architecture

The components this change touches, drawn as `context/architecture/` draws them: one Mermaid block, solid for what exists, dashed (`planned`) for what this spec adds, dotted (`retiring`) for what it removes. Name the architecture page this diagram will change on landing. A terms table follows when the diagram introduces a term.

```mermaid
flowchart TB classDef planned stroke-dasharray: 6 4,stroke-width:2px; classDef retiring stroke-dasharray: 2 3; subgraph router["Router (base.py)"] gate["_gate_params → _gate_entry"] pre["precondition check<br/>if_version, if_absent"] end subgraph storage["Storage (one mount)"] plan["WritePlan (staging.py)"] judge["judgment pass<br/>expected_version"] exec["execute in pinned order (writes.py)"] ow["overwrite= flag"] end gate --> pre --> plan --> judge --> exec class pre,judge planned class ow retiring
```

Page this changes: `../../architecture/07-the-write-path.md` (the plan-then-execute picture gains the judgment step).

## Decisions

Every choice this change needs, numbered, each a sentence with its reason. A decision that departs from a frozen decision record or a landed spec says so by name. Nothing here is open.

### 1. <The decision, as a sentence>

What is decided, then the reason, then what it rules out and why.

### 2. <The next decision>

…

## Intent

One paragraph starting "After this spec, …": the observable state of the system once it lands, in the user's terms.

## Design

The files, functions, types and tests that change, with sizes where a ceiling matters; the slices if the landing is more than one commit; and the commits, in order, each naming the test it adds or makes green.

## Scope

**In:** the decisions by number and the files by path. **Out:** each neighbouring thing this spec does not do, with where it belongs instead.

## Acceptance criteria

Numbered. Tests come first, then code, so each criterion is written so one test can pin it, and names that test before the code exists: the test file and node id, or the conformance-suite row, that will prove it. Each counts operations or states, never clocks. A criterion no test can pin (a doc page exists, a page renders) names the command or the file instead.

1. **<Criterion, as a sentence about observable behaviour.>** Pinned by `tests/<file>.py::<node id>` (to be written first).
2. **<The next criterion.>** Pinned by the conformance row `<suite>::<row name>` on every engine leg.
3. …

## Landing notes

Empty until landing ("Filled in on landing."). Then: **the tests first** — for each criterion, its test was written before the code and seen failing on the base commit, with the failing line and the assertion seen, then seen passing after; the commit shas on `main` by the spec's title; the two review files by relative path; the local gate's result (`scripts/ci.sh`, counts); the engine legs run and their counts; measurements, labelled EXECUTED; the disposition of every review finding; differences from the text above, each with its reason; the architecture page and glossary entries updated.

## One line

The whole change in one sentence.
````

One sentence per part, for the record:

- **Title.** A sentence, not a label; the file name's slug is cut from it.
- **Status.** Starts with one word of a fixed vocabulary (below), then dates and citations.
- **Date.** The day the draft was started; the file name carries the same date.
- **Owner.** The person who can approve the decisions in it.
- **Kind.** The primary word, the flags, the modules (vocabulary below); the flags are what the reviews and gates read.
- **Depends on.** Specs by relative path (`../active/2026-…md` or `../archive/2026-…md`), never by number; the lint checks each path resolves in `active/` or `archive/` by file name.
- **Intention** and **Research it stands on.** Relative paths, or "none" with a reason, because every change needs a spec but not every spec needs the two earlier stages.
- **Reviews.** The two files, filled in as they are written; the lint reads this line and the landing notes.
- **The problem.** Today's behaviour at a commit; this is what spec 174 calls "§0 what the code does today" and wasi-python calls "The problem".
- **Architecture.** The picture before the design, as the intention asks; rules below.
- **Decisions.** The former ADR, now local: numbered `### N.` headings, reasons attached, departures named.
- **Intent.** The after-state, one paragraph.
- **Design.** Where `plan.md` and `tasks.md` go: slices, files, sizes, the commit order.
- **Scope.** In and out, with each out-item pointing at its owner.
- **Acceptance criteria.** Counted; each names its evidence; no clocks.
- **Landing notes.** The evidence that it landed, with the two reviews cited.
- **One line.** The sentence a commit subject or a glossary entry can reuse.

**Rules for the Architecture section.** Use the five Mermaid kinds the pages already use (`flowchart TB` or `LR` for structure, `sequenceDiagram` for a call, `classDiagram` for models, `stateDiagram-v2` for a lifecycle). Define `planned` and `retiring` exactly as the pages do, so a block can be pasted into a page on landing without edits. Solid is what exists at the commit the problem section names; dashed is what this spec adds; dotted is what it removes. Label a dashed box with nothing but its name (the pages label planned boxes with "spec NNN"; under dated names, the page's *What is planned* list carries the spec's path instead). Introduce every new term in a table under the diagram and add it to `glossary.md` on landing. Name the page the diagram changes; on landing, update that page (box turns solid; the spec moves from *What is planned* to *Sources*) and rebuild `index.html`. A diagram is checked by rendering: the lint checks only that the fence exists; GitHub and the viewer check the rest.

**Rules for Decisions.** One decision per `### N.` heading, numbered from 1 in the order a reader needs them. The heading is the decision as a sentence. The body ends with the reason. A decision that reverses or refines a frozen ADR or a landed spec names it ("departs from the 2026-09-04 endpoint-liveness spec's pin 3 because …"); `decisions/` itself is never edited. A decision only the owner can make is asked, answered, and recorded here with the date, as spec 144's pins record "Clay adopted … in session the same day".

**Rules for Acceptance criteria.** Numbered and counted (`STATUS.md` already reports "170 counted criteria" across eight specs). The code stage is tests first, then code, so a criterion is a sentence one test can pin, and it names that test — file and node id, or conformance-suite row — while the test does not yet exist. Writing the name first is what makes the test the first commit of the Design's order. Counts, states and statement numbers; never seconds. A criterion with no possible test (a page exists, a snapshot is regenerated) names the command or the file that shows it, and says so.

**Rules for the Design's commit order.** The first commit of every landing is the tests of the criteria, seen failing on the base; the code follows; the docs and the landing notes close. The sibling project's spec 141 lands in exactly this order (READ: "the rows, seen failing; the reading and the rule; the page, the news file"), and its Decision 8 is titled "The rows first".

**Rules for Landing notes.** Empty while unlanded, so the lint's landed check has a clean signal. On landing, the first record is the tests-first evidence: for every criterion, the test named in it was seen failing on the base commit before the code (the node id, the failing line, the assertion seen) and passing after; a criterion whose test passed on the base says why (a guard, not a goal). Then: commits by sha and by the spec's title; the two reviews by relative path; `scripts/ci.sh` result; engine legs; measurements EXECUTED; findings' disposition; differences from the text with reasons. Spec 144's landing note is the local model for the gate and leg counts; the sibling's spec 141 is the model for the seen-failing record (READ: each row named with its failing line and the assertion text, kept in a `build/` evidence file).

## The Kind line vocabulary

The Kind line has three parts: one **primary word**, zero or more **flags**, then the modules touched. Each word below is defined once and says what it triggers.

Primary words (exactly one):

- **feature** — new behaviour a caller can observe. Triggers: a docs change in the same landing; the criteria name the public verb or argument.
- **fix** — behaviour that was wrong becomes right; no new surface. Triggers: the first criterion is the reproducing test seen failing.
- **refactor** — the same behaviour, a different shape. Triggers: a parity or drift test pins that nothing observable changed.
- **spike** — a throwaway experiment whose result is a research memo, not code on `main`. Triggers: no landing notes beyond "the memo is …"; the lint still requires the sections.
- **process** — a change to `context/`, `scripts/`, CI, or the lint itself. Triggers: the code review's lens is the process standard, not the code patterns.
- **docs** — a change to `docs/` or the README only. Triggers: no engine legs, no scale review.

Flags (any number, each a trigger):

- **structural** — adds or removes a module, a public class, a protocol method, a lifecycle, or a seam between layers. Triggers: a spec review before the build, scored on the structure rows stage 4 defines.
- **changes the public API** — changes a signature, a verb, an argument, a result field, or an error kind a caller sees. Triggers: the docs reference regenerated; the criteria list the lines that change; the review checks nothing else changed.
- **changes the schema format** — adds or changes a table or column, so old mounts are re-provisioned. Triggers: the format number bump is a criterion; the four engine legs run before landing.
- **needs the engine legs** — touches `storage/backends/database/`, a dialect profile, a write or read builder, or any loop over batch input. Triggers: the `db_test` cycle on all four engines before landing, with counts in the landing notes.
- **touches rights** — changes a gate, a grant, a posture, a rung, or anything that decides what a caller may see. Triggers: the security lens of the code review is mandatory, with a leak test among the criteria.
- **touches the engine** — edits `crates/vfs-core`. Triggers: `cargo test -p vfs-core` and the reinstall of the wheel are criteria; the oracle parity tests run.
- **parallel-safe** — touches files no other active spec touches, so it can be built beside them. Triggers: nothing; the absence of the flag tells a session to check for a rebase.

Say the rule again: one primary word; the flags are the triggers; the modules close the line.

## The lifecycle

1. **Born.** A spec is cut from an intention, from a research memo, or directly from a defect or a reviewer's finding. The file is `context/specs/active/YYYY-MM-DD-descriptive-slug.md`, dated the day it is drafted. `Intention` and `Research it stands on` say "none" with a reason when there is nothing earlier. Status: **draft**.
2. **Drafted.** All nine sections present, every decision made with its reason, the diagram drawn. A choice the author cannot make becomes a placeholder research memo and the spec waits in `active/` as a draft, naming that memo in `Research it stands on`. There is never a marker.
3. **Reviewed.** A spec review file is written (stage 4's shape) by someone who did not write the spec; the author folds the findings in; the Status becomes **reviewed** and cites the review by path, and the `Reviews` line fills.
4. **Built.** Status **building** while commits are in flight on `main` or a branch. The first commit is the tests the criteria named, seen failing on the base; the code follows. Status **built** when the design's last commit exists and `scripts/ci.sh` is green. Deviations from the text, and each test's seen-failing line, are written into the landing notes as they happen.
5. **Landed.** The code review file is written (stage 6), findings disposed, the owner says commit. Status becomes **landed YYYY-MM-DD** and the landing notes carry the commits by sha, both reviews by path, the gates and legs. The file moves to `context/specs/archive/` with the same name. Commit subjects name the spec by its title.

Status vocabulary, first word only: `draft`, `reviewed`, `building`, `built`, `landed`, `parked` (deliberately stopped, with a reason), `withdrawn` (will not land, with a reason). The lint reads the first word.

**What flows backward, now that `decisions/` is frozen.** The old rule sent implementation decisions to `decisions/` and research to `research/`. With `decisions/` frozen, three things flow backward and nothing else:

- A decision taken during the build is appended to the spec's own Decisions section before landing (numbered after the last, dated), so the archived spec is complete. Nothing is written to `decisions/`.
- Research or measurement done along the way goes to `research/` as a dated memo, cited from the landing notes.
- The architecture page the Architecture section named is updated (box solid, spec cited under *Sources*), the glossary gains the new terms, and `context/README.md` or a standard changes when the change alters how the project works.

A landed spec is retired, as before: nothing in `archive/` governs current work; the architecture pages and the code are what a reader trusts.

## The lint rule

One test module, `tests/lint/test_context_shape.py` (or a `tests/test_context.py` beside `test_ops.py`; the folder is stage 4's call), run by `scripts/ci.sh` as part of the ordinary `pytest` run. It reads `context/specs/active/*.md` and `context/specs/archive/*.md` (the new-shape files, directly under those folders). It holds five checks; each is a pure function over the file's text returning a list of error strings, and the test asserts the list is empty and prints every error.

1. **The file name.** Matches `YYYY-MM-DD-<lowercase-words-and-hyphens>.md`; no digits-only prefix. The date equals the `Date` line.
2. **The header.** Each of the eight header lines is present as a bold bullet at a line start, in the order given. The Status line's first word is in the status vocabulary. The Kind line's first word is a primary word.
3. **The sections.** Each of the nine `## ` headings is present, in order. The Architecture section holds at least one fenced `mermaid` block. The Decisions section holds at least one `### 1.` heading and the numbers run without gaps.
4. **No open question.** After stripping fenced and inline code: no `[NEEDS CLARIFICATION`, no `TBD`, no `TODO`, no `open question`, no heading whose text contains "question" or "marker". This check also runs over `context/README.md`, `context/specs/README.md`, `CLAUDE.md` and every intention and review file.
5. **Landed means reviewed, and dependencies resolve.** When the Status's first word is `landed`, the Landing notes cite at least one spec review and one code review by relative path, and each cited file exists under `context/reviews/`; the Landing notes also contain the phrase "seen failing" at least once, the cheap signal that the tests-first record was written (the reviewer, not the lint, checks it is true) (stage 4 and 6 name the folder; the check is the same whatever the folder). Every path on the `Depends on` line resolves by file name in `active/` or `archive/` (the folder in the path may be stale after a move; the name is what is checked).

Mirroring the intention's done-when 3 exactly: a spec without its header or sections fails; a spec with an open question fails; a spec that claims to be landed without a review file that exists fails. The sibling project runs the same three checks today (READ, above) with presence-only matching; the additions here are the order, the file name, the diagram fence, the numbered decisions, and the dependency resolution.

A **ratchet allowlist** carries the old shape: a tuple of `(path, count)` for the grandfathered numbered specs still holding markers (see the next section). An entry that admits more than the file holds fails, so the tuple only shrinks. This is the sibling project's pattern for admitted phrases (READ), applied to markers.

## What happens to the 23 active specs with open markers, and to the proposed ADRs' pending pins

**The numbered folders keep their names.** The ruling is that only new work takes the dated name. The 31 active folders and the 142 archived ones stay as they are, `NNN-slug/spec.md`, with their `plan.md` and `tasks.md` where they exist. The lint's shape checks do not read inside a numbered folder; the folder is the old shape and is not asked to be the new one.

**The 23 with markers (72 marker lines).** Three outcomes, chosen per spec at the moment it is next touched:

- *Picked up to build.* Before any commit, every marker in that spec is resolved: each becomes a numbered Decision appended to the spec (the owner's answer with the reason, dated), or a placeholder research memo the spec waits on. The spec gains a `## Decisions` section if it lacks one, an `## Architecture` block, and the `Reviews` header line; it stays in its folder under its number. Its two reviews cite it by title. This is a conversion in place, not a rename.
- *Parked.* The Status line says `parked` with the reason; the markers stay as history; the ratchet admits them.
- *Withdrawn or superseded.* The Status says so and names the dated spec that replaces it; the folder moves to `archive/`.

The ratchet starts at today's counts (23 files; 1 to 9 markers each) and may only fall. `open-questions.md` is frozen with a note; its live entries are closed by the conversions above or dropped.

**The ten or eleven "proposed" ADRs (022, 058, 069, 081–087) and their pending pins.** `decisions/` is frozen as history, so no ADR is ever marked accepted again, and no pin is ever edited there. Each pending pin ("lean pending Clay") is answered where its implementing spec is: specs 174–181 implement ADR 087's pins, 167–172 implement 081–086. When one of those specs is picked up, its Decisions section records the pin's answer by ADR number and pin number ("ADR 087 pin 16, flat names, taken as decided because …"). The frozen ADR keeps its `proposed` status forever; a one-paragraph note at the top of `context/decisions/README.md` says the directory froze on 2026-10-29, that later decisions live in the specs, and that a "proposed" status there means "answered in the spec that implements it, if anywhere". The architecture pages, which cite "ADR 087 pin 5" in their sources, keep those citations (the ADR is still the record of that pin's text) and add the spec that decided it when it lands.

## One line

A spec is one dated file with eight header lines and nine sections in a fixed order — problem, architecture diagram, numbered decisions with reasons, intent, design, scope, counted criteria, landing notes, one line — whose Kind line's flags trigger the reviews and gates, whose Status's first word drives the lifecycle, and whose shape, closedness and landed-with-reviews claim are held by one lint module in `scripts/ci.sh`; the 173 numbered specs keep their names and are converted in place only when touched.
