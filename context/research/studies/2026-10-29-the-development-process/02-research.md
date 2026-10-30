# Stage 2, research: the memo, its studies, and the rules that hold their shape

This is a study for [the development-process memo](../../2026-10-29-the-development-process-seven-studies-and-what-they-recommend.md), owned by Clay Gendron; it was read-only, no file outside this one was edited and no git state changed. Its question: what format should a research memo and its study files take, what rules govern them (labelling, time boxes, placeholders, supersession), and what lint rule can hold the shape? Its method: three passes in a 30-minute box. (1) vfs's own conventions: `context/README.md`, `context/research/README.md`, the headers of four recent memos and one studies folder with its brief, plus counts over all 154 memos (EXECUTED, `grep`). (2) The sibling project wasi-python at `1431ba6f` (`~/Git/Repos/wasi_python`, read-only, dirty only by untracked `.agents/`, `skills-lock.json`, `snapshot_demo.py`): its `context/README.md`, `constitution.md` §5, the lint test `tests/lint/test_writing_conventions.py` and its helper `tests/harness/scan.py`, one executed memo and one placeholder memo. (3) Online prior art, read 2026-10-29: Oxide's RFD 1, the Rust RFC template, the Google design-doc essay, the XP spike, and lab-notebook guidance. Nothing was copied from any source; every description is in my words. The box ran out while writing §5; §5 and §6 are complete but shorter than §3.

## Sources

- vfs: `context/README.md`, `context/research/README.md`, `context/research/2026-10-24-what-ostep-teaches-vfs-eight-studies-and-what-changes-in-the-kernel-plan.md`, `context/research/2026-10-23-a-filesystem-shaped-kernel-for-vfs-prior-art-and-the-recommendation.md`, `context/research/2026-10-23-wasi-python-0-1-0-over-vfs-the-mount-and-the-tool-door.md`, `context/research/2026-10-15-the-agent-shell-prior-art-and-experiments.md`, `context/research/studies/2026-10-28-the-0-1-0-roadmap-audits/00-brief.md` and `07-release-ci-and-repo-hygiene.md`, `context/intentions/2026-10-29-the-development-process.md`.
- wasi-python: `context/README.md`, `context/constitution.md`, `tests/lint/test_writing_conventions.py`, `tests/harness/scan.py`, `context/research/2026-10-24-what-output-capture-costs.md` (executed), `context/research/2026-10-17-what-a-replayable-run-needs.md` (placeholder), `context/research/2026-10-18-a-cap-on-open-files.md` (a completed memo that began as a placeholder).
- Web: `https://rfd.shared.oxide.computer/rfd/0001`, `https://github.com/rust-lang/rfcs/blob/master/0000-template.md`, `https://www.industrialempathy.com/posts/design-docs-at-google/`, `https://en.wikipedia.org/wiki/Spike_(software_development)`, NIH OIR "best practices: keeping an ELN" (PI and trainee slides, via search summary only; the PDF did not render).

Labels used below: **READ** means I read it in a file or page named here. **EXECUTED** means I ran a command here and report its output. **INFERRED** means my own reasoning from the two.

## 1. What the sources say

### 1.1 vfs today

