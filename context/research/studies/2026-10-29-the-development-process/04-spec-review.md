# The review of a specification, before it is built

This is a study for [the development-process memo](../../2026-10-29-the-development-process-seven-studies-and-what-they-recommend.md), owned by Clay Gendron. Its question: what format does a spec review take (file name, header, sections, the checklist, the ranking of findings, the verdict vocabulary)? What does a reviewer check in a spec? How does the author answer? Its method: read wasi-python's review practice in full (the reviews README, constitution §5.6, the two pre-build reviews of 141 and 150, and how those two specs cite them); read vfs's seven review skills and the five "review before build" studies of the agent-shell set, plus spec 164's amendments section; fetched five online sources on design review. Time box 30 minutes; the box was kept, and the "What vfs does today" section was written from the files read rather than a full sweep of `context/specs/active/`.

## Sources

- wasi-python at `1431ba6f` (read 2026-10-29, read-only): `context/reviews/README.md`; `context/constitution.md` §5.6; `context/reviews/141-the-access-lists-on-the-way-to-the-cache-are-read-spec-2026-10-28.md`; `context/reviews/150-a-starting-image-the-embedder-chooses-spec-2026-10-27.md`; `context/specifications/141-*.md` and `150-*.md` (Status, Kind, Depends on, Landing notes).
- vfs: `CLAUDE.md`; `context/README.md`; `context/intentions/2026-10-29-the-development-process.md`; `context/standards/constitution.md` Article 1; `context/architecture/README.md`; `.claude/skills/{code_review,contract_review,scale_review,test_review,ownership_review,adversarial_review,verify_findings}/SKILL.md`; `context/research/studies/2026-10-15-agent-shell/12-spec-167-review-before-build.md`; `context/specs/archive/164-graph-traversal-as-a-frontier-walk/spec.md` ("Amendments from the pre-build review").
- Online (all read 2026-10-29): Malte Ubl, "Design Docs at Google", https://www.industrialempathy.com/posts/design-docs-at-google/; Kubernetes "Production Readiness Review", https://github.com/kubernetes/community/blob/master/sig-architecture/production-readiness.md, and the KEP template, https://github.com/kubernetes/enhancements/blob/master/keps/NNNN-kep-template/README.md; Oxide RFD 1 "Requests for Discussion", https://rfd.shared.oxide.computer/rfd/0001; Gary Klein, "Performing a Project Premortem", HBR 2007, https://hbr.org/2007/09/performing-a-project-premortem (preview only); Michael Nygard, "Documenting Architecture Decisions", https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions; the Amazon narrative-memo practice via a web search (secondary accounts only, see "What the sources say").
- Owner's ruling during this study (2026-10-29): no numbers in document file names; every intention, spec and review file is `YYYY-MM-DD-descriptive-slug.md`.

Terms used below. A **spec review** is the review a specification gets before any code is written. A **finding** is one defect the reviewer names. The **Disposition** is the section where the author answers each finding. The **verdict** is the reviewer's one-sentence decision. A **round** is one exchange: the reviewer writes, the author answers, the reviewer signs again. A **fresh reviewer** is an agent or a person who did not write the spec and has not seen the author's reasoning.

---

## What the sources say

### wasi-python (the sibling project)

