---
name: code_review
description: Run the code review of a commit set — the commits a work branch adds, one commit, or a contiguous range — or an explicitly named code area, before it lands; one fresh Opus agent that did not write the change, given the diff and the spec, runs the five lenses in order (contract_review, scale_review, test_review, ownership_review, adversarial_review), tries to refute each of its own findings (verify_findings), runs the Security lens, and writes the review file to context/reviews/ with a verdict that begins "Lands" or "Does not land yet". Use when the user asks for a "code review", "review before landing", "review the last commit(s)", "review <sha>/ <sha range>", "review the <spec> landing", or "review <module/path>".
---

# Code review — one fresh reviewer, five lenses in order

One agent reviews one committed change: it runs the five review lenses
in order, tries to refute each of its own findings, runs the Security
lens, and writes a single review file.

**The review is one agent's work, on Opus.** The reviewer is started
with the Agent tool (`model: 'opus'`) as a fresh agent that did not
write the change. There is no fan-out: no agent per lens, no agent per
finding, no synthesis agent, no workflow script and no Workflow tool.
One reviewer holds the spec, the diff and every finding in one head, so
nothing is lost between a lens and the report, and a review costs one
agent. A second model can review beside the first when the developer
asks for it; that is a second single review, never a fleet.

The review happens **before the landing, not after a commit is
pushed**. A reviewer who did not write the change reviews the commits,
and only then does the change go to its pull request. So the unit of
review is a **commit set**: the commits `<base>..<tip>` that a work
branch adds, or one commit, or a contiguous range. A named code area (a
module, a subsystem) is the alternative scope when the user asks for
one. The deliverable is a file,
`context/reviews/YYYY-MM-DD-<spec-slug>-code-review.md` (§4), whose
standing verdict must begin "Lands" before the change lands; the change
carries that file, so the review never lands after the code it
reviewed.

The procedure is five numbered steps — **resolve the scope (§0), start
the reviewer (§1), the review itself (§2), report and tear down (§3),
the review file (§4)**. The session that asks for the review does §0,
§1 and §3; the reviewer does §2 and §4. The five lens skills
(`contract_review`, `scale_review`, `test_review`, `ownership_review`,
`adversarial_review`) and `verify_findings` are unchanged: each holds
its own procedure, vocabulary and close-out ledger, and the reviewer
follows them one after another.

Time box: **30 minutes** of the reviewer's work, or **60** when the
diff touches the database backend, a dialect profile, the Rust crate,
or the MCP tool surface. The file states the box and where the reviewer
stood when it ran out.

## 0. Resolve the commit scope first — before the reviewer starts

A reviewer cannot review what it was not pointed at. Resolve the scope
in a few tool calls and put it in the reviewer's brief as concrete
SHAs, never as a description to be worked out:

- **Resolve what the user named** into concrete SHAs: explicit SHAs, a
  range (`A..B`), "the last N commits", a spec or slice's landing (find
  its commits in `git log --oneline`), or a path area. Nothing named →
  the commits the work branch adds over the branch it will land on
  (`git log --oneline origin/dev..HEAD` for a work branch off `dev`);
  when there are none, the latest commit — widened to the whole change
  when the tip commits are one change split into its conventional
  pieces; say in the report which commits were resolved and why.
- **The diff of the set is the review surface**:
  `git log --oneline <base>..<tip>` for the list,
  `git diff --stat <base>..<tip>` for the touched files,
  `git show <sha>` for each message. The reviewer reads whole files and
  surrounding code at the tip to *judge* the change, but reports only
  on what the set changed.