- READ: `context/README.md` says `research/` is append-mostly, date-prefixed `YYYY-MM-DD-slug.md`, never edited after the fact, superseded by a newer memo, and commits the project to nothing. It also says every document has a frontmatter-free header: title, status, date, owner. It names the `[NEEDS CLARIFICATION: …]` marker as a first-class citizen with a pointer in `open-questions.md`.
- READ: `context/research/README.md` repeats append-mostly, adds "a memo should be re-readable by a future reader who has forgotten the original context", and says decisions cite memos. It says nothing about labels, time boxes, placeholders or studies folders.
- READ: `CLAUDE.md` "Project memory" says the research stage means new investigation, not transcription: a memo is produced by gathering new findings, never by recording in-session reasoning or restating a decision.
- READ: the four recent memos share a header of six bold lines: Status, Date, Owner, Question, Method, Sources. The Status line always says "commits us to nothing" and names what the memo feeds. The Question line quotes Clay with a date. The Method line names the studies folder, says every claim is labelled READ, EXECUTED or INFERRED, and says no code was copied. The Sources line lists the study files by name and the clones by commit and licence.
- READ: the kernel memo of 2026-10-23 carries two **Revised** lines at its head and says its §0, §4.1 and §4.3 "are corrected below". So the memo was edited in place after the fact, twice, against the README's rule. The edits are dated and honest, but the rule and the practice disagree.
- READ: the studies folder `2026-10-28-the-0-1-0-roadmap-audits/` holds `00-brief.md` and files `01-` to `12-`. The brief has a Status, Owner and Method header, a "why a study set and not a memo" paragraph, the brief every agent received as a block quote, and a table of files with a one-line "executed findings worth knowing" column. Each study is self-contained, states the commit it audited and "Labels: READ / EXECUTED / INFERRED" in its head, and labels each claim inline, often in a heading ("§1.1 CI workflows — READ").
- READ: the OSTEP and kernel memos cite their studies as `S01`…`S08` after naming the files once in the Sources line. The agent-shell memo does the same.
- READ: the agent-shell studies folder has two files numbered `12-` and two numbered `13-` (`12-python-anywhere.md` and `12-spec-167-review-before-build.md`; `13-wasi-python-spike.md` and `13-spec-168-review-before-build.md`). Later reviews were added to a folder whose numbers were already taken.
- EXECUTED: of 154 memos in `context/research/`, 23 carry at least one READ, EXECUTED or INFERRED label; 75 have no `Question` line; 95 have no `Method` line. The labels arrived around 2026-10-15 and are the norm since.
- EXECUTED: vfs's `tests/` has no test that reads `context/`. Nothing holds a memo's shape today.
- READ: vfs memos hard-wrap prose at about 72 columns (the OSTEP memo has 36 lines over 100 characters, all tables or paths). wasi-python forbids the hard wrap (see 1.2).

### 1.2 wasi-python at `1431ba6f`

- READ, `context/README.md` line 34: `research/` is append-mostly, date-prefixed, never edited after the fact, superseded by a newer memo. A memo is produced by actually gathering new findings: executed builds, measured runs, studied sources. Every claim is labelled EXECUTED, READ or INFERRED. Count operations; report wall-clock as a benchmark fact, never as a test assertion. A memo commits to nothing. A **placeholder** memo, whose Status line says so, is the one exception to "never edited": it holds a question, the experiment that answers it and what it blocks, and is completed in place when the work is done.
- READ, line 27: there is no list of open questions. A spec is written without them. What is not yet known becomes a placeholder memo; the spec that needs it waits.
- READ, `constitution.md` §5 item 2: "No open questions." Same rule, one sentence, with "there is no backlog of undecided things."
- READ, §5 item 3: "Time boxes are real." A research task states its box. At the box the agent stops, records exactly where it stood and why, and reports. A blocked step is skipped, not forced.
- READ, the executed memo `2026-10-24-what-output-capture-costs.md`: header lines are Status (with the date in it, what it attributes, what it changes, which spec it feeds, and "every number is wall-clock on one machine: a benchmark fact, never a check"), Owner, Researcher (which agent and model, and the box), Evidence (a folder of the same name beside the memo: driver, summarizer, results), Stands on (the source files and clones read, with commits), Machine (hardware, OS, interpreter, runtime, artifact set, commit). Then one line defining the three labels. Then "The short version" as a numbered list, then numbered sections, each labelled in its heading or inline.
- READ, the placeholder memo `2026-10-17-what-a-replayable-run-needs.md`: header lines are Status ("placeholder, 2026-10-17"), Owner, Researcher (who raised it and from which review), Feeds (the spec that will use the answer), Blocks (which spec waits and which does not). Then "## The question" as one paragraph, then "## What is known" with labels, then what would answer it.
- READ, `2026-10-18-a-cap-on-open-files.md`: a memo that started as a placeholder and was completed in place. It carries a "## Labels" section that says what EXECUTED meant on that machine, which worktree and commit, where the scripts sit, and that a prototype diff was applied, measured and reversed and nothing of it committed.
- READ, the evidence layout: `context/research/<memo-slug>/` is a folder beside `<memo-slug>.md` with the same name, holding `driver.py`, `summarize.py` and `results/*.json` plus `results/summary.txt`. There is no `studies/` subtree; a memo's evidence sits beside it. There is no numbered study file: one memo, one researcher, one folder.
- READ, `tests/lint/test_writing_conventions.py::test_executed_memos_label_their_claims`: for every `*.md` under `research/`, it collects `scan.memo_label_errors` and fails on any.
- READ, `scan.memo_label_errors`: it reads the file, finds the Status line (`- **Status:**` at line start, lower-cased), and returns no error if the word "placeholder" is in it. Otherwise it searches the whole text for a whole-word EXECUTED, READ or INFERRED and returns one error naming the file if none is found. That is the whole check: one label anywhere in the file, or a placeholder status.
- READ, the neighbouring helpers: `strip_code` removes fenced blocks and inline code before scanning; `open_question_hits` flags `TBD`, `TODO`, "open question" and any heading containing "question" (used on specs, not memos); `spec_shape_errors` requires each header field as `- **Field:**` and each section as `## Section`; `status_line` is the shared Status reader.
- READ, `test_markdown_paragraphs_are_one_line_each`: every Markdown paragraph under the knowledge tree is one line; a `wrap.py --fix` joins hard-wrapped lines. Reason given: a renderer joins the lines anyway, and a wrap makes every edit re-flow its neighbours.
- READ, `test_src_names_no_context_document` and friends: code never names a spec, memo, review or `context/` path; the citation runs the other way, from document to file.
- INFERRED: wasi-python's shape is "one memo, one folder beside it"; vfs's shape is "one memo, a numbered studies folder under `studies/`". Both work. vfs's shape fits the fan-out of many parallel agents; wasi-python's fits one researcher with scripts.

