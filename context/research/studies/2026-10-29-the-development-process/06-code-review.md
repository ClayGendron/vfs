# Stage 6: the review of the code

This is a study for [the development-process memo](../../2026-10-29-the-development-process-seven-studies-and-what-they-recommend.md), owned by Clay Gendron. Its question: what format does the code review take (file name, header, sections, checklist, ranking, verdict)? How do vfs's existing review skills fold into one review file? How is Cloudflare's security-audit skill installed and run as one lens of that review? What lint rule holds "a landed spec cites its code review"? Its method: read the sibling project wasi-python at commit `1431ba6f` (read-only), its `context/reviews/README.md`, one pull-request review, the two rules in `AGENTS.md`, and the lint rule in `tests/checks/test_rules.py` with its scanner in `tests/harness/scan.py`; read the Cloudflare skill as vendored there under `.agents/skills/security-audit/` and its `skills-lock.json`; read vfs's seven review skills under `.claude/skills/`; fetched the Cloudflare repository, its licence, the `skills` CLI documentation, Google's engineering practices, Conventional Comments, CPython's devguide, SQLAlchemy's test README and OpenSSF's concise guide. Nothing was installed, copied or edited outside this file. Box: 30 minutes; the write-up ran a few minutes past it.

## Sources

- wasi-python at `1431ba6f` (READ 2026-10-29): `context/reviews/README.md`; `context/reviews/158-the-upstream-test-archives-are-fetched-from-a-mirror-pr-2026-10-28.md`; `AGENTS.md` ("Nothing lands unreviewed", "Working autonomously" step 7); `tests/checks/test_rules.py::test_landed_specifications_cite_an_existing_review`; `tests/harness/scan.py::landed_review_errors`; `.agents/skills/security-audit/` (all files); `skills-lock.json`; `context/reviews/0.1.0-security-audit-2026-10-25.md` and its run folder.
- vfs (READ 2026-10-29): `.claude/skills/{code_review,contract_review,scale_review,test_review,ownership_review,adversarial_review,verify_findings}/SKILL.md`, `code_review/workflow_template.js`, `code_review/check_workflow.py`; `context/intentions/2026-10-29-the-development-process.md`; `context/standards/commits-and-prs.md`; `scripts/ci.sh`.
- Cloudflare, `github.com/cloudflare/security-audit-skill` README and `LICENSE` (READ 2026-10-29). Licence: MIT, copyright 2025-2026 Cloudflare, Inc.
- Vercel Labs, `github.com/vercel-labs/skills` README and `docs/agents.md` (READ 2026-10-29).
- Google, "What to look for in a code review" and "The standard of code review", `google.github.io/eng-practices/review/reviewer/` (READ 2026-10-29).
- Conventional Comments, `conventionalcomments.org` (READ 2026-10-29).
- CPython devguide, "Lifecycle of a pull request", `devguide.python.org/getting-started/pull-request-lifecycle/` (READ 2026-10-29).
- SQLAlchemy, `README.unittests.rst` on `main` (READ 2026-10-29).
- OpenSSF, "Concise Guide for Developing More Secure Software", `best.openssf.org` (READ 2026-10-29).

Labels in this study: **READ** (a document or code, read), **EXECUTED** (a command run here), **INFERRED** (reasoned, not read or run).

Terms used throughout. A **code review** is the review a built change gets before it lands. A **lens** is one way of looking at the change (does it match its contract, does it survive scale, and so on). A **finding** is one defect the reviewer claims, with evidence. A **verdict** is the one-sentence decision at the end. **Landing** is the commit to `main` that Clay asks for. The owner's ruling of 2026-10-29 applies: no numbers in document file names; every intention, spec and review is `YYYY-MM-DD-descriptive-slug.md`.

## What the sources say

### wasi-python: one review file per change, written by someone else, committed last (READ)

The sibling keeps one Markdown file per review under `context/reviews/`. The README there sets the rules; the 158 review shows them applied.