- READ. One file per review, under `context/reviews/`. A review of a spec before it is built carries `-spec` in its name; a review of code carries `-pr`. The README's naming is numbered (`NNN-slug-spec-DATE.md`); the owner's ruling for vfs replaces the number with a leading date (below).
- READ. The reviewer is "a fresh agent or a person who did not write the change", given "the specification and the change, not the author's summary" (constitution §5.6). The `Reviewer:` line names a session URL or a person, and a sub-agent writes "a fresh sub-agent of <session>; not the author". A `Reviewer:` line that names the author is refused by the CI check.
- READ. **No confirmation round.** The author answers in writing. A fix is a new commit; the reviewer reads it and signs again. A finding ranked Low, or a note, is answered by the author with no further round when the answer is in writing. The reviewer may write a Low that touches only `context/` in itself.
- READ. The checklist has a **time box** (25 minutes for a small spec, 45 for a build-class or structural one), and the review states its box and where it stood when the box ran out. 141's header: "45 minutes…; kept, 07:20 to 07:58". 150's: "45 minutes (structural), 00:16 to 01:01".
- READ. Every claim is labelled **EXECUTED, READ or INFERRED**. 150 defines the labels in its own header: "EXECUTED means I ran it; READ means I read the file cited; INFERRED means my reasoning."
- READ. The template's sections: header lines (Date, Reviewer, Reviewed, Run, Re-ran), "Acceptance criteria against evidence", "Findings, most severe first", "Constitution checks", "Disposition (filled in by the author, then confirmed by the reviewer)", "Verdict".
- READ. For a pre-build review the `Run:` line says "none (a pre-build review)" and the `Re-ran:` line lists the probes the reviewer ran against the live tree (141 ran `ls -led` on sixteen folders; 150 ran the structural measurements and the rules check).
- READ. A pre-build review judges each acceptance criterion "for whether it is countable as written" (150), since there is no build to judge against.
- READ. 141 opens with a section the template does not have: "The questions the brief asked, answered first". The orchestrating session had asked the reviewer ten questions about the draft (is Decision 3 right, is the Kind line right, do the rows count operations, do the warning texts act, are the dependencies ordered). The reviewer answered them one by one before the criteria. This is the author asking the reviewer to look hardest where the author was least sure; it did not leak the author's answer.
- READ. **Ranking**: High (a wrong answer or an unsafe default), Medium (a guarantee not evidenced), Low (a write-in with its fix text). "One Medium per review is normal; state what evidence would close it." A Low carries its fix text in the finding itself, so the author can paste it.
- READ. Findings cite the spec by line (`…/141-….md:90`) and the live code by `path:line`. Each Low in 141 ends in "Fix text: …" — the exact sentence the spec should carry.
- READ. **The Disposition** is one numbered line per finding, written by the author: "M1 — fixed in `1238ffdc`: …" or "kept, with the reason the fix text allows for: …". The reviewer appends "READ, confirmed" to each line, or a precision "for the builder, no round".
- READ. **The verdict vocabulary** of a spec review: "Fit to build" or "Not yet: <the finding>". 150 wrote "Not yet: Finding 1, …; the structure holds once it is fixed", then a dated second line: "2026-10-28, re-read on `5955ee4b`: Fit to build." 141 wrote the final verdict first and the earlier one under it: "Before the amendment (2026-10-28, on `9b83c6c4`): fit to build once M1 is answered…". A verdict that begins "Fit to build" is the reviewer's signature on that commit of the spec.
- READ. How the spec cites the review. 150's Status line: "It is **structural**, so it is reviewed before it is built against the eight rows…". 141's `Research it stands on:` line cites the review of 135 by path and finding ("L2, `../reviews/135-…-spec-2026-10-25.md:45`"). 150's design section says "The pre-build review scores these; this is how the design keeps each", and a goal row names "the pre-build review's Finding 1" as its source. The landing notes cite the pull-request review by path and list the disposition of its findings. So a finding has a life after the review: it becomes a sentence in the spec, a test row, or a reserved line in the roadmap.
- READ. A structural spec (one that moves a module past its ceiling, adds a module-level mutable, a platform branch, a test seam) gets a "Structure" section in its spec review: the eight rows of the structural rubric, one line each, with the measurements before and after. The judge (a test) holds that "a built structural specification cites that review".
- READ. Which specs get a spec review there: ones that change the guest's imports or exports, the artifact set, the build recipe, or are structural. Every other spec gets only the code review. vfs's intention is broader: **every** spec is reviewed before it is built.

### vfs's own practice (today)