### 1.3 Online prior art (read 2026-10-29)

- READ, Oxide RFD 1: a Request for Discussion carries four metadata fields (authors, state, discussion link, labels) and moves through six states: prediscussion, ideation, discussion, published, committed, abandoned. "Committed" means the thing is built and the document now describes how the system works. A published RFD may be revised by a fresh branch and pull request per logical change; a large departure from a committed design calls for a new RFD. Numbers are taken from the next free branch. Note: RFDs are decisions-plus-research in one document; vfs separates the two.
- READ, the Rust RFC template: Summary, Motivation, Guide-level explanation, Reference-level explanation, Drawbacks, Rationale and alternatives, Prior art, Unresolved questions, Future possibilities. "Prior art" asks for experience from other communities, successes and failures both. "Unresolved questions" asks what the process must settle, what implementation will settle, and what is out of scope. Note: an RFC is a proposal; its prior-art section is the part that is research.
- READ, the Google design-doc essay: context and scope, goals and non-goals, the design (trade-offs, not implementation), alternatives considered, cross-cutting concerns. Skip the doc when there are no real trade-offs; a prototype can replace a doc when the problem is unclear. Docs go stale; amendments go in separate linked documents rather than edits. The author calls a doc with no alternatives an implementation manual.
- READ, XP spike (Wikipedia): a spike is a small throwaway program written to answer one question, time-limited so exploration does not drag on; the findings are shared with the team afterward. The page did not say the code is discarded; the XP site, which does, could not be fetched (certificate error). INFERRED from vfs's own practice: the spike's scripts are kept as evidence, the spike's code never enters `src/`.
- READ, via search summary of NIH's ELN (electronic lab notebook) guidance: an entry carries date, title, goal, methods, observations and raw data, then analysis and interpretation as a separate heading, then next steps. The test of an entry is whether another trained person could repeat the experiment from it. The PDF itself did not render through the fetch tool, so this is READ at one remove.
- INFERRED: the lab notebook's split of observation from interpretation is exactly the READ/EXECUTED versus INFERRED split. The notebook's "never erase, amend with a dated note" is exactly "append-mostly, supersede with a newer memo".

## 2. What vfs does today, and what is already good

What is already good and should be kept:

- The six header lines (Status, Date, Owner, Question, Method, Sources) are stable across the four most recent memos and read well. The Question line quoting Clay with a date is the single best feature: a future reader learns what was asked, by whom, and when.
- The three labels are in use and understood. Studies label claims inline and sometimes in headings.
- The studies folder with a `00-brief.md` that holds the brief verbatim, a file table, and the "why a study set and not a memo" paragraph is a strong shape. It makes the fan-out auditable: a reader can see what each agent was told.
- Clones are refreshed, licence-checked, and cited by commit. `refresh.log` and `licenses.log` sit in the folder.
- Experiments live under `experiments/<id>/` beside the studies, so scripts and outputs outlive the session.
- The "commits us to nothing" sentence in every Status line is right and should stay.

What is not yet held by any rule:

- Nothing checks a memo's shape. 95 of 154 memos have no Method line; 131 of 154 carry no label. The convention is a habit, not a gate.
- The "never edit after the fact" rule is broken by the memo that most needed it (the kernel memo, revised twice in place). The practice is honest, but the rule has no exception written for it.
- There is no placeholder memo in vfs. The intention says there will be ("what cannot be decided yet becomes a placeholder research memo"), and `open-questions.md` is still the intake. These two cannot both stand.
- No memo states its time box. Studies agents receive a box in the prompt, but the memo does not record it or where the agent stood at the box.
- Study numbering has collided once (the agent-shell folder). Reviews were appended to a research folder, which the new process moves into its own review stage anyway.
- Memos hard-wrap at 72 columns. That is a choice, not a fault; but it fights a line-based lint and makes diffs noisy. wasi-python's one-line-paragraph rule is the alternative.

## 3. The recommended format

Four skeletons. Each is complete Markdown. Field names are fixed so a lint can find them; the prose inside is free. File names follow the owner's ruling of 2026-10-29: a document is `YYYY-MM-DD-descriptive-slug.md`, never numbered, and documents link to each other by relative path. Study files inside a studies folder keep a two-digit order prefix because that is reading order, not identity.

### 3.1 A research memo

The memo is the synthesis. It answers one question Clay asked. It stands on studies and experiments, cites them by path, labels its own synthesis INFERRED, and commits to nothing.

```markdown
# <A title that states the finding, not the topic>

- **Status:** research memo (commits us to nothing). Feeds `../specs/<YYYY-MM-DD-slug>.md`; or "feeds no spec yet".
- **Date:** YYYY-MM-DD
- **Owner:** Clay Gendron
- **Researcher:** <agent and model, or a person>. Box: <the time box stated at the start>.
- **Question:** <who asked, on what date, in their words or a faithful paraphrase>.
- **Method:** <what was done: how many studies, which clones at which commits, which experiments ran and where their scripts sit; "no code copied"; which steps were skipped at the box and why>.
- **Sources:** <the study files by path under `studies/<YYYY-MM-DD-slug>/`; the clones by name, commit and licence; the web pages by URL and read date>.
- **Supersedes:** <path of the memo this replaces, or "nothing">.

Labels: EXECUTED means run here and reported from its output; READ means read in a file or page cited by path or URL; INFERRED means the researcher's reasoning from the two.

## 0. In one paragraph

<The answer, as plain sentences. Label the paragraph INFERRED if it is synthesis.>

## 1. <First finding> (READ | EXECUTED | INFERRED)

<Each claim carries a label inline or in its heading. Cite a study as `S01` after naming its path once in Sources.>

## 2. <Second finding>

…

## N. What this memo does not settle

<Each item names the placeholder memo or the experiment that would settle it, by path. Never the words "open question".>

## One line

<The finding in one sentence.>
```

### 3.2 A placeholder memo

A placeholder memo is a research memo that holds a question instead of an answer. It is the only memo that is edited in place: when the research is done, the placeholder is completed and its Status line changes. It exists so that a spec can decide every choice it needs and the undecided thing has an owner, an experiment, and a named victim (the spec that waits).

```markdown
# <The question as a title>

- **Status:** placeholder, YYYY-MM-DD. Completed in place when the research is done.
- **Date:** YYYY-MM-DD
- **Owner:** Clay Gendron
- **Researcher:** <who raised it, from which document: `../specs/<slug>.md` or `../reviews/<slug>.md`>.
- **Feeds:** `../specs/<YYYY-MM-DD-slug>.md` (the spec that will use the answer).
- **Blocks:** <which spec waits on this, and which does not>.
- **Box:** <the time box the research will have when it starts>.

## The question

<One paragraph. What must be known, stated so a reader can tell when it is answered.>

## What is known today

<Labelled claims, usually READ or EXECUTED from the review or session that raised the question. If nothing, say "nothing yet".>

## The experiment that answers it

<Steps, inputs, what to count. Count operations, never wall-clock as a check.>
```

### 3.3 A study file

A study is one agent's or one person's report inside a fan-out. It is self-contained: a reader who opens only this file learns what was asked, against which commit, and what was found. It never cites a sibling study it did not read. Its file name is `NN-descriptive-slug.md`, where `NN` is reading order.

