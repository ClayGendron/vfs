---
name: code_review
description: Run the full multi-agent code review of a commit set — the local unpushed commits that will land one spec, one commit, or a contiguous range — or an explicitly named code area, before it lands; five parallel review agents (ownership_review, contract_review, scale_review, test_review, adversarial_review), an adversarial verifier per finding (verify_findings), a final synthesis agent, and the review file written to context/reviews/ with a Security section and a verdict that begins "Lands" or "Does not land yet". Use when the user asks for a "code review", "review before landing", "review the last commit(s)", "review <sha>/ <sha range>", "review the <spec> landing", or "review <module/path>" with the whole suite.
---

# Code review — the full suite as one workflow

Orchestrate the five review lenses over one committed change, verify
every finding adversarially, and deliver a single synthesized report.
Invoking this skill is the user's opt-in to multi-agent orchestration:
launch it with the Workflow tool.

The review happens **before the landing, not after a commit is
pushed**. The house pipeline is intent → research → spec → spec review
→ code → **code review → commit (the landing)**: the author builds on
`main` in local commits that are not pushed, a reviewer who did not
write the change reviews those commits, and only then does one landing
commit go to `main` and get pushed when Clay asks. So the unit of
review is a **commit set**: the local unpushed commits `<base>..<tip>`
on `main` that will land one spec, or one commit, or a contiguous
range. A named code area (a module, a subsystem) is the alternative
scope when the user asks for one. The deliverable is a file,
`context/reviews/YYYY-MM-DD-<spec-slug>-code-review.md` (§4), whose
standing verdict must begin "Lands" before the change lands; the
landing commit carries that file, so the review never lands after the
code it reviewed.

The design follows the suite's contract: each lens owns a defect class,
so the five reviewers run in parallel without overlap; the verifier
exists because unverified findings cost the reader attention — only
findings that survive refutation reach the report.

The orchestrator's own procedure is five numbered steps — **resolve
the scope (§0), bring up the engines then author + check + launch the
script (§1), verify the launch (§2), report and tear down (§3), write
the review file (§4)** — and the §1 checker and §2 check are not
optional: a launch whose scope is wrong or whose prompts did not render
is a review of nothing, and nothing downstream detects that.
The *Shape* and *Per-agent rules* sections between §0 and §1 describe
what the launched workflow does internally. The five lens skills
(`ownership_review`, `contract_review`, `scale_review`, `test_review`,
`adversarial_review`) and `verify_findings` are **unchanged** by the
review-file step: they run as they always have, with their own
vocabularies and close-out ledgers; §4 only says how their output is
written into the file.

Time box: **30 minutes** of the orchestrator's own attention, or **60**
when the diff touches the database backend, a dialect profile, the
Rust crate, or the MCP tool surface; the workflow's agents run inside
it. The file states the box and where you stood when it ran out.

## 0. Resolve the commit scope first — inline, before launching

Reviewers cannot review what they were not pointed at, and a scope
placeholder that reaches an agent verbatim is a silent no-op. Resolve
the scope yourself in a few tool calls, then pass it into the workflow
as `args` — never as hand-substituted text in the script:

- **Resolve what the user named** into concrete SHAs: explicit SHAs, a
  range (`A..B`), "the last N commits", a spec or slice's landing (find
  its commits in `git log --oneline`), or a path area. Nothing named →
  the local unpushed commits on `main` (`git log --oneline
  origin/main..HEAD`), which is the set a review before the landing
  reads; when nothing is unpushed, the latest commit — widened to the
  whole landing when the tip commits are one change split into its
  conventional pieces (fix/feat/docs of the same work); say in the
  report which commits you resolved to and why.
- **The diff of the set is the review surface**:
  `git log --oneline <base>..<tip>` for the list,
  `git diff --stat <base>..<tip>` for the touched files,
  `git show <sha>` for each message. Reviewers read whole files and
  surrounding code at the tip to *judge* the change, but report only on
  what the set changed.
- **Sanity-check the range arithmetic.** `<base>` is the parent of the
  **oldest** commit in the set — and commit-date order is not
  guaranteed to match `git log` order, so identify the oldest from the
  log, not from timestamps. Then confirm
  `git log --oneline <base>..<tip> | wc -l` equals the number of
  commits you mean to review: an off-by-one base (the second-oldest's
  parent) silently drops the oldest commit's diff from the review
  surface while its message still appears in the scope, and nothing
  downstream notices.
