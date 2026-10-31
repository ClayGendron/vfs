# Reviews: the two files a spec gets before it lands

A review is a file in this folder, written by someone who did not write the thing it reviews. Every spec gets two. The **spec review** reads the spec before any code is written and ends "Fit to build" or "Not yet". The **code review** reads the built change before it lands and ends "Lands" or "Does not land yet". Both are decided by [the development process spec](../specifications/active/2026-10-29-the-development-process.md) (decisions 11 to 14); the research behind them is [the spec-review study](../research/studies/2026-10-29-the-development-process/04-spec-review.md) and [the code-review study](../research/studies/2026-10-29-the-development-process/06-code-review.md). The landing that follows a code review is in [the landing standard](../standards/landing.md). The first worked example is [the spec review of the process spec itself](2026-10-29-the-development-process-spec-review.md). The lint in `tests/lint/test_context_shape.py` holds every file here to the headings and the verdict words below.

Terms. A **finding** is one defect the reviewer names, with evidence. The **Disposition** is the section where the author answers each finding. The **verdict** is the reviewer's one-line decision. A **round** is one exchange: the reviewer writes, the author answers, the reviewer re-reads and signs. A **lens** is one way of reading a change (contract, scale, tests, ownership, adversarial, security). A **label** says how a claim was established: EXECUTED means the reviewer ran it, READ means the reviewer read the file cited, INFERRED means the reviewer's reasoning.

## Who writes a review

The reviewer is a fresh agent or a person who did not write the change. The reviewer is given the spec, the diff, the intention, the research the spec cites, the standards ([the constitution](../standards/constitution.md), [CLAUDE.md](../../CLAUDE.md), [how we code](../standards/how-we-code.md), this README) and the live tree read-only, plus the author's questions, as questions. The reviewer is never given the author's summary of the change, the author's transcript or reasoning, the plan that produced the draft, the author's proposed answers to its own questions, or a hint of the expected verdict. A sub-agent of the author's session says so in its first paragraph: "a fresh sub-agent of the author's session; not the author". The reviewer writes the file and runs no git command that changes state; the author's landing commit carries the file.

## File names

`YYYY-MM-DD-<spec-slug>-spec-review.md` and `YYYY-MM-DD-<spec-slug>-code-review.md`. The date is the review's own, so a second review on a later day is a new file and the older one stays. The slug is the spec's file name without its date and its extension: `2026-11-03-the-guarded-append.md` is reviewed in `2026-11-03-the-guarded-append-spec-review.md`. No number anywhere in the name. A spec that still carries a numbered folder name is reviewed under a slug cut from its title.

## The spec-review checklist

The box is 25 minutes, or 45 when the spec touches the storage backend, a verb's contract, the public surface, more than one architecture page, or the gate (`scripts/ci.sh`, `tests/lint/`, a workflow). The review states its box and where it stood when the box ran out. A box that ran out is a note, not a verdict; a second reviewer may continue from where the first stopped.