- READ. `context/README.md`: "Never silently guess. The marker `[NEEDS CLARIFICATION: …]` is a first-class citizen, should be surfaced in reviews, and gets a pointer in `open-questions.md`." The intention retires open questions in a spec: "A specification decides every choice it needs."
- READ. The seven skills review **code**, not specs, but three of their rules carry straight over. (a) Every skill ends with a **close-out ledger**: "what was checked and found clean, so a clean audit is distinguishable from an unfinished one" (scale_review §8, contract_review §7). (b) Evidence standard: a finding quotes "both sides of the disagreement" with `file:line` (contract_review §6); a scale finding names "the statement or loop, the variable that grows with batch size, and the specific cap it can exceed" (scale_review §7). (c) `verify_findings` bans hedged verdicts: "CONFIRMED, REFUTED, or DOWNGRADED… 'Probably a bug' reaching the reader is the exact failure this gate exists to prevent."
- READ. The code review's shared severity scale is `critical / major / minor / question`; scale_review's own is Blocker / Major / Minor; the spec-review studies used "blocking / should fix / nits".
- READ. The agent-shell set has five "review before build" studies (167 to 171), each written as a research study, not as a review file. Study 12 (spec 167) has: a "What I read" header, evidence labels, scripts under `experiments/r167/`, a Verdict ("The spec is not ready to build. The direction is right."), a **readiness score** table of eight weighted dimensions (every behaviour precise enough to test; consistent with the ADRs; consistent with the live tree; internally consistent; nothing left for the developer to invent; bounded at scale and honest about profile; acceptance criteria countable and never clocks; sized for one landing and sequenced green), 21 findings most severe first, "What the spec gets right", and "Questions only Clay can answer".
- READ. Spec 164 records the outcome as a section "Amendments from the pre-build review (2026-10-14)", and says the review itself "is in the session scratchpad, not the repo". That is the gap the intention closes: the review was lost; only its residue survived.
- INFERRED. The readiness-score table was useful once but is heavy for every spec. Its eight dimensions are a good checklist; the weights and the /100 score add work without adding a decision. The verdict is binary (fit or not yet); a number invites argument about 48 versus 55.

### Online prior art

- READ (Ubl, "Design Docs at Google"). The review stage sits between "creation and rapid iteration" and "implementation". The doc carries goals and non-goals, the design centred on trade-offs, alternatives considered, and cross-cutting concerns (security, privacy, observability). Reviewers write in comment threads in the document. The rule for when a design doc is needed: when the solution is ambiguous; "implementation manuals" without trade-offs need none. Implementation starts "once there is confidence that further reviews are unlikely to require major design changes". Lesson: the review is of the trade-offs, not the prose; and the review should not block for a meeting.
- READ (Kubernetes PRR). A KEP (an enhancement proposal) cannot move to `implementable` for a release until a Production Readiness Review approves it, "done by a separate team, apart from the SIG leads", by a named approver recorded in a file per KEP and per stage. The author answers a questionnaire in the KEP itself under fixed headings: Feature Enablement and Rollback, Rollout/Upgrade/Rollback Planning, Monitoring Requirements, Dependencies, Scalability, Troubleshooting. The scalability questions are concrete: new API calls, more or larger objects, slower SLOs, more CPU/RAM/disk. Lesson: the **author fills a questionnaire inside the spec** and the reviewer checks the answers; the approver's name is a file, so a check can hold it.
- READ (Oxide RFD 1). An RFD moves prediscussion → ideation → discussion → published → committed → abandoned. Discussion happens on a pull request named in the header's `discussion:` field; the author merges after about three to five business days of comments; "RFDs should not be merged unless others have read or commented on them"; published means "consensus or direction", and the doc stays open to correction. Lesson: the state and the link to the discussion live in the document's own header, so a reader of the doc can find the review.
- READ, partial (Klein, premortem). The HBR preview gives the core: the team "assume[s] that the project they are planning has just failed" and generates reasons; its purpose is to make it safe to voice doubts. INFERRED from memory of the full article: each person writes reasons independently for a few minutes, the reasons are read out and ranked, and the cited research (prospective hindsight) raised the number of correctly identified reasons by about 30%. Lesson: a reviewer should spend one step imagining the spec was built and failed, and name why.
- READ (Nygard, ADR). An ADR has Title, Context, Decision, Status, Consequences; one to two pages; status moves proposed → accepted, later deprecated or superseded; the old record is kept. The only review is "stakeholder agreement". Lesson for vfs, where decisions now live inside the spec: each Decision needs the same three parts, a context, the choice, and its consequences, and the spec reviewer checks all three exist.
- READ, secondary (Amazon narrative). Accounts agree: a four-to-six-page prose memo, read in silence at the start of the meeting (15 to 30 minutes), questions only after everyone has read, often no single author's name, a decision owner named in the header. Lesson: the reviewer reads the whole spec before writing one finding, and reads it alone.

---

## What vfs does today