```markdown
# <Title stating the finding>

- **Status:** study for `../../<YYYY-MM-DD-memo-slug>.md`. Read-only; nothing outside this file edited; no git state changed.
- **Date:** YYYY-MM-DD
- **Owner:** Clay Gendron
- **Researcher:** <agent and model>. Box: <the box, and where the researcher stood at the box>.
- **Question:** <the one question this study answers>.
- **Method:** <what was read, at which commit; what ran; what was skipped>.
- **Sources:** <files by path and commit; clones by commit and licence; URLs with read date>.

Labels: EXECUTED, READ, INFERRED as defined in `00-brief.md`.

## 1. What the sources say

<Labelled claims, one per bullet or paragraph.>

## 2. What vfs does today

<Labelled, with `file:line`.>

## 3. The recommendation

<INFERRED, kept apart from §1 and §2 so a reader can weigh the evidence before the opinion.>

## One line

<The finding in one sentence.>
```

### 3.4 The studies folder and its `00-brief.md`

```text
context/research/
  YYYY-MM-DD-descriptive-slug.md          # the memo, the synthesis
  studies/
    YYYY-MM-DD-descriptive-slug/          # same slug as the memo
      00-brief.md                         # the brief every researcher received, verbatim
      01-<slug>.md                        # one study per researcher, in reading order
      02-<slug>.md
      …
      experiments/
        e01-<slug>/                       # scripts and outputs of one experiment
          run.py
          output.txt
      refresh.log                         # clones refreshed to origin/HEAD, with commits
      licenses.log                        # the licence read from each clone
```

```markdown
# YYYY-MM-DD — <The memo's title>

- **Status:** study set for `../../<YYYY-MM-DD-descriptive-slug>.md`. Read-only against `main` at `<commit>`.
- **Date:** YYYY-MM-DD
- **Owner:** Clay Gendron
- **Method:** <N parallel studies, one per question, each a fresh agent with the brief below; every claim labelled; nothing copied; box per study>.
- **Why a study set and not a memo:** <one paragraph: each file is new investigation; the synthesis is the memo>.

## Labels

EXECUTED means run here. READ means read in a file or page cited by path or URL. INFERRED means the researcher's reasoning.

## The brief every researcher received

> <the brief, verbatim, as a block quote>

## Files

| # | File | Question | Executed findings worth knowing |
|---|---|---|---|
| 01 | `01-<slug>.md` | … | … |
| 02 | `02-<slug>.md` | … | … |
```

The `Files` table is filled in last, after the studies report. It is the one place the brief is edited after the fan-out starts; that edit is the brief's completion, like a placeholder's.

## 4. The rules

Each rule is stated once as a sentence, then once as the reason.

1. **Label every claim.** Each claim in a memo or study is READ, EXECUTED or INFERRED. READ means it came from a file or page cited by path or URL. EXECUTED means a command ran here and the claim reports its output. INFERRED means the researcher's reasoning. The reason: a reader must know how much to trust each sentence, and a lab notebook's split of observation from interpretation is the same rule. A placeholder memo may carry no label while it holds only a question.

2. **Cite by path, never by number.** A memo names its studies by file path once in the Sources line and may then use short tags (`S01`). A memo names the spec it feeds by relative path. There are no document numbers anywhere outside a studies folder's reading-order prefix. The reason: the owner's ruling of 2026-10-29; a number is an identity that collides and goes stale, a path is a link that a lint can check.

3. **State the box; stop at the box.** A research task states its time box in the Researcher line before it starts. At the box the researcher stops, writes where it stood and what it skipped into the Method line, and reports. A blocked step is skipped and named, never forced. The reason: wasi-python's constitution §5 item 3, and the XP spike; an unbounded investigation is a project, not research.

4. **Append-mostly; supersede, do not rewrite.** A memo is not edited after it is written. A correction is a new memo whose Supersedes line names the old one by path, and the old one gains nothing. Two exceptions, both written down: a placeholder memo is completed in place, and a `00-brief.md`'s Files table is filled in when the studies land. The kernel memo's in-place "Revised" lines were honest but outside the rule; under this rule the OSTEP memo's corrections would stand alone as the superseding record, which is what they already are.

5. **No open questions; placeholders instead.** A memo's last section names what it does not settle, and each item names a placeholder memo or an experiment by path. The words "open question", "TBD" and "TODO" do not appear. `open-questions.md` is retired as intake; a placeholder memo is the intake. The reason: the intention's "No open questions"; a question with an owner, an experiment and a blocked spec gets answered, a list entry does not.

6. **Research means new investigation.** A memo is produced by gathering new findings: executed experiments, studied sources at named commits, measured runs. It never records in-session reasoning alone and never restates a decision. The test: if every label in the memo would be INFERRED, it is not a memo; it is a section of the spec that needs it. The reason: `CLAUDE.md`, Clay 2026-08-04.