- **Who writes it.** A fresh agent or a person who did not write the change. The reviewer is given the specification and the diff. The `Reviewer:` line names a session or a person, and a sub-agent of the author's session says so ("a fresh sub-agent of `<session>`; not the author"). A `Reviewer:` line that is the author's own session is refused by the checker. The README calls this a process guard, not an identity guard.
- **What it reads.** The specification, the diff, and the CI run of the head. It dispatches no CI run of its own; it runs what it needs locally, by test node id.
- **The header.** `Date`, `Reviewer`, `Reviewed` (the commit range, and which spec and pre-build review it was read against, and the time box), `Run` (the CI run id), `Re-ran` (what the reviewer executed locally, with counts and exit codes).
- **The sections.** Acceptance criteria against evidence, one line each, labelled EXECUTED, READ or INFERRED. Findings most severe first, each with a one-sentence defect, a `path:line`, and a concrete failure. Constitution checks (the hard constraints and the never-do list, each one touched named). Disposition: the author fills in "fixed in `<commit>`" or "not fixed because", the reviewer confirms. Verdict: one sentence.
- **The ranking.** High: a wrong answer or an unsafe default. Medium: a guarantee not evidenced. Low: a write-in, with the fix text. One Medium per review is normal; the review states what evidence would close it.
- **The verdict.** Begins "Lands" when nothing stands, or "Does not land yet: `<the High or the Mediums>`". After the author's fix commit the reviewer reads it and writes the verdict again. A verdict beginning "Lands" is the reviewer's signature on that head.
- **No confirmation round.** The author answers in the pull request. A code fix is a new commit on the same branch. A Low that touches only `context/` the reviewer may commit itself; a code fix stays the author's.
- **The review file is committed last.** It is the branch's last commit, after the final code commit. The checker fails the pull request when a commit touching code follows the newest commit that changed the review file. Documentation-only commits after it leave it standing.
- **The time box.** 25 minutes for an ordinary spec, 45 for a build-class one. The review states its box and where it stood at the box.
- **The 158 review in practice.** The `Reviewed` line names the base, the tip, the spec and the pre-build review in one line. `Re-ran` lists six local commands with counts ("775 passed, 38 skipped, exit 0"). Seven criteria, each "met" with the label and the evidence. Two Mediums, three Lows. The Disposition names the fix commit for each. The verdict begins "Lands:" and says why in one sentence.
- **"Every new check was seen failing before the code made it pass."** The sibling holds this three ways (READ, the pull-request template, the 158 spec and its review). First, the pull-request template is the author's self-check; its first box is that sentence, the reviewer reads it first, and an unticked box is a Low finding written as the fix text. Second, the spec's landing notes carry a section "The rows seen failing first": one line per new test, naming its node id and quoting its failing output on the code as it stood before the change (for 158: an `AttributeError` on a function that did not yet exist, a "no line names a mirror" message, and so on), with the logs kept under a build folder. Third, the commit order: the first commit of the branch adds the tests, seen failing; the code commits follow; the landing notes name the commits in that order. The 158 review checked criterion 2 against all three: "each first failure is named in the pull request and in `rows-*-before.txt`".
- **The lint rule** (`landed_review_errors`, READ). For every spec file: if its Status line does not begin with "landed", skip. Otherwise take the text after the "## Landing notes" heading, find every `reviews/<name>.md` reference in it, and fail if there are none or if any named file is missing under `context/reviews/`. The test collects errors across all specs and asserts the list is empty. A sibling rule does the same for a structural spec's pre-build review.

### The Cloudflare security-audit skill (READ)

The skill is a folder of Markdown and two Node validators. `SKILL.md` is the entry; it names the phase files `RECONNAISSANCE.md`, `HUNTING.md`, `VALIDATION-AND-REPORTING.md`, the ordinary attack classes in `ATTACK-CLASSES.md`, nine domain companions (`AI-AND-LLM.md`, `DATA-ISOLATION-AND-LIFECYCLE.md`, `RESOURCE-EXHAUSTION-AND-AVAILABILITY.md`, `SUPPLY-CHAIN-AND-RELEASE.md`, and five more), `report-schema.json`, and the validators.