- **Sanity-check the range arithmetic.** `<base>` is the parent of the
  **oldest** commit in the set — and commit-date order is not
  guaranteed to match `git log` order, so identify the oldest from the
  log, not from timestamps. Then confirm
  `git log --oneline <base>..<tip> | wc -l` equals the number of
  commits meant: an off-by-one base (the second-oldest's parent)
  silently drops the oldest commit's diff from the review surface, and
  nothing downstream notices.
- **Commit messages are reviewed material.** A commit message is
  declared intent, and its claims ("the engine legs pass", "X is
  deleted") are promises the lenses, contract review especially, verify
  like any docstring. The reviewer reads them from `git show`.
- **Check for drift**: `git status --porcelain`. A dirty working tree
  over scoped files means the tree no longer matches the tip — name the
  drifted files in the brief and tell the reviewer to judge the
  committed state (`git show <tip>:<path>`) wherever the two differ. A
  clean tree at the tip needs no ceremony: files read normally.
- **Area scope** (when the user names code rather than commits): list
  the paths and state that the review surface is the current committed
  state of those paths, not a diff. Recent `git log` on those paths is
  context worth passing along.

## 1. Start the reviewer

1. **Engines up, when storage changed.** A reviewer that is told an
   engine is live must find it live. When the diff touches the database
   backend, the schema or a dialect profile, follow the db_test skill's
   build-up for the engines the change is to be judged on before the
   reviewer starts, and leave them up until §3. A diff that touches no
   storage needs none.
2. **Write the brief.** The reviewer starts with nothing but its brief,
   so the brief carries everything it needs and nothing that would
   steer its verdict:
   - the repository path, the range `<base>..<tip>` with the commit
     count, the branch it will land on, and any drift caveat from §0;
   - the spec's path, where there is one, as the declared contract;
   - rulings the developer has already made that bound the change,
     stated as rulings, so a finding against one is a note and not a
     defect;
   - the engines that are up, with their connection URLs, and the ones
     that are down on purpose;
   - the rules of §2 that bind it, and the review file's path;
   - what its final message returns: the file's path, the verdict line,
     the findings most severe first, what was run and what was not
     reached.

   **Never the author's summary.** The brief holds no account of how
   the change was built, no reasoning from the author's session, no
   list of what the author thinks is risky and no expected verdict. A
   reviewer handed the author's view of the change tends to hand it
   back confirmed.
3. **Start one agent** with the Agent tool: `model: 'opus'`, a fresh
   agent, not a fork of the author's session. It runs in the
   background; nothing else reviews the same change while it runs.

## 2. The review — what the reviewer does

- **uv project**: everything runs as `uv run python ...`,
  `uv run pytest ...`, `uv run ty check ...` from the repo root, and
  every command carries a deadline set from an estimate.
- **The repo is read-only apart from the review file**: never modify,
  stash, checkout, or commit anything, and never edit `src/`, `tests/`,
  the spec or another document. Scratch scripts go ONLY under the
  session scratchpad.
- **The lenses, in this order**, each skill file read before its lens,
  its procedure and evidence standard binding:
  - `.claude/skills/contract_review/SKILL.md` — implementation vs declared contracts
  - `.claude/skills/scale_review/SKILL.md` — bounded at production scale, tightest engine
  - `.claude/skills/test_review/SKILL.md` — do the tests pin the contract
  - `.claude/skills/ownership_review/SKILL.md` — structure: who owns each block of logic
  - `.claude/skills/adversarial_review/SKILL.md` — executed attacks on the change
- **The reviewer is its own skeptic.** Before a finding goes in the
  file it is put through `.claude/skills/verify_findings/SKILL.md`:
  reproduce the claimed failure, check declared intent, check
  reachability. A finding that is refuted is dropped; one that could be
  neither reproduced nor refuted is written as UNVERIFIED, never as
  established. Unverified findings cost the reader attention, so only
  what survives refutation is ranked.
- **The close-out ledger is not optional.** Each lens ends with a
  statement of what was checked and found clean, because a review
  reporting only findings hides how much of the surface was actually
  read — including anything the lens deliberately did not reach (a
  spent time box, an engine it could not exercise). A lens that was not
  run or not finished is unreviewed surface, never a clean lens.
- **Severity is normalized on one scale.** Each lens keeps its own
  vocabulary internally (breach/growth/decay/gap;
  misplacement/duplication/envy/leak/divergence; blocker/major/minor;
  high/medium/low); the reviewer carries that label beside the finding
  and maps it onto the shared scale: `critical` (corruption, data loss,
  wrong results), `major` (violated contract, failure at supported
  scale, unpinned high-risk behavior), `minor` (bounded waste, decay,
  smells), `question` (design notes, ambiguous intent). §4 maps that
  scale onto the file's three ranks.
- **Live engines**: the engines the brief names as up are used for
  empirical evidence — scratch scripts or targeted `-m <engine>` test
  selections, each under its own schema. The reviewer never starts,
  stops, or manages Docker itself. An engine-dependent claim is never
  reported as verified without the engine having been touched.
- **Then the Security lens and the review file**, per §4.

## 3. Reporting and teardown

1. **Read the review file the reviewer wrote**, then relay it: lead
   with the resolved scope — the exact commits (SHA + subject) or paths
   reviewed — so the report is traceable to a fixed state of the tree,
   then the verdict and the findings, most severe first. Do not paste
   the reviewer's raw output.
2. **Call `ReportFindings` once**, where the host offers it, with the
   findings most severe first: the defect → `summary`, the repro or
   failure path → `failure_scenario`, the title → `short_summary`
   (≤60 chars), the lens's own label → `category`. Report findings
   through the tool *or* as text, not both.
3. **Say what was not reviewed.** A lens with zero findings and a
   ledger is a result: say what it checked. A lens the reviewer did not
   finish is *not* a clean lens, and saying "no findings" for it is the
   one reporting error that makes a review misleading rather than
   merely incomplete.
4. **The review never applies fixes.** A fix is the author's, as a new
   commit on top of `<tip>`; the reviewed commits are never amended or
   rewritten, so the fix can be diffed. The author answers every
   finding in the Disposition, and the same reviewer — continued, with
   its context intact — reads the fix commits and signs again (§4).
5. **Restore the machine.** Once the verdict stands and nothing else
   needs the engines, tear down per the db_test skill: compose down
   naming every profile, verify no `vfs-test-*` containers remain, quit
   Docker Desktop when the session started it. Skip teardown only when
   something else in the session is still using the containers — then
   it owns teardown.

## 4. Write the review file

The review becomes one file under `context/reviews/`, written by the
reviewer and committed by the author with the change. The file is what
the lint reads and what the spec's landing notes link; a review that
stays in the session is lost.

**Name and shape.** `context/reviews/YYYY-MM-DD-<spec-slug>-code-review.md`:
the date is the review's own day (a second review on a later day is a
new file), the slug is the spec's file name after its date, no number
anywhere. The title is `# Code review of <spec title>`. The opening
paragraph carries **no header bullets**; it names the reviewer (and,
when the reviewer is a sub-agent of the author's session, says "a
fresh sub-agent of the author's session; not the author"), the spec as
a Markdown link with its spec review beside it, the range
`<base>..<tip>` with the commit count and whether the tree was clean
at `<tip>`, what was re-ran (`scripts/ci.sh` with each step's PASS or
FAIL, test counts and exit code; the engine legs by `-m <engine>` with
counts when storage changed; the probes by node id), the method ("one
reviewer, lenses in order"), and the box with where you stood. Say
once: "EXECUTED means I ran it; READ means I read the file cited;
INFERRED means my reasoning." Then these `## ` headings, in this order,
exactly:

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
   and what it did not reach. A lens with zero findings still writes
   its ledger; a lens that was not run or not finished writes
   "unreviewed surface", never "clean".
   **The `### Ownership` subsection opens with two lines**, each a
   paragraph of its own that begins at the margin, taken from step 0
   of the ownership lens, which runs `git diff <base>..<tip> --
   tests/lint/test_code_shape.py tests/lint/allowlist.py` (against
   `HEAD` when the working tree is what is reviewed):
   - `Layer map: <module> on rung <n>, for each touched module; adds
     <import> to rung <n>, for each added import; <closing>.` The
     closing is one of three: "ladder unchanged" when the command
     shows nothing for `tests/lint/test_code_shape.py`, and an empty
     output is the only ground for those two words alone;
     "ladder unchanged, the file changed elsewhere:" and then what
     changed, when the file changed and none of its four declarations
     did; "ladder changed:" and then each change under its
     declaration's name, when one did, as in
     "ladder changed: `LAYERS` gains `vfs.fanout` on rung 7".
   - `Size: <module> <lines before> to <lines after>, for each touched
     module; <closing>.` The closing is one of two:
     "allowlist unchanged" when the command shows nothing for
     `tests/lint/allowlist.py`; "allowlist changed:" and then each
     entry added, removed, raised or lowered, under its key,
     otherwise, as in
     "allowlist changed: `src/vfs/base.py` lowered from 3,660 to 3,190".

   A diff that touches no module of `src/vfs` opens each line with
   "no module of `src/vfs` touched" in place of the modules and keeps
   the closing. The lint requires both lines, the first holding the
   word `ladder` and the second the word `allowlist`, in a code review
   dated on or after `LAYER_LINES_START` in `tests/lint/shapes.py`.
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
ranks; the shared four-value scale of §2 stays inside the lenses and
rides along in parentheses. Map it so:

| the file's rank | meaning | from the shared scale and the lenses |
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
`findings.json`, no six phases, no artifacts. The reviewer runs it
itself, after the five lenses and inside the box. This is the
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
  one red yourself: on a file `git status` reports clean, copy it to
  the scratchpad, write the pre-change version over it with
  `git show <base>:<path>`, run the pinning test by node id, record the
  red, restore from the scratchpad copy, and confirm `git status` is
  clean again. A test that will not go red is a High (it pins
  nothing). The line says what you did, or "not reproduced".
- *The constitution* (`context/standards/constitution.md`): each
  article the diff touches and whether it holds; Article 1's five
  primitives named when the diff composes or manipulates them.
- *The production posture* (`AGENTS.md`): never assumes SQLite; no
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
finding in the Disposition and fixes code in new commits on top of
`<tip>`; you read the fix commits, confirm each Disposition line
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
applies it. The author commits the review file with the change, with
the spec's landing notes linking it.