1. **The author's questions first.** The author may hand over one to ten questions about the draft, the places it was least sure. Answer each, labelled, before anything else. The brief carries questions, never the author's answers.
2. **Read the whole spec once, silently**, before writing a finding. Then the intention it serves, the research it cites at the lines it cites, and the architecture page it names.
3. **The first paragraph.** It says which kind of change this is (feature, fix, refactor, spike, process, docs) and which flags apply (structural, changes the public API, changes the schema format, needs the engine legs, touches rights, touches the engine, parallel-safe). Check each flag against the Design and the Scope. A flag the change needs and the paragraph does not name is a Medium.
4. **Decisions.** Each is a `### N.` heading that is a sentence, with a body that ends in its reason. A decision with no reason is a Medium. A decision that contradicts a landed spec, a frozen record or a standard without naming the departure is a High.
5. **No choice left to the build.** Every default, error class, chunk size and name the developer would otherwise invent is decided in the spec, and no phrase defers a choice to build time. An undecided choice is a High: the build would decide it silently.
6. **Acceptance criteria.** Each names the test file and node id, or the conformance row, that will pin it, before that test exists; each counts something (a count, a state, a file, an exit code) and never a clock. A wish ("fast enough", "works at scale") is a Medium.
7. **Scope.** The spec is one landing: one commit to `main` by one developer, green at the end, or slices each green on its own. A spec that is four landings is a Medium, with the cut proposed.
8. **The diagram.** The Architecture section holds one Mermaid block in the dialect of [context/architecture/](../architecture/README.md) and names the page it will change. Every component the Design names is drawn, and nothing drawn is missing from the Design. A missing diagram is a Medium; a diagram that disagrees with the Design is a High.
9. **Scale and the production posture.** For each statement, loop or in-memory structure the Design adds: what grows with input, and what bounds it. The bound is a declared budget (`membership_budget`, `chunked()`), never a hardcoded size; the floor is the least generous supported engine, never SQLite; a 10,000-file batch is a supported call. Anything unbounded is a High. A suboptimal profile named honestly, with its future direction, is not a finding.
10. **The constitution and CLAUDE.md.** Article 1: which of the five primitives the spec manipulates or composes; a sixth first-class thing is a High. Articles 2 to 5 as touched. CLAUDE.md's posture: no numpy, no designed scale cap, no pure-Python fallback on a hot path, imports at the top, `assert` narrows and never validates, no document names in code.
11. **Dependencies and the live tree.** Every spec this one builds on is named with its state (landed, or active and not yet built); a shape assumed from an unbuilt spec is a Medium. One to three probes, by command or `path:line`, that the spec's claims about today's code are true; a false claim is a Medium, or a High when a decision rests on it.
12. **Premortem.** Three minutes: the spec was built as written and failed in production or in review. Write the three most likely reasons. Each becomes a finding or a line in "Checked and found clean".
13. **Rank, write the fix text, write the ledger, write the verdict.** Each Low carries its fix text so it needs no round. The ledger lists what was read and passed, so a short findings list is not mistaken for a short read.

## The code-review checklist

The box is 30 minutes, or 60 when the diff touches the database backend, a dialect profile, the Rust crate or the MCP tool surface. The review states its box and where it stood at the box.

1. **Resolve what is reviewed first.** With slices, `<base>..<tip>` of the local unpushed commits: confirm `git log --oneline <base>..<tip> | wc -l` equals the number of commits meant and record every subject. With one landing commit still to come, the working tree over `HEAD` at a named commit, with `git status --porcelain` and `git diff --stat` recorded. Commit messages and the draft of the landing commit are reviewed material: every claim in them is a promise.
2. **Read the spec and its spec review**, then the diff. The spec review's findings and their dispositions are the first things to look for in the code.
3. **Run the gate yourself**: `scripts/ci.sh` (EXECUTED). Record each step's PASS or FAIL, the test counts and the exit code in the opening paragraph. Nothing is pushed yet, so there is no CI run to read.
4. **Run the engine legs when storage changed**: the [db_test](../../.claude/skills/db_test/SKILL.md) cycle, then `VFS_TEST_<ENGINE>_URL=<url> uv run pytest -m <engine>` for Postgres, MariaDB, MSSQL and Oracle, counts per engine. A leg that could not run is named as not reached, never as clean.
5. **Criteria against evidence**, one line each, labelled, naming the test node id that pins the criterion. Tests first is an instruction of how to code, not a record the author files: no "seen failing first" section is required anywhere. The reviewer may reproduce one red to check that a test pins its behaviour: copy the changed source file to the session scratchpad, replace it with the version before the change (`git show <base>:src/<file> > src/<file>`), run the test by node id, record the red output, copy the backup back, and confirm the restored file is intact with `ruff` or the same test green. Never run `git checkout --`, `git restore` or `git stash` on a file that carries uncommitted work. A criterion met only by INFERRED is a Medium; a criterion whose test the reviewer could not make go red is a High; a criterion with no test is a High.
6. **One to three probes by node id**: a targeted test, a one-line mutation with the test re-run, a scratch script against an engine. Record the command and the output.
7. **The five lenses, in this order**: contract, scale, tests, ownership, adversarial, by their skills under `.claude/skills/`, or by the `code_review` workflow for a 60-minute diff, with the run id named. Every lens writes its close-out ledger (what it checked and found clean, what it did not reach) even when it finds nothing; a lens the diff gave nothing to look at says so in one line.
8. **The security lens in guidance mode**, with the Cloudflare skill named in [the landing standard](../standards/landing.md): name the trust boundaries the diff touches (the lower-trust principal, the input or action, the control, the sink); read the attack-class blocks that match them (injection in the SQL builders and the pattern compilers, path handling, permission compilation, secrets in database URLs, tool-argument injection and confused deputy on the MCP surface, unbounded growth, data isolation); record each result as confirmed, needs_validation or rejected. No run folder is written. A confirmed record is also a ranked finding. Target code runs only as a scratch script with no network and no live service.
9. **Standards checks**, one line each: tests landed with the code they pin; the constitution articles the diff touches; the production posture; the patterns of how we code; `ruff`, `ruff format` and `ty` at zero; `assert` narrows only; imports at the top; no document names in code.
10. **Rank.** State for each Medium what evidence closes it. Write the fix text for each Low.
11. **Verdict in one line.** It begins "Lands" when nothing High or Medium stands, or "Does not land yet: …" naming what stands. A verdict beginning "Lands" is the reviewer's signature on the tree named in step 1.