- **Commit messages are reviewed material.** Include each commit's
  subject and body in the scope string — a commit message is declared
  intent, and its claims ("all four legs pass", "X is deleted") are
  promises the lenses, contract review especially, verify like any
  docstring.
- **Check for drift**: `git status --porcelain`. A dirty working tree
  over scoped files means the tree no longer matches the tip — name the
  drifted files in the scope string and instruct reviewers to judge the
  committed state (`git show <tip>:<path>`) wherever the two differ. A
  clean tree at the tip needs no ceremony: files read normally.
- **Area scope** (when the user names code rather than commits): list
  the paths and state that the review surface is the current committed
  state of those paths, not a diff. Recent `git log` on those paths is
  context worth passing along.

Materialize `repo`, `scope`, and `scratch` as the authored constants
block of §1, where `scope` carries the resolved SHAs, subjects and
messages, the changed-file list, and any drift caveat. No
`<placeholder>` string and no `undefined` ever survives into a prompt —
the §1 checker and the §2 post-launch check both enforce this.

## Shape

1. **Review** — five agents in parallel, one per skill, each running on
   Fable (`model: 'fable'`). Each agent is instructed to read its skill
   file and follow it exactly:
   - `.claude/skills/ownership_review/SKILL.md` — structure: who owns each block of logic
   - `.claude/skills/contract_review/SKILL.md` — implementation vs declared contracts
   - `.claude/skills/scale_review/SKILL.md` — bounded at production scale, tightest engine
   - `.claude/skills/test_review/SKILL.md` — do the tests pin the contract
   - `.claude/skills/adversarial_review/SKILL.md` — executed attacks on the change
2. **Verify** — verifiers follow
   `.claude/skills/verify_findings/SKILL.md`, on Opus (`model: 'opus'`),
   at high effort. Findings verify as soon as their reviewer finishes
   (pipeline, no barrier between lenses). **One independent skeptic per
   finding, whatever its severity.** A finding survives only if its
   verifier does not refute it; a verifier that died leaves the finding
   UNVERIFIED, never clean.
3. **Synthesize** — after all verification completes, one agent on
   Fable (`model: 'fable'`) merges the surviving findings: dedups
   across lenses, ranks by severity, and writes the report. **Skipped
   entirely when nothing survived** — an empty review is reported
   directly, not narrated by an agent with no material.

## Per-agent rules (must appear in every prompt)

- **uv project**: everything runs as `uv run python ...`,
  `uv run pytest ...`, `uv run ty check ...` from the repo root.
- **Repo is read-only**: never modify, stash, checkout, or commit
  anything. Scratch scripts go ONLY under the session scratchpad.
  Reviewers do not need `isolation: 'worktree'` — nothing writes.
- **Follow the skill file**: the agent's first action is reading its
  assigned SKILL.md; the skill's procedure and evidence standard are
  binding.
- **Structured findings**: reviewers return findings via the schema —
  never prose-only.
- **The close-out ledger is not optional.** Four of the five lenses end
  by requiring a statement of what was checked and found clean, because
  a review reporting only findings hides how much of the surface was
  actually verified. That ledger goes in the schema's `coverage` field —
  including anything the lens deliberately did not reach (a spent time
  box, an engine it could not exercise). A lens that returns findings
  but no coverage has not finished.
- **Severity is normalized at the seam.** Each lens keeps its own
  vocabulary internally (breach/growth/decay/gap;
  misplacement/duplication/envy/leak/divergence; blocker/major/minor;
  high/medium/low); the reviewer carries that label in `category` and
  maps it onto the schema's shared scale: `critical` (corruption, data
  loss, wrong results), `major` (violated contract, failure at
  supported scale, unpinned high-risk behavior), `minor` (bounded
  waste, decay, smells), `question` (design notes, ambiguous intent).
- **Live engines**: the template's `ENGINES` block puts the four real
  engines' connection URLs (Postgres, MariaDB, MSSQL, Oracle — up,
  ephemeral data) in every prompt. Agents use them for empirical
  evidence — scratch scripts or targeted `-m <engine>` test
  selections, each under its own schema so concurrent agents
  do not collide — and never start, stop, or manage Docker themselves.

## 1. Bring up the engines, author the script, check it, launch it