- Spec reviews happen, but as research studies or in a session scratchpad, and only for big specs (the agent-shell set, 164). Their shape varies by session. One of them (164) is gone from the repo; its amendments list is all that remains.
- The code-review skills are strong and have a shared evidence standard, a close-out ledger and a verifier gate; none of that is applied to a spec yet.
- A spec has no fixed line that names its review, so nothing can hold "a built spec cites its review".
- Open questions are allowed in a spec (`[NEEDS CLARIFICATION]`); the intention ends this.
- The constitution's five primitives (Namespace, Entry, Candidate, Mount, Revision; Article 1) and the production posture (`CLAUDE.md`) are checked by the scale and contract lenses on code, never on a design.
- The architecture pages say "a spec author starts here to find the diagram the spec will change, and ends here by changing it", but no review checks that the spec carries the diagram.

---

## The recommended format

One file per review, under `context/reviews/`. The file name carries the review's own date, the spec's slug, and the word `spec` so a listing sorts by day and reads what was reviewed:

`context/reviews/YYYY-MM-DD-<spec-slug>-spec-review.md`

The code review of the same spec is `YYYY-MM-DD-<spec-slug>-code-review.md`. The spec's slug is the slug of the spec's own file name after its date (`2026-10-30-the-ranged-read.md` → `the-ranged-read`). A second spec review of the same spec on a later day is a new file with the new date; the older file stays. No numbers anywhere in the name.

The review names the spec by **relative path** in its header, never by a number. The spec names the review by relative path in its landing notes.

```markdown
# Spec review: <spec title>

- **Date:** YYYY-MM-DD
- **Reviewer:** <a person, or "an agent (<model>), a fresh sub-agent of <session URL>; not the author">
- **Reviewed:** `../specs/active/YYYY-MM-DD-<spec-slug>.md` at `<commit>`, with <the intention, the research memos and the architecture pages it cites>
- **Brief:** <what the reviewer was given: the spec, the intention, the research it cites, the diagram pages, the constitution, CLAUDE.md, the live tree read-only; and that it was not given the author's summary>
- **Re-ran:** <each probe against the live tree, one line, with what was seen> / none
- **Box:** <25 or 45> minutes; <kept, HH:MM to HH:MM / ran out at step N, what was not reached>

Labels: EXECUTED means I ran it; READ means I read the file cited; INFERRED means my reasoning.

## The questions the brief asked, answered first
1. <the author's question> — <the answer, with its label>

## Decisions, one line each
1. Decision 1 — <holds / does not hold: why>, with the constitution article or the research line it rests on

## Acceptance criteria, countable as written
1. <criterion> — countable / not countable: <what it counts, or what it lacks>

## The diagram and the scope
- Diagram: <which architecture page it redraws; every touched component shown; built and planned marked; matches the design>
- Scope: <one landing / not one landing: why>
- Depends on: <each dependency named with its state, or "none">

## Scale and the production posture
- <each statement, loop or structure that grows with input, and the bound it declares; or "nothing grows with input">

## Constitution checks
- Article 1 primitives: <which of the five it touches, and whether it manipulates or composes them without adding a sixth>
- Articles 2 to 5: <each one touched, and whether it holds>
- CLAUDE.md posture: <the 10,000-row batch, the least generous engine, no unbounded statement, no numpy, no designed cap>

## Premortem
<three lines: the build is done and failed; the three most likely reasons; which finding each becomes, or why none>

## Findings, most severe first
1. **H1. <title>** (`../specs/active/…md:<line>`) — <the defect in one sentence>.
   Consequence if built: <what the code would carry>.
   Fix text: <the sentence the spec should carry, when the reviewer can write it>.
2. **M1. …**
3. **L1. …**

## Checked and found clean
<the sections, decisions and criteria read and passed, so a short findings list is not mistaken for a short read>

## Disposition (filled in by the author, then confirmed by the reviewer)
1. H1 — fixed in `<commit>`: <what the spec now says> / kept because <reason>. — READ, confirmed. / Not confirmed: <why>.

## Verdict
<Fit to build. / Not yet: <the High, or the Mediums>.> — in one sentence, on `<commit>`.

<On each later signature, a dated line below the first: "YYYY-MM-DD, re-read on `<commit>`: Fit to build.">
```