## The ranking

- **High.** In a spec review: a wrong design the build would carry (a constitution breach, a statement that grows without bound, a choice left to the developer). In a code review: a wrong answer, data loss, an unsafe default, a statement that grows with batch size, a crossed trust boundary, a test that cannot go red. The verdict is "Not yet" or "Does not land yet" until it is fixed.
- **Medium.** A guarantee not evidenced: a criterion that cannot be counted or is met only by reading, a dependency not named or in the wrong state, a missing diagram, a claim about the live tree that is false, a scale claim not run on the tightest engine, a security `needs_validation` with its fact still missing. The reviewer states what evidence would close it. One Medium per review is normal. The verdict waits until it is closed, or answered in the Disposition with a reason the reviewer confirms.
- **Low.** A write-in: a sentence the spec should carry, a stale docstring, a name, a comment. The finding carries its fix text, so it needs no round and does not hold the verdict.
- **Note.** An observation with no fix the author must take. It is not ranked.

A finding from a lens carries the lens and the lens's own label in parentheses. The lenses' scales map onto these three ranks: a `critical`, a `major` with a demonstrated failure, a `blocker` and a survived mutant are High; a `major` with no demonstrated failure is Medium; `minor` and `question` are Low; the security skill's `confirmed` at critical, high or medium is High, `confirmed` at low or informational is Medium or Low by the demonstrated damage, `needs_validation` is Medium, and `rejected` is not a finding.

## The rounds and the verdict

The Verdict section's first line is the verdict. In a spec review it begins "Fit to build" or "Not yet"; in a code review it begins "Lands" or "Does not land yet". Nothing hedges: "fit once X" is "Not yet: X" with the fix in the Disposition.

1. The reviewer writes the file with its findings, its ledger and its verdict, and commits nothing.
2. The author answers every finding in the Disposition, one line each: "fixed: <what the spec or the code now says>" or "kept because <reason>". A High or a Medium is fixed in the spec, or in the code; a Low is answered with its fix text applied. The author never rewrites a reviewed commit; a code fix is a new change the reviewer can diff.
3. The reviewer re-reads the amended spec or the fix against each Disposition line, appends "READ, confirmed" or "Not confirmed: <why>" to it, and signs again with a dated line below the first verdict: `YYYY-MM-DD, re-read on <commit>: <verdict>`. The first verdict stays where it was. The last dated line is the standing verdict; the lint reads it, and the landing checklist reads it.
4. A fixed finding needs a re-signature. A Low answered with its fix text is confirmed by reading, never by a round.
5. A changed Decision after "Fit to build", a grown scope, or a box that ran out before the checklist's ninth step needs a new dated review file; a change to wording, a criterion's count or a test name is recorded in the Disposition of the same file.
6. A finding the author keeps against the reviewer's rank goes to Clay in one Disposition line; Clay's word, recorded as a Decision in the spec, closes it.
7. A code change made after a code review's signed tree is unreviewed; it needs a re-read and a new dated line before the landing. The landing commit carries both review files; the review file never lands after the code.