- **Two modes.** *Guidance mode* is the default: for a security question, a focused review, triage, or one finding, the reviewer uses only the relevant parts of the skill. It creates no output directory and writes no audit artifacts. *Full audit mode* runs only on an explicit request for an audit, a pen test, a comprehensive review, or report artifacts; it runs all six phases and writes a run folder (`run-metadata.json`, `architecture.md`, `coverage-ledger.json`, `findings.json`, `REPORT.md`, `FINDINGS-DETAIL.md`, `NEEDS-VALIDATION.md`), by default under `~/security-audit-skill/<repo>/run-<N>`, outside the target. If the request could mean either, the skill asks one question first.
- **The evidence bar is the same in both modes.** A finding needs a trust boundary: a lower-trust principal, an accepted input or action, the control that should have stopped it, the boundary crossed, and a concrete result. A missing best practice is not a finding. A guessed deployment fact is not a finding. Severity (critical, high, medium, low, informational) is given only to a `confirmed` record. A `needs_validation` record names the exact missing fact and has no severity. A `rejected` record says why. The fix is the smallest source change at the last trusted decision point.
- **Execution is sandboxed.** Target code runs only inside an OS-enforced sandbox: no network, empty environment, read-only target, scratch-only writes, resource limits. If the sandbox cannot be enforced, the check is not run and becomes a `needs_validation` blocker.
- **The attack classes.** The ordinary ones: injection, access control, resource and file handling, cryptography and secrets, business logic, feature abuse and data leakage, chained boundaries, wildcard, and "obvious things". The AI companion adds tool-argument injection into a downstream sink, confused-deputy authority, action-binding, tool-schema and dispatcher disagreement, unbounded delegated loops, and three MCP trust classes (trust inheritance, server and tool identity confusion, metadata treated as policy).
- **How the sibling used it.** The sibling's release audit (`0.1.0-security-audit-2026-10-25.md`) was a full-audit run: one parent agent, 36 sub-agents, the whole run folder committed beside the review file with paths rewritten to be repository-relative. The review file's header named the skill, its source repository, its install path and the lock file, the profile (`standard`), and the two sandbox controls macOS could not enforce.

### Installing it (READ, with one INFERRED point)

- The Cloudflare README gives one command: `npx skills add https://github.com/cloudflare/security-audit-skill --skill security-audit`, with `--global` for a user-level install.
- The `skills` CLI (Vercel Labs) installs into the current project by default and needs Node 22.20 or later. Its `docs/agents.md` table gives per-agent paths: Claude Code writes `.claude/skills/`; the "universal" target (which the CLI also uses for Amp and Replit) writes `.agents/skills/`. The CLI detects installed agents and asks when none is found. `-a <agent>` (also `--agent`) picks the target. `npx skills check` lists updates; `npx skills update` applies them. The documentation does not say whether `.claude/skills/` is a copy or a link of `.agents/skills/`.
- The sibling's checkout has `.agents/skills/security-audit/` and no `.claude/skills/` (EXECUTED: `ls`). So it installed with the universal target. Its `skills-lock.json` records the source `cloudflare/security-audit-skill`, `sourceType: github`, `skillPath: skills/security-audit/SKILL.md`, and a content hash. The hash is the "installed unchanged" proof: `npx skills check` would report drift.
- Licence: MIT, copyright 2025-2026 Cloudflare, Inc. (READ, the `LICENSE` file on `main`). Vendoring it unchanged with its `LICENSE` is within the terms.

### Prior art online (READ)

- **Google's "What to look for in a code review"** lists design, functionality, complexity, tests, naming, comments, style, consistency, documentation, every line, context, and good things. Its "standard": approve once the change improves the system's overall health, even if it is not perfect; data beats opinion; the style guide is the authority on style; a "Nit:" prefix marks an optional point. Conflicts are settled by consensus, then escalation, never by stalling.
- **Conventional Comments** gives a label vocabulary (praise, nitpick, suggestion, issue, todo, question, thought, chore, note) with decorations `blocking`, `non-blocking`, `if-minor`. The useful idea is that the *blocking* decision is separate from the *kind* of comment. The nit/minor/major/blocking convention is the same idea compressed to a ladder.
- **CPython's devguide**: a reviewer reproduces the issue, checks corner cases, checks tests and docs ("no PR accepted without the proper tests"), and reports what they tested. Fixes are new commits, never force-pushes, so the reviewer can diff the fix. Only a core developer merges.
- **SQLAlchemy** has no written reviewer checklist in its test README; what it does hold is a multi-backend test contract (SQLite, PostgreSQL, MySQL, MariaDB, MSSQL, Oracle), which is the same posture vfs already takes with its engine legs.
- **OpenSSF's concise guide** asks for review before merge enforced by the repository, automated negative tests, no secrets in the repository, scanners in CI, and a documented vulnerability-report path. It is a project checklist, not a reviewer method; the Cloudflare skill is the reviewer method.

## What vfs does today