The verdict vocabulary has two words and no third:

- **Fit to build** — nothing High or Medium stands. The developer may start. This line is the reviewer's signature on that commit of the spec.
- **Not yet: <the finding(s)>** — a High or a Medium stands. The spec is amended, and the reviewer signs again.

"Fit to build once <X>" is not a verdict; it is "Not yet: X" with the fix in the Disposition. A verdict that hedges ("probably fine", "mostly ready") is refused, as `verify_findings` refuses "probably a bug".

---

## The reviewer's checklist for a spec

The time box is 25 minutes for a spec that touches one module and no engine behaviour, 45 minutes for one that touches the storage backend, a verb's contract, the public surface, or more than one architecture page. The review states its box and where it stood when the box ran out. A box that runs out is not a verdict; it is a note, and a second reviewer may pick up where the first stopped.

1. **Read the brief's questions first.** The author may hand the reviewer one to ten questions about the draft (the places it was least sure). Answer each, labelled. Do not read any answer the author proposed; the brief carries questions, not answers.
2. **Read the whole spec once, silently, before writing a finding.** Then the intention it serves, the research memos it cites (by the lines it cites), and the architecture pages it names.
3. **Decisions.** Each decision in the spec is numbered and has three parts: the forces, the choice, the consequences. Check each holds against the research line or the constitution article it rests on. A decision with no reason is a Medium. A decision that contradicts an earlier landed spec or a standard, without saying it supersedes it, is a High.
4. **No open questions.** The spec carries no `[NEEDS CLARIFICATION]`, no "TBD", no "to be decided at build time". Each choice the developer would otherwise invent (a default, an error class, a chunk size, a name) is decided. An undecided choice is a High: the build would decide it silently.
5. **Acceptance criteria.** Each criterion is countable as written: it names a test, a count, a file, a diff, or a command and its exit code. It never names a clock. A criterion that is a wish ("fast enough", "works at scale") is a Medium.
6. **Scope.** The spec is one landing: one commit to `main`, by one developer, green at the end. A spec that is four landings is a Medium (sizing), with the cut proposed. The tests the spec names are sequenced after the code they need exists.
7. **The diagram.** The spec carries an architecture diagram of the components it touches, drawn the way `context/architecture/` draws them, and names the page it will change. Every component the design section names appears in the diagram, and nothing in the diagram is missing from the design. A missing diagram is a Medium; a diagram that disagrees with the design is a High.
8. **Scale posture.** For each statement, loop or in-memory structure the design adds: what grows with input, and what bounds it. The bound is the declared budget (`membership_budget`, `chunked()`), not a hardcoded size. The engine floor is the least generous supported engine (Oracle's 1,000-element `IN` list, SQL Server's ~2,100 binds), never SQLite. A 10,000-file batch is a supported call. Anything unbounded is a High. A suboptimal profile that is named honestly, with its future direction, is not a finding.
9. **The constitution.** Article 1: which of the five primitives (Namespace, Entry, Candidate, Mount, Revision) the spec manipulates or composes; a sixth first-class thing is a High. Articles 2 to 5 as touched. `CLAUDE.md`'s posture: no numpy, no designed scale cap, no pure-Python fallback for a hot path, imports at the top, `assert` narrows and never validates.
10. **Dependencies.** Every spec this one builds on is named with its state (landed at a commit, or active and not yet built). A spec that assumes a dependency's shape that the live tree does not have yet is a Medium, with the order of builds proposed.
11. **The live tree.** One to three probes, by command or by `path:line`, that the spec's claims about today's code are true (the function exists, the seam is where the spec says, the test file is named right). A claim that is false against the tree is a Medium, or a High when a decision rests on it.
12. **Premortem.** Spend three minutes: the spec was built as written and failed in production or in review. Write the three most likely reasons. Each becomes a finding or a line in "Checked and found clean".
13. **Rank, write the fix text, write the ledger, write the verdict.** Each Low carries its fix text so it needs no round.

---

## The ranking