The canonical orchestration code lives in
**`.claude/skills/code_review/workflow_template.js`** — single source
of truth; fixes to the orchestration go there, never into authored
copies. The launch is file-based and gated by a checker; never launch
from an inline `script` string with `args` (the `args` global has been
observed silently failing to bind — see §2).

1. **Engines up.** The template's prompts promise every agent live
   database engines; make that true before anything launches. Follow
   the db_test skill's build-up: start Docker Desktop, bring up all
   four engines with query-level health waits (postgres via plain
   `up -d --wait`, the heavyweights by name), and install every
   driver in one `uv sync --extra postgres --extra mariadb --extra
   mssql --extra oracle --extra documents --group dev` (the document
   libraries, because the conformance contract renders real files on
   every engine). The checker refuses to PASS
   while any engine port is unreachable. Engines stay up for the
   whole run — reviewers and verifiers both use them — and come down
   in §3.

2. **Author.** Copy `workflow_template.js` into the session scratchpad
   and replace its `// __SCOPE_CONSTANTS__` line with the one block
   you write:

   ```js
   // --- scope constants (authored per review; everything else is fixed) ---
   const repo = '<absolute repo path>'
   const scratch = '<absolute session-scratchpad path>'
   const scope = `<the §0 scope: range, commits with subjects and bodies,
   changed files, drift caveats — escape any backtick and ${ inside>`
   // --- end scope constants ---
   ```

   Everything outside the two marker lines must stay byte-identical to
   the template; the checker enforces it.

3. **Check.** Run
   `uv run python .claude/skills/code_review/check_workflow.py <authored file>`
   and iterate until PASS. The checker re-derives ground truth from
   git and fails on: drift from the template outside the authored
   block; destructuring scope from `args`; `undefined` or placeholders
   in the scope; range/enumeration mismatches — including the
   off-by-one base that silently drops the oldest commit and the scope
   naming the base as if reviewed; a commit subject missing from the
   scope (bodies warn); working-tree drift over scoped files with no
   drift caveat naming them; unescaped `${` interpolation; any of the
   four engine ports unreachable (see step 1). A script that fails the
   checker is never launched.

4. **Launch** with `{ scriptPath: <authored file> }` — no `script`, no
   `args`. The tool result returns a task ID, a transcript dir, a
   `scriptPath`, and a `runId` — keep all four: §2 reads the
   transcript dir; stopping, salvage, and iteration use the task ID,
   script path, and run ID.

## 2. Verify the launch — read the prompts the agents actually got

**The failure this step catches.** `args` can silently fail to bind:
the script's `args` global has been observed arriving `undefined` even
though the Workflow call passed a valid JSON object. Every reviewer
prompt then opens with `Repo: undefined. Scope under review:
undefined` — five agents dutifully reviewing nothing, returning
plausible-looking findings and coverage, with no error raised
anywhere. The §1 flow (inlined constants, checker-gated) exists to
make this impossible, but §2 stays as the runtime backstop: it is the
only check that reads what the agents *actually received*, and it
costs one `head`.

**The check.** As soon as the first review agents appear in the
transcript dir from §1, read the opening of one transcript — each
`agent-*.jsonl` line 1 is that agent's prompt:

```sh
head -1 <transcript-dir>/agent-*.jsonl | head -c 400
```

Pass: the text opens with the real repo path and the resolved scope
(SHAs, commit subjects). Fail: any `undefined` or placeholder where
those values belong. One transcript is enough — all prompts render
from the same `RULES` string.

**Recovery when the scope did not render** — the run is invalid and
every result in it is meaningless, however normal it looks. Recovery
is a full re-run: the corrected prompts match nothing in the cache, so
every reviewer runs again at full cost. That makes it an approval
decision, not an orchestrator reflex:

1. **Get user approval first — DO NOT STOP A RUN WITHOUT GETTING
   APPROVAL.** Report what the prompts rendered as, what a re-run
   costs, and wait. Stopping is cheap; what approval protects is the
   re-run-from-the-top that follows it.
2. Once approved: `TaskStop` with the task ID from §1, then fix the
   script per §1 — a legacy args-based script gets its
   `const { repo, scope, scratch } = args` line replaced by the
   authored constants block — and run the checker to PASS before
   relaunching. Inlining is the reliable form: the values live in the
   script text and nothing depends on `args` binding.
3. Relaunch fresh with `{ scriptPath }` — **no `resumeFromRunId`**.
   The invalid run's cache holds answers to the `undefined` prompts;
   the corrected prompts would miss that cache anyway, and a fresh
   launch cannot accidentally reuse a bad result.
4. Run the check again on the new run's transcript dir. Only a run
   whose rendered prompts carry the real scope counts as a review.

## Stopping, resuming, salvage — never pay for a finished agent twice

The review's cost lives in its agents — five Fable reviewers and one
Opus verifier per finding. Losing their finished work by
restarting from the top is the most expensive mistake this skill can
make, so these rules bind the orchestrator:

- **DO NOT STOP A RUN AND RE-RUN FROM THE TOP WITHOUT EXPLICIT USER
  APPROVAL.** One full review is worth its cost; paying for the same
  review twice is not. This includes stopping to fix a scope
  imperfection you discovered mid-run: present the defect, the cost of
  each option, and let the user decide.
- **Stop-and-resume is safe and needs no approval.** Every completed
  `agent()` call is journaled by prompt hash. Relaunching with
  `{ scriptPath, resumeFromRunId }` and an **unchanged** script
  replays every finished agent from cache instantly and free,
  re-running only work that was in flight or not yet started.
- **Editing the script can silently convert a resume into a re-run.**
  The cache hits only unchanged `(prompt, opts)` pairs, and the
  reviewers' and verifiers' prompts all embed the shared `RULES`
  string — so editing `repo`/`scope`/`scratch` or `RULES` invalidates
  *every* agent at once. Before resuming an edited script, work out
  which prompts changed; if the answer is "all of them", that is a
  re-run-from-the-top and needs approval.
- **A mid-run scope defect rarely justifies a restart.** The default
  is to let the run finish and caveat the report, then offer a
  targeted supplement — e.g. one extra reviewer over just the missed
  surface, its findings verified the same way — which costs one agent,
  not a fleet.
- **Approved corrections that must not lose finished work** use a
  continuation script: read the finished lens results out of
  `journal.jsonl` (or the `agent-*.jsonl` transcripts), inline them as
  literal constants in a new script that skips those lenses, and run
  only the missing or corrected pieces plus their verification and the
  synthesis.

## Iterating on a run

Every launch persists its script and returns a `scriptPath` and
`runId`. To adjust a lens prompt or the adjudication rule, edit that
file and relaunch with `{ scriptPath, resumeFromRunId }` — the
unchanged prefix of `agent()` calls returns cached instantly, so only
the edited stage re-runs. Before diagnosing an empty or surprising
result, read `journal.jsonl` in the transcript directory: it records
what each agent actually returned. Do not assume a lens was clean when
its agent may simply have failed.

## 3. Reporting and teardown

1. **Relay the synthesized report**, then write it into the review
   file (§4) — the file is the deliverable the landing needs; the relay
   is for the user in the session. Do not paste raw per-agent output.
   Lead with the resolved scope: the exact commits (SHA + subject) or
   paths reviewed, so the report is traceable to a fixed state of the
   tree.
2. **Call `ReportFindings` once** with the surviving findings, most
   severe first, so the host UI renders them: map `claim` →
   `summary`, the verifier's repro or failure path →
   `failure_scenario`, `title` → `short_summary` (≤60 chars), the
   lens's own label → `category`, and the adjudicated verdict →
   `verdict`. Report findings through the tool *or* as text, not both.
3. **Show the funnel** — raw findings vs survivors, per lens, from the
   returned `ledger`. A lens with zero raw findings *and* a coverage
   ledger is a result: say what it checked. A lens whose agent failed
   is *not* a clean lens — it left that surface unreviewed, and saying
   "no findings" for it is the one reporting error that makes the whole
   review misleading rather than merely incomplete.
4. **Surface the leads** — unverified observations verifiers noticed in
   passing, clearly labelled as unverified, at the end.
5. **Never apply fixes as part of the review.** If the user asks for
   fixes afterward, re-report with `outcome` set per finding. A fix is
   the author's, as a new local commit on top of `<tip>`; the reviewed
   commits are never amended or rewritten, so the fix can be diffed.
6. **Restore the machine.** Once the report is delivered and no
   follow-up supplement still needs the engines, tear down per the
   db_test skill: compose down naming every profile, verify no
   `vfs-test-*` containers remain, quit Docker Desktop. Skip teardown
   only when something else in the session (a resumed run, another
   engine task) is still using the containers — then it owns teardown.

## 4. Write the review file

The synthesis becomes one file under `context/reviews/`, written by
the orchestrator (or by a person who did not write the change) and
committed by the author inside the landing commit. The file is what
the lint reads and what the spec's landing notes link; a review that
stays in the session is lost.

**Name and shape.** `context/reviews/YYYY-MM-DD-<spec-slug>-code-review.md`:
the date is the review's own day (a second review on a later day is a
new file), the slug is the spec's file name after its date, no number
anywhere. The title is `# Code review of <spec title>`. The opening
paragraph carries **no header bullets**; it names the reviewer (and,
when the orchestrator is a sub-agent of the author's session, says "a
fresh sub-agent of the author's session; not the author"), the spec as
a Markdown link with its spec review beside it, the range
`<base>..<tip>` with the commit count and whether the tree was clean
at `<tip>`, what was re-ran (`scripts/ci.sh` with each step's PASS or
FAIL, test counts and exit code; the engine legs by `-m <engine>` with
counts when storage changed; the probes by node id), the method (the
workflow run id and funnel, or "one reviewer, lenses in order"), and
the box with where you stood. Say once: "EXECUTED means I ran it;
READ means I read the file cited; INFERRED means my reasoning." Then
these `## ` headings, in this order, exactly:

1. `Scope` — the commits one line each (`<sha> <subject>`), what the
   diff touches (`git diff --stat`), any drift caveat.
2. `Acceptance criteria against evidence` — one line per criterion,
   quoted from the spec, met or not met with its label, the test node
   id that pins it, and the evidence or the gap. A criterion met only
   by INFERRED is a Medium; a criterion with no test is a High.
3. `Findings, most severe first` — the one ranked list. Each line:
   rank, the lens in parentheses with the lens's own label, the title,
   `path:line`, the defect in one sentence, the concrete failure, and
   what closes it (for a Low, the fix text). An UNVERIFIED finding
   says so.
4. `Lenses` — with `### Contract`, `### Scale`, `### Tests`,
   `### Ownership`, `### Adversarial`, in that order. A subsection
   holds no findings of its own: it holds the lens's method notes and
   **ends in its close-out ledger** — what it checked and found clean
   and what it did not reach — taken from the workflow's `coverage`
   field. A lens with zero findings still writes its ledger; a lens
   whose agent failed writes "unreviewed surface", never "clean".
5. `Security` — the lens below.
6. `Standards checks` — the five lines below.
7. `Disposition` — the author fills it in, one line per finding
   ("fixed in `<commit>`: …" or "not fixed because …"); you confirm
   each line with a label. Leave one line saying it awaits the author
   when you first write the file.
8. `Verdict` — the first line is the verdict.

Like every document under `context/`, the file has one-line paragraphs
(a paragraph or list item is one line of any length) and cites by
Markdown link, never by number.

**The ranking.** The verdict has two outcomes, so the file speaks three
ranks; the workflow's four-value scale stays inside the lenses and
rides along in parentheses. Map it so:

| the file's rank | meaning | from the workflow and the lenses |
|---|---|---|
| **High** — does not land until fixed | a wrong answer, data loss, an unsafe default, a statement that grows with batch size, a crossed trust boundary, a criterion with no test or whose test cannot go red | `critical`; a `major` with a demonstrated failure; `scale_review`'s `blocker`; a `test_review` survived mutant; a Security `confirmed` at critical, high or medium |
| **Medium** — does not land until closed, or answered in the Disposition with a reason you confirm | a guarantee not evidenced: a criterion met only by reading, a contract with no pin, a scale claim not run on the tightest engine, a Security `needs_validation` with its fact still missing | a `major` with no demonstrated failure; `needs_validation`; a `confirmed` at low or informational when the damage warrants it |
| **Low** — lands; no round | a write-in: a nit, a stale docstring, a name, a comment, with the fix text given | `minor`; `question`; a `confirmed` at low or informational otherwise |

`verify_findings`' DOWNGRADED carries its corrected severity through
the same map. A `rejected` security record is not a finding; it is
recorded in the Security section only. State for each Medium what
evidence closes it. Number findings H1, M1, L1 and so on.

**The Security lens.** It runs the installed security-audit skill at
`.claude/skills/security-audit/SKILL.md` (cloudflare/security-audit-skill,
MIT, installed unchanged; the lock is `skills-lock.json` at the repo
root) in its **guidance mode**: no run folder, no output directory, no
`findings.json`, no six phases, no artifacts. It is not one of the
workflow's five agents; run it yourself after the workflow returns, or
as one focused agent that returns to you, inside the box. This is the
vendored skill, not Claude Code's built-in `security-review` skill.
The procedure:

1. Name the **trust boundaries the diff touches**, each as the
   skill's evidence bar asks: the lower-trust principal, the input or
   action it supplies, the control that should stop it, and the sink.
   For vfs the usual ones are the SQL builders and the glob and grep
   pattern compilers (injection), path normalisation and the metadata
   root (resource and file handling), permission compilation and
   mount admission (access control), database URLs in logs, errors,
   `Result` payloads or MCP responses (cryptography and secrets),
   batch size and whole-corpus builds (resource exhaustion), one
   backend shared by two audiences and search as an existence oracle
   (data isolation). A diff that touches none says "none" and why.
2. Read the **matching blocks** of `ATTACK-CLASSES.md` (Injection,
   Access control, Resource and file handling, Cryptography and
   secrets, Business logic, Feature abuse and data leakage, Chained
   vulnerabilities and trust boundaries, Obvious things), and, when
   the diff touches a tool input on the MCP surface, the "Tool and
   action attack classes" and "MCP and sub-agent trust classes"
   blocks of `AI-AND-LLM.md`. Name the blocks you read in the section.
3. **Trace each boundary from entry to sink** through the code at
   `<tip>`. Any target code runs only as a scratch script under the
   session scratchpad with no network and no live service, under the
   skill's execution-safety rules; when a sandbox control cannot be
   enforced, do not run it and record the gap.
4. **Record each result** in the skill's three kinds: `confirmed`
   with its severity (critical, high, medium, low, informational, by
   the skill's anchors), `needs_validation` naming the exact missing
   fact and a safe plan to get it, or `rejected` with why. A missing
   best practice is not a record. A `confirmed` record is also a
   ranked finding above, by the table.

The Security section opens with one line naming the method (the skill
path, guidance mode, no run folder), then the boundaries, the blocks
read, and the records.

**Standards checks**, one line each, in this order:

- *Tests first*: the code stage is tests first, then code — an
  instruction of how to code, not a record to audit. No written record
  of the red run is required and none is asked for. You may reproduce
  one red yourself: after every workflow agent has finished (never
  while they run), on a file `git status` reports clean, copy it to the
  scratchpad, write the pre-change version over it with
  `git show <base>:<path>`, run the pinning test by node id, record the
  red, restore from the scratchpad copy, and confirm `git status` is
  clean again. A test that will not go red is a High (it pins
  nothing). The line says what you did, or "not reproduced".
- *The constitution* (`context/standards/constitution.md`): each
  article the diff touches and whether it holds; Article 1's five
  primitives named when the diff composes or manipulates them.
- *The production posture* (`CLAUDE.md`): never assumes SQLite; no
  statement grows with batch size; budgets from the dialect profile;
  no designed scale cap; no numpy.
- *The patterns standard* (`context/standards/how-we-code.md`): each
  named pattern the diff uses or should have used.
- *Tooling*: `ruff check`, `ruff format --check` and `ty` at zero;
  `assert` narrows only; imports at the top; no spec, ADR or story
  number in code comments or docstrings.

**The verdict and the re-sign protocol.** The Verdict section's first
line begins **"Lands"** (nothing High or Medium stands; say why in one
sentence) or **"Does not land yet: <the Highs, or the Mediums and what
closes them>"**. No third form and no hedge. The author answers every
finding in the Disposition and fixes code in new local commits on top
of `<tip>`; you read the fix commits, confirm each Disposition line
with a label, and sign again as a line below the first verdict
beginning `YYYY-MM-DD, re-read on <commit>:` followed by the verdict
word. The first verdict stays. **The last such dated line is the
standing verdict**, and the landing needs it to begin "Lands". A
`<tip>` that moved by a code commit after your last signature is not
signed; read it and sign again.

**What you may and may not touch.** Write the one review file; never
edit `src/`, `tests/`, the spec or any other document, and never run a
git command that changes state. A Low whose fix touches only
`context/` you may write as its exact text in the finding; the author
applies it. The author commits the review file in the landing commit
with the spec's landing notes linking it.