- **No review file exists.** `context/reviews/` does not exist (EXECUTED: `ls`). The sibling's review folder has one file per change; vfs has none.
- **The standard asks for review but does not say where it goes.** `context/standards/commits-and-prs.md` says "sub-agent review with real integration tests is the standard for non-trivial changes" and lists the reviewer's job: the why is sound, the tests cover the change, the patterns hold, the public surface still composes. It writes nothing down.
- **The pipeline order is wrong for the new process.** `code_review/SKILL.md` says reviews sit after the commit ("code → commit → review"). The intention puts review before landing. The skill's scope resolution (a commit range, the diff as the surface, judge at the tip) still holds; only the position moves.
- **Seven review skills exist.** Each owns one defect class, each ends with a close-out ledger (what it checked and found clean, what it did not reach), each returns findings through a schema and never prose alone:

| skill | what the lens checks | its own labels | what it outputs |
|---|---|---|---|
| `contract_review` | the code against every written promise: docstrings, specs, type signatures, commit messages, error tables; both broken promises and behaviour no contract mentions | breach, growth, decay, gap | findings naming the wrong side (code or contract) with a quote from both |
| `scale_review` | boundedness at 10,000+ batches on the least generous engine: statement growth, `IN`-list and bind budgets, memory high-water marks, concurrency | blocker, major, minor | a statement-growth audit and findings with the input size that breaks |
| `test_review` | whether the tests pin the contract: mutation probes, the mutant ledger replayed, unpinned behaviour | high, medium, low | killed or survived per mutant; unpinned contracts as findings |
| `ownership_review` | which module should own each block of logic; duplication as the primary evidence | misplacement, duplication, envy, leak, divergence | an ownership table and proposed moves; never edits |
| `adversarial_review` | executed attacks: throwaway scripts against the change, properties and invariants, within a time box | critical, major, minor, question | executed repros only, with command and output |
| `verify_findings` | one finding, tried to refute: reproduce, check intent, check reachability | CONFIRMED, REFUTED, DOWNGRADED | a verdict with executed evidence; leads noticed in passing |
| `code_review` | the orchestrator: five lenses in parallel, one Opus verifier per finding, one synthesis; engines up; a checker that refuses a mis-scoped launch | critical, major, minor, question (the shared scale at the seam) | one synthesized report, a funnel (raw vs surviving per lens), leads |

- **The seams are already shared.** The orchestrator normalises every lens onto one scale at the seam (`critical`, `major`, `minor`, `question`) and keeps the lens's own word in `category`. Every lens must return a `coverage` ledger. That is the design that lets one file carry five lenses: one ranked list, lens named per finding, one coverage table.
- **A built-in `security-review` skill is also listed** in this session's skill roster. It is Claude Code's own, not the Cloudflare skill, and it is not the lens the intention names. The study treats it as unrelated.

## The recommended format

One file per code review, under `context/reviews/`. Name: `YYYY-MM-DD-<spec slug>-code-review.md`, where the date is the review's date and `<spec slug>` is the spec's slug without its date (the spec `context/specs/2026-11-03-mount-admission.md` gets `context/reviews/2026-11-10-mount-admission-code-review.md`). The spec review from stage 4 is the same shape with `-spec-review`. The word "code" is in the name so a glance tells the two apart, and so the lint rule can ask for one of each.

Why the spec slug and not a number: the owner's ruling. Why the review's own date and not the spec's: two reviews of one spec on different days then get different names, which the sibling needed an infix for.

The skeleton, complete:

```markdown
# Code review of <spec title>

- **Date:** YYYY-MM-DD
- **Reviewer:** <a session URL or a person; "a fresh sub-agent of <session>; not the author" when spawned by the author's session>
- **Spec:** `../specs/YYYY-MM-DD-<spec slug>.md`, read with its spec review `YYYY-MM-DD-<spec slug>-spec-review.md`
- **Reviewed:** `<base>..<tip>` (<N> commits; subjects listed under Scope) on `main`, local and unpushed; working tree clean at `<tip>` / dirty over <files>, judged at the committed state
- **Re-ran:** `scripts/ci.sh` → <PASS/FAIL per step, test counts, exit code>; <engine legs by `-m <engine>` when storage changed, with counts>; <probes by node id, with counts>
- **Method:** <one reviewer, lenses in order / the code_review workflow, run id, funnel>; security lens in guidance mode over <the boundaries named below>
- **Box:** <30 or 60> minutes; <done inside it / where it stood at the box>

## Scope
The commits, one line each: `<sha> <subject>`. What the diff touches (`git diff --stat`). Any drift caveat.

## Acceptance criteria against evidence
1. <criterion, quoted from the spec> — met / not met (EXECUTED | READ | INFERRED): <the evidence or the gap>.
   Pinned by: `<test node id>`. Seen failing first: <the author's record in the landing notes, quoted: the failing output on `<commit before the code>`> / <the reviewer's own check: `src/<file>` taken back to `<tests commit>`, `<node id>` → <the red output>, restored to `<tip>`, tree clean> / not evidenced.

## Findings, most severe first
1. **High (<lens>: <lens label>) — <title>** (`path:line`). <The defect in one sentence.>
   Failure: <concrete input or state → wrong output, crash, unbounded statement, or crossed boundary>.
   Closes with: <the evidence or the change that would close it; for a Low, the fix text>.

## Lenses
One subsection per lens the reviewer ran, each ending with its close-out ledger: what it checked and found clean, what it did not reach. A lens with no findings still writes its ledger. Fold a lens into one line only when the diff gave it nothing to look at, and say so.

### Contract
### Scale
### Tests
### Ownership
### Adversarial

## Security
Method: the vendored security-audit skill (`.claude/skills/security-audit/`, cloudflare/security-audit-skill, hash in `skills-lock.json`), guidance mode. No run folder.
Boundaries this diff touches: <each one: the lower-trust principal, the input or action, the control, the sink>.
Attack classes read against them: <from ATTACK-CLASSES.md and AI-AND-LLM.md; name the blocks>.
Records: <none / one per record, as confirmed (severity) | needs_validation (the missing fact) | rejected (why)>. A confirmed record is also a finding above, ranked by the table in this study.

## Standards checks
- Tests first: <the tests commit `<sha>` precedes the first `src/` commit; the landing notes' "Seen failing first" section names every new test; the reviewer's own red on criterion <n>>
- Constitution: <each hard rule the diff touches, and whether it holds>
- Production posture: <never assumes SQLite; no statement grows with batch size; no designed scale cap>
- Patterns standard: <each named pattern the diff uses or should have used>
- Tooling: ruff, format, ty at zero; `assert` narrows only; imports at the top; no spec or ADR numbers in code

## Disposition (the author fills it in, the reviewer confirms)
1. <finding 1> — fixed in `<commit>` / not fixed because <reason>. Confirmed (<label>).

## Verdict
Lands: <why, in one sentence>. | Does not land yet: <the High, or the Mediums and what closes them>.
```

Three choices in this skeleton need a reason.

- **The lenses are subsections, not stapled reports.** The findings list at the top is the only ranked list. A lens subsection holds no findings of its own; it holds the lens's method notes and its close-out ledger. So a reader sees one ranked list first, and the per-lens ledgers tell them how much of the surface each lens actually covered. This is the orchestrator's existing design (one shared scale, one `coverage` field per lens) written as prose.
- **Security is one section, in guidance mode, with the skill's three record kinds.** The reviewer names the boundaries the diff touches, names the attack-class blocks read against them, and records each result as `confirmed`, `needs_validation` or `rejected`, exactly the skill's vocabulary. A `confirmed` record is also a numbered finding. A `needs_validation` record is a Medium until the owner supplies the fact. No run folder is written: guidance mode forbids it, and a per-spec review has no room for one.
- **Standards checks replace the sibling's constitution checks.** vfs has a constitution, a production posture in `CLAUDE.md`, a tooling standard, and will have a patterns standard. Each is one line per rule touched.

## The reviewer's checklist

Time box: 30 minutes for an ordinary spec; 60 when the diff touches the database backend, a dialect profile, the Rust crate, or the MCP tool surface. The review states its box and where it stood at the box.