7. **Research is skipped when there is nothing to learn.** An intention goes straight to a spec when the choice has no trade-off a study would change, when the prior art is already in a memo (cite it), or when the work is a correction to something already decided. The spec's "research it stands on" line then says "none needed" and why, in one sentence. The reason: Google's rule that a design doc with no alternatives is an implementation manual; a memo that only confirms the obvious is transcription.

8. **No code copied; clones refreshed and licensed.** Every clone studied is refreshed to its upstream default branch first, its licence read and logged, its commit recorded. Descriptions and citations only. The reason: `CLAUDE.md` "Reference repos".

9. **Count operations; report clocks as facts.** A number in a memo may be wall-clock, labelled EXECUTED with the machine named, but a test derived from the memo counts operations. The reason: `CLAUDE.md` "Performance tests".

10. **Studies are self-contained and ordered, not numbered as identities.** A study file's `NN-` prefix is its reading order inside one folder. A review of a spec is not a study and does not go in a studies folder; it goes to the review stage's folder. The reason: the agent-shell folder's collisions came from appending reviews to a research folder.

## 5. A lint rule that could hold the shape

The box ran out here; this section is the design, not the code. vfs has no test that reads `context/` today (EXECUTED, §1.1), so this is one new test module, `tests/lint/test_context_shape.py`, with a small scan helper beside it. It runs in `scripts/ci.sh` as part of `pytest`, so the intention's "Done when" item 3 is met for memos the way it will be for specs.

What it checks, per file, each as one function returning a list of error strings so a failure names every file and every missing part at once:

1. **Memo header.** Every `context/research/YYYY-MM-DD-*.md` written on or after a cut-over date (so the 154 old memos are left as frozen history, per the intention's "not a rewrite") has each of the header lines `- **Status:**`, `- **Date:**`, `- **Owner:**`, `- **Researcher:**`, `- **Question:**`, `- **Method:**`, `- **Sources:**`, `- **Supersedes:**` at a line start. A placeholder (Status line contains "placeholder") instead needs `Feeds`, `Blocks` and `Box`, and the sections `## The question` and `## The experiment that answers it`.

2. **Labels.** Every non-placeholder memo and every study file carries at least one whole-word EXECUTED, READ or INFERRED outside fenced and inline code. This is wasi-python's check restated; it is a floor, not a count. A stricter form, held as a later step, counts labelled paragraphs under `## ` headings and fails when a memo's §1 ("What the sources say") has a paragraph with no label.

3. **Numbers in names.** No file under `context/research/`, `context/intentions/`, `context/specs/` or `context/reviews/` has a name matching `^\d{3}-`. Study files under `studies/*/` must match `^\d{2}-` or be `00-brief.md`, `refresh.log`, `licenses.log`, or live under `experiments/`. Two studies in one folder may not share a prefix.

4. **Links resolve.** Every relative link in a memo or study (a Markdown link whose target is a relative path, such as one into `../specs/`, or a backticked path ending in `.md` that starts with `../` or `studies/`) points at a file that exists. A memo's Sources line names its studies folder and that folder exists with a `00-brief.md`. This is the check that replaces "cite by number": a path either resolves or the test fails.

5. **No open questions.** A non-placeholder memo contains no `TBD`, `TODO`, "open question" or a heading containing "question" (the Question header line is exempt because it is a bullet, not a heading). This is wasi-python's `open_question_hits` applied to memos as well as specs.

6. **Box stated.** The Researcher line contains the word "Box" (or "box:"). A study's Researcher line likewise. This is the cheapest possible check that rule 3 was followed; it cannot check that the box was honoured, only that it was named.

7. **One-line paragraphs** (optional, decide once). If the owner adopts wasi-python's rule, a fixer joins hard-wrapped prose under `context/` for new files only, and the test fails on a wrapped paragraph. If not, the lint leaves line length alone. INFERRED: the one-line rule makes every other check above simpler, because a header line and a label then always sit on one line.

What the lint does not check, on purpose: the truth of a label, the quality of a method, whether a study was really read. Those are the review stage's job (a fresh reviewer reading the memo against its studies). The lint holds the shape so the reviewer can spend the time on the substance.

## 6. One line

A research memo is a dated, path-linked, labelled, boxed, append-only answer to a question Clay asked, standing on numbered-for-order studies in a folder of the same name; a placeholder memo is the same document holding the question until the experiment runs; and one small lint test holds the header, the labels, the links, the names and the absence of open questions.