## The spec-review template

The first line is the title; the paragraph under it carries no header bullets. The `## ` headings are exactly these, in this order; the first is left out when the author asked no questions.

```markdown
# Spec review: <spec title>

I am <a person / an agent (<model>), a fresh sub-agent of the author's session; not the author>. I reviewed [the spec](../specifications/active/YYYY-MM-DD-<spec-slug>.md) at `<commit>` (or: an uncommitted draft on `main` at `<commit>`). I was given the spec, [the intention](../intentions/YYYY-MM-DD-<slug>.md), [the research memo](../research/YYYY-MM-DD-<slug>.md) and its studies, [the constitution](../standards/constitution.md), [CLAUDE.md](../../CLAUDE.md), [how we code](../standards/how-we-code.md), this README and the live tree read-only; I was not given the author's summary, transcript, reasoning or expected verdict. I re-ran: <each probe against the live tree, with what was seen>, or none. Box: <25 or 45> minutes; <kept, HH:MM to HH:MM / ran out at step N, and what was not reached>.

Labels: EXECUTED means I ran it; READ means I read the file cited; INFERRED means my reasoning.

## The author's questions, answered first

1. **<The question.>** <The answer, labelled.>

## Decisions, one line each

1. Decision 1 — <holds / does not hold: why>, on <the constitution article, the standard or the research line it rests on>.

## Acceptance criteria, countable as written

1. <Criterion> — countable / not countable: <what it counts and the test that will pin it, or what it lacks>.

## The diagram and the scope

- Diagram: <which architecture page it changes; every touched component drawn; built and planned marked; agrees with the Design>.
- Scope: <one landing / not one landing: why>.
- Depends on: <each dependency with its state, or "none">.

## Scale and the production posture

- <Each statement, loop or structure that grows with input, and the bound it declares; or "nothing grows with input".>

## Constitution and CLAUDE.md checks

- Article 1 primitives: <which of the five it manipulates or composes, and that it adds no sixth>.
- Articles 2 to 5: <each one touched, and whether it holds>.
- CLAUDE.md posture: <the 10,000-row batch, the least generous engine, no unbounded statement, no numpy, no designed cap, imports at the top, assert narrows>.

## Premortem

<The build is done and failed; the three most likely reasons; which finding each became, or why none.>

## Findings, most severe first

1. **H1. <Title>** (<the spec section, linked>) — <the defect in one sentence>. Consequence if built: <what the code would carry>. Fix text: <the sentence the spec should carry>.
2. **M1. <Title>** (<the spec section, linked>) — <the guarantee not evidenced>. Closes with: <the evidence>.
3. **L1. <Title>** (<the spec section, linked>) — <the write-in>. Fix text: <the sentence>.

## Checked and found clean

<The sections, decisions and criteria read and passed.>

## Disposition

Filled in by the author, then confirmed by the reviewer.

1. H1 — fixed: <what the spec now says> / kept because <reason>. READ, confirmed. / Not confirmed: <why>.

## Verdict

<Fit to build: <one sentence>. / Not yet: <the High, or the Mediums>.> On `<commit>`.

YYYY-MM-DD, re-read on <commit>: <Fit to build. / Not yet: <what stands>.>
```

## The code-review template

The first line is the title; the paragraph under it carries no header bullets. The `## ` headings are exactly these, in this order, and the Lenses section holds exactly the five `### ` subsections in this order.