1. **Resolve the range first**, as `code_review/SKILL.md` §0 does. `<base>` is the parent of the oldest commit in the set. Confirm `git log --oneline <base>..<tip> | wc -l` equals the number of commits meant. Record every subject. Check `git status --porcelain`; name any drifted file and judge the committed state. Commit messages are reviewed material: every claim in them is a promise.
2. **Read the spec and its spec review**, then the diff. The spec review's open items are the first things to look for in the code.
3. **Run the gate yourself:** `scripts/ci.sh` (EXECUTED). Record each step's PASS or FAIL, the test counts and the exit code on the `Re-ran` line. There is no CI run to read: nothing is pushed yet.
4. **Run the engine legs when storage changed:** the `db_test` skill's build-up, then `VFS_TEST_<ENGINE>_URL=<url> uv run pytest -m <engine>` for each of Postgres, MariaDB, MSSQL and Oracle; record the counts per engine. A leg that could not be exercised is named as not reached, never as clean.
5. **Criteria against evidence**, one line each, labelled EXECUTED, READ or INFERRED. A criterion met only by INFERRED is a Medium. 5a. **Tests first, per criterion.** The code stage is tests first, then code: every new behaviour's test is written and seen failing before the code that passes it. For each criterion the reviewer names the test that pins it and the evidence it was seen failing first. Two sources of evidence, in this order:
   - *The author's record.* The spec's landing notes carry a section "Seen failing first": one line per new test, its node id, the commit it was added in, and its failing output quoted on the code as it stood before the change. The commit order is part of the record: the tests commit comes before the code commits in `<base>..<tip>`, so `git log --oneline <base>..<tip> -- tests/` shows the test's commit older than the first `src/` commit that passes it (EXECUTED by the reviewer, one command, no tree change).
   - *The reviewer's own red.* For at least one criterion, and for every criterion whose record is missing, the reviewer watches the test go red: on a tree that `git status` reports clean at `<tip>`, take the changed source file back to the tests commit (`git checkout <tests commit> -- src/<file>`), run the test by node id, record the failing output, restore it (`git checkout <tip> -- src/<file>`), and confirm `git status` is clean again. The restore-shaped command is allowed only because the file is clean; a dirty tree gets the backup-first rule of `CLAUDE.md` instead. The three outputs (red, restore, clean status) go on the criterion's line.
   - *The ranks.* A criterion whose test the reviewer cannot make go red is a High: the test does not pin the behaviour. A criterion with no author's record whose test the reviewer did see go red is a Low with the fix text (the line to add to the landing notes). A criterion with no test at all is a High.
6. **One to three probes by node id**: a targeted test, a mutation of one line with the test re-run, a scratch script against an engine. Record the command and the output.
7. **The lenses, in this order:** contract, scale, tests, ownership, adversarial. Read each `SKILL.md` and follow its evidence standard. Every lens writes its close-out ledger even when it finds nothing. One reviewer may run all five within the box; for a 60-minute diff the reviewer may instead launch the `code_review` workflow (engines up, the checker to PASS, the launch verified) and write the file from its synthesis and funnel, naming the run id on the `Method` line.
8. **The security lens** in guidance mode: list the trust boundaries the diff touches; read the ordinary attack-class blocks that match them, and the MCP and tool-argument blocks from `AI-AND-LLM.md` when the diff touches a tool input; trace each boundary from entry to sink; record each result in the skill's three kinds. Run target code only under the rules of step 6 (a scratch script, no network, no live service).
9. **Standards checks**, one line each.
10. **Rank** by the table below. State for each Medium what evidence closes it. Write the fix text for each Low.
11. **A Low that touches only `context/`** the reviewer may commit itself, as the exact text. A code fix stays the author's.
12. **Verdict in one sentence.** It begins "Lands" when nothing stands, or "Does not land yet: …". After the author's fix commits, read them, fill in the Disposition's confirmations, and write the verdict again. A verdict beginning "Lands" is the reviewer's signature on `<tip>` as it then stands.

## The ranking

Three ranks, tied to the verdict. The lens's own label rides along in parentheses so the reader knows which standard produced the finding.

| rank | meaning | what it does to the verdict |
|---|---|---|
| **High** | a wrong answer, data loss, an unsafe default, a statement that grows with batch size, a crossed trust boundary | does not land until fixed |
| **Medium** | a guarantee not evidenced: a criterion met only by reading, a contract with no pin, a scale claim not run on the tightest engine, a security `needs_validation` with its fact still missing | does not land until closed or answered in the Disposition with a reason the reviewer confirms |
| **Low** | a write-in: a nit, a stale docstring, a name, a comment; the fix text is given | lands; no round |

Mapping the lenses onto it: the orchestrator's `critical` and a `major` with a demonstrated failure → High; a `major` with no demonstrated failure → Medium; `minor` and `question` → Low. `scale_review`'s `blocker` → High. `test_review`'s survived mutant → High (a pin regressed). `verify_findings`' DOWNGRADED carries the corrected rank. The Cloudflare skill's `confirmed` at critical, high or medium → High; `confirmed` at low or informational → Medium or Low by the demonstrated damage; `needs_validation` → Medium; `rejected` → not a finding, recorded in the Security section only.