- **High** — a wrong design the build would carry: a decision that breaks the constitution or an earlier standard without superseding it; a statement that grows without bound with batch size; a choice left for the developer to invent. Example: "Decision 4 reads every row's lineage with one `IN (...)` list the size of the batch; nothing chunks it, so a 10,000-file write fails on Oracle." The spec is not fit to build until it is fixed.
- **Medium** — a guarantee not evidenced: a criterion that cannot be counted; a dependency not named or named in the wrong state; a diagram missing; a claim about the live tree that is false. Example: "Criterion 3 says 'the sweep stays fast under load'; nothing says what is counted." The reviewer states what evidence would close it. One Medium per review is normal.
- **Low** — a write-in: a sentence the spec should carry, given in the finding as fix text. Example: "Decision 7's error name is `NotFound` in one place and `not_found` in another; fix text: `not_found`, the classified fact's name." A Low needs no round.

A **note** (no rank) is an observation with no fix the spec must take.

---

## The rounds

There is no confirmation round, as in wasi-python; there is a **disposition** and a **signature**.

1. The reviewer writes the review file with its verdict and commits nothing; the author commits it (the review is the author's to carry, the reviewer's to sign).
2. The author answers every finding in the Disposition section of the review file, one line each: "fixed in `<commit>`: <what the spec now says>" or "kept because <reason>". A High or a Medium is fixed in the spec, in a commit that touches the spec and the review file only.
3. The reviewer (the same fresh agent, resumed, or a person) re-reads the amended spec against each Disposition line, appends "READ, confirmed" or "Not confirmed: <why>", and writes a new dated verdict line: "YYYY-MM-DD, re-read on `<commit>`: Fit to build." The first verdict stays above it. A Low answered with its fix text is confirmed by reading, never by a round.
4. The spec's `Status:` line says "reviewed YYYY-MM-DD (`../reviews/YYYY-MM-DD-<slug>-spec-review.md`), fit to build at `<commit>`". The build starts from that commit.
5. **A review is redone** (a new file, a new date) when a Decision changes after "Fit to build", when the spec's scope grows, or when the first reviewer's box ran out before the checklist's step 9. A change to wording, a criterion's count, or a test name after "Fit to build" is recorded in the Disposition of the same file, not a new review.
6. A finding the author keeps against the reviewer's rank goes to the owner in one line in the Disposition; the owner's word in the spec's Decisions closes it.

---

## How a fresh reviewer is briefed

The reviewer **gets**:

- the path of the spec and the commit to read it at;
- the intention it serves, the research memos it cites, and the architecture pages it names (by path);
- `context/standards/constitution.md`, `CLAUDE.md`, and the reviews README (the checklist and template);
- the live tree, read-only, and the scratchpad for probes;
- the author's **questions** (where the author was least sure), as questions;
- the time box.

The reviewer **must not get**:

- the author's summary of the spec, or any paraphrase of what it decides;
- the author's session transcript, the author's reasoning, or the plan that produced the draft;
- a hint of the expected verdict ("should be a quick one", "I think it is ready");
- the author's proposed answers to its own questions;
- write access to the spec, `src/` or `tests/`.

The `Reviewer:` line names the session or person, and a sub-agent writes "a fresh sub-agent of <session>; not the author". A `Reviewer:` line that is empty or names the author's session alone fails the lint rule below. As in wasi-python, this is a process guard, not an identity guard.

---

## A lint rule

A test under `tests/` (run by `scripts/ci.sh`) holds, for every spec whose `Status:` line says built or landed:

1. its landing notes cite, by relative path, one file under `context/reviews/` whose name ends in `-spec-review.md` and one that ends in `-code-review.md`, and both files exist;
2. the spec review's `Reviewed:` line names the spec's own path;
3. the spec review's `Reviewer:` line is not empty and does not name the author named in the spec's `Author:` or `Built by:` line;
4. the last verdict line of the spec review begins "Fit to build", and the Disposition has one line per finding;
5. no file under `context/specs/`, `context/intentions/` or `context/reviews/` has a name that begins with a number; every one begins with `YYYY-MM-DD-`.

A spec with `Status:` drafted is not held to rule 1; it is held to rule 5 and to "no open question" (the intention's third done-when).

---

## One line

A spec review is one dated file, written by someone who did not write the spec and was not told what to think, that checks every decision, every criterion, the diagram, the scale posture and the constitution, ranks what it finds High, Medium or Low with fix text, lets the author answer in the same file, and ends in two words: "Fit to build" or "Not yet".