```markdown
# Code review of <spec title>

I am <a person / an agent (<model>), a fresh sub-agent of the author's session; not the author>. I reviewed <`<base>..<tip>`, N commits, subjects under Scope / the working tree over `HEAD` at `<commit>`, `git status --porcelain` recorded under Scope> for [the spec](../specifications/active/YYYY-MM-DD-<spec-slug>.md), read with [its spec review](YYYY-MM-DD-<spec-slug>-spec-review.md). I was given the spec, the diff, the intention, the research the spec cites, the standards, this README and the live tree; I was not given the author's summary, transcript, reasoning or expected verdict. I re-ran: `scripts/ci.sh` (<each step PASS or FAIL, test counts, exit code>); <the engine legs with counts per engine, or "the engine legs were not needed: storage unchanged", or "<engine> not reached: <why>">; <each probe by node id, with its output>. Method: <one reviewer, the lenses in order / the code_review workflow, run id>; the security lens in guidance mode. Box: <30 or 60> minutes; <kept / where it stood at the box>.

Labels: EXECUTED means I ran it; READ means I read the file cited; INFERRED means my reasoning.

## Scope

<The commits one line each as `<sha> <subject>`, or the working-tree state. What the diff touches (`git diff --stat`). Any drift caveat.>

## Acceptance criteria against evidence

1. <Criterion, quoted from the spec> — met / not met (EXECUTED | READ | INFERRED): <the evidence or the gap>. Pinned by `<test node id>`. <Red reproduced: `<node id>` → <the failing output> on the file at `<base>`, restored, intact. / Not reproduced.>

## Findings, most severe first

1. **High (<lens>: <lens label>) — <title>** (`path:line`). <The defect in one sentence.> Failure: <input or state → wrong output, crash, unbounded statement or crossed boundary>. Closes with: <the evidence or the change>.
2. **Medium (<lens>: <lens label>) — <title>** (`path:line`). <The guarantee not evidenced.> Closes with: <the evidence>.
3. **Low (<lens>: <lens label>) — <title>** (`path:line`). <The write-in.> Fix text: <the text>.

## Lenses

### Contract

<Method notes, then the close-out ledger: checked and found clean; not reached.>

### Scale

<Method notes, then the close-out ledger.>

### Tests

<Method notes, the mutant ledger replayed, then the close-out ledger.>

### Ownership

<Method notes, the ownership table, then the close-out ledger.>

### Adversarial

<Method notes, executed repros only, then the close-out ledger.>

## Security

- Method: the vendored security-audit skill (`.claude/skills/security-audit/`, source `cloudflare/security-audit-skill`, pinned by `skills-lock.json`), guidance mode; no run folder written.
- Boundaries this diff touches: <each one: the lower-trust principal, the input or action, the control, the sink; or "none: the diff crosses no trust boundary">.
- Attack-class blocks read: <the blocks of ATTACK-CLASSES.md and the companions, named>.
- Records: <one per record: confirmed (<severity>, finding <n> above) | needs_validation (<the missing fact>) | rejected (<why>); or "none">.

## Standards checks

- Tests first: <the tests land with the code they pin; the reviewer's own red on criterion <n>, or none reproduced>.
- Constitution: <each hard rule the diff touches, and whether it holds>.
- Production posture: <never assumes SQLite; no statement grows with batch size; no designed scale cap>.
- How we code: <each named pattern the diff uses or should have used>.
- Tooling: <ruff, format and ty at zero; assert narrows only; imports at the top; no document names in code>.

## Disposition

Filled in by the author, then confirmed by the reviewer.

1. <Finding 1> — fixed: <what changed> / kept because <reason>. Confirmed (<label>). / Not confirmed: <why>.

## Verdict

<Lands: <why, in one sentence>. / Does not land yet: <the High, or the Mediums and what closes them>.> On <`<tip>` / the working tree over `<commit>`>.

YYYY-MM-DD, re-read on <commit>: <Lands. / Does not land yet: <what stands>.>
```

## One line

Two dated files per spec, each written by someone who did not write the change and was not told what to think, each with fixed headings, ranked findings with fix text, a Disposition the author fills and the reviewer confirms, and a Verdict whose standing line is the last dated one: "Fit to build" before the build, "Lands" before the landing.