Why three and not four: the verdict has two outcomes, and each rank must say which one it forces. The orchestrator's four-value scale stays inside the lenses, where it already lives; the review file speaks the three words the verdict understands. This is the sibling's rule, kept.

## The rounds, and where the review file sits in the commits

There are no pull requests. A change lands by a commit to `main` when Clay asks. So the code must exist somewhere reviewable before it lands. Two options:

- **Uncommitted working tree.** The diff is `git diff`. There is no commit range to name, no commit messages to review, and a fix cannot be told from the original. Rejected.
- **Local commits on `main`, not yet pushed.** The author commits as they build. The reviewer gets `<base>..<tip>`. A fix is a new commit. The review file is one more commit. Clay asks; the whole sequence is pushed as one push. Recommended.

The rounds, with that choice:

1. The author builds, committing locally: the new tests first, in their own commit, seen failing, with each failing output saved for the landing notes; then the code that passes them. The last code commit is `<tip>`.
2. A fresh agent or a person who did not write the change writes the review file against `<base>..<tip>`. No confirmation round: the reviewer does not ask the author to agree before writing.
3. The author answers each finding in the Disposition, in the review file, and fixes code in new local commits. The author never rewrites or amends the reviewed commits; the reviewer must be able to diff the fix (CPython's rule).
4. The reviewer reads the fix commits, confirms each Disposition line, and writes the verdict again against the new `<tip>`.
5. **The review file is committed last**, after the final code commit, as a context-only commit. Then the landing commit: the spec's Status becomes "landed", its landing notes cite the spec review and the code review by relative path, and the spec moves to its landed folder. The landing commit may be the same commit as the review file's; it may not come before it.
6. Clay asks; one push carries the tests commit, the code commits, the fix commits, the review commit and the landing commit, in that order. A code commit after the review commit means the review did not sign that code: the lint rule below cannot see that from the files alone, so the author states the order in the landing notes and the reviewer's `Reviewed` line names the final tip.

## Installing the Cloudflare skill

- **Command:** `npx skills add https://github.com/cloudflare/security-audit-skill --skill security-audit -a claude-code`, run at the repository root. Node 22.20 or later. The `-a claude-code` target writes `.claude/skills/security-audit/`, beside vfs's seven review skills, where Claude Code loads it (READ, the CLI's agents table). The sibling used the universal target and got `.agents/skills/`; vfs has no `.agents/` folder and every skill it owns lives under `.claude/skills/`, so the Claude Code target is the one that keeps one skill folder. INFERRED: whether the CLI copies or links for this target; either way the files are unchanged.
- **Files installed:** `SKILL.md`, `RECONNAISSANCE.md`, `HUNTING.md`, `VALIDATION-AND-REPORTING.md`, `ATTACK-CLASSES.md`, the nine companions, `report-schema.json`, `validate-findings.cjs`, `validate-coverage-ledger.cjs` and their two test files; and at the root `skills-lock.json`, which records the source repository, the skill path inside it, and a content hash. Commit all of it. The lock file's hash is what "installed unchanged" means; `npx skills check` reports drift and `npx skills update` refreshes to upstream.
- **Licence:** MIT, copyright 2025-2026 Cloudflare, Inc. The `LICENSE` file is at the repository root, not inside the skill folder, so the lock file's source line is the citation; the licence name and holder go in the standard that names the skill.
- **How a review invokes it:** the reviewer reads `SKILL.md` and stays in guidance mode. It does not create an output directory, does not run the six phases, does not write `findings.json`. It reads the attack-class blocks that match the boundaries the diff touches and records results in the skill's three kinds in the review's Security section. Target code runs only as a scratch script with no network and no live service.
- **What a release-time full audit produces:** the sibling's `0.1.0-security-audit-2026-10-25.md` is the model. One review file in `context/reviews/` named `YYYY-MM-DD-<version>-security-audit.md`, and beside it a folder of the same name holding the skill's run folder (`REPORT.md`, `FINDINGS-DETAIL.md`, `NEEDS-VALIDATION.md`, `findings.json`, `coverage-ledger.json`, `architecture.md`, `run-metadata.json`, each agent's evidence), every path rewritten relative to the repository, both validators passing. The review file's header names the profile, the sandbox controls that could and could not be enforced, and what was out of scope. That is a `standard`-profile full audit; it is a release gate, not a per-spec one.
- **Which attack classes apply to vfs**, a library and an MCP server over SQL databases:
  - *Injection*: SQL construction in the storage builders (every identifier and value through SQLAlchemy binds; glob and grep patterns compiled into `LIKE` and regex; the `IN`-list chunking never string-joined). Field names and keys, not only values.
  - *Resource and file handling*: path normalisation (`..`, encoded separators, null bytes, case folding), symlink-shaped edges, the metadata root as a reserved namespace.
  - *Access control*: permission compilation; the same state change reached by two verbs with different checks; bulk writes enforcing per-item permission; mount admission.
  - *Cryptography and secrets*: database URLs carrying passwords in logs, error messages, `Result` payloads or MCP responses; auth tokens for the authority.
  - *AI and LLM companion*: tool-argument injection into the SQL and path sinks; confused deputy (the server's database identity versus the requesting principal's permissions); schema and dispatcher disagreement on tool inputs (aliases, extra fields, coercions); MCP metadata trusted as policy.
  - *Resource exhaustion*: a 10,000-file batch is a contract, so the class is unbounded statement growth, unbounded memory in a whole-corpus build, and fan-out without a deadline.
  - *Data isolation*: one backend shared by two audiences; a search that reveals the existence of a file the caller cannot read.
  - Not applicable per diff, applied at release: supply chain and release (the wheel, the Rust crate's dependencies, CI).

## The lint rule

A pytest test in `tests/` (the folder `scripts/ci.sh` runs), in a module for the context rules, modelled on the sibling's `landed_review_errors` and written here, not copied.

- **Scope:** every spec file under `context/specs/` whose file name begins with a date `YYYY-MM-DD-`. Specs with numbered names are the old shape and are exempt; the intention says only new work takes the new shape, and the name is the switch.
- **Trigger:** the spec's `- **Status:**` line, stars stripped, begins with `landed`.
- **Check:** the text after the `## Landing notes` heading holds at least one `reviews/<name>.md` reference. Every referenced file exists under `context/reviews/`. Among them is at least one whose name ends `-code-review.md` and at least one ending `-spec-review.md`, and each carries the spec's slug. Each cited review's `- **Reviewer:**` line is non-empty, and its `## Verdict` section's first non-blank line begins `Lands`.
- **Failure text:** one line per error, naming the spec and what is missing ("landed, but its landing notes cite no code review"; "cites `reviews/x.md`, which does not exist"; "`reviews/x.md`: Verdict does not begin with Lands").
- **Where it runs:** in the ordinary suite, so `uv run pytest` and `scripts/ci.sh` both hold it. The intention's third "done when" names `scripts/ci.sh`.
- **Tests first, without a pull-request template.** The sibling's box lives in a pull-request description vfs does not have. Here the same claim lives in the spec: the landing notes' "Seen failing first" section is the author's self-check, and the lint rule asks for it. The check: a landed date-named spec's landing notes hold a heading `### Seen failing first` (or a line `Seen failing first:`) under `## Landing notes`, and under it at least one test node id (`tests/...::test_...`), and every node id named there exists in the suite (`uv run pytest --collect-only -q` lists it, or a text search of `tests/` finds the function). The reviewer's step 5a is what makes the record true; the lint only makes it present. A spec whose section says "no new behaviour" by name is allowed through, so a documentation or refactor landing is not forced to invent a test.
- **What it cannot check:** that the review's `<tip>` is the commit that landed, or that no code commit followed the review commit. That needs git history, not the files; the sibling's `ci-status` reads the pull request's commits for it. Without pull requests, the landing notes state the order and the reviewer's `Reviewed` line names the final tip; a later rule may read `git log` for the review file's commit and the spec's.

The sibling's rule is the same shape minus the kind check and the verdict check. Adding those two is cheap and closes the two ways a cited file could exist without being a signature: a spec review cited where a code review was needed, and a review whose verdict says "does not land yet".

## One line

One Markdown file per change, `YYYY-MM-DD-<spec slug>-code-review.md`, written by someone who did not write the change, with each criterion tied to the test that pins it and the evidence it was seen failing first, one ranked findings list, one close-out ledger per lens, one Security section in the Cloudflare skill's guidance mode and vocabulary, a three-rank scale tied to a verdict that begins "Lands", committed after the last code commit and before the landing commit, and held by one pytest rule that a landed spec cites a code review that exists and says "Lands".
